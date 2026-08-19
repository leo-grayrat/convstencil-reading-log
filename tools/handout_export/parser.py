from __future__ import annotations

import re

from .model import Slide, SourceBlock


_ATX_RE = re.compile(r"^(#+)\s+")
_H2_RE = re.compile(r"^##\s+(.*\S|)\s*$")
_FENCE_RE = re.compile(r"^\s*(```+|~~~+)")


class SourceError(ValueError):
    def __init__(self, message: str, line: int | None = None):
        self.line = line
        prefix = f"line {line}: " if line is not None else ""
        super().__init__(prefix + message)


def _count_display_delimiters(line: str) -> int:
    return line.count("$$")


def parse_roadmap(text: str) -> list[Slide]:
    lines = text.splitlines()
    slides: list[Slide] = []
    current_title: str | None = None
    current_title_line: int | None = None
    body: list[tuple[int, str]] = []
    in_fence = False
    fence_token: str | None = None
    display_open_line: int | None = None
    in_display_math = False

    def flush_slide() -> None:
        nonlocal body
        if current_title is None:
            body = []
            return
        if body:
            start = body[0][0]
            blocks = [SourceBlock("raw", [line for _, line in body], start)]
        else:
            blocks = []
        slides.append(Slide(current_title, blocks, current_title_line or 0))
        body = []

    for lineno, line in enumerate(lines, start=1):
        fence_match = _FENCE_RE.match(line)
        if fence_match and not in_display_math:
            token = fence_match.group(1)
            if not in_fence:
                in_fence = True
                fence_token = token[0] * len(token)
            elif token.startswith(fence_token[0]) and len(token) >= len(fence_token):
                in_fence = False
                fence_token = None
            if current_title is None:
                if line.strip():
                    raise SourceError("content appears before the first level-2 heading", lineno)
            else:
                body.append((lineno, line))
            continue

        if in_fence:
            if current_title is None:
                if line.strip():
                    raise SourceError("content appears before the first level-2 heading", lineno)
            else:
                body.append((lineno, line))
            continue

        delimiter_count = _count_display_delimiters(line)
        if delimiter_count % 2 == 1:
            if not in_display_math:
                in_display_math = True
                display_open_line = lineno
            else:
                in_display_math = False
                display_open_line = None

        if not in_display_math and delimiter_count == 0:
            h2 = _H2_RE.match(line)
            if h2:
                if current_title is not None:
                    flush_slide()
                current_title = h2.group(1).strip()
                current_title_line = lineno
                continue

            atx = _ATX_RE.match(line)
            if atx and len(atx.group(1)) != 2:
                raise SourceError(
                    "only level-2 Markdown headings ('##') are allowed",
                    lineno,
                )

            if line.strip() == "---":
                if current_title is None:
                    raise SourceError("slide separator appears before any level-2 heading", lineno)
                flush_slide()
                current_title_line = lineno
                continue

        if current_title is None:
            if line.strip():
                raise SourceError("content appears before the first level-2 heading", lineno)
        else:
            body.append((lineno, line))

    if in_display_math:
        raise SourceError("unclosed display math delimiter '$$'", display_open_line)
    if in_fence:
        raise SourceError("unclosed fenced code block")
    if current_title is not None:
        flush_slide()
    return slides
