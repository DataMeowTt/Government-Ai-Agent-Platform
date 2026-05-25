from __future__ import annotations

import io
import json
import sys
import zipfile
from argparse import Namespace
from pathlib import Path

import pandas as pd
import pytest

from jobs.fetch_official_sources import main as fetch_main
from jobs.fetch_official_sources import _selected_sources, decide_source_change, run_acquisition
from sources.faostat_macro import FAO_REQUIRED_FILES, default_fetch_catalog, materialize_fao_macro
from sources.global_macro_database import materialize_gmd
from sources.official_acquisition import AcquisitionError
from sources.world_bank_wdi import WDI_REQUIRED_FILES, default_wdi_archive_resolver, materialize_wdi


def _zip_bytes(file_map: dict[str, str]) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in file_map.items():
            archive.writestr(name, text)
    return bio.getvalue()


def test_wdi_fixture_zip_materializes_and_records_mapping(tmp_path: Path) -> None:
    payload = _zip_bytes(
        {
            "x/WDICSV.csv": "Country Name,Country Code,Indicator Name,Indicator Code,1960\nA,AAA,I,IC,1\n",
            "x/WDICountry.csv": "Country Code,Country Name\nAAA,A\n",
            "x/WDISeries.csv": "Series Code,Indicator Name\nIC,I\n",
            "x/WDIfootnote.csv": "k,v\n1,2\n",
        }
    )
    entry = materialize_wdi(runtime_raw_dir=tmp_path, allow_network=True, resolve_archive_url=lambda: "https://example/wdi.zip", download_bytes=lambda _: payload)
    assert entry["validation_status"] == "valid"
    assert sorted(entry["required_files"]) == sorted(WDI_REQUIRED_FILES)
    assert entry["upstream_to_runtime_filename_mapping"]["x/WDICSV.csv"] == "WDICSV.csv"


def test_wdi_invalid_payload_fails_safely(tmp_path: Path) -> None:
    with pytest.raises(AcquisitionError):
        materialize_wdi(runtime_raw_dir=tmp_path, allow_network=True, resolve_archive_url=lambda: "x", download_bytes=lambda _: b"<html>bad</html>")


def test_wdi_missing_required_member_fails(tmp_path: Path) -> None:
    payload = _zip_bytes({"WDICSV.csv": "a,b\n1,2\n", "WDICountry.csv": "a,b\n1,2\n"})
    with pytest.raises(AcquisitionError):
        materialize_wdi(runtime_raw_dir=tmp_path, allow_network=True, resolve_archive_url=lambda: "x", download_bytes=lambda _: payload)


def test_default_wdi_archive_resolver_points_to_public_bulk_endpoint() -> None:
    resolved = default_wdi_archive_resolver()
    assert resolved == "https://databank.worldbank.org/data/download/WDI_CSV.zip"


def test_fao_selects_mk_and_uses_catalog_file_location(tmp_path: Path) -> None:
    payload = _zip_bytes({name: "c1,c2\n1,2\n" for name in FAO_REQUIRED_FILES})
    seen: list[str] = []

    def fake_download(url: str) -> bytes:
        seen.append(url)
        return payload

    entry = materialize_fao_macro(
        runtime_raw_dir=tmp_path,
        allow_network=True,
        fetch_catalog=lambda: [{"DatasetCode": "MK", "DatasetName": "Macro-Economic Indicators", "DateUpdate": "2026-05-01", "FileLocation": "https://example/mk.zip"}],
        download_bytes=fake_download,
    )
    assert seen == ["https://example/mk.zip"]
    assert entry["catalog_metadata"]["DatasetCode"] == "MK"
    assert entry["catalog_metadata"]["DateUpdate"] == "2026-05-01"


def test_fao_missing_codebook_fails(tmp_path: Path) -> None:
    partial = [name for name in FAO_REQUIRED_FILES if "Flags" not in name]
    payload = _zip_bytes({name: "c1,c2\n1,2\n" for name in partial})
    with pytest.raises(AcquisitionError):
        materialize_fao_macro(
            runtime_raw_dir=tmp_path,
            allow_network=True,
            fetch_catalog=lambda: [{"DatasetCode": "MK", "DatasetName": "Macro-Economic Indicators", "FileLocation": "https://example/mk.zip"}],
            download_bytes=lambda _: payload,
        )


