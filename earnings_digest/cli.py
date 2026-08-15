"""earnings_digest CLI — the one engine behind every front door.

Subcommands:
  run       <url> [--ticker T.Q] [--engine api|session] [--force] [--max-spend X]
            [--langs th,en] [--transcript-file P] [--model ID] [--vendor V] [--no-polish]
  fetch     <url> [--ticker T.Q] [--force] ...      (phase 1 only — skill mode A)
  finalize  <video_id> --analysis-json P [--polish-file P] [--summary-model M]
            [--summary-mode session|api]
  refile    <video_id> --ticker T.Q
  index     [--rebuild]
  --selftest-unicode

Exit codes: 0 ok/stub/skip · 2 kill switch · 3 ticker · 4 URL · 5 live ·
6 network · 7 cost gate · 8 validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# UTF-8 stdio BEFORE anything can print (Windows consoles default to a cp codepage).
if __package__ in (None, ""):
    _here = Path(__file__).resolve().parent
    sys.path.insert(0, str(_here.parent))
    __package__ = "earnings_digest"

from earnings_digest import ENGINE_VERSION, config  # noqa: E402
config.pin_utf8()

from earnings_digest import (  # noqa: E402
    fetch as fetch_mod,
    grounding,
    polish,
    render,
    sanitize as sanitize_mod,
    schema,
    summarize,
    tickers,
    transcript as transcript_mod,
    watcher,
    writer,
)
from earnings_digest.video_url import UrlError, canonical_url, parse_video_id  # noqa: E402


def run_id_for(video_id: str, transcript_sha: str) -> str:
    raw = f"{video_id}|{transcript_sha}|{config.PROMPT_VERSION}|{config.SCHEMA_VERSION}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _kind_labels(track_kind: str) -> tuple[str, bool]:
    return {
        "manual": ("captions_manual", True),
        "auto": ("captions_auto", True),
        "user": ("user_supplied", True),
    }.get(track_kind, ("none", False))


_PERIOD_RE = re.compile(r"\bQ([1-4])\s*/\s*(\d{4})\b")
_COMPANY_RE = re.compile(r"บมจ\.\s*([^|\-–(]{2,60})")


def extract_period(title: str | None) -> str | None:
    """D2: 'Q2/2026' from an OppDay title; None when absent (never guessed)."""
    m = _PERIOD_RE.search(title or "")
    return f"Q{m.group(1)}/{m.group(2)}" if m else None


def extract_company(title: str | None, analysis: dict | None) -> str | None:
    """D3: subject entity name first (validated data), title 'บมจ. X' fallback."""
    for e in (analysis or {}).get("entities", []) or []:
        if e.get("role") == "subject" and e.get("company"):
            return str(e["company"]).strip()
    m = _COMPANY_RE.search(title or "")
    return f"บมจ. {m.group(1).strip()}" if m else None


def build_front(meta: dict, revision: int, run_id: str, analysis_status: str,
                summary_mode: str | None, summary_model: str | None,
                cost_usd: float, quote_unverified: int,
                entities_unresolved: list[str],
                polish_status: str | None = None,
                anchored_total: int | None = None,
                analysis: dict | None = None) -> dict:
    m = meta.get("meta", {})
    track = meta.get("track", {})
    kind, verbatim = _kind_labels(track.get("kind", "none"))
    t = meta.get("ticker") or {}
    return {
        "schema_version": config.SCHEMA_VERSION,
        "prompt_version": meta.get("prompt_version", config.PROMPT_VERSION),
        "revision": revision,
        "run_id": run_id,
        "video_id": meta["video_id"],
        "source_url": meta.get("source_url", canonical_url(meta["video_id"])),
        "video_title": m.get("video_title") or "",
        "channel": m.get("channel") or "",
        "published": m.get("published"),
        "duration_s": m.get("duration_s") or 0,
        "language": track.get("lang"),
        "track_kind": track.get("kind", "none"),
        "transcript_kind": kind,
        "is_verbatim_source": verbatim,
        "transcript_status": meta.get("transcript_status", "none"),
        "transcript_sha256": meta.get("transcript_sha256"),
        "acquisition_method": meta.get("acquisition_method", "none"),
        "tickers": [t["qualified"]] if t.get("qualified") else [],
        "period": extract_period(m.get("video_title")),
        "company_name": extract_company(m.get("video_title"), analysis),
        "anchored_total": anchored_total,
        "entities_unresolved": entities_unresolved,
        "ticker_source": t.get("source", "none"),
        "ticker_confidence": t.get("confidence", "unresolved"),
        "analysis_status": analysis_status,
        "analysis_date": writer.now_ict(),
        "polish_status": polish_status,
        "summary_mode": summary_mode,
        "summary_model": summary_model,
        "summary_cost_usd": round(cost_usd, 4),
        "sanitize_flags": meta.get("sanitize_flags", 0),
        "quote_unverified_count": quote_unverified,
        "fetched_at": meta.get("fetched_at"),
        "cache_path": str(writer.cache_dir(meta["video_id"])),
    }


def index_row_from_front(front: dict, path: Path) -> dict:
    return {
        "video_id": front["video_id"],
        "run_id": front["run_id"],
        "revision": front["revision"],
        "path": str(path),
        "tickers": front["tickers"],
        "published": front["published"],
        "title": front["video_title"],
        "channel": front["channel"],
        "transcript_status": front["transcript_status"],
        "analysis_status": front["analysis_status"],
        # dashboard fields — kept in lockstep with writer.index_rebuild.
        "period": front.get("period"),
        "company_name": front.get("company_name"),
        "anchored_total": front.get("anchored_total"),
        "quote_unverified_count": front.get("quote_unverified_count"),
        "polish_status": front.get("polish_status"),
        "duration_s": front.get("duration_s"),
        # REQ-G grounding fields (+_status honesty: null name ≠ absent doc).
        "grounding_slide": front.get("grounding_slide"),
        "grounding_slide_status": front.get("grounding_slide_status"),
        "grounding_mda": front.get("grounding_mda"),
        "grounding_mda_status": front.get("grounding_mda_status"),
        "doc_checked_total": front.get("doc_checked_total"),
        "doc_confirmed_total": front.get("doc_confirmed_total"),
        "at": writer.now_ict(),
    }


def _resolve_url(args) -> str:
    """Return an explicit YouTube URL. If --url was given, use it verbatim.
    Otherwise discover it from --ticker + --quarter (NEVER-GUESS: an ambiguous
    or empty search prints candidates and aborts — it never auto-files)."""
    if args.url:
        return args.url
    quarter = getattr(args, "quarter", None)
    if not (args.ticker and quarter):
        raise UrlError(
            "missing", "provide a YouTube URL, or both --ticker and --quarter "
            "for best-effort discovery (e.g. --ticker TU.BK --quarter Q2/2026)"
        )
    base, _suf = tickers.split_ticker(args.ticker)
    try:
        cand = watcher.discover(base, quarter)
    except ValueError as exc:  # bad --quarter format
        raise UrlError("missing", str(exc)) from None
    print(
        f"discovered: {cand.title[:80]}\n"
        f"  channel: {cand.channel}  ·  {cand.url}"
    )
    return cand.url


def stage(args) -> tuple[dict, str | None, int] | None:
    """Phase 1: fetch -> normalize -> sanitize -> cache + KB stub + index.
    Returns (meta, raw_transcript_text_or_None, exit_code_zero) or None on
    SKIP. Raises typed errors mapped by main()."""
    video_id = parse_video_id(_resolve_url(args))

    qualified = None
    if args.ticker:
        qualified = tickers.require_qualified(args.ticker)
        known = writer.known_kb_tickers()
        cols = tickers.collisions(qualified, known)
        if cols:
            print(
                f"note: base collides with existing KB listing(s) {', '.join(cols)} — "
                f"filing under {qualified} as given (distinct listings coexist)."
            )

    # Idempotency (run-key aware once a transcript hash exists).
    existing_meta = writer.load_meta(video_id)
    if existing_meta and not args.force:
        tsha = existing_meta.get("transcript_sha256") or ""
        rk = run_id_for(video_id, tsha)
        done = any(
            r.get("run_id") == rk and r.get("analysis_status") == "ok"
            for r in existing_meta.get("revisions", [])
        )
        if done:
            paths = writer.find_kb_files(video_id)
            where = str(paths[0]) if paths else "(KB file not found — run index --rebuild)"
            print(f"SKIP: {video_id} already in KB at {where} — use --force to redo")
            return None

    reuse = (
        existing_meta is not None
        and writer.transcript_path(video_id).is_file()
        and not args.force
        and not args.transcript_file
        and existing_meta.get("transcript_status") == "ok"
    )
    if reuse:
        meta = existing_meta
        raw_text = writer.transcript_path(video_id).read_text(encoding="utf-8")
        print(f"cache hit: reusing transcript for {video_id} "
              f"({meta.get('acquisition_method')}, {meta.get('track', {}).get('kind')})")
    else:
        langs = [x.strip() for x in (args.langs or "").split(",") if x.strip()] or None
        result = fetch_mod.fetch_video(video_id, langs, args.transcript_file)
        meta = existing_meta or {}
        meta.update(
            {
                "video_id": video_id,
                "source_url": canonical_url(video_id),
                "fetched_at": writer.now_ict(),
                "meta": result.meta or meta.get("meta") or {},
                "track": {
                    "kind": result.track.kind,
                    "lang": result.track.lang,
                    "fmt": result.track.fmt,
                },
                "acquisition_method": result.acquisition_method,
                "prompt_version": config.PROMPT_VERSION,
                "schema_version": config.SCHEMA_VERSION,
            }
        )
        meta.setdefault("revisions", [])

        if result.track.kind == "none":
            meta["transcript_status"] = "none" if "no captions" in (result.error or "") else "error"
            meta["transcript_error"] = result.error
            meta["transcript_sha256"] = None
            meta["sanitize_flags"] = 0
            raw_text = None
        else:
            segments = transcript_mod.dedupe(
                transcript_mod.normalize(result.track.fmt, result.track.content or "")
            )
            raw_text = transcript_mod.render_transcript(segments)
            meta["transcript_status"] = "ok"
            meta["transcript_sha256"] = transcript_mod.transcript_sha256(raw_text)
            clean, flags, hits = sanitize_mod.sanitize(raw_text)
            meta["sanitize_flags"] = flags
            sanitize_mod.log_hits(video_id, meta["source_url"], hits)
            writer.atomic_write(writer.transcript_path(video_id), raw_text)
            writer.atomic_write(writer.sanitized_path(video_id), clean)
            if not meta["meta"].get("duration_s") and segments:
                meta["meta"]["duration_s"] = int(segments[-1][0]) + 30

    if qualified:
        meta["ticker"] = {
            "qualified": qualified,
            "source": "user",
            "confidence": "user-confirmed",
        }
        meta["ticker_shim_sha256"] = tickers.SHIM_SHA256
    meta.setdefault("ticker", {"qualified": None, "source": "none", "confidence": "unresolved"})

    writer.save_meta(video_id, meta)

    # KB stub (phase 1) — analysis pending/skipped; render + index it so even a
    # captionless attempt is recorded knowledge.
    status = "pending" if meta.get("transcript_status") == "ok" else "skipped"
    tsha = meta.get("transcript_sha256") or ""
    rk = run_id_for(video_id, tsha)
    revs = writer.existing_revisions(video_id)
    front = build_front(meta, (revs[-1] if revs else 0), rk, status, None, None, 0.0, 0, [])
    content = render.render_kb(front, None, raw_text)
    path, warnings = writer.write_kb_render(
        meta["ticker"].get("qualified"),
        front["published"],
        video_id,
        front["video_title"],
        content,
        prior_revision=None,
    )
    writer.index_append(index_row_from_front(front, path))
    for w in warnings:
        print(f"note: {w}")
    print(f"staged: {path}")
    if meta.get("transcript_status") != "ok":
        print(f"transcript unavailable ({meta.get('transcript_error')}) — recorded as stub")
    return meta, raw_text, 0


def _render_html(md_path: Path):
    """Emit the TU-parity HTML next to the .md (fail-open: a render error never
    loses the canonical .md — it just prints a note)."""
    try:
        from earnings_digest import render_kb_html  # noqa: PLC0415

        return render_kb_html.convert(md_path)
    except Exception as exc:  # noqa: BLE001 — HTML is a convenience surface
        print(f"note: HTML render skipped ({type(exc).__name__}: {str(exc)[:120]})")
        return None


def finalize_common(meta: dict, raw_text: str, analysis_raw: dict,
                    summary_mode: str, summary_model: str | None,
                    cost_usd: float,
                    polish_text: str | None = None,
                    slide_path: str | None = None,
                    mda_path: str | None = None) -> tuple[Path, schema.ValidationReport]:
    """Validate -> revision -> render -> KB write -> meta + index update.
    REQ-012: polish is gate-checked here; failure DEGRADES (polish_status:
    failed), it never blocks the analysis or the KB render."""
    video_id = meta["video_id"]
    duration = int(meta.get("meta", {}).get("duration_s") or 0)
    normalized, report = schema.validate(analysis_raw, raw_text, duration)
    if not report.ok:
        raise SchemaReject(report)

    polished = None
    polish_status = None
    if polish_text is not None:
        prep = polish.validate_polish(raw_text, polish_text)
        if prep.ok:
            polished = polish_text
            polish_status = "ok"
        else:
            polish_status = "failed"
            for e in prep.errors:
                print(f"  polish gate: {e}")
            print("  polish REJECTED — KB renders analysis + verbatim only (REQ-012 degrade)")

    with writer.video_lock(video_id):
        revision = writer.next_revision(video_id)
        writer.atomic_write(
            writer.analysis_path(video_id, revision),
            json.dumps(normalized, ensure_ascii=False, indent=2),
        )
        if polished:
            # D0: gate-passed polish becomes a cache artifact so rerenders
            # never lose it (it used to live only inside the KB render).
            writer.atomic_write(writer.polish_path(video_id, revision), polished)
        rk = run_id_for(video_id, meta.get("transcript_sha256") or "")

        # Fold validated entity tickers (qualified only) into the ticker list.
        extra = []
        unresolved = []
        for e in normalized.get("entities", []):
            if e.get("ticker"):
                try:
                    extra.append(tickers.canonicalize(e["ticker"]))
                except tickers.TickerError:
                    unresolved.append(e["company"])
            elif e.get("role") in ("subject", "peer", "competitor"):
                unresolved.append(e["company"])

        # Grounding: user supplies slide/MD&A PDFs explicitly (no corpus scan).
        g_slide, g_mda = grounding.locate(slide_path, mda_path)
        grounding.extract_text(g_slide)
        grounding.extract_text(g_mda)
        g_rep = grounding.cross_check(normalized.get("numbers") or [], g_slide, g_mda)
        for n, verdict in zip(normalized.get("numbers") or [], g_rep.per_number):
            n["doc_check"] = verdict
        for hit in (g_slide, g_mda):
            if hit.status not in ("found",):
                print(f"  grounding {hit.kind}: {hit.status}" + (f" — {hit.detail}" if hit.detail else ""))

        anchored_total = report.claim_count + len(normalized.get("numbers") or [])
        front = build_front(
            meta, revision, rk, "ok", summary_mode, summary_model,
            cost_usd, report.quote_fail_count, sorted(set(unresolved)),
            polish_status=polish_status,
            anchored_total=anchored_total,
            analysis=normalized,
        )
        front.update(grounding.front_fields(g_slide, g_mda, g_rep))
        front["doc_checked_total"] = g_rep.checked_total
        front["doc_confirmed_total"] = g_rep.confirmed_total
        primary = meta.get("ticker", {}).get("qualified")
        merged = ([primary] if primary else []) + [t for t in extra if t != primary]
        front["tickers"] = list(dict.fromkeys(merged))

        content = render.render_kb(front, normalized, raw_text, polished)
        prior = revision - 1 if revision > 1 else None
        path, warnings = writer.write_kb_render(
            primary, front["published"], video_id, front["video_title"], content, prior
        )
        meta.setdefault("revisions", []).append(
            {
                "revision": revision,
                "run_id": rk,
                "at": writer.now_ict(),
                "mode": summary_mode,
                "model": summary_model,
                "cost_usd": round(cost_usd, 4),
                "analysis_status": "ok",
                "quote_unverified": report.quote_fail_count,
                "polish_status": polish_status,
            }
        )
        writer.save_meta(video_id, meta)
        writer.index_append(index_row_from_front(front, path))
    html_path = _render_html(path)
    for w in warnings:
        print(f"note: {w}")
    if html_path:
        print(f"HTML: {html_path}")
    return path, report


class SchemaReject(RuntimeError):
    def __init__(self, report: schema.ValidationReport):
        super().__init__("analysis rejected by schema validation")
        self.report = report


def _record_failed(meta: dict, reason: str) -> None:
    meta.setdefault("revisions", []).append(
        {
            "revision": None,
            "run_id": run_id_for(meta["video_id"], meta.get("transcript_sha256") or ""),
            "at": writer.now_ict(),
            "mode": "api",
            "analysis_status": "failed",
            "reason": reason[:500],
        }
    )
    writer.save_meta(meta["video_id"], meta)


def cmd_run(args) -> int:
    staged = stage(args)
    if staged is None:
        return config.EXIT_OK
    meta, raw_text, _ = staged
    if meta.get("transcript_status") != "ok":
        return config.EXIT_OK  # stub recorded; nothing to analyze

    if args.engine == "session":
        polish_step = (
            ""
            if args.no_polish
            else (
                f"  3. Polish per template:       {config.POLISH_TEMPLATE_PATH}\n"
                "     (source language; keep [MM:SS] markers + every number; write to a temp .txt)\n"
            )
        )
        polish_flag = "" if args.no_polish else " --polish-file <tmp.txt>"
        print(
            "\nMODE A (session): the invoking AI harness now writes the analysis.\n"
            f"  1. Read sanitized transcript: {writer.sanitized_path(meta['video_id'])}\n"
            f"  2. Follow persona template:   {config.TEMPLATE_PATH}\n"
            f"{polish_step}"
            "  4. Write AnalysisResult JSON to a temp file\n"
            f"  5. py -3 {Path(__file__).resolve()} finalize {meta['video_id']} "
            f"--analysis-json <tmp.json>{polish_flag} "
            "--summary-mode session --summary-model <model-id>"
        )
        return config.EXIT_OK

    sanitized = writer.sanitized_path(meta["video_id"]).read_text(encoding="utf-8")
    ticker_hint = meta.get("ticker", {}).get("qualified")
    try:
        analysis_raw, cost, model = summarize.run_api(
            {**meta.get("meta", {}), "duration_s": meta.get("meta", {}).get("duration_s")},
            ticker_hint,
            sanitized,
            vendor=args.vendor,
            model=args.model,
            max_spend=args.max_spend,
        )
    except summarize.CostGateError as exc:
        print(f"COST GATE: {exc}")
        return config.EXIT_COST_GATE
    except summarize.SummarizeError as exc:
        print(f"analysis failed: {exc} — transcript kept, analysis_status: failed")
        _record_failed(meta, str(exc))
        return config.EXIT_OK

    polish_text = None
    polish_cost = 0.0
    if not args.no_polish:
        try:
            polish_text, polish_cost, _ = summarize.run_polish(
                sanitized,
                vendor=args.vendor,
                model=args.model,
                max_spend=args.max_spend,
                spent_usd=cost,
            )
        except (summarize.CostGateError, summarize.SummarizeError) as exc:
            print(f"polish skipped: {exc} — continuing without polish (REQ-012 degrade)")

    try:
        path, report = finalize_common(
            meta, raw_text, analysis_raw, "api", model, cost + polish_cost,
            polish_text=polish_text,
            slide_path=getattr(args, "slide", None),
            mda_path=getattr(args, "mda", None),
        )
    except SchemaReject as exc:
        for e in exc.report.errors:
            print(f"  validation: {e}")
        print("analysis rejected — transcript kept, analysis_status: failed")
        _record_failed(meta, "; ".join(exc.report.errors))
        return config.EXIT_OK

    for w in report.warnings:
        print(f"  warning: {w}")
    print(f"DONE: {path}")
    return config.EXIT_OK


def cmd_fetch(args) -> int:
    staged = stage(args)
    if staged is None:
        return config.EXIT_OK
    meta, _, _ = staged
    if meta.get("transcript_status") == "ok":
        print(
            "\nNEXT (mode A):\n"
            f"  sanitized: {writer.sanitized_path(meta['video_id'])}\n"
            f"  template:  {config.TEMPLATE_PATH}\n"
            f"  finalize:  py -3 {Path(__file__).resolve()} finalize {meta['video_id']} "
            "--analysis-json <tmp.json> --summary-mode session --summary-model <model-id>"
        )
    return config.EXIT_OK


def cmd_finalize(args) -> int:
    meta = writer.load_meta(args.video_id)
    if meta is None:
        print(f"no cache for {args.video_id} — run fetch first")
        return config.EXIT_VALIDATION
    if meta.get("transcript_status") != "ok":
        print(f"transcript_status={meta.get('transcript_status')} — nothing to finalize")
        return config.EXIT_VALIDATION
    raw_text = writer.transcript_path(args.video_id).read_text(encoding="utf-8")
    try:
        analysis_raw = json.loads(Path(args.analysis_json).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"analysis file is not valid JSON: {exc}")
        return config.EXIT_VALIDATION
    polish_text = None
    if getattr(args, "polish_file", None):
        polish_text = Path(args.polish_file).read_text(encoding="utf-8")
    try:
        path, report = finalize_common(
            meta, raw_text, analysis_raw, args.summary_mode, args.summary_model, 0.0,
            polish_text=polish_text,
            slide_path=getattr(args, "slide", None),
            mda_path=getattr(args, "mda", None),
        )
    except SchemaReject as exc:
        for e in exc.report.errors:
            print(f"  validation: {e}")
        print("REJECTED — cache preserved; fix the JSON and re-run finalize")
        return config.EXIT_VALIDATION
    for w in report.warnings:
        print(f"  warning: {w}")
    if report.quote_fail_count:
        print(f"  note: {report.quote_fail_count} quote check(s) failed — marked [UNVERIFIED-QUOTE]")
    print(f"DONE: {path}")
    return config.EXIT_OK


def cmd_refile(args) -> int:
    qualified = tickers.require_qualified(args.ticker)
    meta = writer.load_meta(args.video_id)
    if meta is None:
        print(f"no cache for {args.video_id}")
        return config.EXIT_VALIDATION
    files = writer.find_kb_files(args.video_id)
    if not files:
        print(f"no KB files found for [{args.video_id}]")
        return config.EXIT_VALIDATION
    target_dir = writer.kb_dir_for(qualified)
    target_dir.mkdir(parents=True, exist_ok=True)
    import os as _os

    moved = []
    for f in files:
        dest = target_dir / f.name
        if dest.resolve() == f.resolve():
            continue
        _os.replace(f, dest)
        moved.append(dest)
    meta["ticker"] = {"qualified": qualified, "source": "user", "confidence": "user-confirmed"}
    writer.save_meta(args.video_id, meta)
    count = writer.index_rebuild()
    for m in moved:
        print(f"moved: {m}")
    print(f"refiled under {qualified}; index rebuilt ({count} rows)")
    return config.EXIT_OK


_POLISH_HEAD = "## Polished Transcript [AI-EDITED]"
_FULL_HEAD = "## Full Transcript"


def _polish_from_kb_file(video_id: str) -> str | None:
    """Legacy recovery (pre-D0 files): lift the polished section out of the
    current KB render — the only place it lived before polish became a cache
    artifact. Returns the text without the section banner."""
    files = writer.find_kb_files(video_id)
    for f in files:
        if "(superseded r" in f.name:
            continue
        text = f.read_text(encoding="utf-8")
        if _POLISH_HEAD not in text:
            continue
        seg = text.split(_POLISH_HEAD, 1)[1]
        seg = seg.split(_FULL_HEAD, 1)[0]
        lines = [l for l in seg.splitlines() if not l.strip().startswith("> [AI-EDITED]")]
        body = "\n".join(lines).strip("\n")
        return body or None
    return None


def cmd_rerender(args) -> int:
    """D-work maintenance: re-emit KB renders from the cache SSoT via the ONE
    finalize path (mints a superseding revision). Preserves polish from
    the cache artifact, else lifts it from the current render (pre-D0)."""
    rows = writer.index_load()
    targets = [args.video_id] if args.video_id else [
        vid for vid, r in sorted(rows.items()) if r.get("analysis_status") == "ok"
    ]
    if not targets:
        print("nothing to rerender")
        return config.EXIT_OK
    for vid in targets:
        meta = writer.load_meta(vid)
        if not meta or meta.get("transcript_status") != "ok":
            print(f"{vid}: no ok cache — skipped")
            continue
        revs = writer.existing_revisions(vid)
        if not revs:
            print(f"{vid}: no analysis revisions — skipped")
            continue
        last = revs[-1]
        analysis_raw = json.loads(
            writer.analysis_path(vid, last).read_text(encoding="utf-8")
        )
        pol_p = writer.polish_path(vid, last)
        polish_text = pol_p.read_text(encoding="utf-8") if pol_p.is_file() else _polish_from_kb_file(vid)
        raw_text = writer.transcript_path(vid).read_text(encoding="utf-8")
        last_rev = (meta.get("revisions") or [{}])[-1]
        try:
            path, report = finalize_common(
                meta, raw_text, analysis_raw,
                last_rev.get("mode") or "session",
                last_rev.get("model"),
                0.0,
                polish_text=polish_text,
                slide_path=getattr(args, "slide", None),
                mda_path=getattr(args, "mda", None),
            )
        except SchemaReject as exc:
            print(f"{vid}: rerender REJECTED — {'; '.join(exc.report.errors)[:150]}")
            continue
        print(f"rerendered: {path}")
    return config.EXIT_OK


def cmd_index(args) -> int:
    if args.rebuild:
        count = writer.index_rebuild()
        print(f"index rebuilt: {count} rows -> {config.index_path()}")
    else:
        rows = writer.index_load()
        print(f"{len(rows)} video(s) in index {config.index_path()}")
        for vid, row in sorted(rows.items()):
            print(
                f"  {vid}  r{row.get('revision')}  {','.join(row.get('tickers') or []) or '-'}  "
                f"{row.get('analysis_status')}  {row.get('title', '')[:60]}"
            )
    return config.EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="earnings_digest", description=__doc__)
    p.add_argument("--selftest-unicode", action="store_true", help="print Thai/Unicode and exit")
    sub = p.add_subparsers(dest="cmd")

    def add_stage_args(sp):
        sp.add_argument(
            "url", nargs="?", default=None,
            help="YouTube URL; omit to discover from --ticker + --quarter",
        )
        sp.add_argument("--ticker", help="qualified ticker, e.g. PTT.BK / NVDA.US")
        sp.add_argument(
            "--quarter",
            help="Q<n>/<yyyy> for URL-less discovery, e.g. Q2/2026 (best-effort)",
        )
        sp.add_argument("--force", action="store_true")
        sp.add_argument("--langs", help="comma list, default th,en")
        sp.add_argument("--transcript-file", help="user-supplied .vtt/.srt/.txt/.md")
        sp.add_argument("--out", help="output directory for renders (default ./out)")

    def add_grounding_args(sp):
        sp.add_argument("--slide", help="OppDay slide PDF to cross-check numbers against")
        sp.add_argument("--mda", help="MD&A / management-discussion PDF to cross-check")

    sp_run = sub.add_parser("run", help="end-to-end ingest")
    sp_run.add_argument(
        "--no-polish", action="store_true",
        help="skip the REQ-012 polished transcript (api mode: saves the second call)",
    )
    add_stage_args(sp_run)
    add_grounding_args(sp_run)
    sp_run.add_argument("--engine", choices=["api", "session"], default="api")
    sp_run.add_argument("--vendor", default=None)
    sp_run.add_argument("--model", default=None)
    sp_run.add_argument("--max-spend", type=float, default=None)

    sp_fetch = sub.add_parser("fetch", help="phase 1 only (mode A staging)")
    add_stage_args(sp_fetch)

    sp_fin = sub.add_parser("finalize", help="validate + render a staged analysis")
    sp_fin.add_argument("video_id")
    sp_fin.add_argument("--analysis-json", required=True)
    sp_fin.add_argument(
        "--polish-file",
        help="REQ-012 polished transcript text file (gate-checked; failure degrades)",
    )
    sp_fin.add_argument("--summary-mode", choices=["session", "api"], default="session")
    sp_fin.add_argument("--summary-model", default=None)
    sp_fin.add_argument("--out", help="output directory for renders (default ./out)")
    add_grounding_args(sp_fin)

    sp_ref = sub.add_parser("refile", help="move a video's KB files to another ticker")
    sp_ref.add_argument("video_id")
    sp_ref.add_argument("--ticker", required=True)

    sp_idx = sub.add_parser("index", help="list or rebuild the index")
    sp_idx.add_argument("--rebuild", action="store_true")

    sp_rr = sub.add_parser("rerender", help="re-emit KB renders from cache (new revision)")
    sp_rr.add_argument("video_id", nargs="?", default=None)
    sp_rr.add_argument("--out", help="output directory for renders (default ./out)")
    add_grounding_args(sp_rr)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.selftest_unicode:
        print("selftest: ไทย OK → ✓ (cp874-safe UTF-8 stdio)")
        return config.EXIT_OK

    # --out repoints renders + index to a chosen directory (config reads env
    # lazily, so setting it before dispatch is enough; cache stays ./.cache).
    out_dir = getattr(args, "out", None)
    if out_dir:
        import os as _os

        _os.environ["ECD_OUT_DIR"] = out_dir

    reason = config.kill_switch_reason()
    if reason:
        print(f"disabled by kill switch: {reason}")
        return config.EXIT_KILL_SWITCH

    if not args.cmd:
        build_parser().print_help()
        return config.EXIT_OK

    try:
        return {
            "run": cmd_run,
            "fetch": cmd_fetch,
            "finalize": cmd_finalize,
            "refile": cmd_refile,
            "rerender": cmd_rerender,
            "index": cmd_index,
        }[args.cmd](args)
    except watcher.AmbiguousError as exc:
        print(f"discovery: {exc}")
        for c in exc.candidates[:8]:
            mark = "✓" if c.confident else " "
            print(f"  [{mark}] {c.url}  {c.title[:70]}")
        print("re-run with:  run <the exact URL above> --ticker <T.Q>")
        return config.EXIT_URL
    except watcher.DiscoveryError as exc:
        print(f"discovery failed: {exc}")
        return config.EXIT_URL
    except UrlError as exc:
        code = config.EXIT_URL
        print(f"URL error ({exc.kind}): {exc}")
        return code
    except tickers.TickerError as exc:
        print(f"ticker error: {exc}")
        return config.EXIT_TICKER
    except fetch_mod.LiveVideoError as exc:
        print(f"live video: {exc}")
        return config.EXIT_LIVE
    except fetch_mod.NetworkError as exc:
        print(f"network error: {exc}")
        return config.EXIT_NETWORK
    except writer.LockBusyError as exc:
        print(f"lock busy: {exc}")
        return config.EXIT_VALIDATION


if __name__ == "__main__":
    sys.exit(main())
