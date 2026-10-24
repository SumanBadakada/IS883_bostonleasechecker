# --- Owner: (assign, see docs/TEAM_SPLIT.md) | reading the upload and splitting it into clauses ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
"""Turn an uploaded PDF or DOCX into a list of clauses.

No model is used here: text extraction, scanned-PDF detection, the lease check and clause splitting
are plain code, which is cheaper and cannot hallucinate.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from . import config
from .checkboxes import clause_notes, resolve_boxes


class InputRejected(Exception):
    """Raised for inputs we decline. `reason` is a short code, `message` is shown to the user."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


# The lease's own clause number at the start of a clause: "3. Rent", "3) Rent", "Section 3 - Rent",
# and also "3.Rent" with no space (common in PDFs), but only when a capital letter follows, so that
# "2-bedroom" or "2.5 months" is not read as a clause number.
_LEADING_NUMBER = re.compile(
    r"\s*(?:section|article|clause|§)?\s*(\d{1,2}(?:\.\d{1,2})*)\s*(?:[.):\-]\s|[.)](?=[\"“(]?[A-Z]))",
    re.IGNORECASE,
)


@dataclass
class Clause:
    clause_id: int  # our own position counter, used to match the model's answers to clauses
    text: str

    @property
    def display_name(self) -> str:
        """What the tenant sees: the lease's own number ("Clause 3") when it has one."""
        match = _LEADING_NUMBER.match(self.text)
        if match:
            return f"Clause {match.group(1)}"
        return "Opening section" if self.clause_id == 1 else f"Part {self.clause_id}"

    @property
    def notes(self) -> list[str]:
        """Warnings about this clause's text itself, e.g. "check one" boxes nobody ticked."""
        return clause_notes(self.text)


@dataclass
class ParsedDocument:
    clauses: list[Clause]
    warnings: list[str] = field(default_factory=list)  # about the whole document, shown above the results


# A PDF averaging fewer extractable characters per page than this is treated as scanned.
MIN_CHARS_PER_PAGE = 80

# Normal English averages about 5 letters per word. Far above that means the extractor lost the spaces
# ("Nopetsofanykindareallowed..."), and the model would be checking garbled text.
MAX_AVG_WORD_LEN = 10

# Words that almost every residential lease uses. A document needs several of them to count as a lease.
LEASE_TERMS = (
    "landlord", "lessor", "tenant", "lessee", "rent", "premises", "lease",
    "security deposit", "term of", "apartment", "occupan",
)
MIN_LEASE_TERMS = 4


def extract_text(data: bytes, filename: str) -> str:
    """Extract plain text. Raises InputRejected for empty, unsupported, oversized or scanned files."""
    if not data:
        raise InputRejected("empty", "The file is empty. Please upload your lease as a PDF or Word (.docx) file.")
    if len(data) > config.MAX_FILE_MB * 1024 * 1024:
        raise InputRejected("too_large", f"The file is larger than {config.MAX_FILE_MB} MB.")

    name = filename.lower()
    if name.endswith(".pdf"):
        text = _pdf_text(data)
    elif name.endswith(".docx"):
        text = _docx_text(data)
    elif name.endswith(".txt"):  # used by the eval harness and tests
        text = data.decode("utf-8", errors="replace")
    else:
        raise InputRejected("unsupported", "Please upload a PDF or a Word (.docx) file.")

    text = resolve_boxes(_normalise(text))
    if not text.strip():
        raise InputRejected("empty", "We could not find any text in this file.")
    return text


def _pdf_text(data: bytes) -> str:
    """PyMuPDF rebuilds word spacing from glyph positions far better than pypdf, so we prefer it.
    pypdf stays as a fallback in case PyMuPDF is not installed."""
    try:
        pages = _pdf_pages_pymupdf(data)
    except ImportError:
        pages = _pdf_pages_pypdf(data)

    if not pages:
        raise InputRejected("empty", "This PDF has no pages.")
    chars = sum(len(p.strip()) for p in pages)
    if chars / len(pages) < MIN_CHARS_PER_PAGE:
        raise InputRejected(
            "scanned",
            "This looks like a scanned PDF (an image of the pages), so there is no text for us to check. "
            "Please upload the lease as a text-based PDF or a Word file.",
        )
    text = "\n".join(_strip_page_furniture(pages))
    _check_spacing(text)
    return text


