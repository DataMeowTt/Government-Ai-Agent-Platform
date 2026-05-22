import json
import random
from collections import Counter, defaultdict
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "configs"
DATASET_DIR = ROOT_DIR / "datasets" / "parser"
FINAL_DIR = DATASET_DIR / "final"

DISTRIBUTION_PATH = CONFIG_DIR / "dataset_distribution.v1.json"
INTENTS_PATH = CONFIG_DIR / "parser_intents.v1.json"
FAMILIES_PATH = CONFIG_DIR / "question_families.v1.json"
BASE_PLANS_PATH = DATASET_DIR / "base_plans.v1.jsonl"
FULL_PATH = DATASET_DIR / "parser_full.v1.jsonl"
FULL_REPORT_PATH = DATASET_DIR / "parser_full_report.v1.json"
FULL_QUALITY_REPORT_PATH = DATASET_DIR / "parser_full_quality_report.v1.json"

TRAIN_PATH = FINAL_DIR / "parser_train.v1.jsonl"
VALIDATION_PATH = FINAL_DIR / "parser_validation.v1.jsonl"
TEST_PATH = FINAL_DIR / "parser_test.v1.jsonl"
SPLIT_REPORT_PATH = FINAL_DIR / "parser_split_report.v1.json"
FINAL_REPORT_PATH = FINAL_DIR / "parser_final_report.v1.json"

RANDOM_SEED = 42
FILLER_GROUP_LIMIT_PER_FAMILY = 4
DP_TAIL_LIMIT = 120
SPLIT_ORDER = ("train", "validation", "test")
HELDOUT_SPLITS = ("validation", "test")
SOURCE_FILES = [
    "parser_deterministic.v1.jsonl",
    "parser_paraphrase.v1.jsonl",
    "parser_hard_cases.v1.jsonl",
    "parser_offtopic_unsupported.v1.jsonl",
]


def fail(message):
    raise SystemExit(f"Phase 10 split failed: {message}")


def load_json(path):
    if not path.exists():
        fail(f"missing file: {path}")
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_jsonl(path):
    if not path.exists():
        fail(f"missing JSONL file: {path}")
    rows = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                fail(f"empty line in {path} at line {line_number}")
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                fail(f"invalid JSONL in {path} at line {line_number}: {exc}")
    return rows


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")


def group_samples(samples):
    groups = {}
    for sample in samples:
        plan_group_id = sample["plan_group_id"]
        groups.setdefault(plan_group_id, []).append(sample)
    return groups


def build_group_meta(groups):
    meta = {}
    for plan_group_id, samples in groups.items():
        intents = Counter(sample["intent"] for sample in samples)
        families = Counter(sample["question_family"] for sample in samples)
        sources = Counter(sample["generation_source"] for sample in samples)
        styles = Counter(sample["language_style"] for sample in samples)
        meta[plan_group_id] = {
            "plan_group_id": plan_group_id,
            "size": len(samples),
            "intent": intents.most_common(1)[0][0],
            "family": families.most_common(1)[0][0],
            "sources": sources,
            "styles": styles,
        }
    return meta


def counter_for_groups(group_ids, meta, field):
    counter = Counter()
    for group_id in group_ids:
        value = meta[group_id][field]
        counter[value] += meta[group_id]["size"]
    return counter


def source_counter_for_groups(group_ids, meta):
    counter = Counter()
    for group_id in group_ids:
        counter.update(meta[group_id]["sources"])
    return counter


def split_size(group_ids, meta):
    return sum(meta[group_id]["size"] for group_id in group_ids)


def largest_remainder_targets(counter, target_size):
    total = sum(counter.values())
    floors = {}
    remainders = []
    for key, count in counter.items():
        raw = target_size * count / total
        floors[key] = int(raw)
        remainders.append((raw - floors[key], key))
    remaining = target_size - sum(floors.values())
    for _remainder, key in sorted(remainders, reverse=True)[:remaining]:
        floors[key] += 1
    return floors


