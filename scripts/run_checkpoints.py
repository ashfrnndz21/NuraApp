"""Run every checkpoint marked **ready** in `docs/checkpoints.md` against a throwaway dev
server, for CI (#192). A thin wrapper: `make checkpoints-ci`.

    make checkpoints-ci

Boots the app the same way `make dev` does — same fixture providers, same frozen-clock
support — but on a database this run creates and destroys (a fresh sqlite file in a temp
directory) and a port this run picks itself (so two runs, or this run and a laptop's `make
dev`, never collide). It then walks, in order, every checkpoint number that is both marked
`**ready**` in `docs/checkpoints.md` and known to `backend/scripts/checkpoint.py` (that
script's own usage line names the ones it can run — read from there, not hard-coded here, so
a new checkpoint joins this job by being marked ready and wired into that script, with no
edit here or to the workflow). A checkpoint marked ready that script cannot run yet (today:
1, and the web checkpoints 10-12/24-28, which are walked by `make web-e2e` and by hand — see
"How a checkpoint is tested" in docs/checkpoints.md) is listed and skipped, not silently
dropped and not failed.

Stops at the first failing step, printed in that step's own words (`backend/scripts/
checkpoint.py`'s own ✓/✗ output, passed straight through — never reformatted into a
traceback). No retries: a flaky checkpoint is a real finding, not something to paper over.
"""

from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"
CHECKPOINTS_DOC = REPO_ROOT / "docs" / "checkpoints.md"

# The instant `make web-e2e` freezes the backend's clock at (web/playwright.config.ts); every
# checkpoint that needs a different moment moves it itself with `POST /dev/clock` (dev-only),
# the way checkpoint 20 stands it at 06:00 before it starts. NURA_FROZEN_CLOCK overrides this.
DEFAULT_FROZEN_CLOCK = "2026-09-14T10:00:00+08:00"

BOOT_TIMEOUT_SECONDS = 90
POLL_INTERVAL_SECONDS = 0.5


class BootFailed(RuntimeError):
    pass


def free_port() -> int:
    """A port nothing is listening on right now, picked by the OS. Racy in theory (another
    process could take it between this call and uvicorn binding) but that race is exactly
    what a fixed port guarantees instead of merely risking, so this is strictly better."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ready_checkpoints_in_docs() -> list[int]:
    """Every numbered row in the checkpoints table whose Status cell is exactly `**ready**`,
    in table order. The table is the list — see docs/checkpoints.md's own legend."""
    numbers: list[int] = []
    row = re.compile(r"^\|\s*(\d+)\s*\|.*\|\s*(.+?)\s*\|$")
    for line in CHECKPOINTS_DOC.read_text().splitlines():
        match = row.match(line)
        if not match:
            continue
        number, status = match.group(1), match.group(2)
        if status == "**ready**":
            numbers.append(int(number))
    if not numbers:
        raise BootFailed(f"found no ready checkpoints in {CHECKPOINTS_DOC} — table format changed?")
    return numbers