# AI-assisted (Claude Code): running headers and footers ("MJMJ 4" = tenant initials + page number,
# "Page 4 of 10", the lease title on every page) sit between the last line of one page and the first line
# of the next. Left in, they end up inside a clause, and an ALL-CAPS footer even looks like a heading,
# which split clause 30 of a real lease in two at a page break.
_PAGE_MARK = re.compile(
    r"^\s*(?:"
    r"(?:page|pg\.?)\s*\d{1,3}(?:\s*(?:of|/)\s*\d{1,3})?"   # Page 4, Page 4 of 10, pg. 4/10
    r"|-?\s*\d{1,3}\s*-?"                                    # 4, - 4 -
    r"|\d{1,3}\s*(?:of|/)\s*\d{1,3}"                          # 4 of 10, 4/10
    r"|[A-Z]{2,6}\s+\d{1,3}|\d{1,3}\s+[A-Z]{2,6}"               # MJMJ 4 (initials and a page number)
    r"|(?:tenant|landlord|lessee|lessor)?\s*initials?:?\s*_*\s*(?:\d{1,3})?"  # Initials: ____
    r"|.{1,60}?[\s\-–|,]\s*(?:page|pg\.?)\s*\d{1,3}(?:\s*(?:of|/)\s*\d{1,3})?"  # LEASE TITLE - Page 2 of 5
    r")\s*$",
    re.IGNORECASE,
)
_EDGE_LINES = 3  # how many lines at the top and bottom of a page count as header/footer territory


def _furniture_key(line: str) -> str:
    """A line with its numbers blanked out, so "MJMJ 4" and "MJMJ 5" count as the same footer."""
    return re.sub(r"\d+", "#", line.strip().lower())


def _strip_page_furniture(pages: list[str]) -> list[str]:
    """Remove running headers/footers from the top and bottom lines of each page.

    A line is furniture if it is an obvious page marker (_PAGE_MARK), or if the same short line, numbers
    ignored and not ending in a full stop, appears at the top or bottom of at least two pages. Only edge
    lines are touched, so a sentence that repeats in the body of the lease is never removed."""
    split = [p.split("\n") for p in pages]

    def edges(lines: list[str]) -> list[int]:
        filled = [i for i, line in enumerate(lines) if line.strip()]
        return sorted(set(filled[:_EDGE_LINES] + filled[-_EDGE_LINES:]))

    seen: dict[str, int] = {}
    for lines in split:
        for key in {_furniture_key(lines[i]) for i in edges(lines)}:
            seen[key] = seen.get(key, 0) + 1
    # Running headers and footers are short labels, not sentences, so a repeated line that ends a sentence
    # (on a short page the edge lines can be body text) is kept.
    repeated = {k for k, n in seen.items() if n >= 2 and len(k) <= 60 and not k.rstrip().endswith(".")}

    cleaned = []
    for lines in split:
        drop = {i for i in edges(lines)
                if _PAGE_MARK.match(lines[i]) or _furniture_key(lines[i]) in repeated}
        cleaned.append("\n".join(line for i, line in enumerate(lines) if i not in drop))
    return cleaned


def _pdf_pages_pymupdf(data: bytes) -> list[str]:
    try:
        import pymupdf as fitz  # PyMuPDF 1.24+; "fitz" is the deprecated old name
    except ImportError:
        import fitz

    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            if doc.needs_pass:
                raise InputRejected("unreadable", "This PDF is password-protected. Please upload an unlocked copy.")
            return [_pymupdf_page_text(page, fitz) or "" for page in doc]
    except (RuntimeError, ValueError) as exc:  # fitz raises FileDataError (a RuntimeError) for damaged files
        raise InputRejected("unreadable", "This PDF could not be read. It may be damaged or password-protected.") from exc


