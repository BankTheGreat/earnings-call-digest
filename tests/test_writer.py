import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earnings_digest import config, render, writer

import golden_input


class EnvSandbox(unittest.TestCase):
    """Redirect KB root / cache / index into a tmpdir with LITERAL BRACKETS in
    the path — the INVERTER F1 trap (glob would silently return nothing)."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        base = Path(self._td.name)
        self.kb = base / "!@! [KB] root [ALL]"
        self.cache = base / "cache"
        self.index = base / "state" / "index.jsonl"
        os.environ["ECD_KB_ROOT"] = str(self.kb)
        os.environ["ECD_CACHE_ROOT"] = str(self.cache)
        os.environ["ECD_INDEX"] = str(self.index)

    def tearDown(self):
        for k in (
            "ECD_KB_ROOT",
            "ECD_CACHE_ROOT",
            "ECD_INDEX",
        ):
            os.environ.pop(k, None)
        self._td.cleanup()


class TestSlug(EnvSandbox):
    def test_illegal_chars_and_trailing_dots(self):
        self.assertEqual(
            writer.slugify_title('PTT: Q2 <great?> "results"...  '),
            "PTT Q2 great results",
        )

    def test_zero_width_and_nfc(self):
        self.assertEqual(writer.slugify_title("a​b﻿c"), "abc")

    def test_truncation_and_thai(self):
        s = writer.slugify_title("ก" * 60)
        self.assertEqual(len(s), 40)
        self.assertEqual(writer.slugify_title("Oppday ไตรมาส 2"), "Oppday ไตรมาส 2")

    def test_empty_becomes_untitled(self):
        self.assertEqual(writer.slugify_title("???"), "untitled")


class TestCacheAndRevisions(EnvSandbox):
    def test_next_revision_via_iterdir(self):
        vid = "dQw4w9WgXcQ"
        self.assertEqual(writer.next_revision(vid), 1)
        writer.atomic_write(writer.analysis_path(vid, 1), "{}")
        writer.atomic_write(writer.analysis_path(vid, 2), "{}")
        self.assertEqual(writer.existing_revisions(vid), [1, 2])
        self.assertEqual(writer.next_revision(vid), 3)

    def test_video_lock_excludes(self):
        vid = "dQw4w9WgXcQ"
        with writer.video_lock(vid):
            with self.assertRaises(writer.LockBusyError):
                with writer.video_lock(vid):
                    pass
        # Released — can acquire again.
        with writer.video_lock(vid):
            pass


class TestKbWrite(EnvSandbox):
    def _write(self, prior=None, title="PTT Oppday Q2 2026"):
        return writer.write_kb_render(
            "PTT.BK", "2026-07-15", "dQw4w9WgXcQ", title, "content-body\n", prior
        )

    def test_path_shape(self):
        path, _ = self._write()
        self.assertTrue(path.is_file())
        rel = path.relative_to(self.kb)
        self.assertEqual(rel.parts[0], "TH-SET")
        self.assertEqual(rel.parts[1], "PTT.BK")
        self.assertEqual(rel.parts[2], "YouTube")
        self.assertEqual(rel.parts[3], "2026-07-15 [dQw4w9WgXcQ] PTT Oppday Q2 2026.md")

    def test_supersede_never_deletes(self):
        p1, _ = self._write()
        p2, warnings = self._write(prior=1)
        self.assertTrue(p2.is_file())
        names = [e.name for e in p2.parent.iterdir()]
        self.assertIn("2026-07-15 [dQw4w9WgXcQ] PTT Oppday Q2 2026 (superseded r1).md", names)
        self.assertTrue(any("preserved" in w for w in warnings))

    def test_conflict_copy_reported_not_deleted(self):
        p1, _ = self._write()
        conflict = p1.with_name(p1.stem + " (DESKTOP-conflict).md")
        conflict.write_text("hand-annotated by Master Bank", encoding="utf-8")
        p2, warnings = self._write(prior=1)
        self.assertTrue(conflict.is_file())  # F2: NEVER unlinked
        self.assertTrue(any("conflict copy" in w for w in warnings))

    def test_unresolved_routing(self):
        path, _ = writer.write_kb_render(
            None, "2026-07-15", "dQw4w9WgXcQ", "mystery video", "x\n", None
        )
        self.assertEqual(path.relative_to(self.kb).parts[0], config.UNRESOLVED_DIRNAME)


class TestIndex(EnvSandbox):
    def test_append_load_last_wins_and_torn_line(self):
        writer.index_append({"video_id": "a", "revision": 1})
        writer.index_append({"video_id": "a", "revision": 2})
        writer.index_append({"video_id": "b", "revision": 1})
        with open(self.index, "a", encoding="utf-8") as f:
            f.write('{"video_id": "torn...\n')  # malformed line tolerated
        rows = writer.index_load()
        self.assertEqual(rows["a"]["revision"], 2)
        self.assertEqual(set(rows), {"a", "b"})

    def test_rebuild_walks_bracket_tree(self):
        transcript = golden_input.golden_transcript()
        content = render.render_kb(golden_input.golden_front(), None, transcript)
        path, _ = writer.write_kb_render(
            "PTT.BK", "2026-07-15", "dQw4w9WgXcQ", "PTT Oppday Q2 2026", content, None
        )
        # A superseded sibling must be skipped by rebuild.
        sup = path.with_name(path.stem + " (superseded r1).md")
        sup.write_text(content, encoding="utf-8")
        count = writer.index_rebuild()
        self.assertEqual(count, 1)
        rows = writer.index_load()
        self.assertIn("dQw4w9WgXcQ", rows)
        self.assertEqual(rows["dQw4w9WgXcQ"]["path"], str(path))
        self.assertEqual(rows["dQw4w9WgXcQ"]["tickers"], ["PTT.BK"])

    def test_find_kb_files_bracket_safe(self):
        p1, _ = writer.write_kb_render(
            "PTT.BK", "2026-07-15", "dQw4w9WgXcQ", "t", "x\n", None
        )
        found = writer.find_kb_files("dQw4w9WgXcQ")
        self.assertEqual(found, [p1])

    def test_known_kb_tickers_decodes_dirnames(self):
        writer.write_kb_render("COM7.BK", "2026-07-15", "aaaaaaaaaaa", "t", "x\n", None)
        writer.write_kb_render("PTT.BK", "2026-07-15", "bbbbbbbbbbb", "t", "x\n", None)
        known = writer.known_kb_tickers()
        self.assertIn("COM7.BK", known)  # decoded from COM-7.BK dirname (F8)
        self.assertIn("PTT.BK", known)


if __name__ == "__main__":
    unittest.main()
