# --- Owner: Suman | "check one" boxes in lease forms ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
"""Make tick boxes explicit before the model reads a lease.

Standard lease forms (such as the Massachusetts standard residential lease) offer choices with boxes:
"☐ Tenant ☐ Landlord shall pay for heat". In extracted text a box is just a symbol, so the model cannot
tell which option applies and may judge an option nobody chose. This module replaces every box with a
plain-English marker, and decides what to do when no box in a group is ticked:

  - some box ticked      -> each option is marked [ticked] or [not ticked]
  - none ticked, but exactly the filled-in options can be told apart from blank ones
                         -> filled-in options are [assumed chosen], the blank ones [not ticked]
  - none ticked, no way to tell
                         -> every option is [no box ticked], and the clause carries a warning

This is plain code, not the model: whether a box is ticked is a fact about the document.
"""
from __future__ import annotations

import re

TICKED = "[ticked]"
NOT_TICKED = "[not ticked]"
ASSUMED = "[assumed chosen]"
NONE_TICKED = "[no box ticked]"

# Box characters as they come out of PDFs and Word files. The \uf0xx ones are Wingdings symbols, which
# PDF and Word text extraction report as private-use characters (0xF000 + the Wingdings code).
_EMPTY_BOXES = "☐□▢❏❐❑❒◻⬜"
_TICKED_BOXES = "☒☑✓✔✗✘⊠⌧"
_BOX = re.compile(
    rf"[{_EMPTY_BOXES}{_TICKED_BOXES}]"
    r"|\[\s?\]|\[[xX✓✔]\]"      # [ ]  [x]
    r"|\(\s\)|\([xX✓✔]\)"       # ( )  (x)   ("()" with nothing inside is too often a typo to count)
)
_FILLED = re.compile(r"\d")
_BLANK = re.compile(r"_{3,}")

CLAUSE_NOTES = {
    NONE_TICKED: ("None of the “check one” boxes in this clause is ticked, so we reviewed every option. "
                  "Only the option that ends up ticked applies, so make sure the right one is ticked before you sign."),
    ASSUMED: ("No box is ticked in this “check one” section, so we treated the filled-in option as the one that "
              "applies. Confirm with the landlord which option is meant before you sign."),
}


def is_ticked(box: str) -> bool:
    return box[0] in _TICKED_BOXES or bool(re.fullmatch(r"[\[(][xX✓✔][\])]", box))


def _marker_for_group(options: list[tuple[bool, str]]) -> list[str]:
    """One marker per option, given (ticked, option text) for every box in the group."""
    if any(t for t, _ in options) or len(options) == 1:
        return [TICKED if t else NOT_TICKED for t, _ in options]
    filled = [bool(_FILLED.search(text)) and not _BLANK.search(text) for _, text in options]
    if any(filled) and not all(filled):
        return [ASSUMED if f else NOT_TICKED for f in filled]
    return [NONE_TICKED] * len(options)


def resolve_boxes(text: str) -> str:
    """Replace every tick box in the text with a marker (see the module docstring).

    A group is one line with boxes plus any following lines that start with a box, so both
    "☐ Yes ☐ No" on one line and a vertical list of options are treated as a single choice.
    """
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if not _BOX.search(lines[i]):
            out.append(lines[i])
            i += 1
            continue
        group = [lines[i]]
        i += 1
        while i < len(lines) and _BOX.match(lines[i].lstrip()):
            group.append(lines[i])
            i += 1
        out.extend(_resolve_group(group))
    return "\n".join(out)


def _resolve_group(lines: list[str]) -> list[str]:
    # Every option runs from its box to the next box or the end of its line.
    parsed = []  # per line: (prefix, [(ticked, option text)])
    for line in lines:
        boxes = list(_BOX.finditer(line))
        prefix = line[: boxes[0].start()]
        options = []
        for n, m in enumerate(boxes):
            end = boxes[n + 1].start() if n + 1 < len(boxes) else len(line)
            options.append((is_ticked(m.group()), line[m.end():end].strip()))
        parsed.append((prefix, options))
    markers = iter(_marker_for_group([opt for _, opts in parsed for opt in opts]))
    rebuilt = []
    for prefix, options in parsed:
        parts = [f"{next(markers)} {opt_text}".rstrip() for _, opt_text in options]
        rebuilt.append((prefix.rstrip() + " " if prefix.strip() else prefix) + " ".join(parts))
    return rebuilt


def clause_notes(text: str) -> list[str]:
    """Warnings to show next to a clause whose boxes were not ticked."""
    return [note for marker, note in CLAUSE_NOTES.items() if marker in text]
