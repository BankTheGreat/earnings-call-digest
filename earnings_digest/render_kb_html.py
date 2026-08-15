"""Mechanical KB .md -> self-contained human-readable HTML (SSoT = the .md).

Renders one (or more) knowledge-base Markdown files to a standalone HTML page
with the same name (<same-name>.html) next to the source, so a per-stock
folder of digests is browsable offline.

  python -m earnings_digest.render_kb_html <kb.md> [<kb2.md> ...]
  python -m earnings_digest.render_kb_html --all   (every ok row in the index)
"""
from __future__ import annotations

import html
import re
import sys
import time
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from earnings_digest import ENGINE_VERSION, config  # noqa: E402

_TAG_CLASS = {
    "[FACT]": "t-fact", "[ANALYST OPINION]": "t-op", "[FORECAST]": "t-fc",
    "[ANECDOTE]": "t-an", "[CLAIM]": "t-op", "[UNVERIFIED-QUOTE]": "t-warn",
    "[AUTO-CAPTION]": "t-warn", "[AI-EDITED]": "t-warn", "[SOURCE": "t-src",
}

_CSS = """
:root{--bg:#12141a;--panel:#1b1e27;--ink:#e8e6df;--sub:#a9a698;--line:#333845;
--gold:#d4af37;--good:#7fc97f;--warn:#e0b050;--bad:#e07070;color-scheme:dark light;
--surface:#1b1e27;}
:root[data-theme="light"]{--bg:#f7f5ef;--panel:#fff;--ink:#23252b;--sub:#5f5d55;--line:#d8d4c8;--gold:#8a6d1a;--good:#1d8a4e;--warn:#b07a10;--bad:#c0392b;--surface:#fff;color-scheme:light;}
html,body{background:var(--bg);color:var(--ink);}
body{font-family:'Segoe UI',Tahoma,sans-serif;margin:0;padding:26px 4vw 60px;line-height:1.7;}
h1{color:var(--gold);font-size:1.3rem;margin:.2em 0 .4em;}
h2{color:var(--gold);font-size:1.08rem;border-bottom:1px solid var(--line);padding-bottom:4px;margin:1.5em 0 .5em;}
h3{color:var(--gold);font-size:.98rem;margin:1.1em 0 .3em;}
table{border-collapse:collapse;width:100%;margin:.5em 0;font-size:.92rem;}
th,td{border:1px solid var(--line);padding:6px 9px;text-align:left;vertical-align:top;}
th{background:var(--panel);color:var(--gold);}
blockquote{background:var(--panel);border-left:4px solid var(--warn);margin:.6em 0;padding:8px 14px;border-radius:6px;color:var(--sub);}
ol.claims{padding-left:1.4em;}ol.claims>li{margin:.45em 0;}
.q{color:var(--sub);font-size:.92rem;margin:.2em 0 .3em 1em;border-left:2px solid var(--line);padding-left:10px;}
.exec{background:linear-gradient(135deg,rgba(212,175,55,.14),rgba(212,175,55,.03) 60%);
border:1px solid var(--gold);border-left:6px solid var(--gold);border-radius:12px;
padding:6px 22px 14px;margin:.6em 0 1.3em;box-shadow:0 2px 14px rgba(212,175,55,.10);}
.exec h2{border-bottom:none;font-size:1.15rem;letter-spacing:.3px;}
.exec ul{margin:.3em 0;padding-left:1.3em;}
.exec li{margin:.55em 0;font-size:1.08rem;line-height:1.75;}
.exec li::marker{color:var(--gold);}
.lenscard{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 16px 12px;margin:.7em 0;}
.lenscard h3{margin:.2em 0 .5em;}
.lenscard ol.claims{margin:.2em 0;}
.lensgrid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:.6em 0;}
.lensgrid .lenscard{margin:0;}
.bbwrap{display:grid;grid-template-columns:1fr 1fr;gap:6px 22px;align-items:start;margin:.4em 0;}
.bbhead{color:var(--gold);font-size:1.08rem;font-weight:700;border-bottom:1px solid var(--line);padding-bottom:4px;}
.bcell{min-width:0;}
.bcell>b{display:block;margin:.3em 0 .2em;}
ol.claims.kc{list-style:none;padding-left:0;}
ol.claims.kc>li{display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start;
padding:.5em 0;border-bottom:1px solid var(--line);}
ol.claims.kc .ck{min-width:0;}
ol.claims.kc .cnum{color:var(--gold);font-weight:700;}
ol.claims.kc .cq{min-width:0;color:var(--sub);font-size:.9rem;
border-left:2px solid var(--line);padding-left:10px;}
.numwrap .coltoggle{background:var(--panel);color:var(--ink);border:1px solid var(--line);
border-radius:14px;padding:3px 12px;font-size:.82rem;cursor:pointer;margin:.2em 0 .4em;}
.numsplit{display:grid;grid-template-columns:1fr 1fr;gap:0 22px;align-items:start;}
.numwrap.show-detail .numsplit{grid-template-columns:1fr;}
.numtable .cdetail{display:none;}
.numwrap.show-detail .cdetail{display:table-cell;}
@media(max-width:760px){.lensgrid,.bbwrap,.numsplit{grid-template-columns:1fr;}
ol.claims.kc>li{grid-template-columns:1fr;gap:4px;}
ol.claims.kc .cq{border-left:none;padding-left:0;}}
.qok{color:var(--good);font-size:.85em;}
.ai-note{color:var(--warn);font-size:.85rem;margin:.2em 0 .6em;}
.rowwarn td{background:rgba(224,176,80,.08);}
.grp td{background:var(--panel);color:var(--gold);font-weight:600;border-top:2px solid var(--line);}
.tlink{color:inherit;text-decoration:underline dotted;}
.badge{font-size:.75rem;border:1px solid var(--line);border-radius:10px;padding:1px 8px;margin-right:5px;white-space:nowrap;}
.t-fact{color:var(--good);}.t-op{color:var(--sub);}.t-fc{color:var(--warn);}.t-an{color:var(--sub);}
.t-warn{color:var(--warn);}.t-src{color:var(--sub);}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:.5em 0 1.1em;}
.idrow{display:flex;flex-wrap:wrap;gap:14px;align-items:baseline;}
.tk{font-size:1.55rem;color:var(--gold);font-weight:700;letter-spacing:.5px;}
.co{font-size:1rem;}
.per{border:1px solid var(--gold);color:var(--gold);border-radius:10px;padding:1px 10px;font-size:.85rem;}
.subx{color:var(--sub);font-size:.85rem;}
.trust{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;}
.bdg{border-radius:14px;padding:3px 12px;font-size:.85rem;border:1px solid var(--line);}
.bdg.g{color:var(--good);border-color:var(--good);}
.bdg.w{color:var(--warn);border-color:var(--warn);}
.take{margin-top:10px;padding:8px 12px;border-left:3px solid var(--gold);background:rgba(212,175,55,.06);border-radius:6px;font-size:.93rem;}
.take b{color:var(--gold);}
.take.standalone{margin:0 0 1.1em;padding:12px 16px;font-size:1rem;border-left-width:4px;}
.prov{margin-top:10px;color:var(--sub);font-size:.78rem;}
details{border:1px solid var(--line);border-radius:8px;margin:1em 0;background:var(--panel);}
details>summary{cursor:pointer;padding:10px 14px;color:var(--gold);font-weight:600;}
details>div{padding:4px 16px 14px;white-space:pre-wrap;font-size:.92rem;}
details>div.rich{white-space:normal;font-size:.95rem;}
#themeToggle{position:fixed;top:14px;right:16px;z-index:1000;background:var(--panel);
border:1px solid var(--line);border-radius:16px;width:64px;height:30px;cursor:pointer;
display:flex;align-items:center;user-select:none;box-sizing:content-box;}
.ticon{flex:0 0 32px;height:30px;display:flex;align-items:center;justify-content:center;
font-size:.85rem;line-height:1;z-index:0;color:var(--sub);opacity:.45;}
#tknob{position:absolute;top:2px;left:2px;width:26px;height:26px;border-radius:50%;
display:flex;align-items:center;justify-content:center;font-size:.95rem;line-height:1;
box-shadow:0 1px 5px rgba(0,0,0,.35);transition:transform .25s,background .25s;z-index:2;}
#tknob.knob-d{background:#3a4152;color:#dfe6f5;}
#tknob.knob-l{background:#f0a500;color:#fff;}
.tone{font-weight:700;padding:3px 16px;border-radius:16px;border:2px solid;
font-size:1.05rem;letter-spacing:.6px;display:inline-block;}
.tone-bullish{color:var(--good);border-color:var(--good);background:rgba(127,201,127,.12);}
.tone-bearish{color:var(--bad);border-color:var(--bad);background:rgba(224,112,112,.12);}
.tone-neutral{color:var(--sub);border-color:var(--sub);background:rgba(150,150,150,.10);}
.tone-mixed{color:var(--warn);border-color:var(--warn);background:rgba(224,176,80,.12);}
footer{margin-top:36px;color:var(--sub);font-size:.8rem;border-top:1px solid var(--line);padding-top:10px;}
/* Print flips the TOKENS, not just body: setting body background alone left
   --panel at #1b1e27, so every card and quote block printed dark on white. */
@media print{#themeToggle{display:none;}
:root{--bg:#fff;--ink:#111;--panel:#fff;--surface:#fff;--sub:#444;--line:#bbb;}}
"""


