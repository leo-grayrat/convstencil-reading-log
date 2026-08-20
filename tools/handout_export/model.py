from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SourceBlock:
    kind: str
    lines: list[str]
    start_line: int


@dataclass(slots=True)
class Slide:
    title: str
    blocks: list[SourceBlock] = field(default_factory=list)
    source_line: int = 0
