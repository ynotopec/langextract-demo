"""Paired direct/LangExtract benchmark on one endpoint; credentials never saved."""

import collections
import datetime
import getpass
import importlib.util
import json
import os
import random
import re
import time
from pathlib import Path

import httpx
import langextract as lx
from langextract import prompting
from langextract.core.types import ScoredOutput
from langextract.providers.openai import OpenAILanguageModel

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
# Reuse the frozen, tested scorer from the first campaign.
spec = importlib.util.spec_from_file_location(
    "pilot_scoring", ROOT.parent / "business-2026-11-03/run_benchmark.py"
)
scoring = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scoring)
import sys

sys.path.insert(0, str(PROJECT))
from extraction_support import NullSafeFormatHandler

MODEL = "ai-flash"
PARAMETERS = {
    "temperature": 0,
    "seed": 42,
    "max_tokens": 4096,
    "response_format": {"type": "json_object"},
    "n": 1,
}


def align_direct(text, entities):
    """Baseline's explicit deterministic whitespace-tolerant string alignment."""
    chars = []
    mapping = []
    for index, char in enumerate(text):
        if char.isspace():
            if not chars or chars[-1] == " ":
                continue
            chars.append(" ")
            mapping.append(index)
        else:
            chars.append(char)
            mapping.append(index)
    normalized = "".join(chars)
    used = set()
    for e in entities:
        wanted = scoring.norm(e["extraction_text"])
        start = normalized.find(wanted)
        while start >= 0:
            end = start + len(wanted)
            span = (mapping[start], mapping[end - 1] + 1)
            if span not in used:
                used.add(span)
                e["char_interval"] = {"start_pos": span[0], "end_pos": span[1]}
                break
            start = normalized.find(wanted, start + 1)
    return entities


def parse_direct(content, text):
    stripped = content.strip()
    if stripped.startswith("```"):
        matched = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped)
        if matched is None:
            raise ValueError("Invalid JSON fence")
        stripped = matched.group(1)
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("extractions"), list):
        raise ValueError("Missing extractions wrapper")  # noqa: TRY004 - uniform output-contract failure
    entities = []
    for item in parsed["extractions"]:
        if not isinstance(item, dict):
            raise ValueError("Invalid entity object")  # noqa: TRY004 - uniform output-contract failure
        for name, value in item.items():
            if name.endswith("_attributes") or value is None:
                continue
            if not isinstance(value, (str, int, float)):
                raise ValueError("Invalid entity text")  # noqa: TRY004 - uniform output-contract failure
            entities.append({"extraction_class": name, "extraction_text": str(value)})
    return {"document": {"text": text, "extractions": align_direct(text, entities)}}


class Transport:
    def __init__(self, endpoint, token):
        if not endpoint.startswith("https://"):
            raise ValueError("HTTPS required")
        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self.client = httpx.Client(
            timeout=httpx.Timeout(90, connect=15), follow_redirects=False
        )
        self.calls = []
        self.total_calls = 0

    def request(self, parameters):
        if self.total_calls >= 650:
            raise RuntimeError("Predeclared campaign call budget exhausted")
        # All strategies use exactly the same endpoint/model/generation settings.
        assert parameters["model"] == MODEL
        for name, value in PARAMETERS.items():
            assert parameters.get(name) == value, (name, parameters.get(name))
        self.total_calls += 1
        start = time.monotonic()
        response = self.client.post(
            self.endpoint + "/chat/completions",
            headers={"Authorization": "Bearer " + self.token},
            json=parameters,
        )
        row = {
            "seconds": round(time.monotonic() - start, 4),
            "status": response.status_code,
            "parameters": parameters,
        }
        try:
            payload = response.json()
        except ValueError:
            payload = {"unparseable_response": True}
        # Defense in depth: no credential is persisted even if an upstream echoes it.
        payload = json.loads(json.dumps(payload).replace(self.token, "[REDACTED]"))
        row["response"] = payload
        self.calls.append(row)
        response.raise_for_status()
        choices = payload.get("choices", [])
        if not choices or not choices[0].get("message", {}).get("content"):
            raise ValueError("No model content")
        if choices[0].get("finish_reason") == "length":
            raise ValueError("Truncated model output")
        return payload


class MeasuredModel(OpenAILanguageModel):
    def __init__(self, transport):
        super().__init__(
            model_id=MODEL,
            base_url=transport.endpoint,
            api_key=transport.token,
            temperature=0,
            max_workers=1,
            max_output_tokens=4096,
            seed=42,
        )
        self.transport = transport

    def _process_single_prompt(self, prompt, config):
        payload = self.transport.request(
            self._build_chat_completions_params(prompt, config)
        )
        return ScoredOutput(
            score=1.0, output=payload["choices"][0]["message"]["content"]
        )