_CURRENT_VIDEO_URL: str | None = None  # set per convert(); CLI is single-threaded
_TS_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


def _ts_seconds(ts: str) -> int | None:
    m = _TS_RE.match(ts.strip())
    if not m:
        return None
    h_or_m, mm, ss = int(m.group(1)), int(m.group(2)), m.group(3)
    return h_or_m * 3600 + mm * 60 + int(ss) if ss else h_or_m * 60 + mm


def _ts_link(ts: str) -> str:
    """R1: MM:SS -> deep link into the video at that second."""
    secs = _ts_seconds(ts)
    if secs is None or not _CURRENT_VIDEO_URL:
        return html.escape(ts)
    sep = "&" if "?" in _CURRENT_VIDEO_URL else "?"
    return (f'<a class="tlink" href="{html.escape(_CURRENT_VIDEO_URL)}{sep}t={secs}s">'
            f'{html.escape(ts)}</a>')


def _badge_tags(s: str) -> str:
    for tag, cls in _TAG_CLASS.items():
        if tag.endswith("]"):
            s = s.replace(html.escape(tag), f'<span class="badge {cls}">{html.escape(tag[1:-1])}</span>')

    def _src(m: re.Match) -> str:
        inner = m.group(1)
        if " @ " in inner:
            speaker, ts = inner.rsplit(" @ ", 1)
            return (f'<span class="badge t-src">SOURCE {speaker} @ </span>{_ts_link(ts)}'
                    if _ts_seconds(ts) is not None
                    else f'<span class="badge t-src">SOURCE {inner}</span>')
        return f'<span class="badge t-src">SOURCE {inner}</span>'

    s = re.sub(r"\[SOURCE ([^\]]{1,60})\]", _src, s)
    return s