def choose_family_seed_groups(groups_by_family, assigned, train_family_counts, rng, meta, source_targets, current_sources):
    chosen = []
    for family in sorted(groups_by_family):
        candidates = [
            group_id
            for group_id in groups_by_family[family]
            if group_id not in assigned and train_family_counts[family] > 1
        ]
        if not candidates:
            continue
        candidates.sort(
            key=lambda group_id: (
                abs(meta[group_id]["size"] - 5),
                -sum(
                    max(0, source_targets.get(source, 0) - current_sources[source]) * count
                    for source, count in meta[group_id]["sources"].items()
                ),
                rng.random(),
            )
        )
        group_id = candidates[0]
        assigned.add(group_id)
        train_family_counts[family] -= 1
        current_sources.update(meta[group_id]["sources"])
        chosen.append(group_id)
    return chosen


def rank_candidates(candidates, current_groups, target_size, full_intents, full_sources, meta, rng):
    current_intents = counter_for_groups(current_groups, meta, "intent")
    current_sources = source_counter_for_groups(current_groups, meta)

    full_total = sum(full_intents.values())
    target_intents = {
        intent: target_size * count / full_total for intent, count in full_intents.items()
    }
    target_sources = {
        source: target_size * count / full_total for source, count in full_sources.items()
    }

    ranked = []
    for group_id in candidates:
        intent = meta[group_id]["intent"]
        size = meta[group_id]["size"]
        source_gain = 0.0
        for source, count in meta[group_id]["sources"].items():
            source_gain += max(0.0, target_sources.get(source, 0.0) - current_sources[source]) * count
        intent_gain = max(0.0, target_intents.get(intent, 0.0) - current_intents[intent]) * size
        ranked.append((-(source_gain * 2.0 + intent_gain), rng.random(), group_id))
    ranked.sort()
    return [group_id for _, _, group_id in ranked]


def exact_subset_by_size(candidates, needed, meta):
    if needed == 0:
        return []
    reachable = {0: None}
    for group_id in candidates:
        size = meta[group_id]["size"]
        for subtotal in sorted(list(reachable), reverse=True):
            new_total = subtotal + size
            if new_total > needed or new_total in reachable:
                continue
            reachable[new_total] = (subtotal, group_id)
            if new_total == needed:
                selected = []
                cursor = needed
                while cursor:
                    previous, selected_group = reachable[cursor]
                    selected.append(selected_group)
                    cursor = previous
                selected.reverse()
                return selected
    return None


def choose_dynamic_group(candidates, current_groups, target_size, full_intents, source_targets, current_sources, meta, rng):
    current_intents = counter_for_groups(current_groups, meta, "intent")
    full_total = sum(full_intents.values())
    target_intents = {
        intent: target_size * count / full_total for intent, count in full_intents.items()
    }
    scored = []
    for group_id in candidates:
        size = meta[group_id]["size"]
        source_score = 0.0
        for source, count in meta[group_id]["sources"].items():
            source_score += (source_targets.get(source, 0) - current_sources[source]) * count
        intent = meta[group_id]["intent"]
        intent_score = (target_intents.get(intent, 0.0) - current_intents[intent]) * size
        scored.append((source_score * 4.0 + intent_score + rng.random() * 0.001, group_id))
    scored.sort(reverse=True)
    return scored[0][1] if scored else None


