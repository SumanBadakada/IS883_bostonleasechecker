# --- Owner: (assign, see docs/TEAM_SPLIT.md) | download the official legal texts for checking sources/ ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
"""Save the official pages behind sources/*.md into sources/official/ as plain text.

Run from the repo root on your own machine:  python scripts/fetch_sources.py
Then correct the notes in sources/*.md against these files.
"""
import html
import re
import urllib.request
from pathlib import Path

PAGES = {
    "c186_15B.txt": "https://malegislature.gov/Laws/GeneralLaws/PartII/TitleI/Chapter186/Section15B",
    "c186_15.txt": "https://malegislature.gov/Laws/GeneralLaws/PartII/TitleI/Chapter186/Section15",
    "c186_15C.txt": "https://malegislature.gov/Laws/GeneralLaws/PartII/TitleI/Chapter186/Section15C",
    "c186_18.txt": "https://malegislature.gov/Laws/GeneralLaws/PartII/TitleI/Chapter186/Section18",
    "c186_20.txt": "https://malegislature.gov/Laws/GeneralLaws/PartII/TitleI/Chapter186/Section20",
    "940_CMR_3.txt": "https://www.mass.gov/regulations/940-CMR-3-general-regulations",
    "ag_guide.txt": "https://www.mass.gov/guides/the-attorney-generals-guide-to-landlord-and-tenant-rights",
}

OUT = Path(__file__).resolve().parent.parent / "sources" / "official"


def to_text(page: str) -> str:
    page = re.sub(r"(?is)<(script|style|nav|header|footer).*?</\1>", " ", page)
    page = re.sub(r"(?i)<br\s*/?>|</p>|</h\d>|</li>", "\n", page)
    page = re.sub(r"<[^>]+>", " ", page)
    page = html.unescape(page)
    page = re.sub(r"[ \t]+", " ", page)
    return re.sub(r"\n\s*\n+", "\n\n", page).strip()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, url in PAGES.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (IS883 student project)"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = to_text(resp.read().decode("utf-8", errors="replace"))
            (OUT / name).write_text(f"Source: {url}\n\n{text}\n", encoding="utf-8")
            print(f"saved {name} ({len(text):,} chars)")
        except Exception as exc:  # report and keep going
            print(f"FAILED {name}: {exc}")


if __name__ == "__main__":
    main()
