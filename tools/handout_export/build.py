from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from .assets import prepare_assets
from .fonts import font_probe_source
from .parser import parse_roadmap
from .render import render_document


class BuildError(RuntimeError):
    pass


def _find_overflow_frames(log_text: str, slides: list[object]) -> list[tuple[int, str]]:
    title_by_line = {int(getattr(s, "source_line")): str(getattr(s, "title")) for s in slides}
    current_line: int | None = None
    issues: list[tuple[int, str]] = []
    seen: set[int] = set()
    for line in log_text.splitlines():
        marker = re.search(r"HANDOUT-FRAME:line=(\d+)", line)
        if marker:
            current_line = int(marker.group(1))
            continue
        if "Overfull \\vbox" in line and current_line is not None and current_line not in seen:
            issues.append((current_line, title_by_line.get(current_line, "")))
            seen.add(current_line)
    return issues


def _font_probe_source() -> str:
    return font_probe_source()


def _run_process(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def _run_font_probe(xelatex: str, build_dir: Path) -> None:
    probe = build_dir / "font-probe.tex"
    probe.write_text(_font_probe_source(), encoding="utf-8")
    result = _run_process(
        [xelatex, "-interaction=nonstopmode", "-halt-on-error", probe.name],
        build_dir,
    )
    if result.returncode == 0:
        return
    log_path = build_dir / "font-probe.log"
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    combined = result.stdout + "\n" + log_text
    missing = re.search(r"Missing font:\s*([^\n]+)", combined)
    if missing:
        font = missing.group(1).strip().rstrip(".")
        raise BuildError(f"required font not found: {font}; see {log_path}")
    raise BuildError(f"font preflight failed; see {log_path}")


def _compile_tex(xelatex: str, tex_path: Path, slides: list[object]) -> Path:
    build_dir = tex_path.parent
    command = [xelatex, "-interaction=nonstopmode", "-halt-on-error", tex_path.name]
    for pass_no in (1, 2):
        result = _run_process(command, build_dir)
        if result.returncode != 0:
            log_path = tex_path.with_suffix(".log")
            raise BuildError(
                f"XeLaTeX compilation failed on pass {pass_no}; see {log_path}"
            )
    log_path = tex_path.with_suffix(".log")
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    overflow = _find_overflow_frames(log_text, slides)
    if overflow:
        details = ", ".join(f"line {line} ('{title}')" for line, title in overflow)
        raise BuildError(
            "slide content overflow detected at "
            + details
            + f"; build artifacts were preserved in {build_dir}"
        )
    pdf_path = tex_path.with_suffix(".pdf")
    if not pdf_path.exists():
        raise BuildError(f"XeLaTeX reported success but did not create {pdf_path}")
    return pdf_path


def export_handout(
    source: Path,
    build_dir: Path,
    output_pdf: Path | None = None,
    compile_pdf: bool = True,
) -> Path:
    source = Path(source).resolve()
    build_dir = Path(build_dir).resolve()
    if not source.is_file():
        raise BuildError(f"source Markdown file not found: {source}")

    build_dir.mkdir(parents=True, exist_ok=True)
    text = source.read_text(encoding="utf-8")
    slides = parse_roadmap(text)
    assets = prepare_assets(slides, source.parent, build_dir / "assets")
    tex = render_document(slides, assets)
    tex_path = build_dir / "handout.tex"
    tex_path.write_text(tex, encoding="utf-8")

    if not compile_pdf:
        return tex_path

    xelatex = shutil.which("xelatex")
    if not xelatex:
        raise BuildError("xelatex executable not found; install XeLaTeX or use --tex-only")
    _run_font_probe(xelatex, build_dir)
    generated_pdf = _compile_tex(xelatex, tex_path, slides)

    if output_pdf is None:
        output_pdf = build_dir / "ConvStencil-Reading-Handout.pdf"
    else:
        output_pdf = Path(output_pdf).resolve()
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    if generated_pdf.resolve() != output_pdf.resolve():
        shutil.copy2(generated_pdf, output_pdf)
    return output_pdf


__all__ = ["BuildError", "export_handout", "_find_overflow_frames"]