def build_split_assignment(samples, target_sizes, families):
    rng = random.Random(RANDOM_SEED)
    groups = group_samples(samples)
    meta = build_group_meta(groups)
    all_group_ids = list(groups)
    rng.shuffle(all_group_ids)

    groups_by_family = defaultdict(list)
    for group_id in all_group_ids:
        groups_by_family[meta[group_id]["family"]].append(group_id)

    train_family_counts = Counter(meta[group_id]["family"] for group_id in all_group_ids)
    assigned = set()
    assignment = {group_id: "train" for group_id in all_group_ids}
    split_groups = {"train": set(all_group_ids), "validation": set(), "test": set()}

    full_intents = Counter(sample["intent"] for sample in samples)
    full_sources = Counter(sample["generation_source"] for sample in samples)

    source_targets_by_split = {
        split: largest_remainder_targets(full_sources, target_sizes[split])
        for split in HELDOUT_SPLITS
    }

    for split in HELDOUT_SPLITS:
        current_sources = Counter()
        seed_groups = choose_family_seed_groups(
            groups_by_family,
            assigned,
            train_family_counts,
            rng,
            meta,
            source_targets_by_split[split],
            current_sources,
        )
        split_groups[split].update(seed_groups)
        for group_id in seed_groups:
            split_groups["train"].remove(group_id)
            assignment[group_id] = split

        current_size = split_size(split_groups[split], meta)
        needed = target_sizes[split] - current_size
        if needed < 0:
            fail(f"{split} family seed groups exceed target by {-needed} samples")

        filler_family_counts = Counter()
        while target_sizes[split] - split_size(split_groups[split], meta) > DP_TAIL_LIMIT:
            candidates = [
                group_id
                for group_id in split_groups["train"]
                if train_family_counts[meta[group_id]["family"]] > 1
                and filler_family_counts[meta[group_id]["family"]] < FILLER_GROUP_LIMIT_PER_FAMILY
            ]
            size_five_candidates = [group_id for group_id in candidates if meta[group_id]["size"] == 5]
            if size_five_candidates:
                candidates = size_five_candidates
            group_id = choose_dynamic_group(
                candidates,
                split_groups[split],
                target_sizes[split],
                full_intents,
                source_targets_by_split[split],
                current_sources,
                meta,
                rng,
            )
            if group_id is None:
                fail(f"no available candidate while filling {split}")
            split_groups["train"].remove(group_id)
            split_groups[split].add(group_id)
            assigned.add(group_id)
            assignment[group_id] = split
            train_family_counts[meta[group_id]["family"]] -= 1
            filler_family_counts[meta[group_id]["family"]] += 1
            current_sources.update(meta[group_id]["sources"])

        needed = target_sizes[split] - split_size(split_groups[split], meta)
        candidates = [
            group_id
            for group_id in split_groups["train"]
            if train_family_counts[meta[group_id]["family"]] > 1
        ]
        ranked = rank_candidates(
            candidates,
            split_groups[split],
            target_sizes[split],
            full_intents,
            full_sources,
            meta,
            rng,
        )
        limited_ranked = []
        filler_family_counts = Counter()
        for group_id in ranked:
            family = meta[group_id]["family"]
            if filler_family_counts[family] >= FILLER_GROUP_LIMIT_PER_FAMILY:
                continue
            limited_ranked.append(group_id)
            filler_family_counts[family] += 1
        selected = exact_subset_by_size(limited_ranked, needed, meta)
        if selected is None:
            fail(f"could not select exact {needed} samples for {split} without splitting plan groups")
        for group_id in selected:
            split_groups["train"].remove(group_id)
            split_groups[split].add(group_id)
            assigned.add(group_id)
            assignment[group_id] = split
            train_family_counts[meta[group_id]["family"]] -= 1

    expected_train = target_sizes["train"]
    actual_train = split_size(split_groups["train"], meta)
    if actual_train != expected_train:
        fail(f"train size is {actual_train}, expected {expected_train}")

    train_families = {meta[group_id]["family"] for group_id in split_groups["train"]}
    missing_train_families = set(families) - train_families
    if missing_train_families:
        fail(f"train split missing question families: {sorted(missing_train_families)[:10]}")

    return assignment, meta


def add_split_field(samples, assignment):
    rows_by_split = {split: [] for split in SPLIT_ORDER}
    for sample in samples:
        split = assignment[sample["plan_group_id"]]
        row = dict(sample)
        row["split"] = split
        rows_by_split[split].append(row)
    return rows_by_split


def count_by(rows, field):
    return dict(sorted(Counter(row[field] for row in rows).items()))


def count_families(rows):
    return len({row["question_family"] for row in rows})


def plan_group_overlap(rows_by_split):
    split_groups = {
        split: {row["plan_group_id"] for row in rows}
        for split, rows in rows_by_split.items()
    }
    overlap = 0
    for left_index, left in enumerate(SPLIT_ORDER):
        for right in SPLIT_ORDER[left_index + 1:]:
            overlap += len(split_groups[left] & split_groups[right])
    return overlap


def build_split_report(rows_by_split, target_sizes):
    return {
        "version": "v1",
        "split_strategy": {
            "unit": "plan_group_id",
            "random_seed": RANDOM_SEED,
            "leakage_prevention": "All samples with the same plan_group_id are assigned to one split.",
        },
        "target_sizes": target_sizes,
        "actual_sizes": {split: len(rows_by_split[split]) for split in SPLIT_ORDER},
        "plan_groups_by_split": {
            split: len({row["plan_group_id"] for row in rows_by_split[split]})
            for split in SPLIT_ORDER
        },
        "samples_by_generation_source": {
            split: count_by(rows_by_split[split], "generation_source")
            for split in SPLIT_ORDER
        },
        "samples_by_intent": {
            split: count_by(rows_by_split[split], "intent")
            for split in SPLIT_ORDER
        },
        "question_families_covered": {
            split: count_families(rows_by_split[split])
            for split in SPLIT_ORDER
        },
        "leakage_check": {
            "plan_group_id_overlap_between_splits": plan_group_overlap(rows_by_split)
        },
        "warnings": [],
    }


