"""The translation memory: every patient string, in every catalogue, in one table (E22-02).

`make language` runs this module. It reads every string the plain-words verifier reads — the
same files, the same `@patient` tags (`app.safety.plain_words`) — and gives each line a stable
id: the catalogue it lives in, the key it is filed under, and its language,

    backend/app/delivery/strings:LINES.flag_family.1:zh
    web/src/strings:refusals.OutOfScope:ms

so the English line and its Malay and Chinese twins share everything but the last part. The
key is where the line sits in the source: the name it is assigned to, then the dict keys and
tuple positions down to the literal, with the language code left out wherever it is the key;
a line of a multi-line literal adds `lineN`. In a web strings file the key is the property
path and the language is the file.

The checker then holds the table to docs/plain-words.md rule 13, the same words every time:

- `twins`   every English line has a Malay and a Chinese twin under the same key, and no
            twin stands without its English.
- `slots`   twins fill the same `{slots}`: a Malay line that drops `{doctor}` drops his name.
- `phrase`  one English line is one Malay line and one Chinese line, wherever it is filed:
            "This one we do not wait for." is said one way in Chinese, on the card, in the
            reply and in the template.
- `term`    his words for things (docs/plain-words.md §6) are the same phrase in every
            language: where the English says "blood pressure tablet", the Malay says
            "ubat tekanan darah" and the Chinese "血压药".
- `never`   the variants the glossary rules out are not said, in any language: "your
            record", "医院信".

A finding in words that cannot simply be edited is a note, not a failure: a consent's words
are append-only and change only as a new version (`app/consent/`), and a WhatsApp template is
changed only by submitting it again for approval (`templates.py`). Words kept as history
(`# plain-words:` exempt) are left alone. Everything else fails the build.
"""

from __future__ import annotations

import argparse
import ast
import bisect
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

from app.language.glossary import Glossary
from app.language.glossary import load as load_glossary
from app.safety import plain_words as pw

LANGUAGES = ("en", "ms", "zh")
Severity = Literal["fail", "note"]

VERSIONED: tuple[tuple[str, str], ...] = (
    ("backend/app/consent/", "a consent's words change only as a new version"),
    (
        "backend/app/channels/whatsapp/templates",
        "a WhatsApp template changes only by submitting it again for approval",
    ),
)
"""Catalogues whose shipped words cannot be edited in place, and why. A finding there is a
note and a follow-up, never a failure."""


# --- the table ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Entry:
    """One patient line, as the source files it."""

    id: str
    catalogue: str
    key: str
    language: str
    text: str
    kind: str
    path: str
    line: int
    exempt: bool = False

    @property
    def group(self) -> tuple[str, str]:
        """The twins of this line share this: the catalogue and the key."""
        return self.catalogue, self.key

    @property
    def versioned(self) -> str | None:
        """Why this line's words cannot be edited in place, or None when they can."""
        return next((why for prefix, why in VERSIONED if self.catalogue.startswith(prefix)), None)


Filled = tuple[Entry, dict[str, str]]