def test_default_fetch_catalog_parses_current_nested_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    from sources import faostat_macro as mod

    payload = {
        "Datasets": {
            "-xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "Dataset": [
                {"DatasetCode": "MK", "DatasetName": "Macro-Economic Indicators", "FileLocation": "https://example/mk.zip"}
            ],
        }
    }

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(mod, "urlopen", lambda *_args, **_kwargs: _Resp())
    entries = default_fetch_catalog()
    assert entries[0]["DatasetCode"] == "MK"


def test_gmd_materializes_full_dataset_and_src(tmp_path: Path) -> None:
    calls: list[bool] = []

    def fake_gmd(*, show_preview: bool):
        calls.append(show_preview)
        return pd.DataFrame({"countryname": ["A"], "iso3": ["AAA"], "year": [2000]})

    entry = materialize_gmd(runtime_raw_dir=tmp_path, allow_network=True, gmd_callable=fake_gmd, retrieved_version="vX")
    assert calls == [False]
    assert (tmp_path / "gmd" / "GMD.csv").exists()
    src = (tmp_path / "gmd" / "src.txt").read_text(encoding="utf-8")
    assert "resolved_or_retrieved_version: vX" in src
    assert "CC BY-NC-SA 4.0" in src
    assert entry["validation_status"] == "valid"


def test_gmd_empty_dataset_fails(tmp_path: Path) -> None:
    with pytest.raises(AcquisitionError):
        materialize_gmd(runtime_raw_dir=tmp_path, allow_network=True, gmd_callable=lambda **_: pd.DataFrame())


def test_gmd_package_missing_produces_clear_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sources import global_macro_database as mod

    monkeypatch.setattr(mod, "_import_gmd_callable", lambda: (_ for _ in ()).throw(Exception("missing")))
    with pytest.raises(AcquisitionError):
        mod.materialize_gmd(runtime_raw_dir=tmp_path, allow_network=True)


def test_gmd_loader_fallback_without_show_preview_keyword(tmp_path: Path) -> None:
    calls: list[str] = []

    def fallback_loader(**kwargs):
        if kwargs:
            calls.append("with_kwargs")
            raise TypeError("Unexpected keyword argument(s): show_preview")
        calls.append("no_kwargs")
        return pd.DataFrame({"countryname": ["A"], "iso3": ["AAA"], "year": [2000]})

    entry = materialize_gmd(runtime_raw_dir=tmp_path, allow_network=True, gmd_callable=fallback_loader)
    assert calls == ["with_kwargs", "no_kwargs"]
    assert entry["validation_status"] == "valid"


def test_selected_sources_default_and_all_behavior() -> None:
    assert _selected_sources(None) == ["wdi", "fao_macro", "gmd"]
    assert _selected_sources([]) == ["wdi", "fao_macro", "gmd"]
    assert _selected_sources(["all"]) == ["wdi", "fao_macro", "gmd"]
    assert _selected_sources(["all", "wdi"]) == ["wdi", "fao_macro", "gmd"]


def test_selected_sources_single_and_multi_explicit_behavior() -> None:
    assert _selected_sources(["wdi"]) == ["wdi"]
    assert _selected_sources(["fao_macro"]) == ["fao_macro"]
    assert _selected_sources(["gmd"]) == ["gmd"]
    assert _selected_sources(["wdi", "gmd"]) == ["wdi", "gmd"]
    assert _selected_sources(["wdi", "wdi", "gmd"]) == ["wdi", "gmd"]


