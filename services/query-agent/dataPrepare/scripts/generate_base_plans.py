import json
import random
from collections import Counter, defaultdict
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "configs"
DATASET_DIR = ROOT_DIR / "datasets" / "parser"
BASE_PLANS_PATH = DATASET_DIR / "base_plans.v1.jsonl"
REPORT_PATH = DATASET_DIR / "base_plans_report.v1.json"

PARSED_QUERY_FIELDS = [
    "intent",
    "question_family",
    "indicators",
    "countries",
    "country_groups",
    "start_year",
    "end_year",
    "relative_time",
    "event_time",
    "ranking_order",
    "limit",
    "threshold",
    "aggregation",
    "chart_preference",
    "needs_clarification",
    "clarification_questions",
    "confidence",
]
RENDER_CONTEXT_FIELDS = [
    "indicator",
    "indicator_2",
    "indicator_list",
    "country",
    "country_2",
    "country_list",
    "country_group",
    "year",
    "start_year",
    "end_year",
    "period_1",
    "period_2",
    "event",
    "relative_time",
    "top_n",
    "threshold",
    "chart_type",
    "output_format",
    "context_ref",
    "condition",
    "theme",
]


def load_json(path):
    with (CONFIG_DIR / path).open("r", encoding="utf-8") as file:
        return json.load(file)


def slot_base(slot):
    return slot.split(">=", 1)[0]


def weighted_targets(items, total, weights):
    if not items:
        return {}
    target = {item["id"]: 1 for item in items}
    remaining = total - len(items)
    if remaining < 0:
        raise SystemExit(f"Target {total} is smaller than family count {len(items)}")

    weight_sum = sum(weights[item["priority"]] for item in items)
    raw = [
        (
            item["id"],
            remaining * weights[item["priority"]] / weight_sum,
        )
        for item in items
    ]
    for family_id, value in raw:
        target[family_id] += int(value)

    diff = total - sum(target.values())
    remainders = sorted(
        ((value - int(value), family_id) for family_id, value in raw),
        reverse=True,
    )
    for index in range(diff):
        target[remainders[index % len(remainders)][1]] += 1
    return target


def split_target_samples(total, default_size=5):
    groups = []
    quotient, remainder = divmod(total, default_size)
    if remainder == 0:
        groups = [default_size] * quotient
    elif remainder >= 3:
        groups = [default_size] * quotient + [remainder]
    elif quotient > 0:
        groups = [default_size] * (quotient - 1) + [default_size + remainder]
    else:
        groups = [total]
    return [group for group in groups if group > 0]


