from __future__ import annotations

import re
import textwrap
from typing import Any

from .fonts import FONT_SETUP
from .inline import render_inline
from .model import Slide


_IMAGE_RE = re.compile(r"^\s*!\[[^\]]*\]\(([^)]+)\)\s*$")
_LIST_RE = re.compile(r"^(\s*)([-+*]|\d+[.)])\s+(.*)$")
_FENCE_RE = re.compile(r"^\s*(```+|~~~+)(.*)$")
_KANA_RE = re.compile(r"[\u3040-\u30ff]")


PREAMBLE = (
    r"""\documentclass[aspectratio=169,10pt]{beamer}
\usefonttheme{serif}
\usepackage{fontspec}
\usepackage{xeCJK}
\usepackage{amsmath,amssymb,mathtools}
\usepackage{xcolor}
\usepackage{graphicx}
\usepackage{animate}
\usepackage{fancyvrb}
\usepackage[normalem]{ulem}
"""
    + FONT_SETUP
    + r"""
\setbeamertemplate{navigation symbols}{}
\setbeamertemplate{footline}{%
  \leavevmode\hbox to \paperwidth{\hfill\usebeamerfont{page number in head/foot}\insertframenumber\hspace*{0.75em}}\vspace{0.35em}}
\setbeamercolor{normal text}{fg=black,bg=white}
\setbeamercolor{frametitle}{fg=black,bg=white}
\setbeamercolor{structure}{fg=black}
\setbeamersize{text margin left=0.75cm,text margin right=0.75cm}
\setbeamerfont{frametitle}{series=\bfseries,size=\Large}
\setbeamertemplate{itemize item}{--}
\setbeamertemplate{itemize subitem}{--}
\newenvironment{paperquote}{%
  \begin{quote}\small\itshape\color{black!72}%
}{%
  \end{quote}%
}
\providecommand{\cross}{\times}
\newcommand{\handoutcrossmark}{\ensuremath{\times}}
\newenvironment{closingquote}{%
  \begin{center}\vspace{0.6em}\handoutclosinglatin\handoutkai\Large\setlength{\baselineskip}{1.35\baselineskip}%
}{%
  \vspace{0.2em}\end{center}%
}
\title{ConvStencil Reading Handout}
\author{leo\_grayrat}
\date{2026-08-20}
"""
)


def _asset_field(asset: Any, name: str, default: Any = None) -> Any:
    return getattr(asset, name, default)


def _latex_file_arg(path: str) -> str:
    normalized = str(path).replace("\\", "/")
    return r"\detokenize{" + normalized + "}"


def _render_image(path_text: str, prepared_assets: dict[str, Any] | None) -> str:
    asset = (prepared_assets or {}).get(path_text)
    if asset is None:
        path = path_text.replace("\\", "/")
        return (
            r"\begin{center}\includegraphics[width=.92\textwidth,height=.58\textheight,keepaspectratio]{"
            + _latex_file_arg(path)
            + r"}\end{center}"
        )

    kind = _asset_field(asset, "kind")
    if kind != "animation":
        path = _asset_field(asset, "latex_path") or path_text
        return (
            r"\begin{center}\includegraphics[width=.92\textwidth,height=.58\textheight,keepaspectratio]{"
            + _latex_file_arg(str(path))
            + r"}\end{center}"
        )

    sequence = _asset_field(asset, "sequence_paths", None)
    if not sequence:
        sequence = _asset_field(asset, "frame_paths", [])
    fps = float(_asset_field(asset, "fps", 10.0) or 10.0)
    frame_tex: list[str] = []
    for idx, frame in enumerate(sequence):
        frame_tex.append(
            r"\includegraphics[width=.92\textwidth,height=.58\textheight,keepaspectratio]{"
            + _latex_file_arg(str(frame))
            + "}"
        )
        if idx != len(sequence) - 1:
            frame_tex.append(r"\newframe")
    return (
        r"\begin{center}"
        + "\n"
        + rf"\begin{{animateinline}}[autoplay,loop,poster=first]{{{fps:g}}}"
        + "\n"
        + "\n".join(frame_tex)
        + "\n"
        + r"\end{animateinline}"
        + "\n"
        + r"\end{center}"
    )


_MATH_TOKEN_RE = re.compile(r"\\begin\{([^}]+)\}|\\end\{([^}]+)\}|\\\\")


def _strip_math_delimiters(lines: list[str]) -> list[str] | None:
    if not lines:
        return []
    first = lines[0]
    last = lines[-1]
    first_pos = first.find("$$")
    last_pos = last.rfind("$$")
    if first_pos < 0 or last_pos < 0:
        return None
    if len(lines) == 1:
        if last_pos == first_pos:
            return None
        return [first[first_pos + 2 : last_pos]]
    out = [first[first_pos + 2 :], *lines[1:-1], last[:last_pos]]
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return out


