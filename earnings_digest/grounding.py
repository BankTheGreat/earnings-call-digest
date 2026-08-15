"""REQ-G Phase 1 — grounding documents (OppDay slides + MD&A), MECHANICAL only.

Locates the two company-printed sources for (ticker, period), extracts their
text layer, and confirms analysis numbers by digit-token presence. No LLM, no
rescaling (presence-match only), no guessing:

  · Matching is deterministic on the corpus' own naming convention
    (`<BASE> Opp Day <YYYY>Q<N>*` · `<BASE> MD&A <YYYY>Q<N>.pdf`); zero or
    multiple candidates ⇒ recorded ABSENT with a reason — a wrong grounding
    doc is worse than none (killer risk of this feature).
  · A PDF without a text layer is reported `no_text_layer`, never OCR-guessed.
  · Presence-confirm only: `confirmed` means every digit token of the spoken
    figure appears in the document; `unmatched` means NOT FOUND — it is not a
    contradiction claim (semantic discrepancy pairing is Phase 2).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .polish import _number_multiset  # one digit-normalizer, shared with polish gates


@dataclass
class DocHit:
    kind: str                 # "slide" | "mda"
    path: Path | None
    status: str               # found | absent | ambiguous | no_text_layer | error
    detail: str = ""
    text: str = ""
    pages: int = 0


@dataclass
class GroundingReport:
    slide: DocHit | None = None
    mda: DocHit | None = None
    checked_total: int | None = None    # None ⇔ no doc had usable text (≠ 0)
    confirmed_total: int | None = None
    per_number: list[str] = field(default_factory=list)  # both|slide|mda|none per numbers[i]

    def docs_found(self) -> list[DocHit]:
        return [d for d in (self.slide, self.mda) if d and d.status == "found"]


def _period_key(period: str | None) -> tuple[str, str] | None:
    m = re.match(r"^Q([1-4])/(\d{4})$", period or "")
    return (m.group(2), m.group(1)) if m else None


def _pick_one(cands: list[Path], kind: str) -> DocHit:
    if not cands:
        return DocHit(kind, None, "absent", "no file matches the naming convention")
    if len(cands) > 1:
        names = ", ".join(p.name for p in cands[:3])
        return DocHit(kind, None, "ambiguous", f"{len(cands)} candidates: {names}")
    return DocHit(kind, cands[0], "found")


def _ticker_subdir(root: Path, base: str) -> Path | None:
    if not root.is_dir():
        return None
    hits = [d for d in root.iterdir() if d.is_dir() and d.name.upper().startswith(base.upper() + " ")]
    return hits[0] if len(hits) == 1 else None


def _match_files(dirs: list[Path | None], stem_prefix: str) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for d in dirs:
        if not d or not d.is_dir():
            continue
        for f in d.rglob("*.pdf"):
            if f.name.lower().startswith(stem_prefix.lower()) and f.name.lower().endswith(".pdf"):
                key = f.name.lower()
                if key not in seen:
                    seen.add(key)
                    out.append(f)
    return out


def locate(slide_path: str | None = None, mda_path: str | None = None) -> tuple[DocHit, DocHit]:
    """Standalone: grounding docs are supplied EXPLICITLY by the user via
    --slide / --mda. No private corpus is scanned. Absent path -> honest
    'no document supplied' (never a wrong-doc guess)."""
    def _hit(kind: str, p: str | None) -> DocHit:
        if not p:
            return DocHit(kind, None, "absent", "no document supplied")
        path = Path(p)
        if not path.is_file():
            return DocHit(kind, None, "absent", f"file not found: {p}")
        return DocHit(kind, path, "found")
    return _hit("slide", slide_path), _hit("mda", mda_path)


def extract_text(hit: DocHit, max_pages: int = 120) -> DocHit:
    """Fill hit.text from the PDF's text layer; honest failure states."""
    if hit.status != "found" or hit.path is None:
        return hit
    try:
        from pypdf import PdfReader  # noqa: PLC0415

        reader = PdfReader(str(hit.path))
        parts = []
        for page in reader.pages[:max_pages]:
            try:
                parts.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001 — one bad page never kills the doc
                parts.append("")
        hit.pages = len(reader.pages)
        hit.text = "\n".join(parts)
        if len(hit.text.strip()) < 40:
            hit.status = "no_text_layer"
            hit.detail = f"{hit.pages} pages, no extractable text (scan?)"
            hit.text = ""
    except Exception as exc:  # noqa: BLE001
        hit.status = "error"
        hit.detail = f"{type(exc).__name__}: {str(exc)[:120]}"
        hit.text = ""
    return hit


def _value_tokens(value_text: str) -> list[str]:
    return list(_number_multiset(value_text or "").keys())


def cross_check(numbers: list[dict], slide: DocHit, mda: DocHit) -> GroundingReport:
    """Presence-confirm every numbers[].value_text against each doc's tokens."""
    rep = GroundingReport(slide=slide, mda=mda)
    docs = rep.docs_found()
    if not docs:
        return rep  # checked_total stays None: nothing usable ≠ zero confirmed
    token_sets = {d.kind: set(_number_multiset(d.text).keys()) for d in docs}
    confirmed = 0
    for n in numbers or []:
        toks = _value_tokens(str(n.get("value_text") or ""))
        status = []
        for kind, ts in token_sets.items():
            if toks and all(t in ts for t in toks):
                status.append(kind)
        verdict = "both" if len(status) == 2 else (status[0] if status else "none")
        rep.per_number.append(verdict)
        if verdict != "none":
            confirmed += 1
    rep.checked_total = len(rep.per_number)
    rep.confirmed_total = confirmed
    return rep