@dataclass
class Memory:
    entries: list[Entry] = field(default_factory=list)
    _by_id: dict[str, Entry] = field(init=False, repr=False, default_factory=dict)
    _patterns: dict[str, list[tuple[Entry, re.Pattern[str], tuple[str, ...], int]]] = field(
        init=False, repr=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        self._by_id = {entry.id: entry for entry in self.entries}

    def _index(self, language: str) -> list[tuple[Entry, re.Pattern[str], tuple[str, ...], int]]:
        """Every template in `language` as a pattern that captures its slots, most specific
        first. A template with no words outside its slots matches anything and is left out."""
        if language not in self._patterns:
            found = []
            for entry in self.entries:
                if entry.language != language or entry.exempt:
                    continue
                pattern, names, weight = _capture(entry.text)
                if weight:
                    found.append((entry, pattern, names, weight))
            found.sort(key=lambda item: -item[3])
            self._patterns[language] = found
        return self._patterns[language]

    def fills_of(self, line: str, language: str) -> Iterator[Filled]:
        """Every catalogue line a rendered line could have been filled from, most specific
        first, with what went into each slot."""
        text = line.strip()
        tries = [text, text[:1].lower() + text[1:]] if text[:1].isupper() else [text]
        for entry, pattern, names, _ in self._index(language):
            for candidate in tries:
                match = pattern.fullmatch(candidate)
                if match:
                    yield entry, {name: match.group(f"s{i}") for i, name in enumerate(names)}
                    break

    def fill_of(self, line: str, language: str) -> Filled | None:
        """The catalogue line a rendered line was filled from, and what went into each slot;
        the most specific template wins. None for words that are not the catalogue's (a
        compressed page, a memo, his own words)."""
        return next(self.fills_of(line, language), None)

    def __len__(self) -> int:
        return len(self.entries)

    def get(self, entry_id: str) -> Entry | None:
        return self._by_id.get(entry_id)

    def groups(self) -> dict[tuple[str, str], dict[str, Entry]]:
        """Every key, with its line in each language it has one in."""
        found: dict[tuple[str, str], dict[str, Entry]] = defaultdict(dict)
        for entry in self.entries:
            found[entry.group].setdefault(entry.language, entry)
        return found

    def catalogues(self) -> set[str]:
        return {entry.catalogue for entry in self.entries}

    def twins_of(self, entry: Entry) -> dict[str, Entry]:
        return self.groups().get(entry.group, {})

    def match(self, line: str, language: str) -> list[Entry]:
        """Every catalogue line a rendered line could have come from: its template, with every
        `{slot}` matching any words. What the review queue files a rewrite against."""
        text = line.strip()
        tries = [text, text[:1].lower() + text[1:]] if text[:1].isupper() else [text]
        return [
            entry
            for entry, pattern, _, _ in self._index(language)
            if any(pattern.fullmatch(candidate) for candidate in tries)
        ]


_SLOT = re.compile(r"(?<!\{)\{([^{}]*)\}(?!\})")
_WORDISH = re.compile(r"[^\W\d_]")


def _capture(template: str) -> tuple[re.Pattern[str], tuple[str, ...], int]:
    """A template as a pattern with one group per slot (`s0`, `s1`, …), the slots' names, and
    how many letters it holds outside them — how specific it is."""
    parts = _SLOT.split(template.strip())
    literals, names = parts[::2], parts[1::2]
    pattern = ""
    for index, literal in enumerate(literals):
        pattern += re.escape(literal)
        if index < len(names):
            pattern += f"(?P<s{index}>.+?)"
    weight = sum(len(_WORDISH.findall(literal)) for literal in literals)
    return re.compile(pattern), tuple(n.strip().split("!")[0].split(":")[0] for n in names), weight


def slots_of(text: str) -> frozenset[str]:
    return frozenset(m.strip().split("!")[0].split(":")[0] for m in _SLOT.findall(text))


# --- reading the catalogues --------------------------------------------------------------------


APP = Path(__file__).resolve().parents[1]
"""The backend's `app` package, wherever it is installed."""


def catalogue_of(path: Path, root: Path) -> str:
    """The catalogue's name: its path from the top of the repository, without the suffix. A
    backend catalogue is named from the package (`backend/app/delivery/strings`), so a running
    server and `make language` give its lines the same ids. The web client's three files are
    one catalogue, one file per language."""
    resolved = path.resolve()
    if resolved.is_relative_to(APP):
        return "backend/app/" + resolved.relative_to(APP).with_suffix("").as_posix()
    relative = resolved.relative_to(root.resolve()).with_suffix("").as_posix()
    if path.suffix == ".ts" and path.stem in pw.LANGUAGE_CODES:
        return relative.rsplit("/", 1)[0]
    return relative


def _shown(path: Path, root: Path) -> str:
    resolved = path.resolve()
    return (
        resolved.relative_to(root.resolve()).as_posix()
        if resolved.is_relative_to(root.resolve())
        else str(path)
    )


_TAGGED = re.compile(r'^\s*(?:#\s*@patient\b|"""@patient\b)', re.MULTILINE)


@lru_cache(maxsize=1)
def runtime_memory() -> Memory:
    """The backend's own catalogues, read from the installed package: what a running server
    matches a rendered card against (`app.language.review`), with no repository, no rules
    file and no web client beside it. Read once per process."""
    files = sorted(
        path
        for path in APP.rglob("*.py")
        if "language" not in path.relative_to(APP).parts
        and _TAGGED.search(path.read_text(encoding="utf-8"))
    )
    return build(APP.parent, files)


def _key_segment(node: ast.expr | None) -> str:
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.Attribute):
        return node.attr
    return ast.unparse(node) if node is not None else "?"