def _single_outer_environment(lines: list[str]) -> str | None:
    meaningful = [line.strip() for line in lines if line.strip()]
    if len(meaningful) < 2:
        return None
    start = re.fullmatch(r"\\begin\{([^}]+)\}", meaningful[0])
    end = re.fullmatch(r"\\end\{([^}]+)\}", meaningful[-1])
    if start and end and start.group(1) == end.group(1):
        return start.group(1)
    return None


def _has_top_level_linebreak(lines: list[str]) -> bool:
    depth = 0
    for line in lines:
        for match in _MATH_TOKEN_RE.finditer(line):
            begin_env, end_env = match.group(1), match.group(2)
            if begin_env is not None:
                depth += 1
            elif end_env is not None:
                depth = max(0, depth - 1)
            elif depth == 0:
                return True
    return False


def _render_display_math(lines: list[str]) -> str:
    inner = _strip_math_delimiters(lines)
    if inner is None:
        return "\n".join(lines)
    outer_env = _single_outer_environment(inner)
    if outer_env in {"align", "align*"}:
        body = "\n".join(inner)
        body = body.replace(r"\begin{align*}", r"\begin{aligned}", 1)
        body = body.replace(r"\end{align*}", r"\end{aligned}", 1)
        body = body.replace(r"\begin{align}", r"\begin{aligned}", 1)
        body = body.replace(r"\end{align}", r"\end{aligned}", 1)
        return "\\[\n" + body + "\n\\]"
    body = "\n".join(inner)
    if _has_top_level_linebreak(inner):
        return "\\[\n\\begin{aligned}\n" + body + "\n\\end{aligned}\n\\]"
    return "\\[\n" + body + "\n\\]"


def _render_closing_text(lines: list[str]) -> str:
    rendered = r"\\".join(render_inline(x.strip()) for x in lines if x.strip())
    return r"\begin{closingquote}" + "\n" + rendered + "\n" + r"\end{closingquote}"


def _render_quote(lines: list[str]) -> str:
    cleaned: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(">"):
            content = stripped[1:]
            if content.startswith(" "):
                content = content[1:]
            cleaned.append(content)
        else:
            cleaned.append(stripped)
    joined = "\n".join(cleaned).strip()
    if _KANA_RE.search(joined):
        return _render_closing_text(cleaned)
    rendered = r"\\".join(render_inline(x) for x in joined.splitlines())
    return r"\begin{paperquote}" + "\n" + rendered + "\n" + r"\end{paperquote}"


def _render_fence(lines: list[str], start: int) -> tuple[str, int]:
    opening = _FENCE_RE.match(lines[start])
    assert opening is not None
    token = opening.group(1)
    code: list[str] = []
    i = start + 1
    while i < len(lines) and not lines[i].lstrip().startswith(token[0] * len(token)):
        code.append(lines[i])
        i += 1
    if i < len(lines):
        i += 1
    if lines[start].startswith((" ", "\t")):
        code = textwrap.dedent("\n".join(code)).splitlines()
    return (
        r"\begin{Verbatim}[fontsize=\small]"
        + "\n"
        + "\n".join(code)
        + "\n"
        + r"\end{Verbatim}",
        i,
    )


def _list_kind(marker: str) -> str:
    return "itemize" if marker[0] in "-+*" else "enumerate"


