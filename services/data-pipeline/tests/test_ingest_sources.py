from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_DIR = REPO_ROOT / "services" / "data-pipeline"


def _run_ingest(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "jobs.ingest_sources", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _create_fixture_sources(tmp_path: Path) -> dict[str, Path]:
    wdi_root = tmp_path / "worldBank"
    _write_text(
        wdi_root / "WDICSV.csv",
        "Country Name,Country Code,Indicator Name,Indicator Code,1960,1961\n"
        "Testland,TST,GDP growth,NY.GDP.MKTP.KD.ZG,1.0,2.0\n",
    )
    _write_text(wdi_root / "WDICountry.csv", "Country Code,Country Name\nTST,Testland\n")
    _write_text(wdi_root / "WDISeries.csv", "Series Code,Indicator Name\nNY.GDP.MKTP.KD.ZG,GDP growth\n")
    _write_text(wdi_root / "WDIfootnote.csv", "Footnote,Value\nA,1\n")

    gmd_root = tmp_path / "gmd"
    _write_text(
        gmd_root / "GMD.csv",
        "countryname,iso3,year,govdebt_GDP,govexp_GDP,govrev_GDP\n"
        "Testland,TST,2000,10.0,20.0,15.0\n",
    )
    _write_text(gmd_root / "src.txt", "GMD source and license note\n")

    fao_root = tmp_path / "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized)"
    _write_text(
        fao_root / "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized).csv",
        "Area,Item,Element,Year,Unit,Value,Flag,Note\n"
        "Testland,GDP,Value,2000,USD,100,A,Sample\n",
    )
    _write_text(
        fao_root / "Macro-Statistics_Key_Indicators_E_AreaCodes.csv",
        "Area Code,Area\n001,Testland\n",
    )
    _write_text(
        fao_root / "Macro-Statistics_Key_Indicators_E_Elements.csv",
        "Element Code,Element\n001,Value\n",
    )
    _write_text(
        fao_root / "Macro-Statistics_Key_Indicators_E_Flags.csv",
        "Flag,Description\nA,Sample\n",
    )
    _write_text(
        fao_root / "Macro-Statistics_Key_Indicators_E_ItemCodes.csv",
        "Item Code,Item\n001,GDP\n",
    )

    return {
        "wdi_root": wdi_root,
        "gmd_csv": gmd_root / "GMD.csv",
        "fao_root": fao_root,
    }


def _write_registry(tmp_path: Path, *, wdi_root: Path, gmd_csv: Path, fao_root: Path) -> Path:
    registry_path = tmp_path / "source_registry.yaml"
    registry_path.write_text(
        "\n".join(
            [
                "sources:",
                "  - source_name: wdi",
                "    source_type: local_path",
                "    enabled: true",
                "    description: Test WDI fixture",
                "    license_note: Test WDI note",
                f"    local_path: {wdi_root.as_posix()}",
                "    output_format: csv",
                "  - source_name: gmd",
                "    source_type: local_path",
                "    enabled: true",
                "    description: Test GMD fixture",
                "    license_note: Test GMD note",
                f"    local_path: {gmd_csv.as_posix()}",
                "    output_format: csv",
                "  - source_name: fao_macro",
                "    source_type: local_path",
                "    enabled: true",
                "    description: Test FAO fixture",
                "    license_note: Test FAO note",
                f"    local_path: {fao_root.as_posix()}",
                "    output_format: csv",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return registry_path


def test_ingest_sources_help() -> None:
    result = _run_ingest(["--help"], PIPELINE_DIR)
    assert result.returncode == 0
    assert "Ingest configured sources" in result.stdout


def test_ingest_sources_local_fixture_creates_manifest_and_bronze_outputs(tmp_path: Path) -> None:
    fixture_paths = _create_fixture_sources(tmp_path)
    registry_path = _write_registry(
        tmp_path,
        wdi_root=fixture_paths["wdi_root"],
        gmd_csv=fixture_paths["gmd_csv"],
        fao_root=fixture_paths["fao_root"],
    )
    output_dir = tmp_path / "out"
    result = _run_ingest(
        [
            "--no-dry-run",
            "--source",
            "all",
            "--force",
            "--run-id",
            "local-ingest-test",
            "--run-date",
            "2026-05-18",
            "--output-dir",
            str(output_dir),
            "--registry-path",
            str(registry_path),
        ],
        PIPELINE_DIR,
    )

    assert result.returncode == 0, result.stderr

    source_manifest = json.loads((output_dir / "source_manifest.json").read_text(encoding="utf-8"))
    pipeline_manifest = json.loads((output_dir / "pipeline_manifest.json").read_text(encoding="utf-8"))
    ops_records = json.loads((output_dir / "ops_records.json").read_text(encoding="utf-8"))

    assert source_manifest["source_count"] == 3
    assert source_manifest["ingested_count"] == 3
    assert source_manifest["missing_count"] == 0
    assert source_manifest["should_run"] is True
    assert source_manifest["change_reason"] in {"force", "new_or_changed", "no_previous_manifest"}
    assert pipeline_manifest["source_count"] == 3
    assert ops_records["source_snapshots"]
    assert (output_dir / "bronze" / "wdi" / "run_date=2026-05-18" / "bronze_snapshot.json").exists()
    assert (output_dir / "bronze" / "wdi" / "run_date=2026-05-18" / "files" / "WDICSV.csv").exists()
    assert (output_dir / "bronze" / "gmd" / "run_date=2026-05-18" / "files" / "src.txt").exists()
    assert (
        output_dir
        / "bronze"
        / "fao_macro"
        / "run_date=2026-05-18"
        / "files"
        / "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized).csv"
    ).exists()
    assert source_manifest["sources"][0]["discovery_status"] == "present"
    assert source_manifest["sources"][1]["discovery_status"] == "present"
    assert source_manifest["sources"][2]["discovery_status"] == "present"
    assert source_manifest["sources"][0]["main_file_metadata"]["data_row_count"] == 1


def test_ingest_sources_reports_unchanged_with_previous_manifest(tmp_path: Path) -> None:
    fixture_paths = _create_fixture_sources(tmp_path)
    registry_path = _write_registry(
        tmp_path,
        wdi_root=fixture_paths["wdi_root"],
        gmd_csv=fixture_paths["gmd_csv"],
        fao_root=fixture_paths["fao_root"],
    )
    output_dir = tmp_path / "out"
    first_run = _run_ingest(
        [
            "--no-dry-run",
            "--source",
            "all",
            "--force",
            "--run-id",
            "local-ingest-first",
            "--run-date",
            "2026-05-18",
            "--output-dir",
            str(output_dir),
            "--registry-path",
            str(registry_path),
        ],
        PIPELINE_DIR,
    )
    assert first_run.returncode == 0, first_run.stderr

    second_run = _run_ingest(
        [
            "--dry-run",
            "--source",
            "all",
            "--run-id",
            "local-ingest-second",
            "--run-date",
            "2026-05-18",
            "--previous-manifest",
            str(output_dir / "source_manifest.json"),
            "--output-dir",
            str(output_dir / "second"),
            "--registry-path",
            str(registry_path),
        ],
        PIPELINE_DIR,
    )

    assert second_run.returncode == 0, second_run.stderr
    report = json.loads(second_run.stdout)
    assert report["should_run"] is False
    assert report["change_reason"] == "unchanged"
    assert report["source_manifest"]["skipped_count"] == 3


def test_ingest_sources_missing_required_file_reports_clearly(tmp_path: Path) -> None:
    wdi_root = tmp_path / "worldBank"
    _write_text(
        wdi_root / "WDICSV.csv",
        "Country Name,Country Code,Indicator Name,Indicator Code,1960\n"
        "Testland,TST,GDP growth,NY.GDP.MKTP.KD.ZG,1.0\n",
    )
    _write_text(wdi_root / "WDICountry.csv", "Country Code,Country Name\nTST,Testland\n")
    registry_path = _write_registry(
        tmp_path,
        wdi_root=wdi_root,
        gmd_csv=tmp_path / "gmd" / "GMD.csv",
        fao_root=tmp_path / "fao",
    )
    output_dir = tmp_path / "missing"
    result = _run_ingest(
        [
            "--no-dry-run",
            "--source",
            "wdi",
            "--force",
            "--run-id",
            "local-ingest-missing",
            "--run-date",
            "2026-05-18",
            "--output-dir",
            str(output_dir),
            "--registry-path",
            str(registry_path),
        ],
        PIPELINE_DIR,
    )

    assert result.returncode == 1
    assert "SOURCE INPUT REQUIRED" in result.stdout
    assert "WDISeries.csv" in result.stdout

    source_manifest = json.loads((output_dir / "source_manifest.json").read_text(encoding="utf-8"))
    assert source_manifest["missing_count"] == 1
    assert source_manifest["sources"][0]["discovery_status"] == "invalid"