def _is_language(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and node.value in pw.LANGUAGE_CODES:
        return str(node.value)
    return None


def _call_key(node: ast.Call) -> str:
    """What names one call among its siblings, apart from its language: its code arguments
    (`ConsentText(HOLD_HEALTH_RECORD, "1", "en", …, region=SG)` is `HOLD_HEALTH_RECORD/1/SG`)."""
    parts: list[str] = []
    for arg in [*node.args, *(k.value for k in node.keywords)]:
        if _is_language(arg):
            continue
        if isinstance(arg, ast.Attribute):
            parts.append(arg.attr)
        elif (
            isinstance(arg, ast.Constant)
            and isinstance(arg.value, str | int)
            and (not isinstance(arg.value, str) or pw.is_code_token(arg.value))
        ):
            parts.append(str(arg.value))
    return "/".join(parts) or "call"


Located = tuple[tuple[str, int], tuple[tuple[str, ...], str | None]]


def _paths(
    node: ast.AST, segments: tuple[str, ...], language: str | None = None
) -> Iterator[Located]:
    """Every string literal under `node`, as ((text, first line), (key segments, language)).

    The language is the first language code the walk meets as a dict key or beside a call's
    text; a second one further in is part of the key (`LANGUAGE_NAMES["ms"]["en"]` is the
    Malay for "English", filed under `LANGUAGE_NAMES.en`)."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            yield (node.value, node.lineno), (segments, language)
        return
    if isinstance(node, ast.JoinedStr):
        yield (pw._template_of(node), node.lineno), (segments, language)
        return
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values, strict=True):
            code = _is_language(key)
            if code and language is None:
                yield from _paths(value, segments, code)
            else:
                yield from _paths(value, (*segments, _key_segment(key)), language)
        return
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        for index, element in enumerate(node.elts):
            if isinstance(element, ast.Call) and pw._language_beside(element):
                yield from _paths(element, (*segments, _call_key(element)), language)
            else:
                yield from _paths(element, (*segments, str(index)), language)
        return
    if isinstance(node, ast.Call):
        here = language or pw._language_beside(node)
        for child in ast.iter_child_nodes(node):
            yield from _paths(child, segments, here)
        return
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        start = node.lineno
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                yield (child.value, child.lineno), ((*segments, f"@{child.lineno - start}"), None)
            elif isinstance(child, ast.JoinedStr):
                yield (
                    (pw._template_of(child), child.lineno),
                    (
                        (*segments, f"@{child.lineno - start}"),
                        None,
                    ),
                )
        return
    for child in ast.iter_child_nodes(node):
        yield from _paths(child, segments, language)


def _root_name(statement: ast.stmt) -> str:
    target: ast.expr | None = None
    if isinstance(statement, ast.Assign):
        target = statement.targets[0]
    elif isinstance(statement, ast.AnnAssign):
        target = statement.target
    elif isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return statement.name
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return f"L{statement.lineno}"


def _split(text: str) -> list[str]:
    parts = text.split("\n")
    if parts and parts[-1] == "":
        parts.pop()
    return parts


class _Ids:
    """Stable ids, with a counter only when two lines would share one."""

    def __init__(self) -> None:
        self.seen: Counter[str] = Counter()

    def __call__(self, catalogue: str, key: str, language: str) -> str:
        base = f"{catalogue}:{key}:{language}"
        self.seen[base] += 1
        return base if self.seen[base] == 1 else f"{base}#{self.seen[base]}"


def entries_in_python(path: Path, root: Path, source: str | None = None) -> list[Entry]:
    """Every patient line in one Python file, with its key."""
    text = source if source is not None else path.read_text(encoding="utf-8")
    catalogue = catalogue_of(path, root)
    shown = path.resolve().relative_to(root.resolve()).as_posix()
    exempt = pw.exempt_lines(text)
    ids = _Ids()
    found: list[Entry] = []
    seen: set[tuple[str, str, str]] = set()
    for statement, kind in pw.tagged_statements(text):
        root_name = _root_name(statement)
        where = dict(_paths(statement, (root_name,)))
        for literal, first, last, language in pw.literals_in(statement):
            segments, structural = where.get((literal, first), ((root_name, f"L{first}"), None))
            # A word filed under a language is his word even when it looks like a token to
            # the verifier ("demam", "pagi"), and a line that is all slots in one language
            # ("{amount}{name}") is still that language's line.
            if structural is None and (not pw.has_letters(literal) or pw.is_code_token(literal)):
                continue
            if structural is not None and not (pw.has_letters(literal) or slots_of(literal)):
                continue
            parts = _split(literal)
            for index, part in enumerate(parts):
                if not (pw.has_letters(part) or (structural and slots_of(part))):
                    continue
                line = first + index if len(parts) == last - first + 1 else first
                key_parts = (*segments, f"line{index}") if len(parts) > 1 else segments
                key = ".".join(key_parts)
                code = structural or pw.language_of(part, language)
                if (key, code, part) in seen:
                    continue
                seen.add((key, code, part))
                found.append(
                    Entry(
                        ids(catalogue, key, code),
                        catalogue,
                        key,
                        code,
                        part.strip(),
                        kind,
                        shown,
                        line,
                        first in exempt,
                    )
                )
    return found


_TS_TOKEN = re.compile(
    r"(?P<comment>//[^\n]*|/\*.*?\*/)"
    r"|(?P<string>\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`)"
    r"|(?P<key>[A-Za-z_$][\w$]*)\s*:(?!:)"
    r"|(?P<open>[{\[(])"
    r"|(?P<close>[}\])])"
    r"|(?P<comma>,)",
    re.DOTALL,
)


def _ts_decode(raw: str) -> str:
    body = raw[1:-1]
    return body.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8")


def _ts_paths(text: str) -> dict[tuple[int, str], str]:
    """Every string literal in a web strings file, by (line, text), with its property path."""
    newlines = [i for i, c in enumerate(text) if c == "\n"]
    frames: list[dict[str, object]] = [{"kind": "{", "path": (), "pending": None, "index": 0}]
    found: dict[tuple[int, str], str] = {}
    for match in _TS_TOKEN.finditer(text):
        frame = frames[-1]
        path: tuple[str, ...] = frame["path"]  # type: ignore[assignment]
        if match.group("key"):
            frame["pending"] = match.group("key")
        elif match.group("open"):
            opener = match.group("open")
            pending = frame["pending"]
            if pending:
                inner = (*path, str(pending))
            elif frame["kind"] == "[":
                inner = (*path, str(frame["index"]))
                frame["index"] = int(frame["index"]) + 1  # type: ignore[call-overload]
            else:
                inner = path
            frame["pending"] = None
            frames.append({"kind": opener, "path": inner, "pending": None, "index": 0})
        elif match.group("close"):
            if len(frames) > 1:
                frames.pop()
        elif match.group("comma"):
            if frame["kind"] == "{":
                frame["pending"] = None
        elif match.group("string"):
            line = bisect.bisect_left(newlines, match.start()) + 1
            if frame["pending"]:
                key = (*path, str(frame["pending"]))
            elif frame["kind"] == "[":
                key = (*path, str(frame["index"]))
                frame["index"] = int(frame["index"]) + 1  # type: ignore[call-overload]
            else:
                key = path
            try:
                value = _ts_decode(match.group("string"))
            except UnicodeDecodeError:
                continue
            parts = [p.strip() for p in value.replace("\r", "").split("\n")]
            for index, part in enumerate(parts):
                suffix = (f"line{index}",) if len(parts) > 1 else ()
                found.setdefault((line, part), ".".join((*key, *suffix)))
    return found


def entries_in_typescript(path: Path, root: Path, source: str | None = None) -> list[Entry]:
    """Every patient line in one web strings file; the key is the property path."""
    text = source if source is not None else path.read_text(encoding="utf-8")
    catalogue = catalogue_of(path, root)
    shown = path.resolve().relative_to(root.resolve()).as_posix()
    where = _ts_paths(text)
    # The file is the language: `zh: "中文"` in en.ts is the English file's line.
    language = path.stem if path.stem in pw.LANGUAGE_CODES else "en"
    ids = _Ids()
    found: list[Entry] = []
    for patient in pw.strings_in_typescript(path, text):
        key = where.get((patient.line, patient.text), f"L{patient.line}")
        found.append(
            Entry(
                ids(catalogue, key, language),
                catalogue,
                key,
                language,
                patient.text,
                patient.kind,
                shown,
                patient.line,
                patient.exempt,
            )
        )
    return found


def entries_in_xcstrings(path: Path, root: Path, source: str | None = None) -> list[Entry]:
    """Every patient line in an Xcode strings catalogue; the key is the entry's key."""
    text = source if source is not None else path.read_text(encoding="utf-8")
    catalogue = catalogue_of(path, root)
    shown = path.resolve().relative_to(root.resolve()).as_posix()
    by_line: dict[int, str] = {}
    for key in json.loads(text).get("strings", {}):
        number = next((n for n, l in enumerate(text.splitlines(), 1) if json.dumps(key) in l), 1)
        by_line.setdefault(number, key)
    ids = _Ids()
    found: list[Entry] = []
    for patient in pw.strings_in_xcstrings(path, text):
        anchor = max((n for n in by_line if n <= patient.line), default=patient.line)
        key = by_line.get(anchor, f"L{patient.line}")
        found.append(
            Entry(
                ids(catalogue, key, patient.language),
                catalogue,
                key,
                patient.language,
                patient.text,
                patient.kind,
                shown,
                patient.line,
            )
        )
    return found


def entries_in(path: Path, root: Path) -> list[Entry]:
    if path.suffix == ".py":
        return entries_in_python(path, root)
    if path.suffix == ".ts":
        return entries_in_typescript(path, root)
    if path.suffix == ".xcstrings":
        return entries_in_xcstrings(path, root)
    return []


def build(root: Path | None = None, files: Sequence[Path] | None = None) -> Memory:
    """The translation memory of the repository: every patient line under the paths in
    `.claude/rules/patient-strings.md`, or of `files` when given."""
    base = root or pw.repo_root()
    paths = files if files is not None else pw.patient_files(base)
    return Memory([entry for path in paths for entry in entries_in(path, base)])


# --- the checks --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Finding:
    check: str
    problem: str
    fix: str
    entry_id: str
    path: str
    line: int
    severity: Severity = "fail"

    def __str__(self) -> str:
        note = "note " if self.severity == "note" else ""
        return f"{self.path}:{self.line}: {note}{self.check} — {self.problem} → {self.fix}"


@dataclass(slots=True)
class Report:
    strings: int = 0
    groups: int = 0
    catalogues: int = 0
    findings: list[Finding] = field(default_factory=list)

    @property
    def failures(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "fail"]

    @property
    def notes(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "note"]

    @property
    def ok(self) -> bool:
        return not self.failures

    def summary(self) -> str:
        return (
            f"language: {self.strings} strings, {self.groups} keys in {self.catalogues} "
            f"catalogues, {len(self.failures)} failures, {len(self.notes)} notes"
        )


_CJK_SPACE = re.compile(r"(?<=[㐀-鿿　-〿＀-￯}])\s+|\s+(?=[㐀-鿿　-〿＀-￯{])")

SLOT_CLASSES: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "person",
        frozenset(
            {"name", "who", "doctor", "told", "patient", "names", "holder", "chief", "person"}
        ),
    ),
    ("number", frozenset({"number", "emergency_number", "count", "n", "days", "value", "amount"})),
    ("day", frozenset({"day", "date", "when", "time"})),
)
"""Slots that say the same kind of thing compare as one: "{who} knows now." and "{told} knows
now." are the same words; "Call {emergency_number} now." and "Call {patient} now." are not —
a number is called one way in Chinese ("打995") and a person another ("打电话给Mei")."""