class Selector:
    def __init__(self, countries, indicators, analytics_metadata, rng):
        self.rng = rng
        self.country_codes = [country["code"] for country in countries]
        popular = [
            "VNM",
            "THA",
            "USA",
            "CHN",
            "JPN",
            "KOR",
            "IDN",
            "MYS",
            "PHL",
            "IND",
            "DEU",
            "FRA",
            "GBR",
            "ITA",
            "ESP",
            "GRC",
            "ARG",
            "BRA",
            "MEX",
            "TUR",
        ]
        self.popular_countries = [code for code in popular if code in self.country_codes]
        self.country_request_index = 0
        self.country_index = 0
        self.popular_country_index = 0

        self.indicators = indicators
        self.indicator_codes = [indicator["code"] for indicator in indicators]
        self.by_category = defaultdict(list)
        self.analytics_codes = set()
        self.anomaly_codes = set()
        self.trend_codes = set()
        self.cluster_codes = set(analytics_metadata["cluster"]["indicators"])
        for indicator in indicators:
            code = indicator["code"]
            self.by_category[indicator["category"]].append(code)
            if indicator["supports_trend"]:
                self.trend_codes.add(code)
            if indicator["supports_anomaly"]:
                self.anomaly_codes.add(code)
            if indicator["supports_trend"] or indicator["supports_anomaly"]:
                self.analytics_codes.add(code)

        self.indicator_indexes = defaultdict(int)

    def countries(self, count=1, prefer_popular=True):
        result = []
        attempts = 0
        while len(result) < count and attempts < 500:
            attempts += 1
            use_popular = prefer_popular and self.country_request_index % 4 != 0
            self.country_request_index += 1
            pool = self.popular_countries if use_popular else self.country_codes
            if use_popular:
                code = pool[self.popular_country_index % len(pool)]
                self.popular_country_index += 1
            else:
                code = pool[self.country_index % len(pool)]
                self.country_index += 1
            if code not in result:
                result.append(code)
        return result

    def country_group(self, parser_enums):
        groups = parser_enums["country_groups"]
        return groups[self.country_index % len(groups)]

    def _pick_from_pool(self, pool, key, count):
        if not pool:
            pool = self.indicator_codes
        result = []
        while len(result) < count:
            code = pool[self.indicator_indexes[key] % len(pool)]
            self.indicator_indexes[key] += 1
            if code not in result:
                result.append(code)
            if len(result) == len(pool) and len(result) < count:
                break
        return result

    def indicators_for(self, family_id, intent, slots, count=1):
        bases = {slot_base(slot) for slot in slots}
        if intent in {"ANOMALY_DETECTION", "ANOMALY_EXPLANATION"} or "anomaly" in family_id:
            pool = sorted(self.anomaly_codes)
            return self._pick_from_pool(pool, "anomaly", count)
        if intent == "TREND_ANALYSIS" or "trend" in family_id or "analytics" in family_id:
            pool = sorted(self.trend_codes)
            return self._pick_from_pool(pool, "trend", count)
        if intent.startswith("CLUSTER") or "cluster" in family_id:
            pool = sorted(self.cluster_codes)
            return self._pick_from_pool(pool, "cluster", count)
        if "crisis" in family_id or "crisis_flag" in bases:
            return self._pick_from_pool(self.by_category["crisis_risk"], "crisis", count)
        if "fiscal" in family_id:
            return self._pick_from_pool(
                ["govdebt_GDP", "fiscal_balance_GDP", "govrev_GDP", "govexp_GDP", "tax_revenue_pct_GDP"],
                "fiscal",
                count,
            )
        if "monetary" in family_id or "inflation" in family_id:
            return self._pick_from_pool(
                ["inflation_cpi", "inflation_gap", "real_interest_rate", "ltrate", "infl"],
                "monetary",
                count,
            )
        if "growth" in family_id:
            return self._pick_from_pool(
                ["rGDP_growth_YoY", "GDP_growth_YoY", "rolling_mean_5yr", "trend_deviation"],
                "growth",
                count,
            )
        if "social" in family_id:
            return self._pick_from_pool(
                ["unemployment_total", "unemployment_youth", "poverty_headcount", "urban_pop_pct"],
                "social",
                count,
            )
        if "structural" in family_id:
            return self._pick_from_pool(
                ["agri_va_share", "manuf_va_share", "GFCF_to_GDP", "GNI_to_GDP"],
                "structural",
                count,
            )
        if family_id == "compare_growth_vs_inflation":
            return ["rGDP_growth_YoY", "inflation_cpi"][:count]
        if family_id == "compare_policy_mix_fiscal_monetary":
            return ["govdebt_GDP", "inflation_cpi"][:count]
        return self._pick_from_pool(self.indicator_codes, "all", count)


def choose_bucket(intent, sample_count, bucket_totals, ordinary_targets):
    if intent in {"OFF_TOPIC", "UNSUPPORTED"}:
        bucket_totals["off_topic_unsupported"] += sample_count
        return "off_topic_unsupported"
    if intent == "NEED_CLARIFICATION":
        bucket_totals["hard_cases"] += sample_count
        return "hard_cases"

    choices = ["deterministic_template", "llm_paraphrase", "hard_cases"]
    bucket = max(choices, key=lambda item: ordinary_targets[item] - bucket_totals[item])
    bucket_totals[bucket] += sample_count
    return bucket


