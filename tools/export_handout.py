from __future__ import annotations

import argparse
import sys
from pathlib import Path

from handout_export.assets import AssetError
from handout_export.build import BuildError, export_handout
from handout_export.parser import SourceError


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export roadmap.md as a XeLaTeX Beamer reading handout."
    )
    parser.add_argument("source", nargs="?", default="roadmap.md")
    parser.add_argument("--build-dir", default="build/handout")
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--tex-only",
        action="store_true",
        help="generate LaTeX and prepared assets without invoking XeLaTeX",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        output = export_handout(
            Path(args.source),
            Path(args.build_dir),
            Path(args.output) if args.output else None,
            compile_pdf=not args.tex_only,
        )
    except (BuildError, SourceError, AssetError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
