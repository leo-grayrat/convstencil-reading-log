import unittest

from tools.handout_export.parser import parse_roadmap
from tools.handout_export.render import render_document, render_inline


class RenderTests(unittest.TestCase):
    def test_fixed_metadata_fonts_footer_and_math(self):
        slides = parse_roadmap(
            "## A\n正文 $x_1 + y_2$。\n\n$$\n\\begin{align}\na&=b\\\\\n\\end{align}\n$$\n"
        )
        tex = render_document(slides)
        self.assertIn(r"\title{ConvStencil Reading Handout}", tex)
        self.assertIn(r"\author{leo\_grayrat}", tex)
        self.assertIn(r"\date{2026-08-20}", tex)
        self.assertIn("FandolSong-Regular", tex)
        self.assertIn("FandolSong-Bold", tex)
        self.assertIn("FandolKai-Regular", tex)
        self.assertIn("FandolFang-Regular", tex)
        self.assertIn("texgyretermes-regular.otf", tex)
        self.assertIn("texgyretermes-bold.otf", tex)
        self.assertIn("texgyretermes-italic.otf", tex)
        self.assertIn("texgyretermes-bolditalic.otf", tex)
        self.assertNotIn("qtmr.pfb", tex)
        self.assertNotIn("tgtermes.sty", tex)
        self.assertIn(r"\newCJKfontfamily\handoutkai[BoldFont=FandolSong-Bold.otf]{FandolKai-Regular.otf}", tex)
        self.assertIn(r"\newfontfamily\handoutclosinglatin[BoldFont=FandolSong-Bold.otf]{FandolKai-Regular.otf}", tex)
        self.assertIn(r"\newcommand{\handoutcrossmark}{\ensuremath{\times}}", tex)
        self.assertNotIn("unicode-math", tex)
        self.assertIn(r"\insertframenumber", tex)
        self.assertNotIn(r"\inserttotalframenumber", tex)
        self.assertIn(r"\begin{frame}[fragile]{A}", tex)
        self.assertIn(r"$x_1 + y_2$", tex)
        # The source uses $$ around an align environment. Nesting align directly
        # inside display math is invalid LaTeX, so the renderer minimally converts
        # the inner environment to aligned while preserving the formula body.
        self.assertIn(r"\begin{aligned}", tex)
        self.assertNotIn(r"\begin{align}", tex)

    def test_current_roadmap_compatibility_macros_and_strikethrough(self):
        slides = parse_roadmap("## Compat\n$3\\cross3$ stencil。\n\n~~旧句子~~\n")
        tex = render_document(slides)
        self.assertIn(r"\providecommand{\cross}{\times}", tex)
        self.assertIn(r"$3\cross3$", tex)
        self.assertIn(r"\sout{旧句子}", tex)
        self.assertIn(r"\usepackage[normalem]{ulem}", tex)

    def test_inline_markdown_and_plain_latex_escaping(self):
        rendered = render_inline("**粗体** 和 *斜体* 与 `a_b%`，普通 a_b & 50% #1")
        self.assertIn(r"\textbf{粗体}", rendered)
        self.assertIn(r"\emph{斜体}", rendered)
        self.assertIn(r"\texttt{\detokenize{a_b%}}", rendered)
        self.assertIn(r"a\_b \& 50\% \#1", rendered)

    def test_paper_quote_and_japanese_closing_quote_use_different_styles(self):
        slides = parse_roadmap(
            "## Quotes\n> This is quoted from the paper.\n\n---\n\n> そばにいてくれてありがとう **僕は負けないよ**\n> ——〇✕△□ - 浪漫派マシュマロ\n"
        )
        tex = render_document(slides)
        self.assertIn(r"\begin{paperquote}", tex)
        self.assertIn(r"\begin{closingquote}", tex)
        self.assertIn(r"\textbf{僕は負けないよ}", tex)
        self.assertIn(r"\handoutcrossmark{}", render_inline("〇✕△□"))

    def test_nested_lists_are_rendered_as_latex_lists(self):
        slides = parse_roadmap(
            "## Lists\n- outer\n  - inner\n    > quoted under inner\n- second\n1. first\n2. second\n"
        )
        tex = render_document(slides)
        self.assertGreaterEqual(tex.count(r"\begin{itemize}"), 2)
        self.assertIn(r"\begin{enumerate}", tex)
        self.assertIn(r"quoted under inner", tex)

    def test_same_title_is_emitted_for_separator_slide(self):
        slides = parse_roadmap("## A\none\n---\ntwo\n")
        tex = render_document(slides)
        self.assertEqual(tex.count(r"\begin{frame}[fragile]{A}"), 2)

    def test_static_image_uses_prepared_path_and_preserves_aspect_ratio(self):
        from pathlib import Path
        from tools.handout_export.assets import PreparedAsset

        slides = parse_roadmap("## Image\n![diagram](./assets/a.png)\n")
        asset = PreparedAsset(
            source=Path("/repo/assets/a.png"),
            kind="direct",
            latex_path="../../../assets/a.png",
        )
        tex = render_document(slides, {"./assets/a.png": asset})
        self.assertIn(r"\includegraphics[width=.92\textwidth,height=.58\textheight,keepaspectratio]", tex)
        self.assertIn("../../../assets/a.png", tex)

    def test_animation_uses_animateinline_autoplay_loop_and_first_poster(self):
        from pathlib import Path
        from tools.handout_export.assets import PreparedAsset

        slides = parse_roadmap("## Motion\n![motion](./assets/motion.webp)\n")
        asset = PreparedAsset(
            source=Path("/repo/assets/motion.webp"),
            kind="animation",
            frame_paths=["assets/f0.png", "assets/f1.png"],
            sequence_paths=["assets/f0.png", "assets/f1.png", "assets/f1.png"],
            durations_ms=[100, 200],
            fps=10.0,
            poster_path="assets/f0.png",
        )
        tex = render_document(slides, {"./assets/motion.webp": asset})
        self.assertIn(r"\begin{animateinline}[autoplay,loop,poster=first]{10}", tex)
        self.assertNotIn(r"\makebox[0pt][l]{\includegraphics", tex)
        self.assertEqual(tex.count("assets/f0.png"), 1)
        self.assertEqual(tex.count("assets/f1.png"), 2)
        self.assertIn(r"\newframe", tex)


if __name__ == "__main__":
    unittest.main()
