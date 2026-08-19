# Roadmap LaTeX Handout Exporter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained `roadmap.md` → XeLaTeX Beamer → PDF exporter that preserves source content, explicit pagination, formulas, images, paper quotations, and the animated WebP closing/presentation assets.

**Architecture:** A small Python package under `tools/handout_export/` separates source parsing, inline/block rendering, asset preparation, and XeLaTeX build orchestration. `tools/export_handout.py` is the single CLI entry point. Tests use Python `unittest` and temporary fixtures; Pillow is the only required Python library beyond the standard library, and XeLaTeX is invoked only by integration/smoke build paths.

**Tech Stack:** Python 3.10+, standard library, Pillow with WebP/animated-WebP support, XeLaTeX/Beamer, `fontspec`, `xeCJK`, AMS math packages, `graphicx`, `animate`.

**Spec:** `docs/superpowers/specs/2026-08-20-roadmap-latex-handout-export-design.md`

## Global Constraints

- The existing handwritten Beamer file under `presentation/` is unrelated and must not be read, reused, or modified by the exporter.
- Source content is authoritative: do not summarize, rewrite, reorder, or silently delete it.
- Only `##` is legal Markdown heading syntax; all other ATX heading levels are line-numbered errors.
- `---` forces a new slide and inherits the current `##` title; `---` before any `##` is an error.
- Fixed title page: `ConvStencil Reading Handout`, `leo_grayrat`, `2026-08-20`.
- Fonts: FandolSong-Regular/Bold, FandolKai-Regular, FandolFang-Regular, TeX Gyre Termes Regular/Bold; traditional Computer Modern/AMS math; no `unicode-math`.
- Footer contains only the current page number.
- Animated WebP must retain all frames and approximate source frame timing; unsupported viewers fall back to the first frame.
- Build intermediates stay under the build directory and never modify `assets/` or `roadmap.md`.

---

### Task 1: Source model, pagination, and strict preflight

**Files:**
- Create: `tools/handout_export/__init__.py`
- Create: `tools/handout_export/model.py`
- Create: `tools/handout_export/parser.py`
- Create: `tests/test_handout_parser.py`

**Interfaces:**
- Produces: `Slide(title: str, blocks: list[SourceBlock], source_line: int)` and `SourceBlock(kind: str, lines: list[str], start_line: int)` dataclasses.
- Produces: `parse_roadmap(text: str) -> list[Slide]`.
- Raises: `SourceError(message: str, line: int | None = None)` for invalid source structure.

- [ ] **Step 1: Write failing pagination and validation tests**

```python
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
```

- [ ] **Step 2: Run parser tests and verify RED**

Run: `python -m unittest tests.test_handout_parser -v`
Expected: import/module failure because exporter modules do not yet exist.

- [ ] **Step 3: Implement minimal dataclasses and line-aware parser**

`parser.py` must scan line by line, reject `^#{1}(?!#)`, `^#{3,6}\s`, and more-than-six-`#` ATX headings, split on `## ` and standalone `---`, track source lines, group remaining content into coarse source blocks, and ensure block-level `$$` delimiters are balanced.

- [ ] **Step 4: Run parser tests and verify GREEN**

Run: `python -m unittest tests.test_handout_parser -v`
Expected: PASS.

- [ ] **Step 5: Commit parser task**

```bash
git add tools/handout_export tests/test_handout_parser.py
git commit -m "feat: parse roadmap slides strictly"
```

### Task 2: Markdown/LaTeX rendering and Beamer template

**Files:**
- Create: `tools/handout_export/inline.py`
- Create: `tools/handout_export/render.py`
- Create: `tests/test_handout_render.py`

**Interfaces:**
- Consumes: `list[Slide]` from Task 1.
- Produces: `render_document(slides: list[Slide], prepared_assets: dict[str, PreparedAsset] | None = None) -> str`.
- Produces: `render_inline(text: str) -> str` that escapes plain text but preserves inline math and supported raw LaTeX math.

- [ ] **Step 1: Write failing rendering tests**

Tests must assert all of the following independently:

```python
self.assertIn(r"\title{ConvStencil Reading Handout}", tex)
self.assertIn(r"\author{leo\_grayrat}", tex)
self.assertIn(r"\date{2026-08-20}", tex)
self.assertIn(r"\setCJKmainfont[BoldFont=FandolSong-Bold]{FandolSong-Regular}", tex)
self.assertIn(r"\setmainfont{TeX Gyre Termes}", tex)
self.assertNotIn("unicode-math", tex)
self.assertIn(r"\insertframenumber", tex)
self.assertNotIn(r"\inserttotalframenumber", tex)
self.assertIn(r"\begin{frame}{A}", tex)
self.assertIn(r"$x_1 + y_2$", tex)
self.assertIn(r"\begin{align}", tex)
```

