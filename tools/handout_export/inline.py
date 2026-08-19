from __future__ import annotations


_LATEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "✕": r"\handoutcrossmark{}",
}


def escape_text(text: str) -> str:
    return "".join(_LATEX_ESCAPES.get(ch, ch) for ch in text)


def render_inline(text: str) -> str:
    """Render a deliberately small Markdown inline subset.

    Math spans are copied byte-for-byte (as Python text) so existing LaTeX is
    not reinterpreted. Outside math/code, plain text is escaped for LaTeX.
    """

    out: list[str] = []
    i = 0
    n = len(text)
    plain_start = 0

    def flush_plain(end: int) -> None:
        nonlocal plain_start
        if end > plain_start:
            out.append(escape_text(text[plain_start:end]))
        plain_start = end

    while i < n:
        if text[i] == "`":
            j = text.find("`", i + 1)
            if j != -1:
                flush_plain(i)
                code = text[i + 1 : j]
                out.append(r"\texttt{\detokenize{" + code + "}}")
                i = j + 1
                plain_start = i
                continue

        if text.startswith("$$", i):
            j = text.find("$$", i + 2)
            if j != -1:
                flush_plain(i)
                out.append(text[i : j + 2])
                i = j + 2
                plain_start = i
                continue

        if text[i] == "$":
            j = i + 1
            while True:
                j = text.find("$", j)
                if j == -1:
                    break
                if j == 0 or text[j - 1] != "\\":
                    break
                j += 1
            if j != -1:
                flush_plain(i)
                out.append(text[i : j + 1])
                i = j + 1
                plain_start = i
                continue

        if text.startswith("~~", i):
            j = text.find("~~", i + 2)
            if j != -1:
                flush_plain(i)
                inner = render_inline(text[i + 2 : j])
                out.append(r"\sout{" + inner + "}")
                i = j + 2
                plain_start = i
                continue

        if text.startswith("**", i):
            j = text.find("**", i + 2)
            if j != -1:
                flush_plain(i)
                inner = render_inline(text[i + 2 : j])
                out.append(r"\textbf{" + inner + "}")
                i = j + 2
                plain_start = i
                continue

        if text[i] == "*":
            j = text.find("*", i + 1)
            if j != -1:
                flush_plain(i)
                inner = render_inline(text[i + 1 : j])
                out.append(r"\emph{" + inner + "}")
                i = j + 1
                plain_start = i
                continue

        i += 1

    flush_plain(n)
    return "".join(out)