def default_parsed_query(intent, family_id, chart_preference):
    return {
        "intent": intent,
        "question_family": family_id,
        "indicators": [],
        "countries": [],
        "country_groups": [],
        "start_year": None,
        "end_year": None,
        "relative_time": None,
        "event_time": None,
        "ranking_order": None,
        "limit": None,
        "threshold": None,
        "aggregation": None,
        "chart_preference": chart_preference,
        "needs_clarification": False,
        "clarification_questions": [],
        "confidence": 1.0,
    }


def default_render_context():
    return {field: None for field in RENDER_CONTEXT_FIELDS} | {
        "indicator_list": [],
        "country_list": [],
    }


def set_render_from_query(render_context, parsed_query):
    indicators = parsed_query["indicators"]
    countries = parsed_query["countries"]
    render_context["indicator_list"] = list(indicators)
    render_context["indicator"] = indicators[0] if indicators else None
    render_context["indicator_2"] = indicators[1] if len(indicators) > 1 else None
    render_context["country_list"] = list(countries)
    render_context["country"] = countries[0] if countries else None
    render_context["country_2"] = countries[1] if len(countries) > 1 else None
    render_context["country_group"] = (
        parsed_query["country_groups"][0] if parsed_query["country_groups"] else None
    )
    if parsed_query["start_year"] is not None and parsed_query["start_year"] == parsed_query["end_year"]:
        render_context["year"] = parsed_query["start_year"]
    render_context["start_year"] = parsed_query["start_year"]
    render_context["end_year"] = parsed_query["end_year"]
    render_context["event"] = parsed_query["event_time"]
    render_context["relative_time"] = parsed_query["relative_time"]
    render_context["top_n"] = parsed_query["limit"]
    render_context["threshold"] = parsed_query["threshold"]
    if render_context["chart_type"] is None:
        render_context["chart_type"] = parsed_query["chart_preference"]
    return render_context


def choose_years(family_id, slots, config, rng):
    bases = {slot_base(slot) for slot in slots}
    year_policy = config["year_policy"]
    if "event_time" in bases:
        events = list(config["event_mapping"].items())
        event_key, event = events[rng.randrange(len(events))]
        if "before" in family_id:
            start_year, end_year = event["before_period"]
            relative_time = "before_event"
        elif "after" in family_id or "recovery" in family_id:
            start_year, end_year = event["after_period"]
            relative_time = "after_event"
        else:
            start_year, end_year = event["before_period"][0], event["after_period"][1]
            relative_time = None
        return start_year, end_year, relative_time, event_key

    if "relative_time" in bases:
        relative = rng.choice(["recent", "last_3_years", "last_5_years", "last_10_years"])
        if "latest" in family_id:
            return None, None, "latest", None
        return None, None, relative, None

    if "year" in bases:
        year = rng.choice(year_policy["common_single_years"])
        return year, year, None, None

    if "start_year" in bases and "end_year" in bases:
        start_year, end_year = rng.choice(year_policy["common_periods"])
        return start_year, end_year, None, None

    if "decade" in bases or "decades" in bases:
        return 2010, 2019, None, None

    if "periods" in bases or "historical_period" in bases:
        return 2000, 2023, None, None

    return None, None, None, None


def indicator_count_for_family(family_id, slots):
    bases = {slot_base(slot) for slot in slots}
    if any(slot.startswith("indicators>=") for slot in slots) or "multi_indicator" in family_id:
        return 2
    if family_id in {"compare_policy_mix_fiscal_monetary", "compare_growth_vs_inflation"}:
        return 2
    if bases & {
        "indicators",
        "structural_indicators",
        "crisis_flag",
        "fiscal_indicators",
        "monetary_indicators",
        "growth_indicator",
        "inflation_indicator",
        "indicator_alias",
    }:
        return 1
    if family_id.startswith("indicator_"):
        return 1
    return 0