def test_parse_args_source_default_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import jobs.fetch_official_sources as mod

    argv = [
        "fetch_official_sources.py",
        "--mode",
        "plan",
        "--runtime-raw-dir",
        str(tmp_path / "runtime"),
        "--output-dir",
        str(tmp_path / "out"),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    args = mod.parse_args()
    assert args.source is None


def _decision_from_manifest(manifest: dict) -> dict:
    return decide_source_change(mode="dry_run", candidate_manifest=manifest, baseline_path=None)


def _assert_acquisition_failed_decision(decision: dict) -> None:
    assert decision["candidate_status"] == "ACQUISITION_FAILED"
    assert decision["source_changed"] is None
    assert decision["changed_sources"] == []
    assert decision["should_build_downstream"] is False


def test_wdi_runtime_exception_yields_acquisition_failed_decision(tmp_path: Path) -> None:
    args = Namespace(
        run_id="r-wdi",
        run_date="2026-05-24",
        mode="dry_run",
        runtime_raw_dir=str(tmp_path / "runtime"),
        allow_network=True,
    )

    def wdi_fail(**kwargs) -> dict:
        return materialize_wdi(
            runtime_raw_dir=kwargs["runtime_raw_dir"],
            allow_network=kwargs["allow_network"],
            resolve_archive_url=lambda: (_ for _ in ()).throw(TimeoutError("timeout")),
        )

    manifest, errors = run_acquisition(args=args, selected_sources=["wdi"], wdi_fn=wdi_fail)
    assert manifest["status"] == "acquisition_failed"
    assert len(errors) == 1
    _assert_acquisition_failed_decision(_decision_from_manifest(manifest))


def test_fao_runtime_exception_yields_acquisition_failed_decision(tmp_path: Path) -> None:
    args = Namespace(
        run_id="r-fao",
        run_date="2026-05-24",
        mode="dry_run",
        runtime_raw_dir=str(tmp_path / "runtime"),
        allow_network=True,
    )

    def fao_fail(**kwargs) -> dict:
        return materialize_fao_macro(
            runtime_raw_dir=kwargs["runtime_raw_dir"],
            allow_network=kwargs["allow_network"],
            fetch_catalog=lambda: (_ for _ in ()).throw(RuntimeError("catalog down")),
        )

    manifest, errors = run_acquisition(args=args, selected_sources=["fao_macro"], fao_fn=fao_fail)
    assert manifest["status"] == "acquisition_failed"
    assert len(errors) == 1
    _assert_acquisition_failed_decision(_decision_from_manifest(manifest))


def test_gmd_runtime_exception_yields_acquisition_failed_decision_and_uses_full_loader(tmp_path: Path) -> None:
    args = Namespace(
        run_id="r-gmd",
        run_date="2026-05-24",
        mode="dry_run",
        runtime_raw_dir=str(tmp_path / "runtime"),
        allow_network=True,
    )
    calls: list[bool] = []

    def bad_loader(*, show_preview: bool):
        calls.append(show_preview)
        raise RuntimeError("package failure")

    def gmd_fail(**kwargs) -> dict:
        return materialize_gmd(
            runtime_raw_dir=kwargs["runtime_raw_dir"],
            allow_network=kwargs["allow_network"],
            gmd_callable=bad_loader,
        )

    manifest, errors = run_acquisition(args=args, selected_sources=["gmd"], gmd_fn=gmd_fail)
    assert calls == [False]
    assert manifest["status"] == "acquisition_failed"
    assert len(errors) == 1
    _assert_acquisition_failed_decision(_decision_from_manifest(manifest))


def test_plan_mode_no_acquisition_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import jobs.fetch_official_sources as mod

    monkeypatch.setattr(mod, "materialize_wdi", lambda **_: (_ for _ in ()).throw(AssertionError("wdi called")))
    monkeypatch.setattr(mod, "materialize_fao_macro", lambda **_: (_ for _ in ()).throw(AssertionError("fao called")))
    monkeypatch.setattr(mod, "materialize_gmd", lambda **_: (_ for _ in ()).throw(AssertionError("gmd called")))

    runtime_raw = tmp_path / "runtime" / "raw"
    output_dir = tmp_path / "out"
    argv = [
        "fetch_official_sources.py",
        "--mode",
        "plan",
        "--source",
        "all",
        "--run-id",
        "plan-test",
        "--run-date",
        "2026-05-24",
        "--runtime-raw-dir",
        str(runtime_raw),
        "--output-dir",
        str(output_dir),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert fetch_main() == 0

    decision = json.loads((output_dir / "source_change_decision.json").read_text(encoding="utf-8"))
    assert decision == {
        "run_id": "plan-test",
        "run_date": "2026-05-24",
        "candidate_status": "PLANNED",
        "baseline_kind": "local_last_successful_manifest_input",
        "baseline_path": None,
        "source_changed": None,
        "changed_sources": [],
        "reason": "plan_only_no_acquisition",
        "should_build_downstream": False,
    }
    assert not runtime_raw.exists() or not any(runtime_raw.rglob("*"))


def test_global_macro_data_import_smoke() -> None:
    from global_macro_data import gmd

    assert callable(gmd)
