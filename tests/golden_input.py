"""Shared deterministic inputs for the render golden test (and its generator).
Every value is FIXED — no clocks, no environment — so render output is
byte-stable across machines and runs. All identifiers below are synthetic
test fixtures."""
from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"

RUN_ID_FIXTURE = "rk-test-fixture-01"


def golden_transcript() -> str:
    return (FIXTURES / "expected_transcript.txt").read_text(encoding="utf-8")


def golden_front() -> dict:
    return {
        "schema_version": 1,
        "prompt_version": "stock-video-v1.0",
        "revision": 1,
        "run_id": RUN_ID_FIXTURE,
        "video_id": "dQw4w9WgXcQ",
        "source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "video_title": "PTT Oppday Q2 2026",
        "channel": "SET Thailand",
        "published": "2026-07-15",
        "duration_s": 150,
        "language": "th",
        "track_kind": "auto",
        "transcript_kind": "captions_auto",
        "is_verbatim_source": True,
        "transcript_status": "ok",
        "transcript_sha256": "feedface" * 8,
        "acquisition_method": "yt_dlp",
        "tickers": ["PTT.BK"],
        "entities_unresolved": ["Some Unlisted Co"],
        "ticker_source": "user",
        "ticker_confidence": "user-confirmed",
        "analysis_status": "ok",
        "analysis_date": "2026-08-04T22:00:00+07:00",
        "summary_mode": "session",
        "summary_model": "claude-opus-5",
        "summary_cost_usd": 0.0,
        "sanitize_flags": 0,
        "quote_unverified_count": 0,
        "fetched_at": "2026-08-04T21:55:00+07:00",
        "cache_path": "C:/cache/dQw4w9WgXcQ",
    }


def golden_analysis_raw() -> dict:
    return {
        "summary": [
            "ผู้บริหาร PTT รายงานรายได้ 100,000 ล้านบาท",
            "Profit growth of 15 percent stated for the period",
        ],
        "entities": [
            {
                "company": "PTT",
                "ticker": "PTT.BK",
                "exchange": "SET",
                "role": "subject",
                "confidence": 0.95,
                "evidence_ts": ["00:05"],
            },
            {
                "company": "Some Unlisted Co",
                "role": "mentioned",
                "confidence": 0.4,
                "evidence_ts": [],
            },
        ],
        "claims": [
            {
                "text": "Revenue of 100,000 M.Baht was reported",
                "type": "fact",
                "speaker": "ผู้บริหาร",
                "ts": "01:05",
                "basis": "stated",
                "quote": "รายได้ 100,000 ล้านบาท",
            },
            {
                "text": "Profit grew 15 percent",
                "type": "fact",
                "speaker": "ผู้บริหาร",
                "ts": "02:05",
                "basis": "stated",
                "quote": "กำไรโต 15 เปอร์เซ็นต์",
            },
        ],
        "numbers": [
            {
                "value_text": "100,000 ล้านบาท",
                "metric": "revenue",
                "period": "Q2 2026",
                "unit": "M.Baht",
                "currency": "THB",
                "ts": "01:05",
            }
        ],
        "bull": ["Revenue base is large and growing"],
        "bear": ["Growth rate may not persist"],
        "catalysts": ["Next quarterly report"],
        "risks": ["Auto-caption numbers unverified against filings"],
        "open_questions": ["Verify 100,000 M.Baht revenue against the audited filing"],
    }
