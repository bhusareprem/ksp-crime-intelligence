"""Write unified databases and registry."""

from __future__ import annotations

from pathlib import Path

from src.unified_demo.generator import UnifiedMaster, save_registry


def write_all_databases(
    master: UnifiedMaster,
    output_dir: Path,
    project_root: Path,
) -> dict[str, Path]:
    from src.unified_demo.writers import (
        _write_duckdb_cases,
        _write_duckdb_criminal_v2,
        _write_sqlite_ksp,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "ksp_crime": output_dir / "ksp_crime.db",
        "criminal": output_dir / "criminal.db",
        "cases": output_dir / "cases.db",
    }
    _write_sqlite_ksp(master, paths["ksp_crime"], project_root / "schema.sql")
    _write_duckdb_criminal_v2(
        master, paths["criminal"], project_root / "schema_unified_criminal.sql"
    )
    _write_duckdb_cases(master, paths["cases"], project_root / "schema_unified_cases.sql")
    save_registry(master, output_dir / "registry.json")
    return paths