def build_final_report(rows_by_split, full_report, quality_report, families):
    total_samples = sum(len(rows) for rows in rows_by_split.values())
    all_rows = [row for rows in rows_by_split.values() for row in rows]
    return {
        "version": "v1",
        "dataset_name": "government_ai_parser_dataset_v1",
        "task": "Natural language question to ParsedQuery JSON semantic parsing.",
        "total_samples": total_samples,
        "splits": {split: len(rows_by_split[split]) for split in SPLIT_ORDER},
        "source_files": SOURCE_FILES,
        "generation_sources": dict(sorted(Counter(row["generation_source"] for row in all_rows).items())),
        "coverage": {
            "intents": len({row["intent"] for row in all_rows}),
            "question_families": len({row["question_family"] for row in all_rows}),
            "countries": full_report.get("unique_countries_used"),
            "indicators": full_report.get("unique_indicators_used"),
        },
        "quality": {
            "duplicate_user_messages": quality_report["quality_checks"].get("duplicate_user_messages", 0),
            "mojibake_findings": quality_report["quality_checks"].get("mojibake_findings", 0),
            "placeholder_findings": quality_report["quality_checks"].get("placeholder_findings", 0),
            "synthetic_artifact_findings": quality_report["quality_checks"].get("synthetic_artifact_findings", 0),
            "schema_errors": quality_report["quality_checks"].get("schema_errors", 0),
            "chatml_errors": quality_report["quality_checks"].get("chatml_errors", 0),
        },
        "format": {
            "file_type": "jsonl",
            "record_format": "ChatML messages with assistant.content as valid JSON string",
            "assistant_json_schema": "configs/parsed_query_schema.v1.json",
        },
        "notes": [
            "Labels are generated before questions to avoid label drift.",
            "LLM paraphrase samples keep labels from base_plans and do not use model-generated labels.",
            "Split is performed by plan_group_id to avoid paraphrase leakage.",
        ],
    }


def main():
    distribution = load_json(DISTRIBUTION_PATH)
    load_json(INTENTS_PATH)
    families_payload = load_json(FAMILIES_PATH)
    read_jsonl(BASE_PLANS_PATH)
    full_report = load_json(FULL_REPORT_PATH)
    quality_report = load_json(FULL_QUALITY_REPORT_PATH)
    samples = read_jsonl(FULL_PATH)

    target_sizes = distribution["splits"]
    if sum(target_sizes.values()) != len(samples):
        fail(f"split targets sum to {sum(target_sizes.values())}, full dataset has {len(samples)}")

    family_ids = [family["id"] for family in families_payload["families"]]
    assignment, _meta = build_split_assignment(samples, target_sizes, family_ids)
    rows_by_split = add_split_field(samples, assignment)

    for split, path in (
        ("train", TRAIN_PATH),
        ("validation", VALIDATION_PATH),
        ("test", TEST_PATH),
    ):
        if len(rows_by_split[split]) != target_sizes[split]:
            fail(f"{split} size {len(rows_by_split[split])} != target {target_sizes[split]}")
        write_jsonl(path, rows_by_split[split])

    split_report = build_split_report(rows_by_split, target_sizes)
    final_report = build_final_report(rows_by_split, full_report, quality_report, family_ids)
    write_json(SPLIT_REPORT_PATH, split_report)
    write_json(FINAL_REPORT_PATH, final_report)

    print("Phase 10 split complete")
    print(f"train samples: {len(rows_by_split['train'])}")
    print(f"validation samples: {len(rows_by_split['validation'])}")
    print(f"test samples: {len(rows_by_split['test'])}")
    print(f"plan_group leakage overlap: {split_report['leakage_check']['plan_group_id_overlap_between_splits']}")
    print(f"question families covered: {split_report['question_families_covered']}")


if __name__ == "__main__":
    main()
