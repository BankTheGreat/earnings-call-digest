"""D1-D5 units: period/company extractors, display helpers, polish recovery."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earnings_digest import cli  # noqa: E402
from earnings_digest import render_kb_html as rk  # noqa: E402


def test_extract_period():
    assert cli.extract_period("TU: Earnings Call (OPPDAY) Q2/2026 บมจ. ไทยยูเนี่ยน") == "Q2/2026"
    assert cli.extract_period("PTTEP: OPPDAY & JUMP+ Q 4/2025") is None  # spaced digit — no guess
    assert cli.extract_period("SET Sustainability Forum") is None
    assert cli.extract_period(None) is None


def test_extract_company_prefers_subject_entity():
    analysis = {"entities": [
        {"role": "peer", "company": "คู่เทียบ"},
        {"role": "subject", "company": "ไทย Union Group (Thai Union)"},
    ]}
    assert cli.extract_company("อะไรก็ได้", analysis) == "ไทย Union Group (Thai Union)"


def test_extract_company_title_fallback():
    got = cli.extract_company("SCGD: Earnings Call (OPPDAY) Q2/2026 บมจ. เอสซีจี เดคคอร์", None)
    assert got == "บมจ. เอสซีจี เดคคอร์"
    assert cli.extract_company("no company here", None) is None


def test_display_helpers():
    assert rk._hms(2625) == "43:45"
    assert rk._hms(3720) == "1:02:00"
    assert rk._hms(None) == "?"
    assert rk._thai_date("2026-07-22") == "22 ก.ค. 2026"
    assert rk._period_thai("Q2/2026") == "งวด Q2/2569"
    assert rk._period_thai(None) is None


def test_first_summary_bullet():
    body = ["## Executive Summary", "", "- จุดเด่นแรก", "- จุดสอง", "## Next"]
    assert rk._first_summary_bullet(body) == "จุดเด่นแรก"
    assert rk._first_summary_bullet(["## Other", "- x"]) is None


def test_polish_recovery_parse(tmp_path, monkeypatch):
    kb = tmp_path / "kb" / "TH-SET" / "TEST.BK" / "YouTube"
    kb.mkdir(parents=True)
    f = kb / "2026-01-01 [recovervid1] x.md"
    f.write_text(
        "---\nvideo_id: recovervid1\n---\n# t\n"
        "## Polished Transcript [AI-EDITED]\n\n"
        "> [AI-EDITED] banner line\n\n"
        "[00:00] เนื้อเกลาบรรทัดหนึ่ง\n[00:30] บรรทัดสอง\n\n"
        "## Full Transcript\n\nverbatim...\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ECD_KB_ROOT", str(tmp_path / "kb"))
    got = cli._polish_from_kb_file("recovervid1")
    assert got is not None
    assert "[00:00] เนื้อเกลาบรรทัดหนึ่ง" in got and "banner line" not in got and "verbatim" not in got
