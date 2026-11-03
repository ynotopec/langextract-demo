"""Run an authenticated, sequential benchmark; credential is never persisted.
Dependencies: httpx[socks]. Generate PDFs with corpus.py before running.
"""

import collections
import datetime
import getpass
import json
import os
import random
import re
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def norm(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(value))).strip()


def score(case, payload):
    actual = payload.get("document", {}).get("extractions", [])
    gold = collections.Counter((e["class"], norm(e["text"])) for e in case["gold"])
    pred = collections.Counter(
        (e.get("extraction_class"), norm(e.get("extraction_text", ""))) for e in actual
    )
    tp = sum((gold & pred).values())
    fp = sum((pred - gold).values())
    fn = sum((gold - pred).values())
    source = payload.get("document", {}).get("text", "")
    offsets = []
    for e in actual:
        interval = e.get("char_interval") or {}
        start, end = interval.get("start_pos"), interval.get("end_pos")
        offsets.append(
            isinstance(start, int)
            and isinstance(end, int)
            and 0 <= start < end <= len(source)
            and norm(source[start:end]) == norm(e.get("extraction_text", ""))
        )
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "predicted": len(actual),
        "offset_valid": sum(offsets),
        "source_grounded": sum(
            bool(norm(e.get("extraction_text", "")))
            and norm(e.get("extraction_text", "")) in norm(source)
            for e in actual
        ),
        "missing": [
            {"class": k[0], "text": k[1], "count": v} for k, v in (gold - pred).items()
        ],
        "unexpected": [
            {"class": k[0], "text": k[1], "count": v} for k, v in (pred - gold).items()
        ],
        "prediction_multiset": sorted([list(k) + [v] for k, v in pred.items()]),
    }


def main():
    import httpx

    token = os.environ.get("LANGEXTRACT_API_TOKEN") or getpass.getpass(
        "API token (not saved): "
    )
    base = os.environ.get(
        "LANGEXTRACT_BASE_URL", "https://langextract.ailab.infocepo.com"
    ).rstrip("/")
    if not base.startswith("https://"):
        raise ValueError("HTTPS required when sending the token")
    corpus = json.loads((ROOT / "corpus.json").read_text())
    schedule = [
        (c, p)
        for c in corpus["cases"]
        for p in ["one-pass-A", "one-pass-B", "two-passes"]
    ]
    random.Random(20261103).shuffle(schedule)
    run_dir = ROOT / "results"
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(
            "Archive results/ and measurements.json before starting a new campaign"
        )
    run_dir.mkdir(exist_ok=True)
    rows = []
    client = httpx.Client(
        timeout=httpx.Timeout(180, connect=15), follow_redirects=False
    )
    for index, (case, profile) in enumerate(schedule, 1):
        options = {
            "prompt": corpus["prompt"],
            "extraction_passes": 2 if profile == "two-passes" else 1,
            "max_workers": 1,
            "max_char_buffer": 1200,
            "include_text": True,
        }
        row = {
            "case": case["id"],
            "profile": profile,
            "options": options,
            "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "expected_status": case.get("expected_status", 200),
        }
        start = time.monotonic()
        try:
            response = client.post(
                base + "/api/v1/extractions",
                headers={"Authorization": "Bearer " + token},
                files={
                    "file": (
                        case["id"] + ".pdf",
                        (ROOT / case["pdf"]).read_bytes(),
                        "application/pdf",
                    )
                },
                data={"options": json.dumps(options)},
            )
            row.update(
                status=response.status_code,
                seconds=round(time.monotonic() - start, 3),
                response_bytes=len(response.content),
            )
            payload = json.loads(response.text.replace(token, "[REDACTED]"))
            if response.status_code == 200:
                row["score"] = score(case, payload)
                row["jsonl_valid"] = isinstance(json.loads(payload["jsonl"]), dict)
                row["html_present"] = bool(payload.get("html"))
                row["warnings"] = payload.get("warnings", [])
            else:
                row["error_detail"] = payload.get("detail")
            (run_dir / (case["id"] + "-" + profile + ".json")).write_text(
                json.dumps(
                    {"measurement": row, "response": payload},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )
        except (httpx.HTTPError, ValueError) as exc:
            row.update(
                status=None,
                seconds=round(time.monotonic() - start, 3),
                error_type=type(exc).__name__,
            )
        rows.append(row)
        (ROOT / "measurements.json").write_text(
            json.dumps(
                {"base_url": base, "schedule_seed": 20261103, "rows": rows},
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        print(
            json.dumps(
                {
                    "completed": index,
                    "total": len(schedule),
                    "case": case["id"],
                    "profile": profile,
                    "status": row.get("status"),
                    "seconds": row["seconds"],
                    "score": {
                        k: v
                        for k, v in row.get("score", {}).items()
                        if k in ["tp", "fp", "fn"]
                    },
                }
            ),
            flush=True,
        )
    client.close()


if __name__ == "__main__":
    main()