def runnable_checkpoints(env: dict[str, str]) -> list[int]:
    """The checkpoint numbers `backend/scripts/checkpoint.py` itself knows how to run, read
    from its own usage line (an invalid argument makes it print exactly that, to stderr, and
    exit 2) rather than duplicated here — so this stays correct as CHECKPOINTS there grows."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.checkpoint", "0"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    match = re.search(r"ready: ([0-9, ]+)\)", result.stderr)
    if not match:
        raise BootFailed(
            "could not read the ready list from `python -m scripts.checkpoint`'s usage line "
            f"(exit {result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
        )
    return [int(n) for n in match.group(1).split(",")]


def wait_for_health(base_url: str, server: subprocess.Popen) -> None:
    deadline = time.monotonic() + BOOT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise BootFailed(
                f"the dev server exited (code {server.returncode}) before it answered "
                f"{base_url}/health — see backend/.dev.log"
            )
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=2) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(POLL_INTERVAL_SECONDS)
    raise BootFailed(f"{base_url}/health did not answer within {BOOT_TIMEOUT_SECONDS}s")


def stop(server: subprocess.Popen) -> None:
    """`make dev`'s recipe is a shell pipeline (uvicorn --reload, piped into tee), so the
    process this script started is not the only one alive; killing its whole process group
    (it was launched in a new session) is what actually frees the port."""
    try:
        pgid = os.getpgid(server.pid)
    except ProcessLookupError:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return
        try:
            server.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            continue


def main() -> int:
    docs_ready = ready_checkpoints_in_docs()

    base_env = dict(os.environ)
    probe_env = dict(base_env)
    runnable = set(runnable_checkpoints(probe_env))

    to_run = sorted(n for n in docs_ready if n in runnable)
    skipped = sorted(n for n in docs_ready if n not in runnable)

    print(f"ready in docs/checkpoints.md: {docs_ready}")
    print(f"runnable by backend/scripts/checkpoint.py: {sorted(runnable)}")
    if skipped:
        print(
            f"skipping (ready in the docs, no `make checkpoint` runner yet — web checkpoints "
            f"and checkpoint 1 are walked by `make web-e2e` and by hand, see docs/checkpoints.md "
            f"\"How a checkpoint is tested\"): {skipped}"
        )
    if not to_run:
        print("nothing to run", file=sys.stderr)
        return 1
    print(f"will run, in order, stopping at the first failure: {to_run}")

    port = free_port()
    base_url = f"http://127.0.0.1:{port}"

    with tempfile.TemporaryDirectory(prefix="nura-checkpoints-ci-") as tmp:
        db_path = Path(tmp) / "checkpoints.db"
        object_store = Path(tmp) / "objects"

        server_env = dict(base_env)
        server_env["NURA_DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
        server_env["NURA_OBJECT_STORE"] = str(object_store)
        server_env["UVICORN_PORT"] = str(port)
        server_env.setdefault("NURA_FROZEN_CLOCK", DEFAULT_FROZEN_CLOCK)

        print(f"throwaway database: {db_path}")
        print(f"port: {port}")
        print(f"frozen clock: {server_env['NURA_FROZEN_CLOCK']}")
        print("booting `make dev` …")

        server = subprocess.Popen(
            ["make", "dev"],
            cwd=REPO_ROOT,
            env=server_env,
            start_new_session=True,
        )

        results: list[tuple[int, bool, float]] = []
        exit_code = 0
        try:
            wait_for_health(base_url, server)
            print(f"the dev server answers at {base_url} — starting the walk\n")

            checkpoint_env = dict(base_env)
            checkpoint_env["NURA_BASE_URL"] = base_url

            for number in to_run:
                print(f"--- checkpoint {number} " + "-" * 60)
                started = time.monotonic()
                proc = subprocess.run(
                    [sys.executable, "-m", "scripts.checkpoint", str(number)],
                    cwd=BACKEND,
                    env=checkpoint_env,
                    check=False,
                )
                elapsed = time.monotonic() - started
                passed = proc.returncode == 0
                results.append((number, passed, elapsed))
                if not passed:
                    exit_code = 1
                    break
        except BootFailed as failed:
            print(f"✗ {failed}", file=sys.stderr)
            try:
                print((BACKEND / ".dev.log").read_text()[-4000:], file=sys.stderr)
            except OSError:
                pass
            exit_code = 1
        finally:
            print("\nstopping the dev server and destroying the database …")
            stop(server)

        print("\n--- summary " + "-" * 60)
        total = 0.0
        for number, passed, elapsed in results:
            total += elapsed
            mark = "PASS" if passed else "FAIL"
            print(f"{mark}  checkpoint {number:>2}  {elapsed:6.1f}s")
        ran = [n for n, _, _ in results]
        not_reached = [n for n in to_run if n not in ran]
        if not_reached:
            print(f"not reached (stopped early): {not_reached}")
        print(f"total: {total:.1f}s")
        return exit_code


if __name__ == "__main__":
    sys.exit(main())
