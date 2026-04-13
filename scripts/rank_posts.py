#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from danxi_daily.ranking import rank_holes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rank fetched DanXi holes.")
    parser.add_argument("--input", type=Path, required=True, help="Raw hole json file.")
    parser.add_argument("--output", type=Path, required=True, help="Ranked output file.")
    parser.add_argument("--top", type=int, default=20, help="Top N output.")
    parser.add_argument("--source-endpoint", type=str, default="https://forum.fduhole.com/api")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    holes = json.loads(args.input.read_text(encoding="utf-8"))
    ranked = rank_holes(holes=holes, source_endpoint=args.source_endpoint)[: args.top]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps([item.to_dict() for item in ranked], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"ranked={len(ranked)} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