# AI-assisted (Claude Code): fillable PDF forms keep their tick boxes as form fields, which get_text() does
# not include, so "☐ Tenant ☐ Landlord" would read as "Tenant Landlord". We put a box character back where
# each field sits, ticked or not, and checkboxes.resolve_boxes turns it into a marker the model understands.
def _pymupdf_page_text(page, fitz) -> str:
    boxes = [w for w in (page.widgets() or [])
             if w.field_type in (fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON)]
    if not boxes:
        return page.get_text("text")

    # Rebuild the page row by row from character positions, so a box, its label and the sentence it belongs
    # to (often separate text pieces in a form) come out on one line in reading order.
    def inside_a_box(x: float, y: float) -> bool:
        # A ticked box draws its own tick as a ZapfDingbats character ("3", "4", "8"...), which shows up as
        # text inside the box. That is the box itself, not lease text.
        return any(w.rect.x0 - 0.5 <= x <= w.rect.x1 + 0.5 and w.rect.y0 - 0.5 <= y <= w.rect.y1 + 0.5 for w in boxes)

    chars = []  # (x0, x1, mid_y, character)
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                for ch in span["chars"]:
                    x0, y0, x1, y1 = ch["bbox"]
                    if not inside_a_box((x0 + x1) / 2, (y0 + y1) / 2):
                        chars.append((x0, x1, (y0 + y1) / 2, ch["c"]))
    for w in boxes:
        r = w.rect
        ticked = str(w.field_value).strip().lower() not in ("", "off", "false", "none", "0")
        chars.append((r.x0, r.x1, (r.y0 + r.y1) / 2, "☒" if ticked else "☐"))

    rows: list[list[tuple]] = []
    for ch in sorted(chars, key=lambda c: c[2]):
        if rows and abs(rows[-1][0][2] - ch[2]) <= 4:
            rows[-1].append(ch)
        else:
            rows.append([ch])
    out = []
    for row in rows:
        row.sort(key=lambda c: c[0])
        text, prev_x1 = "", None
        for x0, x1, _, c in row:
            if prev_x1 is not None and x0 - prev_x1 > 1.5 and not text.endswith(" ") and c != " ":
                text += " "
            text += c
            prev_x1 = x1
        out.append(text)
    return "\n".join(out)


def _pdf_pages_pypdf(data: bytes) -> list[str]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        return [page.extract_text() or "" for page in reader.pages]
    except (PdfReadError, ValueError, KeyError) as exc:
        raise InputRejected("unreadable", "This PDF could not be read. It may be damaged or password-protected.") from exc


def _check_spacing(text: str) -> None:
    """Refuse text whose spaces were lost in extraction, before spending model calls on it."""
    words = re.findall(r"[A-Za-z]+", text)
    if len(words) >= 50 and sum(map(len, words)) / len(words) > MAX_AVG_WORD_LEN:
        raise InputRejected(
            "no_spaces",
            "We could not read the spacing between words in this PDF, so the check would not be reliable. "
            "Please upload the Word (.docx) version of the lease, or export the PDF again from Word or Google Docs.",
        )


