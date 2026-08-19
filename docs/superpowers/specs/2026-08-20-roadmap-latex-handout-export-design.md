# Roadmap LaTeX Handout Exporter Design

## Goal

Add a self-contained export path that turns `roadmap.md` into a LaTeX Beamer handout and then into PDF, without rewriting or summarizing the source content.

The existing handwritten Beamer file under `presentation/` is unrelated to this exporter and must not be used as an implementation base.

## Fixed title page

The generated deck starts with a title page containing exactly:

- Title: `ConvStencil Reading Handout`
- Author: `leo_grayrat` (escaped correctly in LaTeX source)
- Date: `2026-08-20`

## Source structure and pagination

`roadmap.md` is the source of truth.

Only Markdown level-2 headings are legal heading syntax:

```markdown
## Page title
```

Rules:

1. Every `##` starts a new slide and becomes that slide's title.
2. A standalone `---` forces a new slide while reusing the most recent `##` title.
3. `#`, `###`, `####`, and any other ATX heading level are invalid input. Preflight must stop with a clear line-numbered error instead of guessing how to render them.
4. The exporter must not insert semantic headings that do not exist in the source.
5. The exporter must not summarize, rewrite, reorder, or silently delete source content to make a slide fit.
6. If a slide is too dense to render safely, the exporter reports the offending source page/title so the author can insert an explicit `---`.

## Markdown and LaTeX handling

The document mixes Markdown prose with raw LaTeX mathematics. The converter must preserve this style instead of routing mathematics through a renderer that changes the formulas.

Supported source constructs include:

- normal paragraphs
- `**bold**` and `*italic*`
- inline code using backticks
- unordered and ordered lists, including nested lists
- inline math `$...$`
- display math `$$...$$`
- raw environments already used by the document such as `align`, `aligned`, `matrix`, `bmatrix`, `pmatrix`, and `array`
- LaTeX commands used inside math such as `\textcolor`
- Markdown images with repository-relative paths
- Markdown block quotes

Raw math contents should be passed through with the minimum transformation needed for valid surrounding Beamer syntax.

## Fonts and engine

The generated document is compiled with XeLaTeX.

Typography is fixed to:

- Chinese main text: `FandolSong-Regular`
- Chinese bold: `FandolSong-Bold`
- Chinese Kai style: `FandolKai-Regular`
- Chinese FangSong style: `FandolFang-Regular`
- Latin main/bold: `TeX Gyre Termes Regular / Bold`
- Mathematics: traditional Computer Modern / AMS family

Do not use `unicode-math`, because the mathematical appearance should remain the traditional LaTeX/AMS style.

The exporter may preflight the required fonts and provide a clear missing-font error.

## Beamer appearance

The visual target is a clean academic handout/presentation, not a commercial PowerPoint template.

- 16:9 slide geometry.
- Restrained typography and spacing.
- No Beamer navigation symbols.
- Footer contains only the page number.
- No author, date, title, section name, total-page count, navigation bar, or decorative footer text.
- Source content controls pagination; the template must not introduce unrelated section pages.

## Paper quotations

Normal Markdown block quotes are treated as verbatim excerpts from the ConvStencil paper.

They receive a dedicated restrained quotation style that is visually distinct from the surrounding Chinese explanation, but should still look like an academic source quotation rather than a web card.

The converter must not translate or paraphrase the quote text.

## Japanese closing quotation

The document is expected to contain Japanese only in the final encouragement/lyric quotation. Japanese detection therefore uses the presence of Hiragana or Katakana (`U+3040-U+30FF`) inside a quote block.

A quote containing Japanese kana bypasses the normal paper-quotation style and receives a dedicated closing style. The source text itself remains authoritative; the converter does not hard-code the whole lyric or song title.

Markdown emphasis inside the closing quote remains meaningful, including the intended emphasis around `僕は負けないよ` if that is how the final source is written.

## Images

Markdown image paths are resolved relative to the location of `roadmap.md`, including the current `./assets/...` convention.

Static PNG/JPEG images are included directly through LaTeX graphics support.

Static WebP images are converted to a temporary LaTeX-compatible raster format during the build. Generated intermediates live only in the build directory.

The exporter should size images to the available slide area while preserving aspect ratio. It must not stretch images or silently crop meaningful content.

## Animated WebP

Animated WebP must not be silently flattened to one frame.

Build behavior:

1. Detect whether a WebP contains multiple animation frames.
2. Extract all frames into the temporary build directory.
3. Preserve frame ordering and frame durations as closely as the PDF animation mechanism permits.
4. Generate a LaTeX `animate`/`animateinline` sequence from those extracted frames.
5. Use an autoplaying, looping animation for presentation use.
6. Provide the first frame as the poster/fallback image so static or unsupported PDF viewers still display meaningful content.
7. Do not modify the original WebP asset.

PDF animation is JavaScript-driven and therefore viewer-dependent. The generated PDF remains valid when animation is unsupported; only the motion degrades to the poster frame.

## Build products

The intended command is a single exporter entry point, for example:

```text
python tools/export_handout.py roadmap.md
```

It should:

1. preflight source syntax and required assets/fonts/tools;
2. parse and paginate the Markdown;
3. prepare temporary image/animation assets;
4. emit generated LaTeX into a build directory;
5. invoke XeLaTeX sufficiently many times for stable page numbering;
6. leave a final PDF and optionally the generated `.tex` for inspection;
7. return non-zero with an actionable error on invalid input or compilation failure.

Intermediates should not pollute `assets/` or the repository root.

## Error handling

Errors must identify the relevant source line or asset where possible. At minimum, preflight covers:

- illegal heading levels
- `---` before any `##`
- missing image files
- unsupported image formats
- malformed/unclosed display-math delimiters detectable at block level
- missing XeLaTeX
- missing required fonts
- missing image/animation conversion dependency
- LaTeX compilation failure

Compilation errors should preserve the build directory/log so they can be debugged rather than deleting the evidence.

## Testing strategy

Tests should be fixture-driven and must not depend on the final `roadmap.md` being complete.

Required cases include:

- `##` creates a new slide
- `---` repeats the current title on a new slide
- other heading levels fail with line numbers
- mixed Markdown and raw LaTeX math remains intact
- paper quote selects the paper-quotation style
- a quote containing Hiragana/Katakana selects the Japanese closing style
- relative PNG image resolves correctly
- static WebP uses the static conversion path
- animated WebP uses the animation path and retains all frames
- missing asset fails clearly
- generated footer contains only page number
- fixed title-page metadata is exact

A smoke build against the current draft `roadmap.md` is useful, but the exporter must not require that draft to be semantically complete.

## Non-goals

- Reusing or modifying the old handwritten Beamer deck.
- Automatically rewriting slide content to make it shorter.
- Supporting arbitrary Markdown heading hierarchies.
- Producing PPTX.
- Editing `roadmap.md` as part of export.
- Changing the original image assets.
