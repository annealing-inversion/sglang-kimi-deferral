#!/usr/bin/env python3
import argparse
import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation
from pathlib import Path

from datasets import Dataset


NUMBER_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")
OFFICIAL_NUMBER_RE = re.compile(r"\d+")


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


def extract_official(output):
    nums = OFFICIAL_NUMBER_RE.findall(output.replace(",", ""))
    return nums[-1] if nums else None


def answer_equal(pred, gold):
    if pred is None or gold is None:
        return False
    try:
        return Decimal(pred) == Decimal(gold)
    except InvalidOperation:
        return pred == gold


def get_one_example(row, include_answer):
    ret = f"Question: {row['question']}\nAnswer:"
    if include_answer:
        ret += f" {row['answer']}"
    return ret


def build_prompt(rows, idx, num_shots):
    if num_shots <= 0:
        return get_one_example(rows[idx], False)
    few_shot = "\n\n".join(get_one_example(rows[i], True) for i in range(num_shots))
    return few_shot + "\n\n" + get_one_example(rows[idx], False)


def looks_like_next_question(output):
    return bool(re.search(r"(^|\n)\s*question\s*:", output, re.IGNORECASE))


def request_completion(url, model, prompt, max_tokens, stop):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    payload = {
        "model": model,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    if stop:
        payload["stop"] = stop
    req = urllib.request.Request(
        url.rstrip("/") + "/v1/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with opener.open(req, timeout=600) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    choice = data["choices"][0]
    return choice["text"], data.get("usage", {}), choice.get("finish_reason")


def load_rows(args):
    if args.arrow:
        ds = Dataset.from_file(args.arrow)
        return [dict(row) for row in ds]
    with open(args.data_path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def evaluate_one(args, rows, idx):
    row = rows[idx]
    prompt = build_prompt(rows, idx, args.num_shots)
    start = time.time()
    output, usage, finish_reason = request_completion(
        args.url, args.model, prompt, args.max_new_tokens, args.stop
    )
    latency = time.time() - start
    gold = extract_gold(row["answer"])
    strict = extract_strict(output)
    flexible = (
        extract_official(output)
        if args.extract_mode == "official"
        else extract_flexible(output)
    )
    strict_ok = answer_equal(strict, gold)
    flexible_ok = answer_equal(flexible, gold)
    return {
        "idx": idx,
        "prompt": prompt,
        "gold_answer": row["answer"],
        "gold_extracted": gold,
        "model_output": output,
        "strict_extracted": strict,
        "flexible_extracted": flexible,
        "strict_correct": strict_ok,
        "flexible_correct": flexible_ok,
        "finish_reason": finish_reason,
        "hit_max_tokens": usage.get("completion_tokens") == args.max_new_tokens,
        "looks_like_next_question": looks_like_next_question(output),
        "latency_s": latency,
        "usage": usage,
    }


def main():
    parser = argparse.ArgumentParser()
    data_group = parser.add_mutually_exclusive_group(required=True)
    data_group.add_argument("--arrow")
    data_group.add_argument("--data-path")
    parser.add_argument("--url", default="http://127.0.0.1:30000")
    parser.add_argument("--model", default="/models/Kimi-Linear-48B-A3B-Instruct")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--parallel", type=int, default=1)
    parser.add_argument("--num-shots", type=int, default=0)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument(
        "--stop",
        action="append",
        default=[],
        help="Stop string. Can be passed multiple times.",
    )
    parser.add_argument(
        "--extract-mode",
        choices=("number", "official"),
        default="number",
        help="Answer extraction mode. official matches benchmark/gsm8k/bench_sglang.py.",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = load_rows(args)

    strict_correct = 0
    flexible_correct = 0
    total_completion_tokens = 0
    total_prompt_tokens = 0
    t0 = time.time()

    end_index = min(args.start_index + args.limit, len(rows))
    actual_limit = max(0, end_index - args.start_index)

    indices = list(range(args.start_index, end_index))
    completed = 0
    with output_path.open("w", encoding="utf-8") as f:
        with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as executor:
            futures = {
                executor.submit(evaluate_one, args, rows, idx): idx for idx in indices
            }
            for future in as_completed(futures):
                record = future.result()
                completed += 1
                usage = record["usage"]
                strict_ok = record["strict_correct"]
                flexible_ok = record["flexible_correct"]
                strict_correct += int(strict_ok)
                flexible_correct += int(flexible_ok)
                total_completion_tokens += int(usage.get("completion_tokens") or 0)
                total_prompt_tokens += int(usage.get("prompt_tokens") or 0)
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
                print(
                    f"[{completed}/{actual_limit}] idx={record['idx']} strict={strict_ok} "
                    f"flex={flexible_ok} finish={record['finish_reason']} "
                    f"max={record['hit_max_tokens']} nextq={record['looks_like_next_question']} "
                    f"latency={record['latency_s']:.2f}s gold={record['gold_extracted']} "
                    f"pred={record['flexible_extracted']}"
                )

    wall_time = time.time() - t0
    summary = {
        "start_index": args.start_index,
        "limit": actual_limit,
        "parallel": args.parallel,
        "num_shots": args.num_shots,
        "max_new_tokens": args.max_new_tokens,
        "stop": args.stop,
        "extract_mode": args.extract_mode,
        "strict_exact_match": strict_correct / actual_limit if actual_limit else 0,
        "flexible_exact_match": flexible_correct / actual_limit
        if actual_limit
        else 0,
        "strict_correct": strict_correct,
        "flexible_correct": flexible_correct,
        "wall_time_s": wall_time,
        "requests_per_s": actual_limit / wall_time if wall_time else 0,
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
