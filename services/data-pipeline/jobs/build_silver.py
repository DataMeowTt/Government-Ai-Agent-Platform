from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from config.settings import settings
from pipeline.silver_paths import resolve_silver_inputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build local silver_indicators from WDI/GMD/FAO-Macro sources."
    )
    parser.add_argument("--source", default="all", choices=["all", "wdi", "gmd", "fao_macro"])
    parser.add_argument("--wdi-path", default=None)
    parser.add_argument("--gmd-path", default=None)
    parser.add_argument("--fao-macro-path", default=None)
    parser.add_argument("--output-dir", default="../../tmp/silver_local_output")
    parser.add_argument("--output-format", default="parquet", choices=["parquet", "csv"])
    parser.add_argument("--run-id", default=settings.run_id)
    parser.add_argument("--run-date", default=settings.run_date)
    parser.add_argument("--spark-master", default="local[*]")
    parser.add_argument("--registry-path", default=None)
    parser.add_argument("--fixture", action="store_true")
    return parser.parse_args()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_fixture_sources(root: Path) -> dict[str, str]:
    years = [str(year) for year in range(1980, 2026)]
    indicators = [
        "Unemployment, total (% of total labor force) (modeled ILO estimate)",
        "Unemployment, youth total (% of total labor force ages 15-24) (modeled ILO estimate)",
        "Self-employed, total (% of total employment) (modeled ILO estimate)",
        "Urban population (% of total population)",
        "Urban population growth (annual %)",
        "Population density (people per sq. km of land area)",
        "Population growth (annual %)",
        "Inflation, consumer prices (annual %)",
        "Inflation, GDP deflator (annual %)",
        "Poverty headcount ratio at $3.00 a day (2021 PPP) (% of population)",
        "Trade (% of GDP)",
        "Imports of goods and services (current US$)",
        "Exports of goods and services (% of GDP)",
        "Tax revenue (% of GDP)",
        "GDP (current US$)",
        "GDP growth (annual %)",
        "GDP per capita (current US$)",
        "GDP per capita growth (annual %)",
    ]
    wdi_root = root / "worldBank"
    wdi_root.mkdir(parents=True, exist_ok=True)
    with (wdi_root / "WDICSV.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Country Name", "Country Code", "Indicator Name", "Indicator Code", *years])
        for idx, indicator in enumerate(indicators):
            values = [""] * len(years)
            values[years.index("2000")] = str(1.0 + idx)
            writer.writerow(["Viet Nam", "VNM", indicator, f"CODE{idx:03d}", *values])

    gmd_root = root / "gmd"
    _write_text(
        gmd_root / "GMD.csv",
        "countryname,ISO3,year,rGDP,rGDP_pc_USD,hcons_GDP,govdebt_GDP,govtax_GDP,SovDebtCrisis,CurrencyCrisis,BankingCrisis,exports_GDP,imports_GDP,govrev_GDP,govexp_GDP,ltrate,infl,REER,hcons_USD,income_group\n"
        "Viet Nam,VNM,2000,100,1200,50,40,10,0,0,0,60,55,20,22,8,5,101,500,Lower middle income\n",
    )

    macro_root = root / "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized)"
    macro_rows = [
        "Viet Nam,22008,2000,1000",
        "Viet Nam,22015,2000,250",
        "Viet Nam,22011,2000,980",
        "Viet Nam,22016,2000,180",
        "Viet Nam,22075,2000,320",
        "Viet Nam,22076,2000,120",
    ]
    _write_text(
        macro_root / "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized).csv",
        "Area,Item Code,Year,Value,Flag\n"
        + "\n".join([f"{line},A" for line in macro_rows])
        + "\n",
    )

    return {
        "wdi": str(wdi_root / "WDICSV.csv"),
        "gmd": str(gmd_root / "GMD.csv"),
        "fao_macro": str(
            macro_root / "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized).csv"
        ),
    }


def _build_manifest(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    silver_output_path: Path,
    input_paths: dict[str, str],
    validation_summary: dict,
) -> dict:
    return {
        "run_id": args.run_id,
        "run_date": args.run_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": args.source,
        "output_format": args.output_format,
        "spark_master": args.spark_master,
        "input_paths": input_paths,
        "silver_output_path": str(silver_output_path.resolve()),
        "manifest_path": str((output_dir / "silver_manifest.json").resolve()),
        "validation_summary": validation_summary,
    }


def main() -> int:
    args = parse_args()
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
    from pyspark.sql import SparkSession
    from pipeline.job import build_source_frames, save_output, union_source_frames
    from pipeline.silver_validate import validate_silver

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    silver_output_path = output_dir / "silver_indicators"

    with TemporaryDirectory(prefix="silver_fixture_") as fixture_dir:
        if args.fixture:
            input_paths = _build_fixture_sources(Path(fixture_dir))
        else:
            input_paths = resolve_silver_inputs(
                registry_path=args.registry_path,
                wdi_override=args.wdi_path,
                gmd_override=args.gmd_path,
                fao_macro_override=args.fao_macro_path,
            )

        spark = (
            SparkSession.builder
            .appName("GovernmentAI-SilverLocal")
            .master(args.spark_master)
            .config("spark.sql.shuffle.partitions", "4")
            .config("spark.sql.ansi.enabled", "false")
            .getOrCreate()
        )
        spark.sparkContext.setLogLevel("WARN")
        try:
            source_filter = ["wdi", "gmd", "fao_macro"] if args.source == "all" else [args.source]
            frames = build_source_frames(
                spark,
                wdi_path=input_paths["wdi"] if "wdi" in source_filter else None,
                gmd_path=input_paths["gmd"] if "gmd" in source_filter else None,
                macro_path=input_paths["fao_macro"] if "fao_macro" in source_filter else None,
                run_id=args.run_id,
                run_date=args.run_date,
            )
            union_df = union_source_frames(frames)
            validation_summary = validate_silver(union_df)
            save_output(union_df, str(silver_output_path), args.output_format)
        except Exception as exc:
            if args.output_format == "parquet":
                raise RuntimeError(
                    "Parquet build failed for local silver. Re-run with --output-format csv for debug fallback."
                ) from exc
            raise
        finally:
            spark.stop()

    manifest = _build_manifest(
        args=args,
        output_dir=output_dir,
        silver_output_path=silver_output_path,
        input_paths=input_paths,
        validation_summary=validation_summary,
    )
    manifest_path = output_dir / "silver_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
