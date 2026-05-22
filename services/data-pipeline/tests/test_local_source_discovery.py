from __future__ import annotations

from pathlib import Path

from sources.local_discovery import discover_local_source


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_discover_wdi_folder_includes_required_and_optional_files(tmp_path: Path) -> None:
    root = tmp_path / "worldBank"
    _write_text(
        root / "WDICSV.csv",
        "Country Name,Country Code,Indicator Name,Indicator Code,1960,1961\n"
        "Testland,TST,GDP growth,NY.GDP.MKTP.KD.ZG,1.0,2.0\n",
    )
    _write_text(root / "WDICountry.csv", "Country Code,Country Name\nTST,Testland\n")
    _write_text(root / "WDISeries.csv", "Series Code,Indicator Name\nNY.GDP.MKTP.KD.ZG,GDP growth\n")
    _write_text(root / "WDIfootnote.csv", "Footnote,Value\nA,1\n")

    result = discover_local_source("wdi", root)

    assert result["status"] == "present"
    assert result["file_count"] == 4
    assert result["missing_required_files"] == []
    assert result["main_file_metadata"]["header_columns"][:4] == [
        "Country Name",
        "Country Code",
        "Indicator Name",
        "Indicator Code",
    ]
    assert result["main_file_metadata"]["data_row_count"] == 1
    assert result["main_file_metadata"]["sample_first_data_row"][0] == "Testland"
    assert [item["relative_path"] for item in result["files"]] == [
        "WDICSV.csv",
        "WDICountry.csv",
        "WDISeries.csv",
        "WDIfootnote.csv",
    ]


def test_discover_gmd_file_includes_optional_src_txt(tmp_path: Path) -> None:
    root = tmp_path / "gmd"
    _write_text(
        root / "GMD.csv",
        "countryname,iso3,year,govdebt_GDP\n"
        "Testland,TST,2000,10.0\n",
    )
    _write_text(root / "src.txt", "GMD source and license note\n")

    result = discover_local_source("gmd", root / "GMD.csv")

    assert result["status"] == "present"
    assert result["file_count"] == 2
    assert result["missing_required_files"] == []
    assert result["main_file_metadata"]["header_columns"] == [
        "countryname",
        "iso3",
        "year",
        "govdebt_GDP",
    ]
    assert result["main_file_metadata"]["data_row_count"] == 1
    assert result["main_file_metadata"]["sample_first_data_row"][0] == "Testland"
    assert [item["relative_path"] for item in result["files"]] == ["GMD.csv", "src.txt"]


def test_discover_fao_macro_folder_validates_codebooks(tmp_path: Path) -> None:
    root = tmp_path / "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized)"
    _write_text(
        root / "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized).csv",
        "Area,Item,Element,Year,Unit,Value,Flag,Note\n"
        "Testland,GDP,Value,2000,USD,100,A,Sample\n",
    )
    _write_text(
        root / "Macro-Statistics_Key_Indicators_E_AreaCodes.csv",
        "Area Code,Area\n001,Testland\n",
    )
    _write_text(
        root / "Macro-Statistics_Key_Indicators_E_Elements.csv",
        "Element Code,Element\n001,Value\n",
    )
    _write_text(
        root / "Macro-Statistics_Key_Indicators_E_Flags.csv",
        "Flag,Description\nA,Sample\n",
    )
    _write_text(
        root / "Macro-Statistics_Key_Indicators_E_ItemCodes.csv",
        "Item Code,Item\n001,GDP\n",
    )

    result = discover_local_source("fao_macro", root)

    assert result["status"] == "present"
    assert result["file_count"] == 5
    assert result["missing_required_files"] == []
    assert result["main_file_metadata"]["header_columns"] == [
        "Area",
        "Item",
        "Element",
        "Year",
        "Unit",
        "Value",
        "Flag",
        "Note",
    ]
    assert result["main_file_metadata"]["data_row_count"] == 1
    assert result["main_file_metadata"]["sample_first_data_row"][0] == "Testland"
    assert result["files"][0]["relative_path"].endswith(".csv")


def test_discover_reports_missing_required_file(tmp_path: Path) -> None:
    root = tmp_path / "worldBank"
    _write_text(
        root / "WDICSV.csv",
        "Country Name,Country Code,Indicator Name,Indicator Code,1960\n"
        "Testland,TST,GDP growth,NY.GDP.MKTP.KD.ZG,1.0\n",
    )
    _write_text(root / "WDICountry.csv", "Country Code,Country Name\nTST,Testland\n")

    result = discover_local_source("wdi", root)

    assert result["status"] == "invalid"
    assert "WDISeries.csv" in result["missing_required_files"]
