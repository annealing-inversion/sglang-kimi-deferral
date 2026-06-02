#!/usr/bin/env python3
import argparse
import json
import re
import time
import urllib.request
from pathlib import Path

from datasets import Dataset


NUMBER_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


def normalize_number(text):
    if text is None:
        return None
    return text.replace(",", "").strip()


def extract_gold(answer):
    match = re.search(r"####\s*(" + NUMBER_RE.pattern + r")", answer)
    if match:
        return normalize_number(match.group(1))
    nums = NUMBER_RE.findall(answer)
    return normalize_number(nums[-1]) if nums else None


def extract_strict(output):
    match = re.search(r"####\s*(" + NUMBER_RE.pattern + r")", output)
    if match:
        return normalize_number(match.group(1))
    return None


def extract_flexible(output):
    nums = NUMBER_RE.findall(output)
    return normalize_number(nums[-1]) if nums else None


def request_completion(opener, url, model, prompt, max_tokens):
    payload = {
        "model": model,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    req = urllib.request.Request(
        url.rstrip("/") + "/v1/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with opener.open(req, timeout=600) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["text"], data.get("usage", {})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arrow", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:30000")
    parser.add_argument("--model", default="/models/Kimi-Linear-48B-A3B-Instruct")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ds = Dataset.from_file(args.arrow)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    strict_correct = 0
    flexible_correct = 0
    total_completion_tokens = 0
    total_prompt_tokens = 0
    t0 = time.time()

    with output_path.open("w", encoding="utf-8") as f:
        for idx, row in enumerate(ds.select(range(min(args.limit, len(ds))))):
            prompt = f"Question: {row['question']}\nAnswer:"
            start = time.time()
            output, usage = request_completion(
                opener, args.url, args.model, prompt, args.max_new_tokens
            )
            latency = time.time() - start
            gold = extract_gold(row["answer"])
            strict = extract_strict(output)
            flexible = extract_flexible(output)
            strict_ok = strict == gold
            flexible_ok = flexible == gold
            strict_correct += int(strict_ok)
            flexible_correct += int(flexible_ok)
            total_completion_tokens += int(usage.get("completion_tokens") or 0)
            total_prompt_tokens += int(usage.get("prompt_tokens") or 0)
            record = {
                "idx": idx,
                "prompt": prompt,
                "gold_answer": row["answer"],
                "gold_extracted": gold,
                "model_output": output,
                "strict_extracted": strict,
                "flexible_extracted": flexible,
                "strict_correct": strict_ok,
                "flexible_correct": flexible_ok,
                "latency_s": latency,
                "usage": usage,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            print(
                f"[{idx + 1}/{args.limit}] strict={strict_ok} "
                f"flex={flexible_ok} latency={latency:.2f}s gold={gold} pred={flexible}"
            )

    wall_time = time.time() - t0
    summary = {
        "limit": min(args.limit, len(ds)),
        "strict_exact_match": strict_correct / min(args.limit, len(ds)),
        "flexible_exact_match": flexible_correct / min(args.limit, len(ds)),
        "strict_correct": strict_correct,
        "flexible_correct": flexible_correct,
        "wall_time_s": wall_time,
        "requests_per_s": min(args.limit, len(ds)) / wall_time if wall_time else 0,
        "completion_tokens": total_completion_tokens,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens_per_s": total_completion_tokens / wall_time
        if wall_time
        else 0,
        "output": str(output_path),
    }
    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
