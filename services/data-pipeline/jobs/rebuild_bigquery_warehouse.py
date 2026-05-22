from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from warehouse.bigquery_warehouse_publish import (
    DEFAULT_APPROVAL_ENV,
    publish_with_staging,
    require_write_approval,
    save_write_results,
)
from warehouse.bigquery_warehouse_rebuild import (
    DEFAULT_MAX_VALIDATION_BYTES,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SILVER_TABLE,
    EXPECTED_SILVER_ROW_COUNT,
    run_warehouse_rebuild,
)
from warehouse.bigquery_warehouse_validation import get_table_contract_columns, load_table_contract


DEFAULT_PROJECT_ID = "western-pivot-452008-a6"
DEFAULT_LOCATION = "asia-southeast1"


def _summary_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for item in payload.get("gold_summary", []):
        mapping[item["table_name"]] = item
    for item in payload.get("analytics_summary", []):
        mapping[item["table_name"]] = item
    return mapping


def _required_columns_for_table(contract: dict[str, Any], dataset: str, table_name: str) -> list[str]:
    if dataset == "gov_ai_gold":
        columns = get_table_contract_columns(contract, "gold", table_name)
    else:
        columns = get_table_contract_columns(contract, "analytics", table_name)
    if columns:
        return columns
    if table_name == "analytics_clusters":
        return [
            "country_code",
            "country",
            "year",
            "cluster_id",
            "latest_valid_year",
            "run_id",
            "run_date",
            "loaded_at",
        ]
    return ["country_code", "country", "year", "run_id", "run_date", "loaded_at"]


def _publish_if_requested(
    *,
    execute: bool,
    approval_env: str,
    project_id: str,
    location: str,
    rebuild_payload: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "execute_requested": execute,
        "approval_env": approval_env,
        "approved": False,
        "write_blocked": False,
        "writes": [],
    }
    if not execute:
        result["write_blocked"] = True
        result["reason"] = "execute flag is not set; dry-run only."
        return result

    try:
        _ = require_write_approval(approval_env)
    except Exception as exc:
        result["write_blocked"] = True
        result["reason"] = str(exc)
        return result

    result["approved"] = True
    repo_root = Path(__file__).resolve().parents[3]
    contract = load_table_contract(repo_root / "contracts" / "table_contract.yaml")
    summary_by_table = _summary_map(rebuild_payload)
    for table_plan in rebuild_payload["publish_plan"]["tables"]:
        table_name = table_plan["production_table"]
        dataset = table_plan["dataset"]
        summary = summary_by_table[table_name]
        parquet_path = Path(summary["parquet_path"])
        local_df = pd.read_parquet(parquet_path)
        write_result = publish_with_staging(
            project_id=project_id,
            location=location,
            dataset=dataset,
            staging_table=table_plan["staging_table"],
            production_table=table_name,
            parquet_path=parquet_path,
            expected_required_columns=_required_columns_for_table(contract, dataset, table_name),
            local_row_count=int(len(local_df)),
        )
        result["writes"].append(
            {
                "dataset": write_result.dataset,
                "staging_table": write_result.staging_table,
                "production_table": write_result.production_table,
                "staging_table_id": write_result.staging_table_id,
                "production_table_id": write_result.production_table_id,
                "write_disposition": write_result.write_disposition,
                "local_row_count": write_result.local_row_count,
                "staging_row_count": write_result.staging_row_count,
                "production_row_count": write_result.production_row_count,
                "load_job_id": write_result.load_job_id,
                "copy_job_id": write_result.copy_job_id,
                "staging_columns": write_result.staging_columns,
            }
        )

    save_write_results(output_dir / "publish_result.json", result)
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild Gold + Analytics warehouse from BigQuery Silver with optional staging publish."
    )
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--location", default=DEFAULT_LOCATION)
    parser.add_argument("--silver-table", default=DEFAULT_SILVER_TABLE)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--expected-silver-row-count", type=int, default=EXPECTED_SILVER_ROW_COUNT)
    parser.add_argument("--max-validation-bytes", type=int, default=DEFAULT_MAX_VALIDATION_BYTES)
    parser.add_argument("--approval-env", default=DEFAULT_APPROVAL_ENV)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.dry_run and args.execute:
        raise SystemExit("--dry-run and --execute cannot be used together.")

    output_dir = Path(args.output_dir).expanduser().resolve()
    rebuild_payload = run_warehouse_rebuild(
        project_id=args.project_id,
        location=args.location,
        silver_table_id=args.silver_table,
        output_dir=output_dir,
        expected_silver_row_count=args.expected_silver_row_count,
        max_validation_bytes=args.max_validation_bytes,
    )
    publish_payload = _publish_if_requested(
        execute=args.execute,
        approval_env=args.approval_env,
        project_id=args.project_id,
        location=args.location,
        rebuild_payload=rebuild_payload,
        output_dir=output_dir,
    )
    final_payload = {
        **rebuild_payload,
        "publish": publish_payload,
    }
    (output_dir / "warehouse_rebuild_result.json").write_text(
        json.dumps(final_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(final_payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

