"""Descriptive paired aggregation; no inference and no credential required."""

import collections
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent
METHODS = ["direct", "langextract-1", "langextract-2"]


def summarize(rows):
    totals = collections.Counter()
    for r in rows:
        for k in ["tp", "fp", "fn", "predicted", "source_grounded", "offset_valid"]:
            totals[k] += r["score"][k]
    tp, fp, fn = totals["tp"], totals["fp"], totals["fn"]
    return {
        **dict(totals),
        "jobs": len(rows),
        "successes": sum(r["ok"] for r in rows),
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        "median_seconds": statistics.median(r["seconds"] for r in rows),
        "mean_seconds": statistics.mean(r["seconds"] for r in rows),
        "p95_seconds_descriptive": sorted(r["seconds"] for r in rows)[
            max(0, math.ceil(len(rows) * 0.95) - 1)
        ],
        "http_calls": sum(r["http_calls"] for r in rows),
        "usage_complete": all(r["usage_complete"] for r in rows),
        "tokens": {
            k: sum(r["usage"][k] for r in rows)
            for k in ["prompt_tokens", "completion_tokens", "total_tokens"]
        },
    }


def main():
    cases = json.loads((ROOT / "corpus.json").read_text())["cases"]
    rows = json.loads((ROOT / "measurements.json").read_text())["rows"]
    assert len(rows) == 240, ("Incomplete campaign", len(rows))
    assert len({(r["case"], r["strategy"], r["repetition"]) for r in rows}) == 240
    overview = {}
    by_case = []
    by_class = {}
    stability = {}
    for method in METHODS:
        selected = [r for r in rows if r["strategy"] == method]
        overview[method] = summarize(selected)
        stable = []
        negativeok = 0
        classcounts = collections.defaultdict(collections.Counter)
        for case in cases:
            pair = [r for r in selected if r["case"] == case["id"]]
            stable.append(
                all(r["ok"] for r in pair)
                and pair[0]["score"]["prediction_multiset"]
                == pair[1]["score"]["prediction_multiset"]
            )
            if case.get("negative"):
                negativeok += sum(
                    r["ok"] and r["score"]["predicted"] == 0 for r in pair
                )
            gold = collections.Counter((e["class"], e["text"]) for e in case["gold"])
            for r in pair:
                pred = collections.Counter(
                    {
                        (name, text): count
                        for name, text, count in r["score"]["prediction_multiset"]
                    }
                )
                # Corpus expected texts use NFC and single spaces, confirmed on build.
                for key, count in (gold & pred).items():
                    classcounts[key[0]]["tp"] += count
                for key, count in (pred - gold).items():
                    classcounts[key[0]]["fp"] += count
                for key, count in (gold - pred).items():
                    classcounts[key[0]]["fn"] += count
        stability[method] = {
            "identical_entity_multisets": sum(stable),
            "documents": len(stable),
            "negative_successes": negativeok,
            "negative_jobs": 8,
        }
        by_class[method] = {
            key: dict(value) for key, value in sorted(classcounts.items())
        }
    for case in cases:
        by_case.append(
            {
                "case": case["id"],
                "title": case["title"],
                "gold_occurrences": len(case["gold"]),
                "pages": case["pages"],
                "negative": case.get("negative", False),
                "methods": {
                    method: summarize(
                        [
                            r
                            for r in rows
                            if r["case"] == case["id"] and r["strategy"] == method
                        ]
                    )
                    for method in METHODS
                },
            }
        )
    long_methods = {
        method: summarize(
            [
                r
                for r in rows
                if r["strategy"] == method and int(r["case"][-2:]) in range(33, 37)
            ]
        )
        for method in METHODS
    }
    before = json.loads((ROOT / "models-before.json").read_text())
    after = json.loads((ROOT / "models-after.json").read_text())
    alias = lambda snap: next(
        model for model in snap["data"] if model["id"] == "ai-flash"
    )
    summary = {
        "overview": overview,
        "stability": stability,
        "by_class": by_class,
        "by_case": by_case,
        "long_documents": long_methods,
        "alias_before": alias(before),
        "alias_after": alias(after),
        "alias_unchanged": alias(before) == alias(after),
    }
    (ROOT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "overview": overview,
                "stability": stability,
                "long_documents": long_methods,
                "alias_unchanged": summary["alias_unchanged"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