Add a paper-quote fixture and a quote containing `そばにいて` and assert that they emit different environments/macros. Add tests for `**bold**`, `*italic*`, inline code, unordered/ordered nested lists, and escaped plain-text `_`, `%`, `&`, `#` outside math/code.

- [ ] **Step 2: Run render tests and verify RED**

Run: `python -m unittest tests.test_handout_render -v`
Expected: import/module failure for renderer.

- [ ] **Step 3: Implement conservative inline and block renderer**

Requirements:
- Preserve `$...$` and `$$...$$` contents verbatim.
- Render Markdown emphasis outside math to `\textbf{}` / `\emph{}`.
- Render inline code using a safe monospace command that escapes LaTeX metacharacters.
- Convert nested Markdown lists into nested `itemize`/`enumerate` environments without inventing headings.
- Render normal `>` blocks using a restrained `paperquote` Beamer environment.
- If quote text contains any character in `\u3040-\u30ff`, render it using a distinct `closingquote` environment and preserve inline emphasis.
- Emit a 16:9 Beamer preamble with requested fonts, no navigation symbols, and a footer containing only `\insertframenumber`.
- Use `amsmath`, `amssymb`, `mathtools`, `xcolor`, `graphicx`, `animate`, `fontspec`, `xeCJK`; do not use `unicode-math`.

- [ ] **Step 4: Run render tests and verify GREEN**

Run: `python -m unittest tests.test_handout_render -v`
Expected: PASS.

- [ ] **Step 5: Commit renderer task**

```bash
git add tools/handout_export/inline.py tools/handout_export/render.py tests/test_handout_render.py
git commit -m "feat: render roadmap as beamer latex"
```

### Task 3: Static and animated image preparation

**Files:**
- Create: `tools/handout_export/assets.py`
- Create: `tests/test_handout_assets.py`

**Interfaces:**
- Produces: `PreparedAsset(source: pathlib.Path, kind: Literal["direct", "static-raster", "animation"], latex_path: str | None, frame_paths: list[str], fps: float | None, poster_path: str | None)`.
- Produces: `prepare_asset(source: Path, build_assets_dir: Path) -> PreparedAsset`.
- Produces: `prepare_assets(slides: list[Slide], source_dir: Path, build_assets_dir: Path) -> dict[str, PreparedAsset]`.

- [ ] **Step 1: Write failing image tests**

Use Pillow in temporary directories to create:
- a PNG fixture and assert direct inclusion;
- a one-frame WebP and assert conversion to a build-directory PNG;
- a three-frame animated WebP with durations `[100, 200, 100]` and assert all original frames are retained in order, poster is frame 0, and the generated animation sequence approximates the 1:2:1 timing ratio;
- a missing image path and assert a clear source-path error.

- [ ] **Step 2: Run asset tests and verify RED**

Run: `python -m unittest tests.test_handout_assets -v`
Expected: import/module failure for asset preparation.

- [ ] **Step 3: Implement Pillow-based preparation**

Requirements:
- Accept PNG/JPEG directly.
- Open WebP with Pillow; require WebP support explicitly.
- If `n_frames == 1`, convert to PNG in the build asset directory.
- If animated, extract every frame as a numbered PNG and read each frame's duration.
- Convert variable durations to a fixed-rate `animateinline` sequence by choosing a practical base tick (use the GCD when useful, clamp to at least 20 ms), repeating frame references to approximate source durations without changing original assets.
- Store only build-relative paths in rendered LaTeX.
- Reject unsupported extensions with an actionable error.

- [ ] **Step 4: Run asset tests and verify GREEN**

Run: `python -m unittest tests.test_handout_assets -v`
Expected: PASS.

- [ ] **Step 5: Commit assets task**

```bash
git add tools/handout_export/assets.py tests/test_handout_assets.py
git commit -m "feat: prepare static and animated handout images"
```

### Task 4: Image-aware renderer and animation output

**Files:**
- Modify: `tools/handout_export/render.py`
- Modify: `tests/test_handout_render.py`

**Interfaces:**
- Consumes: `PreparedAsset` map from Task 3.
- Produces: direct `\includegraphics` for PNG/JPEG/static-converted WebP and `animateinline` blocks for animated WebP.

- [ ] **Step 1: Add failing image rendering tests**

Assert:
- static image Markdown emits `\includegraphics` with aspect-ratio-preserving max width/height;
- animation emits `\begin{animateinline}[autoplay,loop,poster=first]{...}`;
- every extracted frame appears in order/repeated according to the prepared timing sequence;
- the first frame is the fallback poster.

- [ ] **Step 2: Run targeted tests and verify RED**

Run: `python -m unittest tests.test_handout_render -v`
Expected: new image/animation assertions fail.

- [ ] **Step 3: Implement image rendering**

Use a centered image box with both width and height maxima and `keepaspectratio`. Animated assets use `animateinline`; no source WebP path is emitted directly into XeLaTeX.