def _docx_text(data: bytes) -> str:
    import docx
    from docx.opc.exceptions import PackageNotFoundError

    try:
        document = docx.Document(io.BytesIO(data))
    except (PackageNotFoundError, KeyError, ValueError) as exc:
        raise InputRejected("unreadable", "This Word file could not be read.") from exc
    numbering = _WordNumbering()
    lines = [numbering.prefix(p) + _paragraph_text(p) for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            lines.append(" | ".join(" ".join(_paragraph_text(p) for p in cell.paragraphs) for cell in row.cells))
    return "\n".join(lines)


_W14 = "{http://schemas.microsoft.com/office/word/2010/wordml}"


# AI-assisted (Claude Code): paragraph.text skips text inside content controls (where Word keeps its
# clickable ☐/☒ boxes), legacy form-field checkboxes (which have no text at all) and symbol-font
# characters such as Wingdings boxes. Walking the XML in order picks all three up.
def _paragraph_text(paragraph) -> str:
    out: list[str] = []
    for el in paragraph._p.iter():
        tag = el.tag
        if tag == _W + "t":
            out.append(el.text or "")
        elif tag == _W + "tab":
            out.append("\t")
        elif tag in (_W + "br", _W + "cr"):
            out.append("\n")
        elif tag == _W + "sym":  # e.g. w:font="Wingdings" w:char="F0FE"
            code = int(el.get(_W + "char", "0"), 16)
            out.append(chr(code if code >= 0xF000 else code + 0xF000))
        elif tag == _W + "checkBox":  # legacy form field: ticked state is in w:checked, else w:default
            state = el.find(_W + "checked")
            if state is None:
                state = el.find(_W + "default")
            ticked = state is not None and state.get(_W + "val", "1") not in ("0", "false")
            out.append("☒ " if ticked else "☐ ")
    return "".join(out)


# AI-assisted (Claude, Oct 15 2026): rebuilds Word list numbers so auto-numbered leases split correctly.
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _list_info(paragraph) -> tuple[str, int, bool] | None:
    """(list id, level, is_bullet) for a paragraph in a Word list, or None if it is not in a list."""
    p_pr = paragraph._p.pPr
    num_pr = p_pr.numPr if p_pr is not None else None
    style_pr = paragraph.style.element.pPr if paragraph.style is not None else None
    if num_pr is None and style_pr is not None:
        num_pr = style_pr.numPr  # numbering can come from the paragraph style ("List Number")
    if num_pr is None or num_pr.numId is None or str(num_pr.numId.val) == "0":
        return None
    num_id = str(num_pr.numId.val)
    level = int(num_pr.ilvl.val) if num_pr.ilvl is not None else 0
    try:
        numbering = paragraph.part.numbering_part.element
    except (AttributeError, KeyError, NotImplementedError):
        return num_id, level, False
    abstract_id = None
    for num in numbering.iterchildren(_W + "num"):
        if num.get(_W + "numId") == num_id:
            ref = num.find(_W + "abstractNumId")
            abstract_id = ref.get(_W + "val") if ref is not None else None
    is_bullet = False
    for absnum in numbering.iterchildren(_W + "abstractNum"):
        if absnum.get(_W + "abstractNumId") != abstract_id:
            continue
        for lvl in absnum.iterchildren(_W + "lvl"):
            if int(lvl.get(_W + "ilvl", "0")) == level:
                fmt = lvl.find(_W + "numFmt")
                is_bullet = fmt is not None and fmt.get(_W + "val") == "bullet"
    return num_id, level, is_bullet


class _WordNumbering:
    """Rebuilds the numbers Word shows on screen, which are not part of paragraph.text.

    Most lease templates number clauses with Word's numbering feature, so without this the splitter
    sees no "1.", "2.", ... and treats the whole lease as one clause. The first numbered list in the
    document is taken to be the clause list ("1. ", "2. ", ...). Deeper levels and other numbered lists
    become "(a) ", "(b) " so they stay inside their parent clause. Bullets get no prefix."""

    def __init__(self) -> None:
        self.main_list: str | None = None
        self.clause_number = 0
        self.sub_counters: dict[tuple[str, int], int] = {}

    def prefix(self, paragraph) -> str:
        info = _list_info(paragraph)
        if info is None:
            return ""
        num_id, level, is_bullet = info
        if is_bullet:
            return ""
        if self.main_list is None and level == 0:
            self.main_list = num_id
        if num_id == self.main_list and level == 0:
            self.clause_number += 1
            self.sub_counters.clear()  # a new clause restarts its sub-items
            return f"{self.clause_number}. "
        n = self.sub_counters[(num_id, level)] = self.sub_counters.get((num_id, level), 0) + 1
        return f"({chr(ord('a') + (n - 1) % 26)}) "


def _normalise(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def check_is_lease(text: str) -> None:
    """Reject documents that are clearly not leases, before spending any model calls on them."""
    lower = text.lower()
    found = [term for term in LEASE_TERMS if term in lower]
    if len(found) < MIN_LEASE_TERMS:
        raise InputRejected(
            "not_a_lease",
            "This does not look like a residential lease, so we have not checked it. "
            "Please upload the lease agreement itself.",
        )


# A line that starts a new clause: "1.", "12)", "3.1", "4.No pets" (no space, capital next),
# "Section 4", "ARTICLE V", or a short ALL-CAPS heading such as "SECURITY DEPOSIT".
# "(a)" is NOT a new clause (sub-item). Roman numerals still need a space, so "i.e." is not a clause.
_NUMBERED = re.compile(
    r"^\s*(?:section|article|clause|§)?\s*"
    r"(?:\d{1,2}(?:\.\d{1,2})*\s*(?:[.):\-]\s+\S|[.)](?=[\"“(]?[A-Z]))"
    r"|[IVXL]{1,6}\s*[.):\-]\s+\S)",
    re.IGNORECASE,
)
_HEADING = re.compile(r"^\s*[A-Z][A-Z0-9 ,'&/\-]{3,60}:?\s*$")
# AI-assisted (Claude, Oct 15 2026): a clause that opens with an ALL-CAPS lead-in ending in a period,
# e.g. "LATE FEE. If Rent is not paid...", as in common Massachusetts lease templates.
_LEAD_IN = re.compile(r"^\s*[A-Z][A-Z0-9 ,'&/()\-]{2,60}\.\s+\S")

# A clause number in the middle of a line: "...animal shelter. 2.No unauthorized parking...".
# The lookbehinds reject "$50.00", "Unit 12." glued to a word, and "5.2." style sub-numbers.
_INLINE_NUMBER = re.compile(r"(?<![\w$,/])(?<!\d\.)(\d{1,2})\.(?!\d)\s*(?=[\"“(]?[A-Z])")
_REFERENCE_WORDS = ("section", "article", "clause", "paragraph", "§")


def _break_inline_numbers(text: str) -> str:
    """Put each mid-line clause number on its own line, so the line-based splitter can see it.

    Only numbers that continue the sequence (1, 2, 3, ...) count, which filters out page numbers,
    amounts and stray "5." matches. A return to 1 after a few clauses is allowed, since an addendum
    often restarts its numbering."""
    cuts, expected = [], 1
    for m in _INLINE_NUMBER.finditer(text):
        before = text[max(0, m.start() - 12):m.start()].lower().rstrip()
        if before.endswith(_REFERENCE_WORDS):  # "Section 4." is handled by _NUMBERED, and "see paragraph 4." is a cross-reference
            continue
        n = int(m.group(1))
        if n == expected or (n == 1 and expected > 3):
            cuts.append(m.start())
            expected = n + 1
    if len(cuts) < 3:  # too few to trust; leave the text alone
        return text

    pieces, prev = [], 0
    for cut in cuts:
        pieces.append(text[prev:cut].rstrip(" "))
        prev = cut
    pieces.append(text[prev:])
    return "\n".join(pieces)


def split_clauses(text: str) -> list[Clause]:
    """Split lease text into clauses using numbering and headings, falling back to paragraphs."""
    text = _break_inline_numbers(text)
    lines = [line.rstrip() for line in text.split("\n")]
    lines = [line for i, line in enumerate(lines) if not _stray_page_mark(lines, i)]
    starts = [i for i, line in enumerate(lines)
              if _NUMBERED.match(line)
              or ((_HEADING.match(line) or _LEAD_IN.match(line)) and not _mid_sentence(lines, i))]

    blocks: list[str] = []
    if len(starts) >= 3:
        # Anything before the first numbered line is the preamble (parties, address), kept as its own block.
        if starts[0] > 0:
            blocks.append("\n".join(lines[: starts[0]]))
        for a, b in zip(starts, starts[1:] + [len(lines)]):
            blocks.append("\n".join(lines[a:b]))
        blocks = _merge_headings(blocks)
    else:
        blocks = [b for b in re.split(r"\n\s*\n", text)]

    cleaned = [re.sub(r"\s*\n\s*", " ", b).strip() for b in blocks]
    cleaned = [b for b in cleaned if len(b) >= 25]
    if len(cleaned) > config.MAX_CLAUSES:
        raise InputRejected(
            "too_long",
            f"This document splits into {len(cleaned)} clauses, more than the {config.MAX_CLAUSES} we can check at once.",
        )
    return [Clause(clause_id=i + 1, text=b) for i, b in enumerate(cleaned)]


def _neighbours(lines: list[str], i: int) -> tuple[str, str]:
    before = next((l.strip() for l in reversed(lines[:i]) if l.strip()), "")
    after = next((l.strip() for l in lines[i + 1:] if l.strip()), "")
    return before, after


def _mid_sentence(lines: list[str], i: int) -> bool:
    """True when line i sits inside a sentence: the text before it does not end a sentence and the text
    after it carries on in lowercase ("...disturb any / MJMJ 4 / other residents..."). A heading there
    is really a stray page header or footer, so it must not start a new clause."""
    before, after = _neighbours(lines, i)
    return bool(before) and not re.search(r"[.:;!?)\]\"”]$", before) and after[:1].islower()


def _stray_page_mark(lines: list[str], i: int) -> bool:
    """A page marker left in the middle of a sentence (e.g. a footer on a page with no repeat to compare)."""
    return bool(_PAGE_MARK.match(lines[i])) and lines[i].strip() != "" and _mid_sentence(lines, i)


def _merge_headings(blocks: list[str]) -> list[str]:
    """A bare heading line ("SECURITY DEPOSIT") belongs with the text after it."""
    merged: list[str] = []
    carry = ""
    for block in blocks:
        if _HEADING.match(block.strip()) and "\n" not in block.strip():
            carry = (carry + " " + block.strip()).strip()
            continue
        merged.append((carry + "\n" + block).strip() if carry else block)
        carry = ""
    if carry:
        merged.append(carry)
    return merged


# AI-assisted (Claude Code): the app only knows Massachusetts law. A lease for a property elsewhere would be
# judged against the wrong rules, so we look for the state it names and warn when it is not Massachusetts.
STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}
_STATE_NAMES = "|".join(sorted(map(re.escape, STATES.values()), key=len, reverse=True))
# Only places where a name clearly means the state, so "Washington Street" or "Virginia Ave" never count:
_STATE_MENTIONS = [
    re.compile(rf"\b(?i:state|commonwealth) (?i:of) ({_STATE_NAMES})\b"),            # State of Texas
    re.compile(rf"\b(?i:laws of (?:the )?(?:state of |commonwealth of )?)({_STATE_NAMES})\b"),  # laws of New York
    re.compile(rf",\s*({_STATE_NAMES}),?\s+\d{{5}}\b"),                                 # Austin, Texas 78701
    re.compile(rf"\b({_STATE_NAMES}) (?i:law|statutes?|general laws|revised statutes)\b"),  # Texas law
]
_STATE_CODE = re.compile(r",\s*([A-Z]{2})\.?\s+\d{5}(?:-\d{4})?\b")                     # Austin, TX 78701


def states_named(text: str) -> set[str]:
    found = {m.group(1) for pattern in _STATE_MENTIONS for m in pattern.finditer(text)}
    found |= {STATES[m.group(1)] for m in _STATE_CODE.finditer(text) if m.group(1) in STATES}
    if re.search(r"\bM\.?G\.?L\.?\b|\bMassachusetts\b", text):
        found.add("Massachusetts")
    return found


def state_warning(text: str) -> str | None:
    """A warning when the lease names another state, or None for Massachusetts (or no state at all)."""
    others = sorted(states_named(text) - {"Massachusetts"})
    if not others:
        return None
    names = " and ".join(others)
    if "Massachusetts" in states_named(text):
        return (f"This lease also mentions {names}. This app checks against Massachusetts law only, so make sure "
                "the property is in Massachusetts and that the lease is governed by Massachusetts law.")
    return (f"This lease appears to be for a property in {names}, but this app only checks Massachusetts law. "
            "The results below may not apply to your lease. Check with a tenant-rights resource in that state.")


def load_document(data: bytes, filename: str) -> ParsedDocument:
    """The full deterministic front end: extract, check it is a lease, split, collect warnings."""
    text = extract_text(data, filename)
    check_is_lease(text)
    clauses = split_clauses(text)
    if not clauses:
        raise InputRejected("empty", "We could not find any clauses in this document.")
    warnings = []
    other_state = state_warning(text)
    if other_state:
        warnings.append(other_state)
    unticked = [c.display_name for c in clauses if c.notes]
    if unticked:
        warnings.append(f"Some “check one” boxes in this lease are not ticked ({', '.join(unticked)}). "
                        "Each affected clause says how we handled it. Make sure the right options are ticked "
                        "before you sign.")
    return ParsedDocument(clauses, warnings)


def load_clauses(data: bytes, filename: str) -> list[Clause]:
    return load_document(data, filename).clauses
