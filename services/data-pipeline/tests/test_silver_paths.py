from __future__ import annotations

from pathlib import Path

from pipeline.silver_paths import resolve_silver_inputs


def test_resolve_silver_inputs_from_registry() -> None:
    paths = resolve_silver_inputs(base_dir=Path.cwd())
    assert Path(paths["wdi"]).as_posix().endswith("data/raw/worldBank/WDICSV.csv")
    assert Path(paths["gmd"]).as_posix().endswith("data/raw/gmd/GMD.csv")
    assert Path(paths["fao_macro"]).as_posix().endswith(
        "data/raw/Macro-Statistics_Key_Indicators_E_All_Data_(Normalized)/Macro-Statistics_Key_Indicators_E_All_Data_(Normalized).csv"
    )


def test_resolve_silver_inputs_with_overrides(tmp_path: Path) -> None:
    wdi = tmp_path / "WDICSV.csv"
    gmd = tmp_path / "GMD.csv"
    macro = tmp_path / "Macro.csv"
    wdi.write_text("x\n", encoding="utf-8")
    gmd.write_text("x\n", encoding="utf-8")
    macro.write_text("x\n", encoding="utf-8")

    paths = resolve_silver_inputs(
        wdi_override=str(wdi),
        gmd_override=str(gmd),
        fao_macro_override=str(macro),
    )
    assert paths["wdi"] == str(wdi)
    assert paths["gmd"] == str(gmd)
    assert paths["fao_macro"] == str(macro)
