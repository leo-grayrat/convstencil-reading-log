from __future__ import annotations


FONT_SETUP = r"""
% Latin: TeX Gyre Termes files distributed with TeX Live.
\IfFontExistsTF{[qtmr.pfb]}{}{%\n  \PackageError{handout-fonts}{Missing font: TeX Gyre Termes Regular}{Install the TeX Gyre Termes fonts.}%\n}
\IfFontExistsTF{[qtmb.pfb]}{}{%\n  \PackageError{handout-fonts}{Missing font: TeX Gyre Termes Bold}{Install the TeX Gyre Termes fonts.}%\n}
\IfFontExistsTF{[qtmri.pfb]}{}{%\n  \PackageError{handout-fonts}{Missing font: TeX Gyre Termes Italic}{Install the TeX Gyre Termes fonts.}%\n}
\IfFontExistsTF{[qtmbi.pfb]}{}{%\n  \PackageError{handout-fonts}{Missing font: TeX Gyre Termes Bold Italic}{Install the TeX Gyre Termes fonts.}%\n}
\setmainfont[
  BoldFont={[qtmb.pfb]},
  ItalicFont={[qtmri.pfb]},
  BoldItalicFont={[qtmbi.pfb]}
]{[qtmr.pfb]}

% CJK: exact Fandol OpenType files distributed with TeX Live.
\IfFontExistsTF{FandolSong-Regular.otf}{}{%\n  \PackageError{handout-fonts}{Missing font: FandolSong-Regular}{Install the required Fandol font.}%\n}
\IfFontExistsTF{FandolSong-Bold.otf}{}{%\n  \PackageError{handout-fonts}{Missing font: FandolSong-Bold}{Install the required Fandol font.}%\n}
\IfFontExistsTF{FandolKai-Regular.otf}{}{%\n  \PackageError{handout-fonts}{Missing font: FandolKai-Regular}{Install the required Fandol font.}%\n}
\IfFontExistsTF{FandolFang-Regular.otf}{}{%\n  \PackageError{handout-fonts}{Missing font: FandolFang-Regular}{Install the required Fandol font.}%\n}
\setCJKmainfont[BoldFont=FandolSong-Bold.otf]{FandolSong-Regular.otf}
\xeCJKsetup{CJKmath=true}
\newCJKfontfamily\handoutkai[BoldFont=FandolSong-Bold.otf]{FandolKai-Regular.otf}
\newfontfamily\handoutclosinglatin[BoldFont=FandolSong-Bold.otf]{FandolKai-Regular.otf}
\newCJKfontfamily\handoutfang{FandolFang-Regular.otf}
""".strip()


def font_probe_source() -> str:
    return (
        r"\documentclass{article}" + "\n"
        r"\usepackage{fontspec}" + "\n"
        r"\usepackage{xeCJK}" + "\n"
        + FONT_SETUP
        + "\n"
        r"\begin{document}" + "\n"
        r"English Regular \textbf{English Bold}. "
        r"中文正文 \textbf{中文粗体}. "
        r"{\handoutkai 楷体 そばにいて}. "
        r"{\handoutfang 仿宋}." + "\n"
        r"\end{document}" + "\n"
    )


__all__ = ["FONT_SETUP", "font_probe_source"]