def _slot_class(match: re.Match[str]) -> str:
    name = match.group(1).strip().split("!")[0].split(":")[0]
    for label, names in SLOT_CLASSES:
        if name in names:
            return "{" + label + "}"
    return "{" + name + "}"


def normal(text: str) -> str:
    """A line as the same-words checks compare it: slots by their kind, spaces tidied, the
    first letter's case left out (a line and the same words mid-sentence are the same words)."""
    unnamed = _SLOT.sub(_slot_class, text.strip())
    tidy = re.sub(r"\s+", " ", unnamed)
    if re.search(r"[㐀-鿿]", tidy):
        tidy = _CJK_SPACE.sub("", tidy)
    return tidy[:1].lower() + tidy[1:]


def _finding(check: str, problem: str, fix: str, entry: Entry, why: str | None = None) -> Finding:
    reason = why if why is not None else entry.versioned
    severity: Severity = "note" if reason is not None or entry.exempt else "fail"
    shown_fix = f"{fix} (follow-up: {reason})" if reason else fix
    return Finding(check, problem, shown_fix, entry.id, entry.path, entry.line, severity)


def _live(entries: Iterable[Entry]) -> list[Entry]:
    return [entry for entry in entries if not entry.exempt]


_LINE_SEGMENT = re.compile(r"^(?:\d+|line\d+)$")


