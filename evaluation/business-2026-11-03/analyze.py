"""Aggregate saved measurements. No model calls and no credential required."""

import collections
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def f1(tp, fp, fn):
    return 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None


def main():
    corpus = json.loads((ROOT / "corpus.json").read_text())
    measurements = json.loads((ROOT / "measurements.json").read_text())
    rows = measurements["rows"]
    summaries = {}
    for name, profiles in [
        ("one-pass-pooled", ["one-pass-A", "one-pass-B"]),
        ("two-passes", ["two-passes"]),
        ("one-pass-A", ["one-pass-A"]),
        ("one-pass-B", ["one-pass-B"]),
    ]:
        selected = [
            r for r in rows if r["profile"] in profiles and r["expected_status"] == 200
        ]
        totals = collections.Counter()
        for r in selected:
            if "score" in r:
                totals.update(
                    {
                        k: r["score"][k]
                        for k in [
                            "tp",
                            "fp",
                            "fn",
                            "predicted",
                            "offset_valid",
                            "source_grounded",
                        ]
                    }
                )
            else:
                totals["fn"] += len(
                    next(c for c in corpus["cases"] if c["id"] == r["case"])["gold"]
                )
        tp, fp, fn = totals["tp"], totals["fp"], totals["fn"]
        summaries[name] = {
            **totals,
            "requests": len(selected),
            "successes": sum(r.get("status") == 200 for r in selected),
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": f1(tp, fp, fn),
            "mean_seconds": statistics.mean(r["seconds"] for r in selected),
            "median_seconds": statistics.median(r["seconds"] for r in selected),
            "min_seconds": min(r["seconds"] for r in selected),
            "max_seconds": max(r["seconds"] for r in selected),
        }
    per_class = {}
    for group, profiles in [
        ("one-pass-pooled", ["one-pass-A", "one-pass-B"]),
        ("two-passes", ["two-passes"]),
    ]:
        classes = collections.defaultdict(collections.Counter)
        for r in rows:
            if r["profile"] not in profiles or r["expected_status"] != 200:
                continue
            case = next(c for c in corpus["cases"] if c["id"] == r["case"])
            gold = collections.Counter((e["class"], e["text"]) for e in case["gold"])
            # Archived prediction texts are already NFC/whitespace-normalized.
            from run_benchmark import norm

            gold = collections.Counter(
                (name, norm(text))
                for (name, text), count in gold.items()
                for _ in range(count)
            )
            pred = collections.Counter(
                {
                    (name, text): count
                    for name, text, count in r.get("score", {}).get(
                        "prediction_multiset", []
                    )
                }
            )
            for key, count in (gold & pred).items():
                classes[key[0]]["tp"] += count
            for key, count in (pred - gold).items():
                classes[key[0]]["fp"] += count
            for key, count in (gold - pred).items():
                classes[key[0]]["fn"] += count
        per_class[group] = {
            name: dict(counts) for name, counts in sorted(classes.items())
        }
    pairs = []
    for case in corpus["cases"]:
        if case.get("expected_status", 200) != 200:
            continue
        pair = [
            next(r for r in rows if r["case"] == case["id"] and r["profile"] == p)
            for p in ["one-pass-A", "one-pass-B"]
        ]
        pairs.append(
            {
                "case": case["id"],
                "same_entity_multiset": all("score" in r for r in pair)
                and pair[0]["score"]["prediction_multiset"]
                == pair[1]["score"]["prediction_multiset"],
            }
        )
    summary = {
        "profiles": summaries,
        "per_class": per_class,
        "stability_pairs": pairs,
        "stable_documents": sum(p["same_entity_multiset"] for p in pairs),
        "stability_documents": len(pairs),
        "scan_expected_rejections": sum(
            r["expected_status"] == 422 and r.get("status") == 422 for r in rows
        ),
        "negative_empty_successes": sum(
            r["case"] == "09-no-entities"
            and r.get("status") == 200
            and r["score"]["predicted"] == 0
            for r in rows
        ),
        "unexpected_http_failures": sum(
            r.get("status") != r["expected_status"] for r in rows
        ),
    }
    (ROOT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