- [ ] **Step 4: Run renderer tests and verify GREEN**

Run: `python -m unittest tests.test_handout_render -v`
Expected: PASS.

- [ ] **Step 5: Commit image rendering task**

```bash
git add tools/handout_export/render.py tests/test_handout_render.py
git commit -m "feat: render handout images and animations"
```

### Task 5: Build orchestration, tool/font preflight, overflow reporting, and CLI

**Files:**
- Create: `tools/handout_export/build.py`
- Create: `tools/export_handout.py`
- Create: `tests/test_handout_build.py`
- Create: `requirements-handout.txt`

**Interfaces:**
- Produces: `export_handout(source: Path, build_dir: Path, output_pdf: Path | None = None, compile_pdf: bool = True) -> Path`.
- CLI: `python tools/export_handout.py roadmap.md [--build-dir build/handout] [--tex-only]`.

- [ ] **Step 1: Write failing build/CLI tests**

Tests must cover:
- missing source and missing image errors are actionable;
- `--tex-only` creates generated `.tex` without requiring XeLaTeX;
- executable preflight reports missing `xelatex` clearly when compilation is requested;
- generated `.tex` contains exact fixed metadata and page-only footer;
- mocked compilation log parsing reports `Overfull \\vbox`/frame overflow with the corresponding slide title/source line while keeping the build directory.

- [ ] **Step 2: Run build tests and verify RED**

Run: `python -m unittest tests.test_handout_build -v`
Expected: import/module failure for build orchestration.

- [ ] **Step 3: Implement build pipeline and CLI**

Requirements:
- Resolve source and image paths relative to `roadmap.md`.
- Create/retain the build directory.
- Preflight Pillow WebP support and `xelatex` when compiling.
- Add a small XeLaTeX font probe using `\IfFontExistsTF` for the six named fonts and fail with the missing font name before the full deck compile.
- Write `handout.tex` into the build directory.
- Compile with `xelatex -interaction=nonstopmode -halt-on-error` twice.
- Preserve `.log` and `.tex` on failure.
- Parse log warnings for overfull boxes and report the related frame marker injected by renderer comments such as `% SOURCE_FRAME line=... title=...`.
- Copy/leave the final PDF at `build/handout/ConvStencil-Reading-Handout.pdf` by default.
- `--tex-only` performs parsing/assets/rendering but skips XeLaTeX/font-tool checks that require compilation.

- [ ] **Step 4: Run all unit tests and verify GREEN**

Run: `python -m unittest discover -s tests -p 'test_handout_*.py' -v`
Expected: PASS.

- [ ] **Step 5: Commit build pipeline task**

```bash
git add tools/handout_export/build.py tools/export_handout.py tests/test_handout_build.py requirements-handout.txt
git commit -m "feat: add handout export cli and xelatex build"
```

### Task 6: Current-roadmap smoke test and documentation

**Files:**
- Modify: `README.md`
- Optionally create locally only: `build/handout/*` (must not be committed)

**Interfaces:**
- End-to-end command: `python tools/export_handout.py roadmap.md --tex-only` always available after Python dependencies are installed.
- Full command: `python tools/export_handout.py roadmap.md` when XeLaTeX and fonts are installed.

- [ ] **Step 1: Run source preflight and TeX generation against current `roadmap.md`**

Run: `python tools/export_handout.py roadmap.md --tex-only`
Expected: generated TeX succeeds if the current draft obeys the strict heading/display-math rules; otherwise report the exact source line without editing `roadmap.md`.

- [ ] **Step 2: Inspect generated TeX for required invariants**

Run grep/search checks for fixed metadata, fonts, absence of `unicode-math`, absence of `inserttotalframenumber`, and presence of animation output for the repository animated WebP.

- [ ] **Step 3: Attempt a full XeLaTeX smoke build when the environment has required TeX/fonts**

Run: `python tools/export_handout.py roadmap.md`
Expected: PDF produced at the default path. If the environment lacks XeLaTeX/fonts, record that as an environment limitation after unit tests and `--tex-only` pass; do not weaken exporter preflight.

- [ ] **Step 4: Add concise README usage**

Document dependency installation (`python -m pip install -r requirements-handout.txt`), the normal command, `--tex-only`, output location, and the viewer-dependent nature of PDF animation.

- [ ] **Step 5: Run final verification**

Run:
```bash
python -m unittest discover -s tests -p 'test_handout_*.py' -v
python tools/export_handout.py roadmap.md --tex-only
```
Expected: both commands succeed, unless the current unfinished `roadmap.md` itself violates a strict source rule; in that case the test suite must still pass and the smoke error must identify the exact source line.

- [ ] **Step 6: Commit documentation**

```bash
git add README.md
git commit -m "docs: document roadmap handout export"
```