def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"_([^_]{2,60})_", r"<em>\1</em>", s)
    return _badge_tags(s)


def _parse_frontmatter(lines: list[str]) -> tuple[dict, int]:
    if not lines or lines[0].strip() != "---":
        return {}, 0
    front = {}
    for i, ln in enumerate(lines[1:], start=1):
        if ln.strip() == "---":
            return front, i + 1
        if ":" in ln:
            k, v = ln.split(":", 1)
            front[k.strip()] = v.strip().strip('"')
    return front, 0


_THAI_MONTHS = ["", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
                "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def _hms(seconds) -> str:
    try:
        s = int(seconds)
    except (TypeError, ValueError):
        return "?"
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def _thai_date(iso: str | None) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    if not m:
        return iso or "?"
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return f"{d} {_THAI_MONTHS[mo]} {y}"


def _period_thai(period: str | None) -> str | None:
    m = re.match(r"Q([1-4])/(\d{4})", period or "")
    return f"งวด Q{m.group(1)}/{int(m.group(2)) + 543}" if m else None


def _first_summary_bullet(body_lines: list[str]) -> str | None:
    in_sum = False
    for ln in body_lines:
        s = ln.strip()
        if s.startswith("## "):
            if in_sum:
                return None
            in_sum = s == "## Executive Summary"
        elif in_sum and s.startswith("- ") and not s.startswith("- _"):
            return s[2:]
    return None


_DEFER_TO_BOTTOM = ("Companies & Securities Mentioned",)
_TRANSCRIPT_HEADS = ("Polished Transcript", "Full Transcript")
# MB 2026-08-06: Bull vs Bear sits DIRECTLY above Catalysts & Risks — the
# evidence pair (Claims, Numbers) reads first, the synthesis pair together.
_MOVE_BEFORE = {"Bull vs Bear": "Catalysts & Risks"}


def _reorder_sections(body: list[str]) -> list[str]:
    """Presentation-order surgery (md SSoT order untouched)."""
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    for ln in body:
        s = ln.strip()
        if s.startswith("## ") and not s.startswith("### "):
            sections.append((s[3:], [ln]))
        else:
            sections[-1][1].append(ln)

    for mover, anchor in _MOVE_BEFORE.items():
        mv = [sec for sec in sections if sec[0] and sec[0].startswith(mover)]
        if mv:
            sections = [sec for sec in sections if sec not in mv]
            at = next((i for i, sec in enumerate(sections)
                       if sec[0] and sec[0].startswith(anchor)), None)
            if at is not None:
                sections = sections[:at] + mv + sections[at:]
            else:
                sections.extend(mv)  # anchor absent — keep content, never drop

    deferred = [sec for sec in sections if sec[0] and sec[0].startswith(_DEFER_TO_BOTTOM)]
    if deferred:
        kept = [sec for sec in sections if sec not in deferred]
        insert_at = next(
            (idx for idx, sec in enumerate(kept)
             if sec[0] and sec[0].startswith(_TRANSCRIPT_HEADS)),
            len(kept),
        )
        sections = kept[:insert_at] + deferred + kept[insert_at:]

    # MB 2026-08-06: drop the Full Transcript section from the human render
    # (verbatim stays in the .md SSoT — this is a display cut, not a data cut).
    sections = [sec for sec in sections
                if not (sec[0] and sec[0].startswith("Full Transcript"))]
    return [ln for _, lines in sections for ln in lines]


def convert(md_path: Path) -> Path:
    global _CURRENT_VIDEO_URL
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    front, body_start = _parse_frontmatter(lines)
    body = lines[body_start:]
    _CURRENT_VIDEO_URL = front.get("source_url") or None  # R1 deep links

    out: list[str] = []
    title = front.get("video_title") or md_path.stem
    out.append(f"<h1>{html.escape(title)}</h1>")

    # D5 three-tier card: identity -> trust badges -> provenance footer.
    ticker = str(front.get("tickers") or "").strip("[]") or "?"
    company = front.get("company_name") or ""
    period_th = _period_thai(front.get("period"))
    ident = [f'<span class="tk">{html.escape(ticker)}</span>']
    if company:
        ident.append(f'<span class="co">{html.escape(company)}</span>')
    if period_th:
        ident.append(f'<span class="per">{html.escape(period_th)}</span>')
    src = front.get("source_url") or "#"
    ident.append(
        f'<span class="subx">Opp Day · {html.escape(_thai_date(front.get("published")))}'
        f' · ยาว {_hms(front.get("duration_s"))} นาที'
        f' · <a href="{html.escape(src)}">เปิดคลิปต้นฉบับ</a></span>'
    )

    badges = []
    if front.get("analysis_status") == "ok":
        badges.append('<span class="bdg g">✅ ผ่านการตรวจสอบครบ</span>')
    else:
        badges.append(f'<span class="bdg w">สถานะ: {html.escape(str(front.get("analysis_status")))}</span>')
    try:
        failed = int(front.get("quote_unverified_count") or 0)
        total = int(front.get("anchored_total") or 0)
    except (TypeError, ValueError):
        failed, total = 0, 0
    if total > 0:
        okn = total - failed
        pct = round(okn * 100 / total)
        cls = "g" if pct >= 90 else "w"
        badges.append(f'<span class="bdg {cls}">อ้างอิงตรงคำพูด {okn}/{total} ({pct}%)</span>')
    elif failed:
        badges.append(f'<span class="bdg w">อ้างอิงติดป้ายตรวจ {failed} จุด</span>')
    else:
        badges.append('<span class="bdg g">อ้างอิงตรงคำพูดครบ</span>')
    if front.get("track_kind") == "auto":
        badges.append('<span class="bdg w">⚠ ซับอัตโนมัติ — ตัวเลขควรยืนยันกับงบ</span>')
    if front.get("polish_status") == "ok":
        badges.append('<span class="bdg g">บทพูดฉบับอ่านง่าย: มี ✓</span>')
    else:
        badges.append('<span class="bdg w">บทพูดฉบับอ่านง่าย: ไม่มี (ระบบกันเลขเพี้ยน)</span>')
    try:
        dchecked = int(front.get("doc_checked_total"))
        dok = int(front.get("doc_confirmed_total") or 0)
    except (TypeError, ValueError):
        dchecked = None
    if dchecked:
        dpct = round(dok * 100 / dchecked)
        dcls = "g" if dpct >= 70 else "w"
        badges.append(f'<span class="bdg {dcls}">ตัวเลขยืนยันกับสไลด์/MD&amp;A {dok}/{dchecked} ({dpct}%)</span>')
    else:
        badges.append('<span class="bdg w">ไม่พบสไลด์/MD&amp;A ของงวดนี้ให้ยืนยัน</span>')

    takeaway = _first_summary_bullet(body)
    # MB 2026-08-06: no cost line; clip link lives in the identity row;
    # documents listed plainly under "Materials:".
    gdocs = " · ".join(
        html.escape(str(front.get(k)))
        for k in ("grounding_slide", "grounding_mda")
        if front.get(k) not in (None, "", "null")
    )
    prov = (
        f'วิเคราะห์โดย {html.escape(str(front.get("summary_model") or "?"))} '
        f'(โหมด {html.escape(str(front.get("summary_mode") or "?"))})'
        + (f' · Materials: {gdocs}' if gdocs else "")
    )
    out.append(
        '<div class="card"><div class="idrow">' + "".join(ident) + "</div>"
        + '<div class="trust">' + "".join(badges) + "</div>"
        + f'<div class="prov">{prov}</div></div>'
    )
    # ประเด็นเด่น is its OWN block below the card (MB directive 2026-08-05),
    # not a row inside the identity/trust box.
    if takeaway:
        out.append(f'<div class="take standalone"><b>ประเด็นเด่น:</b> {_inline(takeaway)}</div>')

    # Render-layer section order (MB 2026-08-05): the companies/securities
    # reference table reads LAST in the analysis, just before the transcript
    # folds. The .md SSoT order is untouched — this is presentation only.
    body = _reorder_sections(body)

    i = 0
    in_details = False
    list_open = None  # "ul" | "ol"
    table_buf: list[str] = []
    cur_h2 = ""
    lens_card_open = False
    lensgrid_open = False
    bb_open = False        # inside the Bull/Catalysts 2x2 aligned grid
    bb_cell_open = False   # a placed sub-block cell is currently open
    exec_open = False
    rich_open = False
    auto_track = front.get("track_kind") == "auto"
    # MB 2026-08-06: explicit grid placement so Bull|Catalysts share row 3 and
    # Bear|Risks share row 4 (rows auto-size to the taller cell → aligned).
    _BB_PLACE = {"Bull": (1, 3), "Bear": (1, 4), "Catalysts": (2, 3), "Risks": (2, 4)}

    def close_list():
        nonlocal list_open
        if list_open:
            out.append(f"</{list_open}>")
            list_open = None

    def _merge_verify(check: str, doc: str) -> tuple[str, bool]:
        """R5 + MB 2026-08-06: one verification cell NAMING the confirming
        document(s). Returns (cell_html, warn_row)."""
        voice_ok = check.strip().lower().startswith("ok")
        has_doc = "✓" in doc
        unfound = "ไม่พบ" in doc
        doc_names = html.escape(doc.replace("✓", "").strip())  # "สไลด์+MD&A" | "สไลด์" | "MD&A"
        if voice_ok and has_doc:
            return f'<span class="qok">✓ เสียง+{doc_names}</span>', False
        if voice_ok and unfound:
            return '<span class="badge t-warn">⚠ ไม่พบในเอกสาร</span>', True
        if voice_ok:
            return '<span class="qok">✓ เสียง</span>', False
        tail = f" · {doc_names} ✓" if has_doc else ""
        return f'<span class="badge t-warn">⚠ เสียงไม่ผ่านตรวจ{tail}</span>', True

    _NUM_HEADER = ["Value", "Metric", "Period", "Unit", "Currency", "@", "Check", "Doc"]

    # MB 2026-08-06: mechanical grouping of the numbers table. Rule ORDER is
    # load-bearing — specific vocabularies outrank broad ones; no match falls
    # to "อื่น ๆ" honestly (never a wrong bucket by force).
    _GROUP_RULES = [
        ("Dividends & Shareholder Returns",
         re.compile(r"dividend|payout|ปันผล|buyback|buy-back|share repurchase|treasury", re.I)),
        ("Segments", re.compile(
            r"ambient|frozen|petcare|pet care|value-added|value added|segment|"
            r"premium mix|high-margin|packaging", re.I)),
        ("Balance Sheet & Cash Flow", re.compile(
            r"net debt|debt/|d/e|equity|ebitda|cash flow|fcf|cost of debt|"
            r"capex|leverage|gearing", re.I)),
        ("Guidance & Targets", re.compile(r"guidance|target|band|เป้า", re.I)),
        ("Margins", re.compile(r"margin|gpm|กำไรขั้นต้น", re.I)),
        ("Overall Performance", re.compile(
            r"sales|revenue|profit|earnings|eps|income|รายได้|กำไร", re.I)),
        ("Raw Materials & FX", re.compile(
            r"tuna|shrimp|fish|raw material|\bfx\b|thb/usd|อัตราแลกเปลี่ยน|"
            r"วัตถุดิบ|ทูน่า|กุ้ง|ค่าเงิน", re.I)),
    ]
    _GROUP_OTHER = "Others"
    # MB 2026-08-06: display importance order — financial performance first;
    # Guidance & Targets closes the company-goal story, and Dividends &
    # Shareholder Returns sits at the very bottom after it.
    # (Rule order above stays classification-specificity order — separate axes.)
    _GROUP_DISPLAY = ["Overall Performance", "Margins", "Segments",
                      "Balance Sheet & Cash Flow", "Raw Materials & FX",
                      _GROUP_OTHER, "Guidance & Targets",
                      "Dividends & Shareholder Returns"]

    def _metric_group(metric: str) -> str:
        for name, rx in _GROUP_RULES:
            if rx.search(metric):
                return name
        return _GROUP_OTHER

    def flush_table():
        nonlocal table_buf
        if not table_buf:
            return
        rows = [r for r in table_buf if not re.match(r"^\|[\s\-|]+\|$", r)]
        cells0 = [c.strip() for c in rows[0].strip().strip("|").split("|")] if rows else []
        numbers_mode = cur_h2.startswith("Numbers") and cells0 == _NUM_HEADER
        if numbers_mode and auto_track:
            # R4: one table-level caption note replaces the per-row tag.
            out.append('<p class="ai-note">⚠ ตัวเลขทั้งตารางถอดจากซับอัตโนมัติของ YouTube — '
                       'แถวที่มี ✓ เอกสาร ได้รับการยืนยันจากไฟล์ของบริษัทแล้ว</p>')
        def _emit_row(cellstr: list[str], ri: int) -> None:
            tag = "th" if ri == 0 else "td"
            row_cls = ""
            if numbers_mode and len(cellstr) == 8:
                if ri == 0:
                    cells_html = [_inline(c) for c in ["Metric", "Value", "Period", "@", "การยืนยัน"]]
                else:
                    # R6': drop Unit/Currency; R5 merge Check+Doc; R7 warn rows.
                    # MB 2026-08-06: Metric leads, Value second.
                    check_raw = cellstr[6].replace("[AUTO-CAPTION]", "").strip()
                    verify_html, warn = _merge_verify(check_raw, cellstr[7])
                    kept = [cellstr[1], cellstr[0], cellstr[2], cellstr[5]]
                    cells_html = [
                        _ts_link(c) if _ts_seconds(c) is not None else _inline(c)
                        for c in kept
                    ] + [verify_html]
                    row_cls = ' class="rowwarn"' if warn else ""
            else:
                cells_html = [
                    _ts_link(c) if ri > 0 and _ts_seconds(c) is not None else _inline(c)
                    for c in cellstr
                ]
            # MB 2026-08-06: Period(2) + @(3) + การยืนยัน(4) are detail columns —
            # hidden by default, revealed via the .numwrap toggle. Metric+Value
            # are the only always-on columns, keeping the split tables narrow.
            detail_idx = {2, 3, 4} if (numbers_mode and len(cells_html) == 5) else set()
            tds = "".join(
                f'<{tag}{" class=\"cdetail\"" if ci in detail_idx else ""}>{c}</{tag}>'
                for ci, c in enumerate(cells_html)
            )
            out.append(f"<tr{row_cls}>{tds}</tr>")

        parsed = [[c.strip() for c in row.strip().strip("|").split("|")] for row in rows]
        if numbers_mode and parsed:
            # MB 2026-08-06: two side-by-side tables (Metric+Value default) so
            # the section is half as tall. Groups stay whole; split by row count.
            groups: dict[str, list[list[str]]] = {}
            for cells in parsed[1:]:
                groups.setdefault(_metric_group(cells[1] if len(cells) == 8 else ""), []).append(cells)
            present = [(g, groups[g]) for g in _GROUP_DISPLAY if g in groups]
            total = sum(1 + len(rws) for _, rws in present)  # header row + data rows
            left, right, acc = [], [], 0
            for g, rws in present:
                (left if acc < total / 2 else right).append((g, rws))
                acc += 1 + len(rws)
            if not right:  # everything landed left — move the last group over
                right = [left.pop()] if len(left) > 1 else []
            out.append('<div class="numwrap"><button class="coltoggle" '
                       "onclick=\"var w=this.closest('.numwrap');"
                       "var on=w.classList.toggle('show-detail');"
                       "this.textContent=on?'ซ่อน งวด/เวลา/การยืนยัน':'แสดง งวด/เวลา/การยืนยัน'\">"
                       'แสดง งวด/เวลา/การยืนยัน</button><div class="numsplit">')

            def _emit_side(side):
                out.append('<table class="numtable">')
                _emit_row(parsed[0], 0)
                for gname, rws in side:
                    out.append(f'<tr class="grp"><td colspan="5">{_inline(gname)}</td></tr>')
                    for cells in rws:
                        _emit_row(cells, 1)
                out.append("</table>")

            _emit_side(left)
            _emit_side(right)
            out.append("</div></div>")
            table_buf = []
            return
        out.append("<table>")
        for ri, cells in enumerate(parsed):
            _emit_row(cells, ri)
        out.append("</table>")
        table_buf = []

    def open_details(summary: str):
        nonlocal in_details
        close_all()
        out.append(f"<details><summary>{_inline(summary)}</summary><div>")
        in_details = True

    def close_details():
        nonlocal in_details
        if in_details:
            out.append("</div></details>")
            in_details = False

    def close_all():
        close_list()
        flush_table()

    while i < len(body):
        ln = body[i]
        s = ln.strip()
        if s.startswith("<!--"):
            i += 1
            continue
        if in_details and not s.startswith("## "):
            # The Full Transcript section is cut from the HTML (MB 2026-08-06);
            # rewrite the polished banner's pointer to it so it isn't dangling.
            ln = ln.replace("the verbatim Full Transcript at the tail",
                            "the verbatim transcript in the source .md file")
            out.append(html.escape(ln))
            i += 1
            continue
        if s.startswith("# ") and not s.startswith("## "):
            i += 1  # page title already lives on the card — skip the raw md h1
            continue
        if s.startswith("## "):
            close_all()
            close_details()
            if lens_card_open:
                out.append("</div>")
                lens_card_open = False
            if lensgrid_open:
                out.append("</div>")
                lensgrid_open = False
            if exec_open:
                out.append("</div>")
                exec_open = False
            if rich_open:
                out.append("</div></details>")
                rich_open = False
            head = s[3:]
            # MB 2026-08-06: Bull vs Bear + Catalysts & Risks form one 2x2 grid
            # so Bull|Catalysts and Bear|Risks align row-for-row (explicit
            # grid placement — reorder already made them adjacent).
            if bb_open and not head.startswith("Catalysts & Risks"):
                if bb_cell_open:
                    out.append("</div>")
                    bb_cell_open = False
                out.append("</div>")  # close bbwrap
                bb_open = False
            cur_h2 = head
            if head == "Executive Summary":
                # MB 2026-08-06: the summary lives in a standout hero box.
                out.append('<div class="exec">')
                exec_open = True
            elif head.startswith(("Open Questions", "Companies & Securities Mentioned")):
                # MB 2026-08-06: reference sections collapse like transcripts,
                # but keep RICH rendering (tables/lists) inside the fold.
                out.append(f'<details><summary>{_inline(head)}</summary><div class="rich">')
                rich_open = True
                i += 1
                continue
            if head.startswith("Polished Transcript"):
                open_details(head)
            elif head.startswith("Bull vs Bear"):
                out.append('<div class="bbwrap">'
                           f'<div class="bbhead" style="grid-column:1;grid-row:1">{_inline(head)}</div>')
                bb_open = True
                # MB 2026-08-05: synthesis carries an explicit AI-generated note.
                out.append('<p class="ai-note" style="grid-column:1/-1;grid-row:2">'
                           '⚠ ส่วนนี้ AI สังเคราะห์ขึ้นจากเนื้อหาคลิป '
                           '(ไม่ได้ผูก quote รายข้อ) — ตรวจย้อนหลักฐานได้จาก Key Claims ด้านบน</p>')
            elif head.startswith("Catalysts & Risks") and bb_open:
                if bb_cell_open:
                    out.append("</div>")
                    bb_cell_open = False
                out.append(f'<div class="bbhead" style="grid-column:2;grid-row:1">{_inline(head)}</div>')
            elif head.startswith("Value-Investing Lens"):
                out.append(f'<h2>{_inline(head)}</h2><div class="lensgrid">')
                lensgrid_open = True
            else:
                out.append(f"<h2>{_inline(head)}</h2>")
        elif s.startswith("### "):
            close_all()
            # MB 2026-08-06: each Value-Investing Lens subsection is a card.
            if lens_card_open:
                out.append("</div>")
                lens_card_open = False
            if cur_h2.startswith("Value-Investing Lens"):
                out.append('<div class="lenscard">')
                lens_card_open = True
            out.append(f"<h3>{_inline(s[4:])}</h3>")
        elif s == "---":
            close_all()
            out.append("<hr>")
        elif s.startswith("> "):
            close_all()
            body_q = s[2:]
            if body_q.startswith("Doc column:"):
                # Post-R5 the Doc column is merged — rewrite the md footnote
                # into the merged-cell vocabulary (files list preserved).
                m_files = re.search(r"against (.+?) \(REQ-G", body_q)
                files = m_files.group(1) if m_files else ""
                out.append('<p class="ai-note">ยืนยันเอกสารกับ: '
                           f'{_inline(files)} — ตรวจการปรากฏของตัวเลขแบบกลไก '
                           '("ไม่พบ" คือหาไม่เจอในเอกสาร ไม่ใช่ขัดแย้ง)</p>')
            else:
                out.append(f"<blockquote>{_inline(body_q)}</blockquote>")
        elif s.startswith("|"):
            close_list()
            table_buf.append(s)
        elif re.match(r"^\d+\. ", s):
            flush_table()
            is_kc = cur_h2.startswith("Key Claims")
            if list_open != "ol":
                close_list()
                out.append('<ol class="claims kc">' if is_kc else '<ol class="claims">')
                list_open = "ol"
            m_num = re.match(r"^(\d+)\. ", s)
            claim_num = m_num.group(1) if m_num else ""
            raw_item = re.sub(r"^\d+\. ", "", s)
            # MB 2026-08-05: claims render WITHOUT the type badge and WITHOUT
            # the SOURCE speaker chip — only the clickable timestamp leads.
            # (Type + speaker stay in the .md SSoT; safety badges remain.)
            raw_item = re.sub(r"^\[(?:FACT|ANALYST OPINION|FORECAST|ANECDOTE|CLAIM)\] ", "", raw_item)
            m_src = re.match(r"^\[SOURCE [^\]]*? @ (\d{1,2}:\d{2}(?::\d{2})?)\] ", raw_item)
            ts_link = ""
            if m_src:
                ts_link = _ts_link(m_src.group(1))
                raw_item = raw_item[m_src.end():]
            else:
                raw_item = re.sub(r"^\[SOURCE [^\]]*\] ", "", raw_item)
            # R2 + MB 2026-08-06: "(stated)" hidden; inference hoisted to the
            # LINE START as an English badge so the reader sees it before the text.
            inferred = "(inferred)" in raw_item
            raw_item = raw_item.replace("(inferred) ", "").replace("(inferred)", "")
            raw_item = raw_item.replace("(stated) ", "").replace("(stated)", "")
            inf_badge = '<span class="badge t-warn">AI-inferred</span> ' if inferred else ""
            key_html = inf_badge + _inline(raw_item)
            quotes = []
            while i + 1 < len(body) and body[i + 1].strip().startswith("- quote:"):
                i += 1
                raw_q = body[i].strip()[2:]
                tick = "" if "[UNVERIFIED-QUOTE]" in raw_q else ' <span class="qok">✓</span>'
                quotes.append(f"{_inline(raw_q)}{tick}")
            if is_kc:
                # MB 2026-08-06: two columns — key (with its number) left,
                # timestamp+quote right.
                num_html = f'<span class="cnum">{claim_num}.</span> ' if claim_num else ""
                right = (f"{ts_link} " if ts_link else "") + " ".join(
                    f'<span class="q">{q}</span>' for q in quotes)
                out.append(f'<li><div class="ck">{num_html}{key_html}</div>'
                           f'<div class="cq">{right}</div></li>')
            else:
                # Value-Investing Lens (MB 2026-08-06): key on top, the
                # timestamp+link leads the quote line below — not the key.
                if quotes:
                    lead = f"{ts_link} " if ts_link else ""
                    qhtml = f'<div class="q">{lead}{quotes[0]}</div>' + "".join(
                        f'<div class="q">{q}</div>' for q in quotes[1:])
                elif ts_link:
                    qhtml = f'<div class="q">{ts_link}</div>'
                else:
                    qhtml = ""
                out.append(f"<li>{key_html}{qhtml}</li>")
        elif bb_open and re.match(r"^\*\*(Bull|Bear|Catalysts|Risks):\*\*$", s):
            # MB 2026-08-06: place each sub-block in the 2x2 grid so
            # Bull|Catalysts (row 3) and Bear|Risks (row 4) align.
            close_all()
            if bb_cell_open:
                out.append("</div>")
            label = re.match(r"^\*\*(Bull|Bear|Catalysts|Risks):\*\*$", s).group(1)
            col, row = _BB_PLACE[label]
            out.append(f'<div class="bcell" style="grid-column:{col};grid-row:{row}">'
                       f'<b>{label}:</b>')
            bb_cell_open = True
        elif s.startswith("- "):
            flush_table()
            if list_open != "ul":
                close_list()
                out.append("<ul>")
                list_open = "ul"
            out.append(f"<li>{_inline(s[2:])}</li>")
        elif s == "":
            close_all()
        else:
            close_all()
            # MB 2026-08-06: the tone verdict renders as a bold colored pill.
            m_tone = (re.match(r"\*\*Read:\*\* (\w+) \((.+)\)$", s)
                      if cur_h2.startswith("Management Tone") else None)
            if m_tone:
                label = m_tone.group(1).upper()
                cls = {"BULLISH": "tone-bullish", "BEARISH": "tone-bearish",
                       "NEUTRAL": "tone-neutral"}.get(label, "tone-mixed")
                out.append(f'<p><strong>Read:</strong> <span class="tone {cls}">{html.escape(label)}</span> '
                           f'<span class="subx">({html.escape(m_tone.group(2))})</span></p>')
            else:
                out.append(f"<p>{_inline(s)}</p>")
        i += 1
    close_all()
    if lens_card_open:
        out.append("</div>")
    if lensgrid_open:
        out.append("</div>")
    if bb_cell_open:
        out.append("</div>")
    if bb_open:
        out.append("</div>")
    if exec_open:
        out.append("</div>")
    if rich_open:
        out.append("</div></details>")
    close_details()

    stamp = time.strftime("%Y-%m-%d %H:%M ICT", time.gmtime(time.time() + 7 * 3600))
    doc = (
        "<!DOCTYPE html>\n<html lang=\"th\" data-theme=\"dark\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{html.escape(title)}</title>\n<style>{_CSS}</style>\n</head>\n<body>\n"
        "<div id=\"themeToggle\" title=\"สลับโหมดสว่าง/มืด\" "
        "onclick=\"var r=document.documentElement;var k=document.getElementById('tknob');"
        "var L=r.dataset.theme==='light';r.dataset.theme=L?'dark':'light';"
        "k.style.transform=L?'translateX(0)':'translateX(34px)';"
        "k.className=L?'knob-d':'knob-l';k.textContent=L?'\\u263e':'\\u2600\\ufe0e'\">"
        "<span class=\"ticon\">☾</span><span class=\"ticon\">☀︎</span>"
        "<span id=\"tknob\" class=\"knob-d\">☾</span>"
        "</div>\n"
        + "\n".join(out)
        + f"\n<footer>Source of truth: {html.escape(md_path.name)} (same folder) · rendered by "
        f"earnings-call-digest v{ENGINE_VERSION} · {stamp} · "
        "the .md is canonical — regenerate this page on any source edit.</footer>\n"
        "</body>\n</html>\n"
    )
    out_path = md_path.with_suffix(".html")
    out_path.write_text(doc, encoding="utf-8")
    return out_path


def _all_from_index() -> list[Path]:
    import json  # noqa: PLC0415

    seen: dict[str, Path] = {}
    idx = config.index_path()
    if idx.is_file():
        for line in idx.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            p = Path(str(row.get("path", "")))
            if row.get("analysis_status") == "ok" and p.suffix == ".md" and p.is_file():
                seen[row["video_id"]] = p
    return list(seen.values())


def main() -> int:
    args = sys.argv[1:]
    paths = _all_from_index() if args == ["--all"] else [Path(a) for a in args]
    if not paths:
        print("no KB files given (or --all found none)")
        return 8
    for p in paths:
        if not p.is_file():
            print(f"missing: {p}")
            return 8
        outp = convert(p)
        print(f"rendered: {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
