import unittest

from tools.handout_export.parser import SourceError, parse_roadmap


class ParserTests(unittest.TestCase):
    def test_h2_starts_slide_and_separator_reuses_title(self):
        slides = parse_roadmap("## A\nfirst\n\n---\n\nsecond\n## B\nthird\n")
        self.assertEqual([s.title for s in slides], ["A", "A", "B"])
        self.assertIn("first", "\n".join(slides[0].blocks[0].lines))
        self.assertIn("second", "\n".join(slides[1].blocks[0].lines))

    def test_other_heading_levels_fail_with_line_number(self):
        with self.assertRaisesRegex(SourceError, r"line 2.*only level-2"):
            parse_roadmap("## A\n### illegal\n")

    def test_separator_before_heading_fails(self):
        with self.assertRaisesRegex(SourceError, r"line 1"):
            parse_roadmap("---\n")

    def test_unclosed_display_math_fails(self):
        with self.assertRaisesRegex(SourceError, r"display math"):
            parse_roadmap("## A\n$$\nx+1\n")

    def test_content_before_first_heading_fails(self):
        with self.assertRaisesRegex(SourceError, r"line 1"):
            parse_roadmap("orphan\n## A\nbody\n")

    def test_heading_like_text_inside_code_fence_is_not_rejected(self):
        slides = parse_roadmap("## A\n```text\n### not a heading\n---\n```\n")
        self.assertEqual(len(slides), 1)
        self.assertIn("### not a heading", "\n".join(slides[0].blocks[0].lines))


if __name__ == "__main__":
    unittest.main()