def parent_of(key: str) -> str:
    """The card a line belongs to: its key without the line's position, when it has one. A
    language may say a card in more lines than another (Chinese keeps a date and two numbers
    apart, rule 10), so twins are matched card by card where the lines do not line up."""
    head, _, last = key.rpartition(".")
    return head if head and _LINE_SEGMENT.match(last) else key


def _cards(memory: Memory) -> dict[tuple[str, str], dict[str, list[Entry]]]:
    found: dict[tuple[str, str], dict[str, list[Entry]]] = defaultdict(lambda: defaultdict(list))
    for entry in memory.entries:
        found[(entry.catalogue, parent_of(entry.key))][entry.language].append(entry)
    return found


def check_twins(memory: Memory) -> list[Finding]:
    findings: list[Finding] = []
    cards = _cards(memory)
    for (catalogue, key), by_language in memory.groups().items():
        live = {code: e for code, e in by_language.items() if not e.exempt}
        if not live:
            continue
        card = cards[(catalogue, parent_of(key))]
        english = live.get("en")
        if english is None:
            if card.get("en"):
                continue  # the English card says it in fewer lines
            first = next(iter(live.values()))
            findings.append(
                _finding("twins", "a line with no English twin", "write the English line", first)
            )
            continue
        for code, name in (("ms", "Malay"), ("zh", "Chinese")):
            if code in by_language or card.get(code):
                continue
            findings.append(
                _finding(
                    "twins",
                    f'"{english.text}" has no {name} twin',
                    f"add the {name} line under {english.key}",
                    english,
                )
            )
    return findings


