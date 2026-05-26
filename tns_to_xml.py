#!/usr/bin/env python3
"""Compatibility wrapper for the decode half of tnstools.py."""

from __future__ import annotations

import argparse
import pathlib

from tnstools import decode_tns_file


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=pathlib.Path)
    ap.add_argument(
        "out_xml",
        type=pathlib.Path,
        nargs="?",
        help="output directory (default: <input filename>.xml)",
    )
    ap.add_argument(
        "--tixc-backend",
        choices=("auto", "pure", "phoenix", "none"),
        default="auto",
        help="TIXC expander backend for method 13 entries (default: auto/pure Python)",
    )
    ap.add_argument("--phoenix", type=pathlib.Path, help="path to phoenix.dll")
    ap.add_argument("--list", action="store_true", help="print parsed entries before extraction")
    ap.add_argument("--artifacts", action="store_true", help="write _artifacts with TIXC streams and entry manifest")
    ap.add_argument(
        "--write-tixc-on-failure",
        action="store_true",
        help="write inflated TIXC streams with .tixc suffix if XML expansion is unavailable",
    )
    args = ap.parse_args()

    try:
        decode_tns_file(
            args.input,
            args.out_xml,
            list_entries=args.list,
            artifacts=args.artifacts,
            tixc_backend_kind=args.tixc_backend,
            phoenix=args.phoenix,
            write_tixc_on_failure=args.write_tixc_on_failure,
        )
    except Exception as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
