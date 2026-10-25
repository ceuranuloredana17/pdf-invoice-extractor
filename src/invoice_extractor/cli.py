"""Command-line interface: ``invoice-extractor invoices/ -f csv -o out.csv``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from invoice_extractor import __version__
from invoice_extractor.exporters import EXPORTERS
from invoice_extractor.pipeline import collect_pdfs, extract_many


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="invoice-extractor",
        description="Extract and validate structured data from PDF invoices.",
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="PDF files and/or directories")
    parser.add_argument("-f", "--format", choices=sorted(EXPORTERS), default="json")
    parser.add_argument("-o", "--output", type=Path, help="output file (default: stdout)")
    parser.add_argument("-w", "--workers", type=int, default=1,
                        help="parallel worker processes (default: 1)")
    parser.add_argument("--strict", action="store_true",
                        help="exit with code 1 if any invoice fails or is invalid")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    paths = collect_pdfs(args.inputs)
    if not paths:
        print("No PDF files found.", file=sys.stderr)
        return 2

    results = extract_many(paths, workers=args.workers)
    output = EXPORTERS[args.format](results)

    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output + ("" if output.endswith("\n") else "\n"))

    failed = sum(r.error is not None for r in results)
    valid = sum(r.is_valid for r in results)
    print(
        f"Processed {len(results)} file(s): {valid} valid, "
        f"{len(results) - valid - failed} with errors, {failed} unreadable.",
        file=sys.stderr,
    )
    return 1 if args.strict and valid < len(results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
