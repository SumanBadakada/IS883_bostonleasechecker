# Author: Suman Somaiah B A (original placeholder)
# --- Owner: (assign, see docs/TEAM_SPLIT.md) | Streamlit UI, usage cap, secrets, error display ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
from html import escape
from pathlib import Path

import streamlit as st

from leasecheck import config, prompts
from leasecheck.analyzer import AnalysisResult, analyze, findings_digest
from leasecheck.llm import GeminiLLM, LLMError
from leasecheck.parsing import InputRejected
from leasecheck.report import (DISCLAIMER, HELP_RESOURCES, LABEL_NAMES, SEVERITY, html_report, next_steps,
                               overall_verdict)
from leasecheck.art import ART_CSS, compact_skyline_svg, hero_skyline_svg, scanning_house_html
from leasecheck.retrieval import SourceIndex, format_passages

st.set_page_config(page_title="Boston Lease Checker", page_icon="🏠", layout="wide",
                   initial_sidebar_state="auto")

SAMPLE_LEASE = Path(__file__).parent / "samples" / "sample_lease.docx"
DEV_MODE = st.query_params.get("dev") == "1"  # developer options only appear at <app-url>/?dev=1

LABEL_ORDER = ["possibly_unlawful", "unusual", "lawful", "not_checked"]
LABEL_TONE = {"possibly_unlawful": "danger", "unusual": "warning", "lawful": "success", "not_checked": "neutral"}
STATUS_TONE = {"ok": ("success", "Allowed"), "check": ("warning", "Check"), "not_allowed": ("danger", "Not allowed")}
SUGGESTED_QUESTIONS = [
    "Which of these issues matter most before I sign?",
    "Can my landlord keep part of my deposit for cleaning?",
    "What should I ask the landlord to change?",
]

# ---------- styling ----------

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, .stButton button, .stTabs button { font-family: 'Inter', sans-serif; }
.block-container { padding-top: 2rem; padding-bottom: 4rem; max-width: 1200px; }
footer { visibility: hidden; }