def check_slots(memory: Memory) -> list[Finding]:
    """Twins fill the same slots, card by card: every slot the English card fills, each twin
    card fills, however many lines it takes."""
    findings: list[Finding] = []
    for by_language in _cards(memory).values():
        english = [e for e in by_language.get("en", []) if not e.exempt]
        if not english:
            continue
        wanted = frozenset().union(*(slots_of(e.text) for e in english))
        for code in ("ms", "zh"):
            twins = [e for e in by_language.get(code, []) if not e.exempt]
            if not twins:
                continue
            said = frozenset().union(*(slots_of(e.text) for e in twins))
            if said == wanted:
                continue
            missing = sorted(wanted - said)
            extra = sorted(said - wanted)
            what = ", ".join(
                [*(f"{{{s}}} missing" for s in missing), *(f"{{{s}}} extra" for s in extra)]
            )
            shown = " / ".join(e.text for e in english)
            findings.append(
                _finding(
                    "slots",
                    f'the {code} twin of "{shown}" fills other slots: {what}',
                    "fill the same slots in every language",
                    twins[0],
                )
            )
    return findings


def _majority(
    variants: Mapping[str, list[Entry]], canonical: str | None
) -> tuple[str | None, list[str]]:
    """The words to keep and the words to change. The glossary's words win; then the words
    that can only change as a new version (consent, a template); then the most used."""
    if canonical is not None:
        saying = [v for v in variants if _contains(v, canonical)]
        if len(saying) == 1:
            return saying[0], [v for v in variants if v != saying[0]]
    locked = {v for v, entries in variants.items() if any(e.versioned for e in entries)}
    if len(locked) == 1:
        keep = next(iter(locked))
        return keep, [v for v in variants if v != keep]
    counted = sorted(variants.items(), key=lambda item: (-len(item[1]), item[0]))
    if len(counted) > 1 and len(counted[0][1]) == len(counted[1][1]):
        return None, list(variants)
    keep = counted[0][0]
    return keep, [v for v in variants if v != keep]