def country_count_for_family(family_id, slots):
    if any(slot.startswith("countries>=") for slot in slots) or "peer_countries>=1" in slots:
        return 2
    if "countries" in {slot_base(slot) for slot in slots}:
        return 1
    return 0


def apply_family_rules(parsed_query, render_context, family, selector, parser_enums, config, rng):
    family_id = family["id"]
    intent = family["intent"]
    slots = family["required_slots"]
    bases = {slot_base(slot) for slot in slots}

    if intent == "OFF_TOPIC":
        parsed_query["chart_preference"] = "none"
        return

    if intent == "UNSUPPORTED":
        parsed_query["chart_preference"] = "none"
        if family_id != "unsupported_raw_sql_request":
            parsed_query["indicators"] = selector.indicators_for(family_id, intent, slots, 1)
            parsed_query["countries"] = selector.countries(1)
        if family_id == "unsupported_no_data_year":
            year = rng.choice(config["year_policy"]["unsupported_years"])
            parsed_query["start_year"] = year
            parsed_query["end_year"] = year
        return

    if intent == "NEED_CLARIFICATION":
        parsed_query["needs_clarification"] = True
        parsed_query["chart_preference"] = "none"
        parsed_query["clarification_questions"] = ["Please clarify the missing or ambiguous slot."]
        if family_id == "missing_indicator":
            parsed_query["countries"] = selector.countries(1)
            year = rng.choice(config["year_policy"]["common_single_years"])
            parsed_query["start_year"] = year
            parsed_query["end_year"] = year
        elif family_id == "missing_country":
            parsed_query["indicators"] = selector.indicators_for(family_id, intent, slots, 1)
            year = rng.choice(config["year_policy"]["common_single_years"])
            parsed_query["start_year"] = year
            parsed_query["end_year"] = year
        elif family_id == "missing_year_for_ranking":
            parsed_query["indicators"] = selector.indicators_for(family_id, intent, slots, 1)
            parsed_query["limit"] = rng.choice(config["ranking_policy"]["top_n_values"])
            parsed_query["ranking_order"] = "desc"
        elif family_id == "ambiguous_indicator":
            parsed_query["countries"] = selector.countries(1)
            year = rng.choice(config["year_policy"]["common_single_years"])
            parsed_query["start_year"] = year
            parsed_query["end_year"] = year
            render_context["theme"] = rng.choice(["growth", "inflation", "risk"])
        elif family_id == "ambiguous_country":
            parsed_query["indicators"] = selector.indicators_for(family_id, intent, slots, 1)
            year = rng.choice(config["year_policy"]["common_single_years"])
            parsed_query["start_year"] = year
            parsed_query["end_year"] = year
        elif family_id == "ambiguous_time_range":
            parsed_query["indicators"] = selector.indicators_for(family_id, intent, slots, 1)
            parsed_query["countries"] = selector.countries(1)
            parsed_query["relative_time"] = "recent"
        return

    indicator_count = indicator_count_for_family(family_id, slots)
    if indicator_count:
        parsed_query["indicators"] = selector.indicators_for(
            family_id,
            intent,
            slots,
            indicator_count,
        )

    country_count = country_count_for_family(family_id, slots)
    if country_count:
        parsed_query["countries"] = selector.countries(country_count)

    if "country_groups" in bases:
        parsed_query["country_groups"] = [selector.country_group(parser_enums)]

    start_year, end_year, relative_time, event_time = choose_years(family_id, slots, config, rng)
    parsed_query["start_year"] = start_year
    parsed_query["end_year"] = end_year
    parsed_query["relative_time"] = relative_time
    parsed_query["event_time"] = event_time

    default_aggregation = family.get("default_aggregation")
    if default_aggregation is not None:
        parsed_query["aggregation"] = default_aggregation

    if intent == "LATEST_VALUE":
        parsed_query["relative_time"] = "latest"
        parsed_query["aggregation"] = "latest"
        parsed_query["start_year"] = None
        parsed_query["end_year"] = None

    if intent == "RANKING":
        parsed_query["limit"] = rng.choice(config["ranking_policy"]["top_n_values"])
        parsed_query["ranking_order"] = "asc" if family_id == "ranking_bottom_n" else "desc"
        if parsed_query["start_year"] is None:
            year = rng.choice(config["year_policy"]["common_single_years"])
            parsed_query["start_year"] = year
            parsed_query["end_year"] = year
        parsed_query["chart_preference"] = "bar"

    if intent == "RANK_BY_CHANGE":
        if parsed_query["start_year"] is None or parsed_query["end_year"] is None:
            parsed_query["start_year"], parsed_query["end_year"] = rng.choice(
                config["year_policy"]["common_periods"]
            )
        parsed_query["aggregation"] = "pct_change" if "pct" in family_id else "change"
        parsed_query["ranking_order"] = "asc" if "decrease" in family_id else "desc"
        parsed_query["limit"] = rng.choice(config["ranking_policy"]["top_n_values"])
        parsed_query["chart_preference"] = "bar"

    if "threshold" in bases or "threshold" in family_id:
        if "anomaly" in family_id:
            parsed_query["threshold"] = rng.choice(config["threshold_policy"]["anomaly_thresholds"])
        elif "debt" in family_id:
            parsed_query["threshold"] = rng.choice(config["threshold_policy"]["debt_thresholds"])
        elif "inflation" in family_id:
            parsed_query["threshold"] = rng.choice(config["threshold_policy"]["inflation_thresholds"])
        else:
            parsed_query["threshold"] = rng.choice([5, 10, 20, 0.75])

    if family_id.startswith("conditional_filter") or "conditions" in bases or "condition" in bases:
        if not parsed_query["indicators"]:
            parsed_query["indicators"] = selector.indicators_for(family_id, intent, slots, 1)
        if parsed_query["threshold"] is None:
            parsed_query["threshold"] = rng.choice([5, 10, 20])
        render_context["condition"] = f"{parsed_query['indicators'][0]} > {parsed_query['threshold']}"

    if intent.startswith("CLUSTER"):
        cluster_years = config["analytics_metadata"]["cluster"]["target_years"]
        if "transition" in family_id or "period" in family_id:
            parsed_query["start_year"] = cluster_years[1]
            parsed_query["end_year"] = cluster_years[-1]
        else:
            year = rng.choice(cluster_years)
            parsed_query["start_year"] = year
            parsed_query["end_year"] = year

    if family_id == "indicator_catalog_by_theme":
        render_context["theme"] = rng.choice(
            ["growth_dynamics", "fiscal_monetary", "crisis_risk", "social_welfare", "structural_composition"]
        )
    elif intent == "THEME_SUMMARY":
        render_context["theme"] = family_id.replace("theme_summary_", "")

    if family_id == "follow_up_change_chart":
        render_context["chart_type"] = rng.choice(["line", "bar", "table", "scatter"])
    if intent == "FOLLOW_UP":
        render_context["context_ref"] = rng.choice(["truy vấn trước", "kết quả vừa rồi", "so sánh đó"])
    if intent == "VISUALIZATION_REQUEST":
        if "line" in family_id:
            render_context["chart_type"] = "line"
        elif "bar" in family_id:
            render_context["chart_type"] = "bar"
        elif "table" in family_id:
            render_context["chart_type"] = "table"
        elif "json" in family_id:
            render_context["output_format"] = "json"
        elif "csv" in family_id:
            render_context["output_format"] = "csv"
        elif "short" in family_id:
            render_context["output_format"] = "short summary"
        elif "paragraph" in family_id:
            render_context["output_format"] = "report paragraph"


