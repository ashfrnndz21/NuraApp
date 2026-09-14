"""The printable emergency card: one self-contained page, paper, high contrast, offline.

The web client caches this route for the day there is no data, and a printed copy goes in
his wallet and on the fridge, so the page carries everything it needs: the design-system
tokens inline (`docs/design-system.md` §2), no stylesheet, no script, no font file, no
image — nothing fetched. Paper surface, Ink text, 20px body in Dad mode, 56px-tall contact
rows, and Coral only where the design system allows it: nowhere on this page, because the
card is not the not-feeling-well button. The ambulance number sits under its own sentence
("The ambulance number is 995."), like every other number on the page sits beside a name.

Every sentence on the page is one of the card's verified lines. The two things the standard
keeps out of sentences and a stranger needs — the chief's phone number, the medicine's
strength — are printed as data in a table beside them, with the generic name the register
gave. The lock-screen widget of the native client is deferred (docs/adr/0001-web-first-client.md);
this page, and the home-screen icon that opens the card in one tap, are its substitute.
"""

from __future__ import annotations

from html import escape

from app.safety.emergency_card import Card

TOKENS: dict[str, str] = {
    "mist": "#F5F1F4",
    "paper": "#FFFFFF",
    "ink": "#2B2733",
    "ink_soft": "#6A6377",
    "plum": "#4E3A78",
    "good": "#3B7A57",
    "watch": "#B8741A",
    "act": "#C24A3A",
}
"""The design-system colours, by name. Ink on Paper is above 12:1; Ink soft on Paper 5.6:1 and
so used only for the small caption under a number, never for a line he reads."""

BODY_PX = 20
TITLE_PX = 24
TARGET_PX = 56
RADIUS_PX = 20

FONT_STACK = "Outfit, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
"""Outfit if the device has it; the system face otherwise. Nothing is downloaded."""


def _style() -> str:
    return f"""
:root {{
  --mist: {TOKENS["mist"]}; --paper: {TOKENS["paper"]}; --ink: {TOKENS["ink"]};
  --ink-soft: {TOKENS["ink_soft"]}; --plum: {TOKENS["plum"]}; --act: {TOKENS["act"]};
}}
html, body {{ margin: 0; padding: 0; background: var(--mist); color: var(--ink); }}
body {{ font-family: {FONT_STACK}; font-size: {BODY_PX}px; line-height: 1.5;
       -webkit-text-size-adjust: 100%; }}
main {{ max-width: 640px; margin: 0 auto; padding: 20px; }}
.paper {{ background: var(--paper); border-radius: {RADIUS_PX}px; padding: 20px; margin: 0 0 12px 0;
          box-shadow: 0 8px 24px rgba(60,40,80,.06); }}
h1 {{ font-size: {TITLE_PX}px; font-weight: 500; margin: 0 0 8px 0; }}
h2 {{ font-size: {TITLE_PX}px; font-weight: 500; margin: 0 0 8px 0; }}
p {{ margin: 0 0 8px 0; }}
.number {{ font-size: 40px; font-weight: 500; font-variant-numeric: tabular-nums; }}
.contact {{ display: flex; align-items: center; min-height: {TARGET_PX}px; justify-content: space-between;
            border-top: 1px solid var(--mist); padding: 8px 0; }}
.contact a {{ color: var(--plum); text-decoration: none; font-weight: 500; }}
table {{ width: 100%; border-collapse: collapse; }}
td, th {{ text-align: left; padding: 8px 4px; border-top: 1px solid var(--mist); vertical-align: top; }}
th {{ font-weight: 500; }}
.caption {{ font-size: 16px; color: var(--ink-soft); }}
@media print {{ body {{ background: var(--paper); }} .paper {{ box-shadow: none; border: 1px solid var(--mist); }} }}
"""


def _tel(number: str) -> str:
    return "tel:" + "".join(ch for ch in number if ch.isdigit() or ch == "+")


def emergency_card_html(card: Card) -> str:
    """The card as one HTML page. Sentences from the card's lines; data in the tables."""
    by_id: dict[str, list[str]] = {}
    for line in card.lines:
        by_id.setdefault(line.id, []).append(line.text)

    def section(*ids: str) -> str:
        return "".join(f"<p>{escape(text)}</p>" for one in ids for text in by_id.get(one, []))

    medicines = "".join(
        "<tr>"
        f"<td>{escape(m.plain_name)}</td>"
        f"<td>{escape(m.strength)} {escape(m.form)}</td>"
        f"<td>{escape(m.amount)}, {escape(m.when)}</td>"
        "</tr>"
        for m in card.medicines
    )
    contacts = "".join(
        '<div class="contact">'
        f"<span>{escape(c.name)}</span>"
        + (
            f'<a href="{_tel(c.phone_e164)}">{escape(c.phone_e164)}</a>'
            if c.phone_e164
            else ""
        )
        + "</div>"
        for c in card.contacts
    )
    clinic = ""
    if card.clinic is not None:
        clinic = (
            '<div class="contact">'
            f"<span>{escape(card.clinic.name)}</span>"
            + (
                f'<a href="{_tel(card.clinic.phone_e164)}">{escape(card.clinic.phone_e164)}</a>'
                if card.clinic.phone_e164
                else ""
            )
            + "</div>"
        )
    ambulance = (
        f'{section("ec.ambulance")}<div class="contact">'
        f'<span class="number"><a href="{_tel(card.emergency_number)}">{escape(card.emergency_number)}</a></span>'
        "</div>"
    )
    title = by_id.get("ec.title", [card.name])[0]
    return (
        "<!doctype html>\n"
        f'<html lang="{escape(card.language)}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title><style>{_style()}</style></head><body><main>"
        f'<section class="paper"><h1>{escape(title)}</h1>{section("ec.show", "ec.language", "ec.age")}</section>'
        f'<section class="paper">{section("ec.condition", "ec.no_condition")}</section>'
        f'<section class="paper">{section("ec.medicine", "ec.medicine_when", "ec.high_risk", "ec.no_medicine")}'
        + (f"<table><tbody>{medicines}</tbody></table>" if medicines else "")
        + "</section>"
        f'<section class="paper">{section("ec.allergy", "ec.no_allergy", "ec.blood_type")}</section>'
        f'<section class="paper">{section("ec.chief_who", "ec.chief", "ec.no_chief")}{contacts}{section("ec.doctor", "ec.clinic")}{clinic}{ambulance}</section>'
        f'<section class="paper">{section("ec.last_reading", "ec.boundary")}</section>'
        "</main></body></html>"
    )
