import json
import re
from collections import Counter
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT_DIR / "datasets" / "parser"

SOURCE_FILES = [
    ("deterministic_template", DATASET_DIR / "parser_deterministic.v1.jsonl"),
    ("llm_paraphrase", DATASET_DIR / "parser_paraphrase.v1.jsonl"),
    ("hard_cases", DATASET_DIR / "parser_hard_cases.v1.jsonl"),
    ("off_topic_unsupported", DATASET_DIR / "parser_offtopic_unsupported.v1.jsonl"),
]
FULL_PATH = DATASET_DIR / "parser_full.v1.jsonl"
REPORT_PATH = DATASET_DIR / "parser_full_report.v1.json"

ARTIFACT_PATTERNS = [
    re.compile(r"#\d+"),
    re.compile(r"\b(request|case|sample|id)\s*#?\d+\b", re.IGNORECASE),
    re.compile(r"\b(yeu cau|yêu cầu|mau|mẫu)\s*#?\d+\b", re.IGNORECASE),
]


def read_jsonl(path):
    if not path.exists():
        raise SystemExit(f"missing source file: {path}")
    rows = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                raise SystemExit(f"empty line in {path} at line {line_number}")
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"invalid JSONL in {path} line {line_number}: {exc}") from exc
    return rows


def has_artifact(text):
    return any(pattern.search(text) for pattern in ARTIFACT_PATTERNS)


def normalized_sample(source, source_sample, next_id):
    assistant_json = source_sample["assistant_json"]
    assistant_content = json.dumps(assistant_json, ensure_ascii=False, separators=(",", ":"))
    messages = list(source_sample["messages"])
    messages[2] = dict(messages[2])
    messages[2]["content"] = assistant_content
    if json.loads(messages[2]["content"]) != assistant_json:
        raise SystemExit(f"assistant JSON normalization failed for {source_sample['sample_id']}")

    sample = dict(source_sample)
    sample["sample_id"] = f"full_{next_id:06d}"
    sample["source_sample_id"] = source_sample["sample_id"]
    sample["generation_source"] = source
    sample["messages"] = messages
    return sample


def build_report(samples, source_counts, merged_counts, dropped_duplicates, dropped_invalid):
    by_intent = Counter(sample["intent"] for sample in samples)
    by_family = Counter(sample["question_family"] for sample in samples)
    by_style = Counter(sample["language_style"] for sample in samples)
    messages = Counter(sample["user_message"] for sample in samples)
    plan_groups = {sample["plan_group_id"] for sample in samples}
    countries = Counter()
    indicators = Counter()
    for sample in samples:
        for country in sample["assistant_json"].get("countries") or []:
            countries[country] += 1
        for indicator in sample["assistant_json"].get("indicators") or []:
            indicators[indicator] += 1
    return {
        "version": "v1",
        "total_samples": len(samples),
        "source_counts": dict(source_counts),
        "merged_counts": dict(merged_counts),
        "dropped_duplicates": dropped_duplicates,
        "dropped_invalid": dropped_invalid,
        "samples_by_intent": dict(sorted(by_intent.items())),
        "samples_by_family": dict(sorted(by_family.items())),
        "samples_by_language_style": dict(sorted(by_style.items())),
        "unique_user_messages": len(messages),
        "unique_plan_groups": len(plan_groups),
        "unique_countries_used": len(countries),
        "unique_indicators_used": len(indicators),
    }


def main():
    source_counts = Counter()
    merged_counts = Counter()
    output_samples = []
    seen_messages = set()
    dropped_duplicates = 0
    dropped_invalid = 0
    artifact_examples = []

    for source, path in SOURCE_FILES:
        rows = read_jsonl(path)
        source_counts[source] = len(rows)
        for row in rows:
            if row.get("generation_source") != source:
                raise SystemExit(f"{row.get('sample_id')} generation_source mismatch: {row.get('generation_source')} != {source}")
            user_message = row.get("user_message", "")
            if has_artifact(user_message):
                artifact_examples.append((row.get("sample_id"), user_message))
                dropped_invalid += 1
                continue
            if user_message in seen_messages:
                dropped_duplicates += 1
                continue
            seen_messages.add(user_message)
            output_samples.append(normalized_sample(source, row, len(output_samples) + 1))
            merged_counts[source] += 1

    if artifact_examples:
        print("synthetic artifact examples:")
        for sample_id, message in artifact_examples[:30]:
            print(f"  {sample_id}: {message}")
        raise SystemExit(f"Merge failed: {len(artifact_examples)} synthetic artifact findings")

    with FULL_PATH.open("w", encoding="utf-8", newline="\n") as file:
        for sample in output_samples:
            file.write(json.dumps(sample, ensure_ascii=False, separators=(",", ":")) + "\n")

    report = build_report(output_samples, source_counts, merged_counts, dropped_duplicates, dropped_invalid)
    with REPORT_PATH.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")

    print(f"total samples: {report['total_samples']}")
    print(f"source counts: {report['source_counts']}")
    print(f"merged counts: {report['merged_counts']}")
    print(f"dropped duplicates: {dropped_duplicates}")
    print(f"dropped invalid: {dropped_invalid}")
    print(f"unique user messages: {report['unique_user_messages']}")


if __name__ == "__main__":
    main()