def make_constraints(family, parsed_query, indicator_by_code):
    family_id = family["id"]
    intent = family["intent"]
    slots = family["required_slots"]
    requires_anomaly = intent in {"ANOMALY_DETECTION", "ANOMALY_EXPLANATION"} or "anomaly" in family_id
    requires_analytics = requires_anomaly or intent == "TREND_ANALYSIS" or "analytics" in family_id
    requires_cluster = intent.startswith("CLUSTER") or "cluster" in family_id
    if parsed_query["indicators"]:
        requires_analytics = requires_analytics or any(
            indicator_by_code[code]["supports_trend"] or indicator_by_code[code]["supports_anomaly"]
            for code in parsed_query["indicators"]
        )
    return {
        "requires_analytics": bool(requires_analytics),
        "requires_anomaly": bool(requires_anomaly),
        "requires_cluster": bool(requires_cluster),
        "requires_multi_country": any(slot.startswith("countries>=") for slot in slots)
        or len(parsed_query["countries"]) >= 2,
        "requires_multi_indicator": any(slot.startswith("indicators>=") for slot in slots)
        or len(parsed_query["indicators"]) >= 2,
    }


def build_report(plans):
    sample_by_intent = Counter()
    groups_by_intent = Counter()
    sample_by_family = Counter()
    groups_by_family = Counter()
    sample_by_bucket = Counter()
    indicator_counts = Counter()
    country_counts = Counter()
    analytics_counts = Counter()

    for plan in plans:
        samples = plan["target_sample_count"]
        sample_by_intent[plan["intent"]] += samples
        groups_by_intent[plan["intent"]] += 1
        sample_by_family[plan["question_family"]] += samples
        groups_by_family[plan["question_family"]] += 1
        sample_by_bucket[plan["generation_bucket"]] += samples
        for indicator in plan["parsed_query"]["indicators"]:
            indicator_counts[indicator] += 1
        for country in plan["parsed_query"]["countries"]:
            country_counts[country] += 1
        for key, value in plan["constraints"].items():
            if key in {"requires_analytics", "requires_anomaly", "requires_cluster"} and value:
                analytics_counts[key] += 1

    return {
        "version": "v1",
        "total_base_plan_groups": len(plans),
        "total_target_samples": sum(plan["target_sample_count"] for plan in plans),
        "target_samples_by_intent": dict(sorted(sample_by_intent.items())),
        "plan_groups_by_intent": dict(sorted(groups_by_intent.items())),
        "target_samples_by_family": dict(sorted(sample_by_family.items())),
        "plan_groups_by_family": dict(sorted(groups_by_family.items())),
        "target_samples_by_generation_bucket": dict(sorted(sample_by_bucket.items())),
        "indicator_coverage": {
            "unique_indicators_used": len(indicator_counts),
            "top_indicators": indicator_counts.most_common(20),
        },
        "country_coverage": {
            "unique_countries_used": len(country_counts),
            "top_countries": country_counts.most_common(20),
        },
        "analytics_plan_counts": {
            "requires_analytics": analytics_counts["requires_analytics"],
            "requires_anomaly": analytics_counts["requires_anomaly"],
            "requires_cluster": analytics_counts["requires_cluster"],
        },
    }