def check_phrases(memory: Memory, glossary: Glossary) -> list[Finding]:
    """One English line is one Malay line and one Chinese line, wherever it is filed.

    Whole lines only: a phrase that fills a slot ("a fall", "跌倒了") takes the grammar of the
    line around it, which is the term check's business (§6), not this one's. A key said the
    same in every language (a name, a language's own name for itself) is not a translation."""
    by_english: dict[str, list[dict[str, Entry]]] = defaultdict(list)
    for by_language in memory.groups().values():
        english = by_language.get("en")
        if english is None or english.exempt or english.kind == "phrase":
            continue
        if len({normal(e.text) for e in by_language.values()}) == 1:
            continue
        by_english[normal(english.text)].append(by_language)
    findings: list[Finding] = []
    for said, groups in by_english.items():
        if len(groups) < 2:
            continue
        term = glossary.term(said.rstrip(".")) or glossary.term(said)
        for code, name in (("ms", "Malay"), ("zh", "Chinese")):
            variants: dict[str, list[Entry]] = defaultdict(list)
            for group in groups:
                twin = group.get(code)
                if twin is not None and not twin.exempt:
                    variants[normal(twin.text)].append(twin)
            if len(variants) < 2:
                continue
            canonical = term.say(code) if term else None
            keep, change = _majority(variants, normal(canonical) if canonical else None)
            english_text = groups[0]["en"].text
            for variant in change:
                for entry in variants[variant]:
                    if keep is None:
                        others = " / ".join(f'"{v}"' for v in variants if v != variant)
                        fix = f"pick one and say it everywhere: {others}"
                    else:
                        shown = next(e.text for e in variants[keep])
                        fix = f'say "{shown}"'
                    findings.append(
                        _finding(
                            "phrase",
                            f'"{english_text}" is said {len(variants)} ways in {name}; '
                            f'this is "{entry.text}"',
                            fix,
                            entry,
                        )
                    )
    return findings


