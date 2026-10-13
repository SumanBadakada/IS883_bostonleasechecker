# --- Owner: (assign, see docs/TEAM_SPLIT.md) | reading the upload and splitting it into clauses ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
"""Turn an uploaded PDF or DOCX into a list of clauses.

No model is used here: text extraction, scanned-PDF detection, the lease check and clause splitting
are plain code, which is cheaper and cannot hallucinate.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass

from . import config


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

    text = _normalise(text)
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
    text = "\n".join(pages)
    _check_spacing(text)
    return text


def _pdf_pages_pymupdf(data: bytes) -> list[str]:
    import fitz  # PyMuPDF

    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            if doc.needs_pass:
                raise InputRejected("unreadable", "This PDF is password-protected. Please upload an unlocked copy.")
            return [page.get_text("text") or "" for page in doc]
    except (RuntimeError, ValueError) as exc:  # fitz raises FileDataError (a RuntimeError) for damaged files
        raise InputRejected("unreadable", "This PDF could not be read. It may be damaged or password-protected.") from exc


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
    lines = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            lines.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(lines)


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
    starts = [i for i, line in enumerate(lines) if _NUMBERED.match(line) or _HEADING.match(line)]

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


def load_clauses(data: bytes, filename: str) -> list[Clause]:
    """The full deterministic front end: extract, check it is a lease, split."""
    text = extract_text(data, filename)
    check_is_lease(text)
    clauses = split_clauses(text)
    if not clauses:
        raise InputRejected("empty", "We could not find any clauses in this document.")
    return clauses
