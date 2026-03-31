#!/usr/bin/env python3
"""Run a zero-dependency toy sequence experiment for the ARIS demo workspace."""

from __future__ import annotations

import argparse
import json
from itertools import product
from typing import Dict, Iterable, List


def label(sequence: Iterable[int]) -> int:
    bits = tuple(sequence)
    return int(bits[0] == bits[-1])


def count_statistics(length: int) -> Dict[int, Dict[str, int]]:
    stats: Dict[int, Dict[str, int]] = {}
    for bits in product((0, 1), repeat=length):
        ones = sum(bits)
        bucket = stats.setdefault(ones, {"label_0": 0, "label_1": 0})
        bucket[f"label_{label(bits)}"] += 1
    return stats


def optimal_count_only_accuracy(length: int) -> float:
    correct = 0
    total = 2 ** length
    for bucket in count_statistics(length).values():
        correct += max(bucket["label_0"], bucket["label_1"])
    return correct / total


def boundary_aware_accuracy(length: int) -> float:
    del length
    return 1.0


def evaluate_lengths(lengths: Iterable[int]) -> List[Dict[str, float]]:
    results = []
    for length in lengths:
        results.append(
            {
                "length": length,
                "count_only_accuracy": optimal_count_only_accuracy(length),
                "boundary_aware_accuracy": boundary_aware_accuracy(length),
            }
        )
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate a toy sequence task with count-only and boundary-aware summaries."
    )
    parser.add_argument(
        "--lengths",
        nargs="+",
        type=int,
        default=[4, 8, 12, 16],
        help="Sequence lengths to enumerate exactly.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a table.",
    )
    return parser.parse_args()


def render_table(results: List[Dict[str, float]]) -> str:
    lines = [
        "Toy sequence task: label = 1 iff the first and last bit match",
        "",
        f"{'Length':>6}  {'Count-only':>12}  {'Boundary-aware':>16}",
    ]
    for row in results:
        lines.append(
            f"{int(row['length']):>6}  "
            f"{row['count_only_accuracy'] * 100:>11.2f}%  "
            f"{row['boundary_aware_accuracy'] * 100:>15.2f}%"
        )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    results = evaluate_lengths(args.lengths)
    if args.json:
        print(json.dumps(results, indent=2))
        return
    print(render_table(results))


if __name__ == "__main__":
    main()
