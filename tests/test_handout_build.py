import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from tools.handout_export.build import BuildError, _find_overflow_frames, _font_probe_source, export_handout


class BuildTests(unittest.TestCase):
    def test_tex_only_build_does_not_require_xelatex(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "roadmap.md"
            source.write_text("## A\nhello\n", encoding="utf-8")
            with mock.patch("tools.handout_export.build.shutil.which", return_value=None):
                out = export_handout(source, root / "build", compile_pdf=False)
            self.assertTrue(out.exists())
            self.assertEqual(out.suffix, ".tex")

    def test_compile_requested_reports_missing_xelatex(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "roadmap.md"
            source.write_text("## A\nhello\n", encoding="utf-8")
            with mock.patch("tools.handout_export.build.shutil.which", return_value=None):
                with self.assertRaisesRegex(BuildError, r"xelatex.*not found"):
                    export_handout(source, root / "build", compile_pdf=True)

    def test_tex_only_contains_exact_metadata_and_page_only_footer(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "roadmap.md"
            source.write_text("## A\nhello\n", encoding="utf-8")
            tex_path = export_handout(source, root / "build", compile_pdf=False)
            tex = tex_path.read_text(encoding="utf-8")
            self.assertIn(r"\title{ConvStencil Reading Handout}", tex)
            self.assertIn(r"\author{leo\_grayrat}", tex)
            self.assertIn(r"\date{2026-08-20}", tex)
            self.assertIn(r"\insertframenumber", tex)
            self.assertNotIn(r"\inserttotalframenumber", tex)
            self.assertIn(r"\typeout{HANDOUT-FRAME:line=1}", tex)

    def test_missing_image_is_reported_in_tex_only_mode(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "roadmap.md"
            source.write_text("## A\n![x](./assets/nope.png)\n", encoding="utf-8")
            with self.assertRaisesRegex(Exception, r"missing image asset.*nope.png"):
                export_handout(source, root / "build", compile_pdf=False)

    def test_relative_png_is_resolved_from_source_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "assets").mkdir()
            Image.new("RGB", (5, 5), "white").save(root / "assets" / "ok.png")
            source = root / "roadmap.md"
            source.write_text("## A\n![x](./assets/ok.png)\n", encoding="utf-8")
            tex_path = export_handout(source, root / "build", compile_pdf=False)
            tex = tex_path.read_text(encoding="utf-8")
            self.assertIn("ok.png", tex)

    def test_font_probe_uses_texlive_opentype_files(self):
        probe = _font_probe_source()
        self.assertIn("FandolSong-Regular.otf", probe)
        self.assertIn("FandolSong-Bold.otf", probe)
        self.assertIn("FandolKai-Regular.otf", probe)
        self.assertIn("FandolFang-Regular.otf", probe)
        self.assertIn("texgyretermes-regular.otf", probe)
        self.assertIn("texgyretermes-bold.otf", probe)
        self.assertIn("texgyretermes-italic.otf", probe)
        self.assertIn("texgyretermes-bolditalic.otf", probe)
        self.assertNotIn("qtmr.pfb", probe)
        self.assertNotIn("tgtermes.sty", probe)
        self.assertNotIn(r"\IfFontExistsTF{FandolSong-Regular}{", probe)

    def test_overflow_log_maps_to_source_frame(self):
        slides = [
            type("S", (), {"source_line": 10, "title": "A"})(),
            type("S", (), {"source_line": 20, "title": "B"})(),
        ]
        log = """
HANDOUT-FRAME:line=10
some output
HANDOUT-FRAME:line=20
Overfull \\vbox (12.0pt too high) detected at line 77
"""
        issues = _find_overflow_frames(log, slides)
        self.assertEqual(issues, [(20, "B")])


if __name__ == "__main__":
    unittest.main()
