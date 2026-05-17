from __future__ import annotations

from config.source_registry import SourceRegistryEntry, load_source_registry
from sources.registry import render_required_input_blocks


def test_load_source_registry_has_expected_sources() -> None:
    registry = load_source_registry()

    assert set(registry) == {"wdi", "gmd", "macro"}
    assert registry["wdi"].source_type == "api"
    assert registry["gmd"].source_type == "csv_url"
    assert registry["macro"].source_type == "local_path"


def test_missing_inputs_are_reported_per_source_type() -> None:
    wdi = SourceRegistryEntry(
        source_name="wdi",
        source_type="api",
        enabled=True,
        description="World Bank placeholder",
        license_note=None,
        api_url=None,
        indicator_mapping=None,
        output_format="json",
    )
    gmd = SourceRegistryEntry(
        source_name="gmd",
        source_type="csv_url",
        enabled=True,
        description="GMD placeholder",
        license_note=None,
        csv_url=None,
        output_format="csv",
    )
    macro = SourceRegistryEntry(
        source_name="macro",
        source_type="local_path",
        enabled=True,
        description="Macro placeholder",
        license_note=None,
        local_path=None,
        output_format="csv",
    )

    assert wdi.missing_inputs() == ["license note", "api_url", "indicator_mapping"]
    assert gmd.missing_inputs() == ["license note", "csv_url"]
    assert macro.missing_inputs() == ["license note", "local_path"]

    blocks = render_required_input_blocks(wdi)
    assert len(blocks) == 3
    assert blocks[0].startswith("SOURCE INPUT REQUIRED:")
    assert "- source_name: wdi" in blocks[0]