def _render_list(
    lines: list[str], start: int, prepared_assets: dict[str, Any] | None
) -> tuple[str, int]:
    out: list[str] = []
    stack: list[tuple[int, str]] = []
    i = start

    def close_to(indent: int) -> None:
        while stack and stack[-1][0] > indent:
            _, env = stack.pop()
            out.append(rf"\end{{{env}}}")

    while i < len(lines):
        line = lines[i]
        m = _LIST_RE.match(line)
        if m:
            indent = len(m.group(1).replace("\t", "    "))
            marker = m.group(2)
            content = m.group(3)
            env = _list_kind(marker)
            close_to(indent)
            if not stack or stack[-1][0] < indent:
                stack.append((indent, env))
                out.append(rf"\begin{{{env}}}")
            elif stack[-1][1] != env:
                _, old = stack.pop()
                out.append(rf"\end{{{old}}}")
                stack.append((indent, env))
                out.append(rf"\begin{{{env}}}")
            out.append(r"\item " + render_inline(content))
            i += 1
            continue

        if not line.strip():
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                next_m = _LIST_RE.match(lines[j])
                next_indent = len(lines[j]) - len(lines[j].lstrip(" \t"))
                if next_m or (stack and next_indent > stack[-1][0]):
                    i += 1
                    continue
            break

        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if not stack or indent <= stack[-1][0]:
            break

        if stripped.startswith(">"):
            quote_lines = [line]
            i += 1
            while i < len(lines):
                nxt = lines[i]
                nxt_strip = nxt.lstrip()
                nxt_indent = len(nxt) - len(nxt_strip)
                if nxt_strip.startswith(">") and nxt_indent > stack[-1][0]:
                    quote_lines.append(nxt)
                    i += 1
                else:
                    break
            out.append(_render_quote(quote_lines))
            continue

        if _FENCE_RE.match(line):
            rendered, i = _render_fence(lines, i)
            out.append(rendered)
            continue

        if "$$" in line:
            math_lines = [line]
            delim_count = line.count("$$")
            i += 1
            while delim_count % 2 == 1 and i < len(lines):
                math_lines.append(lines[i])
                delim_count += lines[i].count("$$")
                i += 1
            out.append(_render_display_math([x.lstrip() for x in math_lines]))
            continue

        image = _IMAGE_RE.match(line)
        if image:
            out.append(_render_image(image.group(1).strip(), prepared_assets))
            i += 1
            continue

        if _KANA_RE.search(stripped):
            closing_lines = [stripped]
            i += 1
            while i < len(lines):
                nxt = lines[i]
                nxt_strip = nxt.strip()
                nxt_indent = len(nxt) - len(nxt.lstrip(" \t"))
                if not nxt_strip or nxt_indent <= stack[-1][0] or _is_special_start(nxt):
                    break
                closing_lines.append(nxt_strip)
                i += 1
            out.append(_render_closing_text(closing_lines))
            continue

        out.append(render_inline(stripped))
        i += 1

    while stack:
        _, env = stack.pop()
        out.append(rf"\end{{{env}}}")
    return "\n".join(out), i


def _is_special_start(line: str) -> bool:
    stripped = line.strip()
    return bool(
        not stripped
        or stripped.startswith("$$")
        or _FENCE_RE.match(line)
        or _IMAGE_RE.match(line)
        or line.lstrip().startswith(">")
        or _LIST_RE.match(line)
    )


def _render_lines(lines: list[str], prepared_assets: dict[str, Any] | None) -> str:
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        if _FENCE_RE.match(line):
            rendered, i = _render_fence(lines, i)
            out.append(rendered)
            continue

        if "$$" in line:
            math_lines = [line]
            delim_count = line.count("$$")
            i += 1
            while delim_count % 2 == 1 and i < len(lines):
                math_lines.append(lines[i])
                delim_count += lines[i].count("$$")
                i += 1
            out.append(_render_display_math(math_lines))
            continue

        image = _IMAGE_RE.match(line)
        if image:
            out.append(_render_image(image.group(1).strip(), prepared_assets))
            i += 1
            continue

        if line.lstrip().startswith(">"):
            qlines = [line]
            i += 1
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                qlines.append(lines[i])
                i += 1
            out.append(_render_quote(qlines))
            continue

        if _LIST_RE.match(line):
            rendered, i = _render_list(lines, i, prepared_assets)
            out.append(rendered)
            continue

        para = [line.strip()]
        i += 1
        while i < len(lines) and not _is_special_start(lines[i]):
            para.append(lines[i].strip())
            i += 1
        if _KANA_RE.search("\n".join(para)):
            out.append(_render_closing_text(para))
        else:
            out.append(render_inline(" ".join(para)))
            out.append(r"\par")

    return "\n".join(out)


def render_document(
    slides: list[Slide], prepared_assets: dict[str, Any] | None = None
) -> str:
    parts: list[str] = [PREAMBLE, "\\begin{document}", ""]
    parts.extend([r"\begin{frame}", r"\titlepage", r"\end{frame}", ""])
    for slide in slides:
        body_lines: list[str] = []
        for block in slide.blocks:
            body_lines.extend(block.lines)
        title = render_inline(slide.title)
        parts.append(
            f"% SOURCE_FRAME line={slide.source_line} title={slide.title.replace(chr(10), ' ')}"
        )
        parts.append(rf"\typeout{{HANDOUT-FRAME:line={slide.source_line}}}")
        parts.append(rf"\begin{{frame}}[fragile]{{{title}}}")
        parts.append(_render_lines(body_lines, prepared_assets))
        parts.append(r"\end{frame}")
        parts.append("")
    parts.append(r"\end{document}")
    return "\n".join(parts) + "\n"


__all__ = ["render_document", "render_inline"]
