from __future__ import annotations

from pathlib import Path

from config.source_registry import SourceRegistryEntry, load_source_registry, normalize_source_name

MAIN_FILE_NAMES = {
    "wdi": "WDICSV.csv",
    "gmd": "GMD.csv",
    "fao_macro": "Macro-Statistics_Key_Indicators_E_All_Data_(Normalized).csv",
}


def _resolve_local_path(raw_path: str, *, base_dir: Path) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path


def _resolve_source_main_file(source_name: str, entry: SourceRegistryEntry, *, base_dir: Path) -> Path:
    if entry.source_type != "local_path" or not entry.local_path:
        raise ValueError(f"Source {source_name} must be local_path with local_path configured.")
    root = _resolve_local_path(entry.local_path, base_dir=base_dir)
    if source_name == "gmd" and root.is_file():
        return root
    main_file = MAIN_FILE_NAMES[source_name]
    return root / main_file if root.is_dir() else root


def resolve_silver_inputs(
    *,
    registry_path: str | None = None,
    wdi_override: str | None = None,
    gmd_override: str | None = None,
    fao_macro_override: str | None = None,
    base_dir: Path | None = None,
) -> dict[str, str]:
    working_dir = (base_dir or Path.cwd()).resolve()
    registry = load_source_registry(registry_path)

    resolved: dict[str, str] = {}
    for canonical in ("wdi", "gmd", "fao_macro"):
        entry = registry.get(canonical)
        if entry is None:
            raise KeyError(f"Source {canonical} not found in source registry.")
        resolved[canonical] = str(
            _resolve_source_main_file(canonical, entry, base_dir=working_dir)
        )

    overrides = {
        "wdi": wdi_override,
        "gmd": gmd_override,
        "fao_macro": fao_macro_override,
    }
    for source_name, override in overrides.items():
        if not override:
            continue
        resolved[normalize_source_name(source_name)] = str(
            _resolve_local_path(override, base_dir=working_dir)
        )

    return resolved