def execute_case(case, strategy, corpus, transport):
    text = case["text"]
    example = corpus["example"]
    examples = [
        lx.data.ExampleData(
            text=example["text"],
            extractions=[
                lx.data.Extraction(extraction_class=name, extraction_text=value)
                for item in example["extractions"]
                for name, value in item.items()
            ],
        )
    ]
    handler = NullSafeFormatHandler(
        format_type=lx.data.FormatType.JSON, use_fences=True
    )
    if strategy == "direct":
        generator = prompting.QAPromptGenerator(
            template=prompting.PromptTemplateStructured(
                description=corpus["prompt"], examples=examples
            ),
            format_handler=handler,
        )
        prompt = generator.render(text)
        # Prompt renderer only supplies the shared few-shot text; no LangExtract
        # chunking, resolver, annotation or passes run in the direct strategy.
        payload = transport.request(
            {
                "model": MODEL,
                **PARAMETERS,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that responds in JSON format.",
                    },
                    {"role": "user", "content": prompt},
                ],
            }
        )
        return parse_direct(payload["choices"][0]["message"]["content"], text)
    model = MeasuredModel(transport)
    try:
        result = lx.extract(
            text_or_documents=text,
            prompt_description=corpus["prompt"],
            examples=examples,
            model=model,
            format_type=lx.data.FormatType.JSON,
            fence_output=True,
            use_schema_constraints=False,
            resolver_params={"format_handler": handler, "suppress_parse_errors": False},
            extraction_passes=1 if strategy == "langextract-1" else 2,
            max_workers=1,
            max_char_buffer=1200,
            temperature=0,
            show_progress=False,
        )
    finally:
        model._client.close()
    entities = []
    for e in result.extractions or []:
        entities.append(
            {
                "extraction_class": e.extraction_class,
                "extraction_text": e.extraction_text,
                "char_interval": {
                    "start_pos": e.char_interval.start_pos,
                    "end_pos": e.char_interval.end_pos,
                }
                if e.char_interval
                else None,
                "alignment_status": str(e.alignment_status),
            }
        )
    return {
        "document": {"text": text, "extractions": entities},
        "omitted_null_entities": handler.omitted_entities,
    }


def main():
    corpus = json.loads((ROOT / "corpus.json").read_text())
    results = ROOT / "results"
    if results.exists() and any(results.iterdir()):
        raise FileExistsError("Archive this campaign before rerunning")
    results.mkdir(exist_ok=True)
    token = os.environ.get("LANGEXTRACT_LLM_TOKEN") or getpass.getpass(
        "LLM token (not saved): "
    )
    endpoint = os.environ.get(
        "LANGEXTRACT_LLM_URL", "https://api-llm-custom.ailab.infocepo.com/v1"
    )
    transport = Transport(endpoint, token)

    def model_snapshot(name):
        r = transport.client.get(
            endpoint.rstrip("/") + "/models",
            headers={"Authorization": "Bearer " + token},
        )
        r.raise_for_status()
        (ROOT / name).write_text(
            json.dumps(r.json(), ensure_ascii=False, indent=2).replace(
                token, "[REDACTED]"
            )
            + "\n"
        )

    model_snapshot("models-before.json")
    schedule = [
        (case, method, rep)
        for case in corpus["cases"]
        for method in ["direct", "langextract-1", "langextract-2"]
        for rep in [1, 2]
    ]
    random.Random(20261104).shuffle(schedule)
    rows = []
    for index, (case, method, rep) in enumerate(schedule, 1):
        transport.calls = []
        row = {
            "case": case["id"],
            "strategy": method,
            "repetition": rep,
            "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        start = time.monotonic()
        output = None
        try:
            output = execute_case(case, method, corpus, transport)
            row["ok"] = True
        except Exception as exc:  # noqa: BLE001 - all failures are counted, never retried or hidden
            row.update(ok=False, error_type=type(exc).__name__)
        row["seconds"] = round(time.monotonic() - start, 4)
        row["score"] = scoring.score(
            case, output or {"document": {"text": case["text"], "extractions": []}}
        )
        row["http_calls"] = len(transport.calls)
        row["usage"] = dict(
            collections.Counter(
                {
                    key: sum(
                        call["response"].get("usage", {}).get(key, 0) or 0
                        for call in transport.calls
                    )
                    for key in ["prompt_tokens", "completion_tokens", "total_tokens"]
                }
            )
        )
        row["usage_complete"] = all(
            "usage" in call["response"] for call in transport.calls
        ) and bool(transport.calls)
        (results / f"{case['id']}-{method}-{rep}.json").write_text(
            json.dumps(
                {"measurement": row, "output": output, "calls": transport.calls},
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        rows.append(row)
        (ROOT / "measurements.json").write_text(
            json.dumps(
                {
                    "endpoint": endpoint,
                    "model_alias": MODEL,
                    "parameters": PARAMETERS,
                    "seed_schedule": 20261104,
                    "rows": rows,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        print(
            json.dumps(
                {
                    "done": index,
                    "total": len(schedule),
                    "case": case["id"],
                    "method": method,
                    "ok": row["ok"],
                    "seconds": row["seconds"],
                    "calls": row["http_calls"],
                    "tp": row["score"]["tp"],
                    "fp": row["score"]["fp"],
                    "fn": row["score"]["fn"],
                }
            ),
            flush=True,
        )
        if transport.total_calls >= 650:
            break
    model_snapshot("models-after.json")
    transport.client.close()


if __name__ == "__main__":
    main()
