from __future__ import annotations


FONT_SETUP = r"""
% Latin: TeX Gyre Termes, loaded through fontconfig/fontspec by family name.
% This works with the standard fonts-texgyre package and keeps the exact
% requested Termes family for regular/bold/italic faces.
\IfFontExistsTF{TeX Gyre Termes}{}{%
  \PackageError{handout-fonts}{Missing font: TeX Gyre Termes}{Install the TeX Gyre font collection.}%
}
\setmainfont{TeX Gyre Termes}
\setsansfont{TeX Gyre Termes}

% CJK: exact Fandol OpenType files distributed with TeX Live.
\IfFontExistsTF{FandolSong-Regular.otf}{}{%
  \PackageError{handout-fonts}{Missing font: FandolSong-Regular}{Install the required Fandol font.}%
}
\IfFontExistsTF{FandolSong-Bold.otf}{}{%
  \PackageError{handout-fonts}{Missing font: FandolSong-Bold}{Install the required Fandol font.}%
}
\IfFontExistsTF{FandolKai-Regular.otf}{}{%
  \PackageError{handout-fonts}{Missing font: FandolKai-Regular}{Install the required Fandol font.}%
}
\IfFontExistsTF{FandolFang-Regular.otf}{}{%
  \PackageError{handout-fonts}{Missing font: FandolFang-Regular}{Install the required Fandol font.}%
}
\setCJKmainfont[BoldFont=FandolSong-Bold.otf]{FandolSong-Regular.otf}
\xeCJKsetup{CJKmath=true}
\newCJKfontfamily\handoutkai[BoldFont=FandolSong-Bold.otf]{FandolKai-Regular.otf}
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
