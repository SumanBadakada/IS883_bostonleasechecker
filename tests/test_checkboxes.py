# --- Owner: Suman | tests for "check one" boxes in PDFs, Word files and plain text ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
import io

import docx
import pytest
from docx.oxml import parse_xml

from leasecheck.checkboxes import ASSUMED, NONE_TICKED, NOT_TICKED, TICKED, clause_notes, resolve_boxes
from leasecheck.parsing import extract_text, load_document

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
W14 = 'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"'
LEASE_TOP = ["RESIDENTIAL LEASE", "This lease is between Landlord and Tenant for the premises at 1 Main St. Rent is due monthly.",
             "1. TERM. The term of this lease is twelve months."]


# ---------- text rules ----------

def test_ticked_option_marked_and_others_not():
    out = resolve_boxes("Heat is paid by: ☒ Landlord ☐ Tenant")
    assert out == f"Heat is paid by: {TICKED} Landlord {NOT_TICKED} Tenant"


def test_none_ticked_but_one_filled_in_is_assumed_chosen():
    # The Input A case: options filled in with amounts count as chosen when no box is ticked.
    out = resolve_boxes("Late fee: ☐ $200 if rent is 7 days late ☐ $____ if rent is ___ days late")
    assert f"{ASSUMED} $200" in out and f"{NOT_TICKED} $____" in out
    assert clause_notes(out) and "treated the filled-in option" in clause_notes(out)[0]


def test_none_ticked_and_no_way_to_tell_is_flagged():
    out = resolve_boxes("Tenancy type (check one):\n☐ Tenancy at will\n☐ Fixed-term lease")
    assert out.count(NONE_TICKED) == 2 and "Tenancy type (check one):" in out
    assert "reviewed every option" in clause_notes(out)[0]


def test_vertical_list_is_one_group():
    out = resolve_boxes("Pets:\n☐ allowed\n☒ not allowed")
    assert out == f"Pets:\n{NOT_TICKED} allowed\n{TICKED} not allowed"


def test_single_box_keeps_its_state():
    assert resolve_boxes("☐ Tenant received the lead paint notice") == f"{NOT_TICKED} Tenant received the lead paint notice"


@pytest.mark.parametrize("text", ["[x] Landlord [ ] Tenant", "(X) Landlord ( ) Tenant", " Landlord  Tenant"])
def test_text_and_wingdings_boxes(text):
    assert resolve_boxes(text) == f"{TICKED} Landlord {NOT_TICKED} Tenant"


def test_ordinary_text_untouched():
    text = "3. RENT. Tenant shall pay $2,000 (two thousand dollars) [see Schedule A] on the 1st."
    assert resolve_boxes(text) == text


# ---------- Word files ----------

def _docx_with(*paragraph_xml):
    d = docx.Document()
    for line in LEASE_TOP:
        d.add_paragraph(line)
    for xml in paragraph_xml:
        d.element.body.append(parse_xml(xml))
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _content_control(glyph, ticked):
    return (f'<w:sdt {W} {W14}><w:sdtPr><w14:checkbox><w14:checked w14:val="{1 if ticked else 0}"/></w14:checkbox>'
            f'</w:sdtPr><w:sdtContent><w:r><w:t>{glyph}</w:t></w:r></w:sdtContent></w:sdt>')


def test_word_content_control_checkboxes():
    para = (f'<w:p {W}><w:r><w:t xml:space="preserve">2. UTILITIES. Heat is paid by </w:t></w:r>'
            + _content_control("☐", False) + '<w:r><w:t xml:space="preserve"> Landlord </w:t></w:r>'
            + _content_control("☒", True) + '<w:r><w:t xml:space="preserve"> Tenant</w:t></w:r></w:p>')
    text = extract_text(_docx_with(para), "lease.docx")
    assert f"{NOT_TICKED} Landlord {TICKED} Tenant" in text


def test_word_legacy_form_checkbox_and_symbol():
    legacy = (f'<w:p {W}><w:r><w:t xml:space="preserve">2. PETS. </w:t></w:r>'
              '<w:r><w:fldChar w:fldCharType="begin"><w:ffData><w:checkBox><w:checked/></w:checkBox></w:ffData></w:fldChar></w:r>'
              '<w:r><w:instrText> FORMCHECKBOX </w:instrText></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>'
              '<w:r><w:t xml:space="preserve"> No pets </w:t></w:r>'
              '<w:r><w:sym w:font="Wingdings" w:char="F0A8"/></w:r><w:r><w:t xml:space="preserve"> One cat</w:t></w:r></w:p>')
    text = extract_text(_docx_with(legacy), "lease.docx")
    assert f"{TICKED} No pets {NOT_TICKED} One cat" in text
    assert "FORMCHECKBOX" not in text


# ---------- PDF form fields ----------

def _pdf_with_checkboxes(states):
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for line in LEASE_TOP:
        page.insert_text((72, y), line, fontsize=10)
        y += 16
    page.insert_text((72, y), "2. UTILITIES. Heat is paid by", fontsize=10)
    for (x, label), ticked in zip([(230, "Landlord"), (300, "Tenant")], states):
        w = pymupdf.Widget()
        w.field_type = pymupdf.PDF_WIDGET_TYPE_CHECKBOX
        w.field_name = f"box_{label}"
        w.rect = pymupdf.Rect(x, y - 9, x + 10, y + 1)
        w.field_value = w.on_state() if ticked else "Off"
        page.add_widget(w)
        if ticked:
            w.field_value = w.on_state()
            w.update()
        page.insert_text((x + 13, y), label, fontsize=10)
    for _ in range(6):  # enough text on the page not to look scanned
        y += 16
        page.insert_text((72, y), "Tenant shall keep the premises clean and pay rent when due.", fontsize=10)
    return doc.tobytes()


def test_pdf_form_checkbox_states_are_read():
    text = extract_text(_pdf_with_checkboxes([False, True]), "lease.pdf")
    assert f"{NOT_TICKED} Landlord {TICKED} Tenant" in text


def test_pdf_unticked_form_boxes_produce_a_document_warning():
    parsed = load_document(_pdf_with_checkboxes([False, False]), "lease.pdf")
    assert parsed.warnings and "not ticked" in parsed.warnings[0]
    utilities = next(c for c in parsed.clauses if "UTILITIES" in c.text)
    assert utilities.notes and NONE_TICKED in utilities.text
