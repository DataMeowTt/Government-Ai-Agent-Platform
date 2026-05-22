from __future__ import annotations

from config.source_registry import SourceRegistryEntry, load_source_registry
from sources.registry import render_required_input_blocks, select_sources


def test_load_source_registry_has_expected_sources() -> None:
    registry = load_source_registry()

    assert set(registry) == {"wdi", "gmd", "fao_macro"}
    assert registry["wdi"].source_type == "local_path"
    assert registry["gmd"].source_type == "local_path"
    assert registry["fao_macro"].source_type == "local_path"
    assert "World Bank WDI" in registry["wdi"].license_note
    assert "Global Macro Database" in registry["gmd"].license_note
    assert "FAOSTAT/FAO" in registry["fao_macro"].license_note


def test_select_sources_supports_macro_alias() -> None:
    registry = load_source_registry()

    selected = select_sources(registry, ["macro"])
    assert [entry.source_name for entry in selected] == ["fao_macro"]


def test_missing_inputs_are_reported_per_source_type() -> None:
    wdi = SourceRegistryEntry(
        source_name="wdi",
        source_type="local_path",
        enabled=True,
        description="World Bank placeholder",
        license_note="note",
        local_path=None,
        output_format="csv",
    )
    gmd = SourceRegistryEntry(
        source_name="gmd",
        source_type="local_path",
        enabled=True,
        description="GMD placeholder",
        license_note="note",
        local_path=None,
        output_format="csv",
    )
    fao_macro = SourceRegistryEntry(
        source_name="fao_macro",
        source_type="local_path",
        enabled=True,
        description="Macro placeholder",
        license_note="note",
        local_path=None,
        output_format="csv",
    )

    assert wdi.missing_inputs() == ["local_path"]
    assert gmd.missing_inputs() == ["local_path"]
    assert fao_macro.missing_inputs() == ["local_path"]

    blocks = render_required_input_blocks(wdi)
    assert len(blocks) == 1
    assert blocks[0].startswith("SOURCE INPUT REQUIRED:")
    assert "- source_name: wdi" in blocks[0]
