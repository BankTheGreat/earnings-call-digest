"""Filesystem layer: cache pair, revisions, KB render placement, index.

INVERTER mitigations implemented here:
  F1 — NEVER glob under the KB tree (filenames contain literal brackets:
       "<date> [<video_id>] <title>.md"); iterdir/scandir walks only.
  F2 — quarantine-not-delete: cloud-sync conflict copies are REPORTED, never
       unlinked (a hand-annotated human file must survive).
  F4 — single current pointer: the canonical filename IS the current revision;
       a superseded render is renamed "... (superseded rN).md", never deleted.
  F7 — per-video lockfile for revision numbering; index appends via one
       O_APPEND write.
  F10 — slug hardening (NTFS-illegal chars, trailing dots/spaces, zero-width,
        NFC) and the on-disk dirent is re-read as truth after writing.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from pathlib import Path

from . import config, tickers

# (b) superseded renders live in a per-ticker subfolder so the main YouTube
# folder shows only the current .md/.html — dashboard- and AI-scan-clean (F4:
# evidence kept, never destroyed).
SUPERSEDED_DIRNAME = "_superseded"


class LockBusyError(RuntimeError):
    pass


# ---------------------------------------------------------------- atomic io


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp~")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def now_ict() -> str:
    # ICT is UTC+7 with no DST; wall clock on this box is ICT.
    return time.strftime("%Y-%m-%dT%H:%M:%S+07:00")


# ---------------------------------------------------------------- slugs (F10)

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_ZERO_WIDTH = re.compile("[​-‏⁠﻿]")


def slugify_title(title: str, max_len: int | None = None) -> str:
    max_len = max_len or config.TITLE_SLUG_MAX
    s = unicodedata.normalize("NFC", title or "")
    s = _ZERO_WIDTH.sub("", s)
    s = _ILLEGAL.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s[:max_len].strip()
    s = s.rstrip(". ")  # NTFS silently strips trailing dots/spaces — do it ourselves
    return s or "untitled"


# ---------------------------------------------------------------- cache layer


def cache_dir(video_id: str) -> Path:
    return config.cache_root() / video_id


def meta_path(video_id: str) -> Path:
    return cache_dir(video_id) / "meta.json"


def transcript_path(video_id: str) -> Path:
    return cache_dir(video_id) / "transcript.md"


def sanitized_path(video_id: str) -> Path:
    return cache_dir(video_id) / "transcript.sanitized.txt"


def analysis_path(video_id: str, revision: int) -> Path:
    return cache_dir(video_id) / f"analysis.r{revision}.json"


def polish_path(video_id: str, revision: int) -> Path:
    """D0 (2026-08-05): the gate-passed polish is a cache ARTIFACT — before
    this, it lived only inside the KB render and a rerender would lose it."""
    return cache_dir(video_id) / f"polish.r{revision}.txt"


def load_meta(video_id: str) -> dict | None:
    p = meta_path(video_id)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save_meta(video_id: str, meta: dict) -> None:
    atomic_write(meta_path(video_id), json.dumps(meta, ensure_ascii=False, indent=2))


class video_lock:
    """Per-video O_EXCL lockfile (F7). Stale after 10 minutes."""

    def __init__(self, video_id: str, stale_s: int = 600):
        self.path = cache_dir(video_id) / ".lock"
        self.stale_s = stale_s
        self.fd: int | None = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode())
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > self.stale_s:
                        self.path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                raise LockBusyError(
                    f"another session holds {self.path} — retry shortly or remove if stale"
                )
        raise LockBusyError(f"could not acquire {self.path}")

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)
        self.path.unlink(missing_ok=True)
        return False


def existing_revisions(video_id: str) -> list[int]:
    d = cache_dir(video_id)
    if not d.is_dir():
        return []
    out = []
    for entry in d.iterdir():  # F1: iterdir, never glob
        m = re.fullmatch(r"analysis\.r(\d+)\.json", entry.name)
        if m:
            out.append(int(m.group(1)))
    return sorted(out)


def next_revision(video_id: str) -> int:
    revs = existing_revisions(video_id)
    return (revs[-1] + 1) if revs else 1


# ---------------------------------------------------------------- KB layer


def kb_dir_for(qualified_ticker: str | None) -> Path:
    root = config.kb_root()
    if not qualified_ticker:
        return root / config.UNRESOLVED_DIRNAME / config.SOURCE_SHELF
    market = tickers.market_folder(qualified_ticker)
    tdir = tickers.ticker_dirname(tickers.canonicalize(qualified_ticker))
    return root / market / tdir / config.SOURCE_SHELF


def kb_filename(published: str | None, video_id: str, title: str) -> str:
    date = published or "0000-00-00"
    return f"{date} [{video_id}] {slugify_title(title)}.md"


def _iter_md_files(root: Path):
    """Recursive iterdir walk (F1 — no glob; bracket-safe)."""
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = list(d.iterdir())
        except (FileNotFoundError, NotADirectoryError, PermissionError):
            continue
        for e in entries:
            if e.is_dir():
                stack.append(e)
            elif e.is_file() and e.name.lower().endswith(".md"):
                yield e


def find_kb_files(video_id: str) -> list[Path]:
    """All KB .md files carrying [video_id] in their name (current + superseded)."""
    needle = f"[{video_id}]"
    return [p for p in _iter_md_files(config.kb_root()) if needle in p.name]


def conflict_copies(kb_file: Path, video_id: str) -> list[Path]:
    """Cloud-sync fork copies next to a KB file — reported, NEVER deleted (F2)."""
    if not kb_file.parent.is_dir():
        return []
    needle = f"[{video_id}]"
    out = []
    for e in kb_file.parent.iterdir():
        if not e.is_file() or e == kb_file or needle not in e.name:
            continue
        if "(superseded r" in e.name:
            continue
        out.append(e)
    return sorted(out)


def write_kb_render(
    qualified_ticker: str | None,
    published: str | None,
    video_id: str,
    title: str,
    content: str,
    prior_revision: int | None,
) -> tuple[Path, list[str]]:
    """Write the current render to the canonical name. If a canonical file
    already exists it is renamed to '(superseded rN)' first (F4 — evidence is
    never destroyed). Returns (actual_path, warnings)."""
    warnings: list[str] = []
    kdir = kb_dir_for(qualified_ticker)
    kdir.mkdir(parents=True, exist_ok=True)
    target = kdir / kb_filename(published, video_id, title)

    unchanged = False
    if target.is_file():
        try:
            existing = target.read_text(encoding="utf-8")
        except OSError:
            existing = None
        if existing == content:
            # (a) Identical render — do NOT mint a superseded twin. Re-render
            # rounds that leave a given stock's content unchanged used to pile up
            # (superseded rN) copies carrying no information; the on-disk file
            # already IS this render, so there is nothing to write.
            unchanged = True
        elif prior_revision is not None:
            # (b) Preserve the prior render under _superseded/ (F4 — evidence is
            # never destroyed); the main folder keeps only the current render.
            sup_dir = kdir / SUPERSEDED_DIRNAME
            sup_dir.mkdir(parents=True, exist_ok=True)
            superseded = sup_dir / f"{target.stem} (superseded r{prior_revision}){target.suffix}"
            n = 2
            while superseded.exists():
                superseded = sup_dir / f"{target.stem} (superseded r{prior_revision}-{n}){target.suffix}"
                n += 1
            os.replace(target, superseded)
            warnings.append(f"previous render preserved under {SUPERSEDED_DIRNAME}/: {superseded.name}")

    if unchanged:
        warnings.append("render unchanged — kept existing file (no new revision written)")
    else:
        atomic_write(target, content)

    # F10: the on-disk dirent is the truth (NTFS may normalize the name).
    actual = target
    for e in kdir.iterdir():
        if e.name.lower() == target.name.lower():
            actual = e
            break

    for c in conflict_copies(actual, video_id):
        warnings.append(
            f"cloud-sync conflict copy detected (kept, not touched — resolve by hand): {c.name}"
        )
    return actual, warnings


# ---------------------------------------------------------------- index layer


def index_append(row: dict) -> None:
    p = config.index_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False)
    fd = os.open(str(p), os.O_APPEND | os.O_CREAT | os.O_WRONLY)  # F7 idiom
    try:
        os.write(fd, (line + "\n").encode("utf-8"))
    finally:
        os.close(fd)


def index_load() -> dict[str, dict]:
    """Last-wins per video_id; malformed lines skipped (torn-write tolerant)."""
    p = config.index_path()
    out: dict[str, dict] = {}
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        vid = row.get("video_id")
        if vid:
            out[vid] = row
    return out


def read_frontmatter(path: Path) -> dict:
    """Parse the frontmatter WE emit (known shape): scalars + flow lists."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    out: dict = {}
    for line in text[3:end].strip().splitlines():
        if ":" not in line:
            continue
        key, _, raw = line.partition(":")
        key, raw = key.strip(), raw.strip()
        if raw.startswith("[") and raw.endswith("]"):
            try:
                out[key] = json.loads(raw.replace("'", '"')) if raw != "[]" else []
            except json.JSONDecodeError:
                out[key] = [x.strip().strip('"') for x in raw[1:-1].split(",") if x.strip()]
        elif raw == "null":
            out[key] = None
        elif raw in ("true", "false"):
            out[key] = raw == "true"
        else:
            if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
                raw = raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            out[key] = raw
    return out