def main():
    parsed_schema = load_json("parsed_query_schema.v1.json")
    parser_intents = load_json("parser_intents.v1.json")
    parser_enums = load_json("parser_enums.v1.json")
    question_families = load_json("question_families.v1.json")
    dataset_distribution = load_json("dataset_distribution.v1.json")
    country_catalog = load_json("country_catalog.v1.json")
    indicator_catalog = load_json("indicator_catalog.v1.json")
    analytics_metadata = load_json("analytics_metadata.v1.json")
    question_templates = load_json("question_templates.v1.json")
    config = load_json("base_plan_generation.v1.json")
    config["analytics_metadata"] = analytics_metadata

    if config["target_total_samples"] != dataset_distribution["target_total_samples"]:
        raise SystemExit("base_plan_generation target_total_samples does not match dataset_distribution")
    if config["generation_buckets"] != dataset_distribution["generation_mix"]:
        raise SystemExit("base_plan_generation generation_buckets does not match dataset_distribution")
    if set(parsed_schema["required"]) != set(PARSED_QUERY_FIELDS):
        raise SystemExit("parsed query field contract changed; update generator")

    rng = random.Random(config["random_seed"])
    families = question_families["families"]
    families_by_intent = defaultdict(list)
    for family in families:
        families_by_intent[family["intent"]].append(family)

    family_targets = {}
    for intent in parser_intents:
        family_targets.update(
            weighted_targets(
                families_by_intent[intent],
                dataset_distribution["intent_targets"][intent],
                config["family_weight_policy"],
            )
        )

    selector = Selector(
        country_catalog["countries"],
        indicator_catalog["indicators"],
        analytics_metadata,
        rng,
    )
    indicator_by_code = {indicator["code"]: indicator for indicator in indicator_catalog["indicators"]}

    forced_off = dataset_distribution["intent_targets"]["OFF_TOPIC"] + dataset_distribution["intent_targets"]["UNSUPPORTED"]
    forced_hard = dataset_distribution["intent_targets"]["NEED_CLARIFICATION"]
    ordinary_total = config["target_total_samples"] - forced_off - forced_hard
    ordinary_targets = {
        "deterministic_template": int(round(ordinary_total * 0.65)),
        "llm_paraphrase": int(round(ordinary_total * 0.30)),
        "hard_cases": forced_hard + int(round(ordinary_total * 0.05)),
    }
    ordinary_targets["deterministic_template"] += (
        config["target_total_samples"]
        - forced_off
        - sum(ordinary_targets.values())
    )
    bucket_totals = Counter()
    plans = []

    for family in families:
        family_target = family_targets[family["id"]]
        for sample_count in split_target_samples(
            family_target,
            config["target_samples_per_plan"]["default"],
        ):
            parsed_query = default_parsed_query(
                family["intent"],
                family["id"],
                family["default_chart_preference"],
            )
            render_context = default_render_context()
            apply_family_rules(parsed_query, render_context, family, selector, parser_enums, config, rng)
            set_render_from_query(render_context, parsed_query)

            if render_context["period_1"] is None:
                render_context["period_1"] = (
                    f"{parsed_query['start_year']}-{parsed_query['end_year']}"
                    if parsed_query["start_year"] is not None and parsed_query["end_year"] is not None
                    else None
                )
            if render_context["period_2"] is None and family["id"] in {
                "compare_periods_single_country",
                "compare_decades",
                "compare_recent_vs_historical",
                "compare_periods_multi_indicator",
            }:
                render_context["period_1"] = "2000-2010"
                render_context["period_2"] = "2011-2023"
            if render_context["condition"] is None and "condition" in {slot_base(slot) for slot in family["required_slots"]}:
                render_context["condition"] = "selected indicator threshold"
            if render_context["theme"] is None and "theme" in {slot_base(slot) for slot in family["required_slots"]}:
                render_context["theme"] = "growth_dynamics"

            constraints = make_constraints(family, parsed_query, indicator_by_code)
            bucket = choose_bucket(family["intent"], sample_count, bucket_totals, ordinary_targets)

            plans.append(
                {
                    "plan_group_id": f"bp_{len(plans) + 1:06d}",
                    "version": "v1",
                    "intent": family["intent"],
                    "question_family": family["id"],
                    "priority": family["priority"],
                    "generation_bucket": bucket,
                    "target_sample_count": sample_count,
                    "parsed_query": {field: parsed_query[field] for field in PARSED_QUERY_FIELDS},
                    "render_context": {field: render_context[field] for field in RENDER_CONTEXT_FIELDS},
                    "constraints": constraints,
                }
            )

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    with BASE_PLANS_PATH.open("w", encoding="utf-8", newline="\n") as file:
        for plan in plans:
            file.write(json.dumps(plan, ensure_ascii=False, separators=(",", ":")) + "\n")

    report = build_report(plans)
    with REPORT_PATH.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")

    print(f"wrote {BASE_PLANS_PATH}")
    print(f"wrote {REPORT_PATH}")
    print(f"total base plan groups: {len(plans)}")
    print(f"total target samples: {report['total_target_samples']}")


if __name__ == "__main__":
    main()
