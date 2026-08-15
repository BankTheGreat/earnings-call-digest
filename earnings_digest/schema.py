"""AnalysisResult validation — structural + semantic + derivation checks.

INVERTER killer F3: a schema-valid but FABRICATED analysis must not land as
complete. The mechanical derivation guard is quote verification — every
fact-type claim and every number must anchor to text that actually exists in
the normalized transcript (whitespace-normalized substring). Failures are
marked per-item; above QUOTE_FAIL_RATIO the whole result is rejected.

No external jsonschema dependency — explicit checks (they carry the semantic
rules a schema cannot express anyway).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .transcript import parse_ts

CLAIM_TYPES = {"fact", "opinion", "forecast", "anecdote"}
BASIS_VALUES = {"stated", "inferred"}
ENTITY_ROLES = {"subject", "peer", "supplier", "customer", "competitor", "mentioned"}
TONE_LABELS = {"bullish", "neutral", "defensive", "mixed"}
QUOTE_FAIL_RATIO = 0.30  # > this fraction of failed quote checks -> hard reject
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9&-]{0,11}\.[A-Z]{1,8}$")

# REQ-011: value-investing lens groups — claim-shaped, same anchoring rules.
LENS_KEYS = (
    "moat_durability",
    "management_quality",
    "unit_economics",
    "risk_inversion",
)

_LIST_KEYS = (
    "summary",
    "entities",
    "claims",
    "numbers",
    "bull",
    "bear",
    "catalysts",
    "risks",
    "open_questions",
)

_KNOWN_KEYS = set(_LIST_KEYS) | {"value_lens", "management_tone"}


@dataclass
class ValidationReport:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    claim_count: int = 0
    quote_fail_count: int = 0


def _norm_for_match(text: str) -> str:
    """Whitespace-insensitive, case-insensitive normal form for substring
    anchoring. Thai has no spaces — removal makes matching robust for both."""
    return re.sub(r"\s+", "", text or "").lower()


def _check_ts(value, duration_s: int, where: str, rep: ValidationReport) -> None:
    if value in (None, ""):
        return
    secs = parse_ts(str(value))
    if secs is None:
        rep.errors.append(f"{where}: timestamp {value!r} is not MM:SS / H:MM:SS")
    elif duration_s and secs > duration_s + 90:
        rep.errors.append(
            f"{where}: timestamp {value} exceeds video duration ({duration_s}s)"
        )


def _validate_claim_items(
    seq, label: str, haystack: str, duration_s: int, rep: ValidationReport
) -> list[dict]:
    """Shared claim validator (F3 core) — used by claims[] AND every REQ-011
    value_lens group so the lens obeys the identical anchoring rules."""
    items = []
    for i, c in enumerate(seq or []):
        where = f"{label}[{i}]"
        if not isinstance(c, dict) or not str(c.get("text", "")).strip():
            rep.errors.append(f"{where}: missing text")
            continue
        claim = {
            "text": str(c["text"]).strip(),
            "type": str(c.get("type", "")).strip().lower(),
            "speaker": str(c.get("speaker") or "speaker").strip(),
            "ts": str(c.get("ts") or "").strip(),
            "basis": str(c.get("basis", "stated")).strip().lower(),
            "quote": str(c.get("quote") or "").strip(),
            "verification": "unverified",
        }
        if claim["type"] not in CLAIM_TYPES:
            rep.errors.append(
                f"{where}: type {claim['type']!r} not in {sorted(CLAIM_TYPES)}"
            )
        if claim["basis"] not in BASIS_VALUES:
            rep.warnings.append(f"{where}: basis {claim['basis']!r} -> 'stated'")
            claim["basis"] = "stated"
        _check_ts(claim["ts"], duration_s, f"{where}.ts", rep)

        if claim["type"] == "fact" and not claim["quote"]:
            rep.errors.append(
                f"{where}: fact-type claim requires a short verbatim quote from the transcript"
            )
        if claim["quote"]:
            if _norm_for_match(claim["quote"]) in haystack:
                claim["verification"] = "quote_verified"
            else:
                claim["verification"] = "quote_not_found"
                rep.quote_fail_count += 1
        rep.claim_count += 1
        items.append(claim)
    return items


def _require_str_list(analysis: dict, key: str, rep: ValidationReport) -> list[str]:
    val = analysis.get(key)
    if val is None:
        return []
    if not isinstance(val, list) or any(not isinstance(x, str) for x in val):
        rep.errors.append(f"{key}: must be a list of strings")
        return []
    return [x.strip() for x in val if x.strip()]


def validate(
    analysis: dict,
    transcript_text: str,
    duration_s: int,
) -> tuple[dict, ValidationReport]:
    """Return (normalized_analysis, report). Normalized dict has every group
    present, enums lower-cased, per-item verification marks applied."""
    rep = ValidationReport()
    if not isinstance(analysis, dict):
        rep.ok = False
        rep.errors.append("top level: not a JSON object")
        return {}, rep

    unknown = set(analysis) - _KNOWN_KEYS
    for k in sorted(unknown):
        rep.warnings.append(f"unknown top-level key ignored: {k}")

    haystack = _norm_for_match(transcript_text)
    norm: dict = {}

    norm["summary"] = _require_str_list(analysis, "summary", rep)

    # entities[]
    entities = []
    for i, e in enumerate(analysis.get("entities") or []):
        if not isinstance(e, dict) or not str(e.get("company", "")).strip():
            rep.errors.append(f"entities[{i}]: missing company")
            continue
        ent = {
            "company": str(e["company"]).strip(),
            "ticker": None,
            "exchange": (str(e["exchange"]).strip().upper() or None) if e.get("exchange") else None,
            "role": str(e.get("role", "mentioned")).strip().lower(),
            "confidence": e.get("confidence"),
            "evidence_ts": [str(t) for t in (e.get("evidence_ts") or [])],
        }
        raw_ticker = str(e.get("ticker") or "").strip().upper()
        if raw_ticker:
            if _TICKER_RE.match(raw_ticker):
                ent["ticker"] = raw_ticker
            else:
                # Bare/malformed model ticker is NEVER trusted for filing (§3.7);
                # keep it visible as a hint, flagged.
                ent["ticker"] = None
                ent["ticker_hint_rejected"] = raw_ticker
                rep.warnings.append(
                    f"entities[{i}]: ticker {raw_ticker!r} not qualified BASE.SUFFIX — demoted to hint"
                )
        if ent["role"] not in ENTITY_ROLES:
            rep.warnings.append(f"entities[{i}]: unknown role {ent['role']!r} -> 'mentioned'")
            ent["role"] = "mentioned"
        c = ent["confidence"]
        if c is None:
            ent["confidence"] = 0.5
        elif not isinstance(c, (int, float)) or not (0.0 <= float(c) <= 1.0):
            rep.errors.append(f"entities[{i}]: confidence {c!r} outside [0,1]")
        for t in ent["evidence_ts"]:
            _check_ts(t, duration_s, f"entities[{i}].evidence_ts", rep)
        entities.append(ent)
    norm["entities"] = entities

    # claims[] — the F3 quote-verification core (shared with the REQ-011 lens).
    norm["claims"] = _validate_claim_items(
        analysis.get("claims"), "claims", haystack, duration_s, rep
    )

    # value_lens{} — REQ-011: four claim-shaped groups, same anchoring machine.
    lens_in = analysis.get("value_lens")
    lens_norm: dict = {}
    if lens_in is not None and not isinstance(lens_in, dict):
        rep.errors.append("value_lens: must be an object of lens-name -> claim list")
    elif isinstance(lens_in, dict):
        for k in sorted(set(lens_in) - set(LENS_KEYS)):
            rep.warnings.append(f"value_lens: unknown lens ignored: {k}")
        for key in LENS_KEYS:
            items = lens_in.get(key)
            if items:
                lens_norm[key] = _validate_claim_items(
                    items, f"value_lens.{key}", haystack, duration_s, rep
                )
    norm["value_lens"] = lens_norm

    # management_tone — REQ-011: labeled inference; quotes still anchored.
    tone_in = analysis.get("management_tone")
    tone_norm = None
    if tone_in is not None:
        if not isinstance(tone_in, dict):
            rep.errors.append("management_tone: must be an object")
        else:
            label = str(tone_in.get("label") or "").strip().lower()
            if label and label not in TONE_LABELS:
                rep.warnings.append(
                    f"management_tone: label {label!r} not in {sorted(TONE_LABELS)} -> 'mixed'"
                )
                label = "mixed"
            quotes = []
            for j, q in enumerate(tone_in.get("quotes") or []):
                # Idempotent re-validation (rerender lesson 2026-08-05): our own
                # normalized shape stores {"quote", "verification"} objects —
                # accept both, or a round-trip miscounts every tone quote.
                if isinstance(q, dict):
                    q = q.get("quote")
                # SEQUENTIAL, not elif (double-poison lesson): a poisoned repr
                # can sit INSIDE the dict's quote field — unwrap dict first,
                # then heal a str(dict) left by the pre-fix round-trip.
                if isinstance(q, str) and q.startswith("{'quote':"):
                    try:
                        import ast  # noqa: PLC0415

                        parsed = ast.literal_eval(q)
                        if isinstance(parsed, dict):
                            q = parsed.get("quote")
                    except (ValueError, SyntaxError):
                        pass
                qs = str(q or "").strip()
                if not qs:
                    continue
                mark = "quote_verified"
                if _norm_for_match(qs) not in haystack:
                    mark = "quote_not_found"
                    rep.quote_fail_count += 1
                rep.claim_count += 1
                quotes.append({"quote": qs, "verification": mark})
            tone_norm = {
                "label": label or "mixed",
                "rationale": str(tone_in.get("rationale") or "").strip(),
                "quotes": quotes,
            }
    norm["management_tone"] = tone_norm

    # numbers[] — value_text must appear in the transcript (digit anchoring).
    numbers = []
    for i, n in enumerate(analysis.get("numbers") or []):
        if not isinstance(n, dict) or not str(n.get("value_text", "")).strip():
            rep.errors.append(f"numbers[{i}]: missing value_text")
            continue
        num = {
            "value_text": str(n["value_text"]).strip(),
            "metric": str(n.get("metric") or "").strip(),
            "period": str(n.get("period") or "").strip(),
            "unit": str(n.get("unit") or "").strip(),
            "currency": str(n.get("currency") or "").strip(),
            "ts": str(n.get("ts") or "").strip(),
            "verification": "unverified",
        }
        _check_ts(num["ts"], duration_s, f"numbers[{i}].ts", rep)
        digits = re.sub(r"[^0-9.]", "", num["value_text"])
        if digits and re.sub(r"\s+", "", digits) in re.sub(r"[^0-9.]", "", transcript_text):
            num["verification"] = "quote_verified"
        elif _norm_for_match(num["value_text"]) in haystack:
            num["verification"] = "quote_verified"
        else:
            num["verification"] = "quote_not_found"
            rep.quote_fail_count += 1
        numbers.append(num)
    norm["numbers"] = numbers

    for key in ("bull", "bear", "catalysts", "risks", "open_questions"):
        norm[key] = _require_str_list(analysis, key, rep)

    # Fabrication tripwire: too many unverifiable anchors -> reject the result.
    anchored = rep.claim_count + len(numbers)
    if anchored > 0 and rep.quote_fail_count / anchored > QUOTE_FAIL_RATIO:
        rep.errors.append(
            f"fabrication suspicion: {rep.quote_fail_count}/{anchored} quote checks "
            f"failed (> {int(QUOTE_FAIL_RATIO * 100)}%) — analysis rejected; "
            "the analyzer must quote the transcript verbatim"
        )

    if not norm["summary"] and not rep.errors:
        rep.errors.append("summary: empty — at least one summary bullet required")

    rep.ok = not rep.errors
    return norm, rep
