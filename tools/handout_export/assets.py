from __future__ import annotations

import hashlib
import math
import os
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, features

from .model import Slide


_IMAGE_RE = re.compile(r"^\s*!\[[^\]]*\]\(([^)]+)\)\s*$")
_SUPPORTED_DIRECT = {".png", ".jpg", ".jpeg"}


class AssetError(ValueError):
    def __init__(self, message: str, line: int | None = None):
        self.line = line
        prefix = f"line {line}: " if line is not None else ""
        super().__init__(prefix + message)


@dataclass(slots=True)
class PreparedAsset:
    source: Path
    kind: str
    latex_path: str | None = None
    frame_paths: list[str] = field(default_factory=list)
    sequence_paths: list[str] = field(default_factory=list)
    durations_ms: list[int] = field(default_factory=list)
    fps: float | None = None
    poster_path: str | None = None


def _latex_rel(path: Path, build_root: Path) -> str:
    return Path(os.path.relpath(path, build_root)).as_posix()


def _asset_tag(source: Path) -> str:
    digest = hashlib.sha1(str(source.resolve()).encode("utf-8")).hexdigest()[:8]
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", source.stem).strip("-") or "asset"
    return f"{stem}-{digest}"


def _parse_webp_frame_durations(data: bytes) -> list[int]:
    """Read ANMF frame durations directly from the WebP RIFF container."""

    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return []
    durations: list[int] = []
    pos = 12
    while pos + 8 <= len(data):
        fourcc = data[pos : pos + 4]
        size = struct.unpack_from("<I", data, pos + 4)[0]
        payload_start = pos + 8
        payload_end = payload_start + size
        if payload_end > len(data):
            break
        if fourcc == b"ANMF" and size >= 16:
            payload = data[payload_start:payload_end]
            duration = payload[12] | (payload[13] << 8) | (payload[14] << 16)
            durations.append(max(1, duration))
        pos = payload_end + (size & 1)
    return durations


def _timing_sequence(frame_paths: list[str], durations_ms: list[int]) -> tuple[list[str], float]:
    if not frame_paths:
        return [], 10.0
    positive = [max(1, int(d)) for d in durations_ms if d]
    if len(positive) != len(frame_paths):
        positive = [100] * len(frame_paths)
    tick = positive[0]
    for duration in positive[1:]:
        tick = math.gcd(tick, duration)
    tick = max(20, tick)
    sequence: list[str] = []
    for path, duration in zip(frame_paths, positive):
        repeats = max(1, min(50, round(duration / tick)))
        sequence.extend([path] * repeats)
    return sequence, 1000.0 / tick


def prepare_asset(source: Path, build_assets_dir: Path) -> PreparedAsset:
    source = Path(source)
    build_assets_dir = Path(build_assets_dir)
    if not source.is_file():
        raise AssetError(f"missing image asset: {source}")

    suffix = source.suffix.lower()
    build_root = build_assets_dir.parent
    if suffix in _SUPPORTED_DIRECT:
        return PreparedAsset(
            source=source,
            kind="direct",
            latex_path=_latex_rel(source, build_root),
        )
    if suffix != ".webp":
        raise AssetError(f"unsupported image format '{suffix}' for {source}")
    if not features.check("webp"):
        raise AssetError("Pillow was built without WebP support")

    build_assets_dir.mkdir(parents=True, exist_ok=True)
    tag = _asset_tag(source)
    try:
        with Image.open(source) as image:
            n_frames = int(getattr(image, "n_frames", 1) or 1)
            if n_frames <= 1:
                out = build_assets_dir / f"{tag}.png"
                image.convert("RGBA").save(out, format="PNG")
                return PreparedAsset(
                    source=source,
                    kind="static-raster",
                    latex_path=_latex_rel(out, build_root),
                )

            frame_paths_abs: list[Path] = []
            for idx in range(n_frames):
                image.seek(idx)
                out = build_assets_dir / f"{tag}-frame-{idx:04d}.png"
                image.convert("RGBA").save(out, format="PNG")
                frame_paths_abs.append(out)
    except OSError as exc:
        raise AssetError(f"cannot decode WebP asset {source}: {exc}") from exc

    durations = _parse_webp_frame_durations(source.read_bytes())
    if len(durations) != len(frame_paths_abs):
        durations = [100] * len(frame_paths_abs)
    frame_paths = [_latex_rel(path, build_root) for path in frame_paths_abs]
    sequence, fps = _timing_sequence(frame_paths, durations)
    return PreparedAsset(
        source=source,
        kind="animation",
        frame_paths=frame_paths,
        sequence_paths=sequence,
        durations_ms=durations,
        fps=fps,
        poster_path=frame_paths[0],
    )


def prepare_assets(
    slides: list[Slide], source_dir: Path, build_assets_dir: Path
) -> dict[str, PreparedAsset]:
    source_dir = Path(source_dir)
    prepared: dict[str, PreparedAsset] = {}
    for slide in slides:
        for block in slide.blocks:
            for offset, line in enumerate(block.lines):
                match = _IMAGE_RE.match(line)
                if not match:
                    continue
                raw_path = match.group(1).strip()
                if raw_path in prepared:
                    continue
                fs_path = raw_path.replace("\\", "/")
                path = (source_dir / fs_path).resolve()
                try:
                    prepared[raw_path] = prepare_asset(path, build_assets_dir)
                except AssetError as exc:
                    line_no = block.start_line + offset
                    raise AssetError(str(exc), line_no) from exc
    return prepared


__all__ = ["AssetError", "PreparedAsset", "prepare_asset", "prepare_assets"]