def _contains(text: str, phrase: str) -> bool:
    if re.search(r"[㐀-鿿]", phrase):
        return phrase in text
    lead = r"(?<![\w])" if phrase[:1].isalnum() else ""
    tail = r"(?![\w])" if phrase[-1:].isalnum() else ""
    return re.search(lead + re.escape(phrase) + tail, text, re.IGNORECASE) is not None


def check_terms(memory: Memory, glossary: Glossary) -> list[Finding]:
    """His words for things (§6) are the same phrase in every language."""
    findings: list[Finding] = []
    for by_language in memory.groups().values():
        english = by_language.get("en")
        if english is None or english.exempt:
            continue
        for term in glossary.terms:
            if not _contains(english.text, term.en):
                continue
            for code in ("ms", "zh"):
                said = term.say(code)
                twin = by_language.get(code)
                if said is None or twin is None or twin.exempt:
                    continue
                if not any(_contains(twin.text, option) for option in said.split(" / ")):
                    findings.append(
                        _finding(
                            "term",
                            f'"{term.en}" is "{said}" in {code}, and this line does not say it: '
                            f'"{twin.text}"',
                            f'say "{said}"',
                            twin,
                        )
                    )
    return findings


def check_never(memory: Memory, glossary: Glossary) -> list[Finding]:
    """The variants the glossary rules out are not said, in any language."""
    findings: list[Finding] = []
    rules = {code: list(glossary.never(code)) for code in LANGUAGES}
    for entry in _live(memory.entries):
        for variant, say in rules.get(entry.language, ()):
            if _contains(entry.text, variant):
                findings.append(
                    _finding(
                        "never",
                        f'"{variant}" is not his word: "{entry.text}"',
                        f'say "{say}"',
                        entry,
                    )
                )
    return findings


def check(memory: Memory, glossary: Glossary) -> Report:
    report = Report(
        strings=len(_live(memory.entries)),
        groups=len(memory.groups()),
        catalogues=len(memory.catalogues()),
    )
    for found in (
        check_twins(memory),
        check_slots(memory),
        check_phrases(memory, glossary),
        check_terms(memory, glossary),
        check_never(memory, glossary),
    ):
        report.findings.extend(found)
    report.findings.sort(key=lambda f: (f.severity, f.path, f.line, f.check))
    return report


def check_repo(root: Path | None = None) -> Report:
    base = root or pw.repo_root()
    return check(build(base), load_glossary(base))


# --- the command line --------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="language",
        description="Hold every patient string to the same words in English, Malay and Chinese.",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable findings")
    parser.add_argument("--table", action="store_true", help="print the translation memory")
    parser.add_argument("--quiet-notes", action="store_true", help="do not print notes")
    args = parser.parse_args(argv)
    root = pw.repo_root()
    memory = build(root)
    if args.table:
        print(json.dumps([asdict(e) for e in memory.entries], ensure_ascii=False, indent=1))
        return 0
    report = check(memory, load_glossary(root))
    if args.json:
        print(
            json.dumps(
                {
                    "ok": report.ok,
                    "strings": report.strings,
                    "keys": report.groups,
                    "catalogues": report.catalogues,
                    "failures": [asdict(f) for f in report.failures],
                    "notes": [asdict(f) for f in report.notes],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for finding in report.findings:
            if finding.severity == "note" and args.quiet_notes:
                continue
            print(finding)
        print(report.summary())
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