def _int_or_none(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def index_rebuild() -> int:
    """Regenerate the index from KB frontmatter (iterdir walk — F1). Returns
    row count. Superseded renders are skipped; canonical files win."""
    rows: dict[str, dict] = {}
    for p in _iter_md_files(config.kb_root()):
        if "(superseded r" in p.name:
            continue
        fm = read_frontmatter(p)
        vid = fm.get("video_id")
        if not vid:
            continue
        rows[str(vid)] = {
            "video_id": vid,
            "run_id": fm.get("run_id"),
            "revision": fm.get("revision"),
            "path": str(p),
            "tickers": fm.get("tickers") or [],
            "published": fm.get("published"),
            "title": fm.get("video_title"),
            "channel": fm.get("channel"),
            "transcript_status": fm.get("transcript_status"),
            "analysis_status": fm.get("analysis_status"),
            # D4 dashboard fields (2026-08-05) — the index is the dashboard's
            # single read surface; keep in lockstep with
            # cli.index_row_from_front. Frontmatter reads back as strings —
            # coerce numerics so consumers get typed rows.
            "period": fm.get("period"),
            "company_name": fm.get("company_name"),
            "anchored_total": _int_or_none(fm.get("anchored_total")),
            "quote_unverified_count": _int_or_none(fm.get("quote_unverified_count")),
            "polish_status": fm.get("polish_status"),
            "duration_s": _int_or_none(fm.get("duration_s")),
            "grounding_slide": fm.get("grounding_slide"),
            "grounding_slide_status": fm.get("grounding_slide_status"),
            "grounding_mda": fm.get("grounding_mda"),
            "grounding_mda_status": fm.get("grounding_mda_status"),
            "doc_checked_total": _int_or_none(fm.get("doc_checked_total")),
            "doc_confirmed_total": _int_or_none(fm.get("doc_confirmed_total")),
            "at": now_ict(),
        }
    p = config.index_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows.values())
    atomic_write(p, body)
    return len(rows)


def known_kb_tickers() -> list[str]:
    """Qualified tickers currently present as KB directories (collision corpus).
    iterdir walk of <root>/<MARKET>/<TICKER-DIR> — bracket-safe (F1); dirnames
    decoded via ticker_from_dirname BEFORE any comparison (F8)."""
    root = config.kb_root()
    out: list[str] = []
    if not root.is_dir():
        return out
    for market in root.iterdir():
        if not market.is_dir() or market.name.startswith("_"):
            continue
        for tdir in market.iterdir():
            if tdir.is_dir():
                try:
                    out.append(tickers.ticker_from_dirname(tdir.name))
                except Exception:  # noqa: BLE001 — foreign dirs are ignorable
                    continue
    return sorted(set(out))