.blc-hero { background: linear-gradient(135deg, #0B2545 0%, #1F4E79 60%, #2E6DA4 100%); color: #FFFFFF;
            border-radius: 18px; padding: 34px 38px; margin-bottom: 22px; box-shadow: 0 10px 30px rgba(11,37,69,.18); }
.blc-hero h1 { color: #FFFFFF; font-size: 2.1rem; font-weight: 700; margin: 0 0 6px 0; padding: 0; letter-spacing: -0.02em; }
.blc-hero.compact { padding: 18px 26px; margin-bottom: 18px; }
.blc-hero.compact h1 { font-size: 1.35rem; margin: 0; }
.blc-hero.compact p { font-size: .9rem; }
.blc-hero p { color: #D6E4F5; font-size: 1.05rem; margin: 0; max-width: 760px; }
.blc-badges { margin-top: 18px; display: flex; flex-wrap: wrap; gap: 8px; }
.blc-badge { background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.22); color: #FFFFFF;
             border-radius: 999px; padding: 4px 12px; font-size: .82rem; font-weight: 500; }

.blc-card { background: #FFFFFF; color: #101828; border: 1px solid #EAECF0; border-radius: 14px; padding: 20px 22px;
            box-shadow: 0 1px 2px rgba(16,24,40,.04); }
.blc-card h4 { margin: 0 0 12px 0; font-size: 1rem; font-weight: 600; color: #101828; }
.blc-step { display: flex; gap: 12px; align-items: flex-start; margin-bottom: 12px; color: #344054; font-size: .93rem; }
.blc-step-n { flex: 0 0 26px; height: 26px; border-radius: 50%; background: #E8F0F9; color: #1F4E79; font-weight: 700;
              display: flex; align-items: center; justify-content: center; font-size: .85rem; }
.blc-note { background: #FFFAEB; border: 1px solid #FEDF89; color: #7A2E0E; border-radius: 12px;
            padding: 12px 16px; font-size: .9rem; margin: 6px 0 18px 0; }
.blc-muted { color: #667085; font-size: .85rem; }

.blc-verdict { border-radius: 14px; padding: 18px 22px; margin: 6px 0 18px 0; border: 1px solid; }
.blc-verdict b { font-size: 1.2rem; display: block; margin-bottom: 2px; }
.blc-verdict.danger  { background: #FEF3F2; border-color: #FECDCA; color: #912018; }
.blc-verdict.warning { background: #FFFAEB; border-color: #FEDF89; color: #93370D; }
.blc-verdict.success { background: #ECFDF3; border-color: #ABEFC6; color: #085D3A; }

.blc-stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 8px; }
@media (max-width: 800px) { .blc-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.blc-stat { background: #FFFFFF; border: 1px solid #EAECF0; border-radius: 14px; padding: 14px 18px; }
.blc-stat .n { font-size: 1.9rem; font-weight: 700; line-height: 1.1; }
.blc-stat .l { color: #475467; font-size: .85rem; font-weight: 500; }
.blc-stat.danger .n { color: #B42318; } .blc-stat.warning .n { color: #B54708; }
.blc-stat.success .n { color: #067647; } .blc-stat.neutral .n { color: #475467; }

.blc-pill { display: inline-block; white-space: nowrap; font-size: .75rem; font-weight: 600; padding: 2px 10px; border-radius: 999px;
            margin-right: 8px; vertical-align: middle; }
.blc-pill.danger { background: #FEE4E2; color: #B42318; } .blc-pill.warning { background: #FEF0C7; color: #B54708; }
.blc-pill.success { background: #DCFAE6; color: #067647; } .blc-pill.neutral { background: #EAECF0; color: #475467; }
.blc-clause-title { font-weight: 600; color: #101828; font-size: 1rem; vertical-align: middle; }
.blc-quote { border-left: 3px solid #D0D5DD; padding: 4px 0 4px 14px; margin: 12px 0; color: #344054; font-size: .92rem; }
.blc-cite { color: #1F4E79; font-weight: 600; font-size: .85rem; }

.blc-step-item { border: 1px solid #EAECF0; border-left: 4px solid; border-radius: 10px; padding: 12px 16px;
                 margin-bottom: 10px; background: #FFFFFF; color: #101828; }
.blc-step-item.high { border-left-color: #D92D20; } .blc-step-item.medium { border-left-color: #F79009; }
.blc-step-item .t { font-weight: 600; } .blc-step-item .d { color: #475467; font-size: .9rem; margin-top: 2px; }

.blc-lease { background: #FFFFFF; border: 1px solid #EAECF0; border-radius: 14px; padding: 26px 30px;
             font-family: Georgia, 'Times New Roman', serif; color: #1D2939; line-height: 1.65; }
.blc-lease .c { padding: 6px 12px; margin: 6px -12px; border-radius: 8px; border-left: 4px solid transparent; }
.blc-lease .c.danger { background: #FEF3F2; border-left-color: #D92D20; }
.blc-lease .c.warning { background: #FFFAEB; border-left-color: #F79009; }
.blc-lease .c.neutral { background: #F2F4F7; border-left-color: #98A2B3; }
.blc-lease .tag { font-family: 'Inter', sans-serif; font-size: .72rem; font-weight: 600; margin-left: 6px; }
.blc-lease .c.danger .tag { color: #B42318; } .blc-lease .c.warning .tag { color: #B54708; }

.blc-table { width: 100%; border-collapse: separate; border-spacing: 0; background: #FFFFFF; border: 1px solid #EAECF0;
             border-radius: 14px; overflow: hidden; font-size: .92rem; color: #101828; }
.blc-table th { background: #F9FAFB; color: #475467; font-weight: 600; text-align: left; padding: 12px 14px;
                border-bottom: 1px solid #EAECF0; font-size: .8rem; text-transform: uppercase; letter-spacing: .03em; }
.blc-table td { padding: 12px 14px; border-bottom: 1px solid #F2F4F7; vertical-align: top; }
.blc-table tr:last-child td { border-bottom: none; }

[data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid #EAECF0; }
.stTabs [data-baseweb="tab-list"] { gap: 6px; }
.stTabs [data-baseweb="tab"] { font-weight: 600; }
</style>
""", unsafe_allow_html=True)
st.markdown(f"<style>{ART_CSS}</style>", unsafe_allow_html=True)


def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def esc(text: str) -> str:
    """HTML-escape, and stop Streamlit reading "$2,450 ... $300" as a LaTeX formula."""
    return escape(text or "").replace("$", "&#36;")


def md(text: str) -> str:
    """Plain text for st.markdown, with dollar signs kept literal."""
    return (text or "").replace("$", "\\$")


def pill(tone: str, text: str) -> str:
    return f'<span class="blc-pill {tone}">{esc(text)}</span>'


# ---------- setup: secrets, client, source index (cached across sessions) ----------

def get_api_key() -> str | None:
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:  # no secrets file, or the key is not in it
        return None


@st.cache_resource(show_spinner="Loading Massachusetts law sources...")
def get_index(api_key: str) -> SourceIndex:
    return SourceIndex.build(GeminiLLM(api_key))


for key, value in {"analyses_used": 0, "chat_used": 0, "result": None, "filename": None, "chat": [],
                   "llm": None, "pending_question": None}.items():
    st.session_state.setdefault(key, value)

api_key = get_api_key()
if api_key and st.session_state.llm is None:
    st.session_state.llm = GeminiLLM(api_key)
llm: GeminiLLM | None = st.session_state.llm


# ---------- sidebar ----------

with st.sidebar:
    st.markdown("### 🏠 Boston Lease Checker")
    st.caption("An IS883 student project (Team 4, Boston University).")

    st.markdown("##### Your session")
    used, cap = st.session_state.analyses_used, config.MAX_ANALYSES_PER_SESSION
    st.progress(used / cap, text=f"Lease checks: {cap - used} of {cap} left")
    qused, qcap = st.session_state.chat_used, config.MAX_CHAT_MESSAGES_PER_SESSION
    st.progress(qused / qcap, text=f"Questions: {qcap - qused} of {qcap} left")
    st.caption("Limits keep this free class project within its API quota.")

    st.markdown("##### What we check")
    st.markdown("- Move-in charges and deposits\n- Last month's rent and interest\n- Late fees and landlord entry\n"
                "- Repairs, heat, liability waivers\n- Required disclosures")
    st.caption("Based on M.G.L. c. 186 §15B, 940 CMR 3.17 and the Massachusetts Attorney General's Guide to "
               "Landlord and Tenant Rights.")

    st.markdown("##### Get help")
    for name, url, desc in HELP_RESOURCES:
        st.markdown(f"[{name}]({url})  \n<span class='blc-muted'>{esc(desc)}</span>", unsafe_allow_html=True)

    version, use_retrieval = prompts.ACTIVE_VERSION, True
    if DEV_MODE:
        st.divider()
        st.markdown("##### Developer options")
        version = st.selectbox("Prompt version", list(prompts.PROMPTS),
                               index=list(prompts.PROMPTS).index(prompts.ACTIVE_VERSION))
        use_retrieval = st.toggle("Use retrieval", value=True)
        st.caption(f"Model: `{config.MODEL}`")
        if llm:
            st.caption(f"Tokens this session: {llm.usage.input_tokens:,} in / {llm.usage.output_tokens:,} out "
                       f"(≈ ${llm.usage.cost_usd:.4f} at paid-tier prices)")


# ---------- header ----------

if st.session_state.result is None:
    html('<div class="blc-hero"><div class="blc-hero-text"><h1>Boston Lease Checker</h1>'
         '<p>Signing your first Greater Boston lease? Upload it and see which clauses may break Massachusetts '
         'tenant law, with the law they may break, before you sign.</p><div class="blc-badges">'
         '<span class="blc-badge">⚖️ Massachusetts tenant law</span>'
         '<span class="blc-badge">📑 Clause-by-clause review</span>'
         '<span class="blc-badge">💵 Move-in charge check</span>'
         '<span class="blc-badge">🔗 Every flag cites its source</span></div></div>'
         f'<div class="blc-hero-art">{hero_skyline_svg()}</div></div>')
else:
    html('<div class="blc-hero compact"><div class="blc-hero-text"><h1>Boston Lease Checker</h1>'
         '<p>Your lease review. Not legal advice.</p></div>'
         f'<div class="blc-hero-art">{compact_skyline_svg()}</div></div>')

if not api_key:
    st.error("The app is not configured: GEMINI_API_KEY is missing from Streamlit secrets.")
    st.stop()


# ---------- upload ----------

def run_check(data: bytes, filename: str) -> None:
    if st.session_state.analyses_used >= config.MAX_ANALYSES_PER_SESSION:
        st.error("You have used all the lease checks for this session. Please come back later.")
        return
    st.session_state.analyses_used += 1  # count attempts, so retries cannot bypass the cap
    loader = st.empty()
    loader.markdown(scanning_house_html("Reviewing your lease"), unsafe_allow_html=True)
    bar = st.progress(0.0, text="Reading your lease")
    notice = st.empty()  # explains any wait the free tier forces on us
    llm.on_wait = lambda message: notice.info(message, icon="⏳")

    def show_progress(message: str, fraction: float) -> None:
        notice.empty()
        bar.progress(min(fraction, 1.0), text=message)

    try:
        index = get_index(api_key) if use_retrieval else None
        result = analyze(data, filename, llm, index, prompt_version=version, progress=show_progress)
        st.session_state.update(result=result, filename=filename, chat=[], pending_question=None)
    except InputRejected as exc:
        st.session_state.analyses_used -= 1  # rejected before any model call; don't count it
        st.error(exc.message, icon="📄")
    except LLMError as exc:
        st.error(f"Sorry, the check could not finish. {exc}", icon="⚠️")
    except FileNotFoundError:
        st.error("The app's legal sources are missing. Please tell the team.")
    finally:
        loader.empty()
        bar.empty()
        notice.empty()
        llm.on_wait = lambda message: None


if st.session_state.result is None:
    left, right = st.columns([3, 2], gap="large")
    with left:
        with st.container(border=True):
            st.markdown("#### Check your lease")
            uploaded = st.file_uploader("Upload your lease as a text-based PDF or a Word (.docx) file",
                                        type=["pdf", "docx"], help=f"Up to {config.MAX_FILE_MB} MB. Scanned "
                                        "PDFs (photos of pages) can't be read.")
            b1, b2 = st.columns(2)
            run = b1.button("Check my lease", type="primary", disabled=uploaded is None, use_container_width=True)
            sample = b2.button("Try a sample lease", use_container_width=True,
                               disabled=not SAMPLE_LEASE.exists())
            html('<div class="blc-muted">Tip: remove your name, address and other personal details first. '
                 'The text is sent to Google\'s Gemini API for analysis.</div>')
        if run and uploaded is not None:
            run_check(uploaded.getvalue(), uploaded.name)
            if st.session_state.result is not None:
                st.rerun()
        if sample:
            run_check(SAMPLE_LEASE.read_bytes(), "Sample lease (fictional).docx")
            if st.session_state.result is not None:
                st.rerun()
    with right:
        html("""
        <div class="blc-card">
          <h4>How it works</h4>
          <div class="blc-step"><div class="blc-step-n">1</div><div><b>We split your lease into clauses</b><br>
            Text-based PDFs and Word files only.</div></div>
          <div class="blc-step"><div class="blc-step-n">2</div><div><b>Each clause is checked against Massachusetts law</b><br>
            We find the relevant passages of the statute, regulations and the Attorney General's guide.</div></div>
          <div class="blc-step"><div class="blc-step-n">3</div><div><b>Move-in charges are checked against legal limits</b><br>
            First and last month's rent, deposit, lock fee: nothing else is allowed.</div></div>
          <div class="blc-step" style="margin-bottom:0"><div class="blc-step-n">4</div><div><b>You get a report with citations</b><br>
            Plus questions to ask your landlord before you sign.</div></div>
        </div>""")
    html(f'<div class="blc-note" style="margin-top:18px"><b>Not legal advice.</b> {esc(DISCLAIMER)}</div>')
    st.stop()


# ---------- results ----------

result: AnalysisResult = st.session_state.result
filename: str = st.session_state.filename

head_l, head_r1, head_r2 = st.columns([6, 2, 2], vertical_alignment="center")
head_l.markdown(f"### Results for *{esc(filename)}*")
head_r1.download_button("⬇ Download report", data=html_report(result, filename),
                        file_name=f"lease-review-{Path(filename).stem}.html", mime="text/html",
                        use_container_width=True, help="A printable report. Open it in a browser and print to PDF.")
if head_r2.button("↺ Check another lease", use_container_width=True):
    st.session_state.update(result=None, filename=None, chat=[], pending_question=None)
    st.rerun()

tone, headline, sub = overall_verdict(result)
html(f'<div class="blc-verdict {tone}"><b>{esc(headline)}</b>{esc(sub)}</div>')

counts = result.counts()
html('<div class="blc-stats">' + "".join(
    f'<div class="blc-stat {LABEL_TONE[k]}"><div class="n">{counts.get(k, 0)}</div><div class="l">{LABEL_NAMES[k]}</div></div>'
    for k in LABEL_ORDER) + "</div>")
if result.parse_failures:
    st.warning(f"{counts.get('not_checked', 0)} clause(s) could not be checked because the model's answer was not in "
               "the expected format. Read those clauses yourself, or try again.")
html(f'<div class="blc-note"><b>Not legal advice.</b> {esc(DISCLAIMER)}</div>')

tab_overview, tab_clauses, tab_lease, tab_money, tab_chat = st.tabs(
    ["Overview", "Clause review", "Full lease", "Move-in costs", "Ask a question"])

# --- Overview ---
with tab_overview:
    steps = next_steps(result)
    col_a, col_b = st.columns([3, 2], gap="large")
    with col_a:
        st.markdown("#### Questions to ask your landlord")
        if not steps:
            st.success("Nothing to raise. Still read the whole lease before signing.")
        for s in steps:
            cite = f'<div class="blc-cite" style="margin-top:4px">{esc(s.citation)}</div>' if s.citation else ""
            html(f'<div class="blc-step-item {s.severity}"><div class="t">{esc(s.title)}</div>'
                 f'<div class="d">{esc(s.detail)}</div>{cite}</div>')
    with col_b:
        st.markdown("#### Move-in costs at a glance")
        check = result.charges.check
        if check:
            problems, review = check["problems_found"], check["needs_checking"]
            badges = (pill("danger", f"{problems} not allowed") if problems else pill("success", "Within the limits")) \
                + (pill("warning", f"{review} to check") if review else "")
            html(f'<div class="blc-card"><div class="blc-muted">Total requested before move-in</div>'
                 f'<div style="font-size:1.8rem;font-weight:700">&#36;{check["total_requested"]:,.2f}</div>'
                 f'<div class="blc-muted" style="margin-bottom:10px">Legal maximum (excluding a lock): '
                 f'&#36;{check["maximum_allowed_excluding_lock"]:,.2f}</div>{badges}</div>')
        else:
            html(f'<div class="blc-card"><div class="blc-muted">{esc(result.charges.summary)}</div></div>')
        st.markdown("#### Need help?")
        for name, url, desc in HELP_RESOURCES[:3]:
            st.markdown(f"**[{name}]({url})**  \n{desc}")

# --- Clause review ---
with tab_clauses:
    available = [k for k in LABEL_ORDER if counts.get(k)]
    default = [k for k in ["possibly_unlawful", "unusual", "not_checked"] if k in available] or available
    shown = st.pills("Show", options=available, default=default, selection_mode="multi",
                     format_func=lambda k: f"{LABEL_NAMES[k]} ({counts.get(k, 0)})")
    ordered = sorted(result.clauses, key=lambda r: (SEVERITY[r.label], r.clause.clause_id))
    visible = [r for r in ordered if r.label in (shown or [])]
    if not visible:
        st.info("Choose a category above to see those clauses.")
    for r in visible:
        f = r.finding
        with st.container(border=True):
            topic = f" · {esc(f.topic.capitalize())}" if f and f.topic else ""
            html(f'{pill(LABEL_TONE[r.label], LABEL_NAMES[r.label])}'
                 f'<span class="blc-clause-title">{esc(r.clause.display_name)}{topic}</span>'
                 f'<div class="blc-quote">{esc(r.clause.text)}</div>')
            if f:
                st.markdown(md(f.explanation))
                if f.citation:
                    html(f'<div class="blc-cite">⚖️ {esc(f.citation)}</div>')
                if r.cited:
                    with st.expander("Read the law we cited"):
                        for chunk in r.cited:
                            st.markdown(f"**{chunk.citation}**")
                            st.markdown(md(chunk.text))
            else:
                st.markdown("We could not check this clause automatically. Please read it carefully yourself.")

# --- Full lease ---
with tab_lease:
    st.caption("Your lease as we read it. Highlighted clauses are the ones to look at.")
    parts = []
    for r in result.clauses:
        cls = {"possibly_unlawful": "danger", "unusual": "warning", "not_checked": "neutral"}.get(r.label, "")
        tag = f'<span class="tag">{LABEL_NAMES[r.label].upper()}</span>' if cls else ""
        parts.append(f'<div class="c {cls}">{esc(r.clause.text)}{tag}</div>')
    html('<div class="blc-lease">' + "".join(parts) + "</div>")

# --- Move-in costs ---
with tab_money:
    check = result.charges.check
    if check:
        rows = "".join(
            f"<tr><td><b>{esc(i['charge'])}</b></td><td>&#36;{i['amount']:,.2f}</td>"
            f"<td>{pill(*STATUS_TONE[i['status']])}</td><td>{esc(i['reason'])}</td>"
            f"<td class='blc-muted'>{esc(i['citation'])}</td></tr>" for i in check["items"])
        html(f'<table class="blc-table"><tr><th>Charge</th><th>Amount</th><th>Status</th><th>Why</th><th>Law</th></tr>'
             f'{rows}</table>')
        st.caption(f"Monthly rent \\${check['monthly_rent']:,.2f}. In Massachusetts a landlord may collect only first "
                   "month's rent, last month's rent, a security deposit of at most one month's rent, and the cost of "
                   "a new lock and key.")
    if result.charges.summary:
        st.markdown(md(result.charges.summary))

# --- Ask a question ---
def queue_question() -> None:
    st.session_state.pending_question = st.session_state.chat_box


def answer_question(question: str) -> str:
    try:
        passages = ""
        if result.used_retrieval:
            hits = get_index(api_key).search_many(llm, [question], k=4)[0]
            passages = format_passages([c for c, _ in hits])
        system = prompts.CHAT_SYSTEM.format(findings=findings_digest(result), passages=passages or "(none)")
        return llm.chat(system, st.session_state.chat[-10:], question[:2000])
    except LLMError as exc:
        return f"Sorry, I could not answer that. {exc}"


with tab_chat:
    st.caption("Ask about your lease. Answers use the findings above and the Massachusetts sources. "
               "Not legal advice.")
    question = (st.session_state.pending_question or "").strip()
    st.session_state.pending_question = None

    if not st.session_state.chat and not question:
        cols = st.columns(len(SUGGESTED_QUESTIONS))
        for col, q in zip(cols, SUGGESTED_QUESTIONS):
            if col.button(q, use_container_width=True):
                st.session_state.pending_question = q
                st.rerun()

    for turn in st.session_state.chat:
        with st.chat_message(turn["role"], avatar="🧑" if turn["role"] == "user" else "⚖️"):
            st.markdown(md(turn["content"]))

    if question:
        if st.session_state.chat_used >= config.MAX_CHAT_MESSAGES_PER_SESSION:
            st.error("You have used all your questions for this session.")
        else:
            st.session_state.chat_used += 1
            with st.chat_message("user", avatar="🧑"):
                st.markdown(md(question))
            with st.chat_message("assistant", avatar="⚖️"):
                with st.spinner("Checking your lease and the law..."):
                    answer = answer_question(question)
                st.markdown(md(answer))
            st.session_state.chat += [{"role": "user", "content": question},
                                      {"role": "assistant", "content": answer}]

    st.chat_input("Ask about your lease, e.g. Can my landlord enter without notice?", key="chat_box",
                  on_submit=queue_question)
