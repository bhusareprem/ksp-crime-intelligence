"""Database connections and SQL execution for all three KSP databases."""

import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path

import duckdb
import pandas as pd
import sqlite3


class QueryTimeoutError(TimeoutError):
    """Raised when a SQL query exceeds the configured time limit."""


def _query_timeout_seconds() -> float:
    try:
        return max(5.0, float(os.getenv("QUERY_TIMEOUT_SECONDS", "20")))
    except ValueError:
        return 20.0


def _resolve_data_dir(data_dir: Path) -> Path:
    custom = os.getenv("KSP_DATA_DIR", "").strip()
    if custom:
        return Path(custom)

    mode = os.getenv("KSP_DATA_MODE", "").strip().lower()
    unified = data_dir / "unified"
    if mode == "unified" and (unified / "registry.json").exists():
        return unified
    if (unified / "ksp_crime.db").exists() and mode != "legacy":
        return unified
    return data_dir


class DatabaseManager:
    def __init__(self, data_dir: Path):
        self.data_dir = _resolve_data_dir(data_dir)
        self.ksp_path = self.data_dir / "ksp_crime.db"
        self.criminal_path = self.data_dir / "criminal.db"
        self.cases_path = self.data_dir / "cases.db"
        # New large-scale KSP FIR DB — check root data dir and resolved dir
        _root = data_dir
        self.fir_path = next(
            (p for p in [_root / "ksp_fir.duckdb", self.data_dir / "ksp_fir.duckdb"] if p.exists()),
            _root / "ksp_fir.duckdb",   # default (may not exist yet)
        )
        self.is_unified = (self.data_dir / "registry.json").exists() or (
            data_dir / "unified_registry.json"
        ).exists()

    @property
    def _criminal_actual(self) -> Path:
        """Prefer new ksp_fir.duckdb over old criminal.db when available."""
        return self.fir_path if self.fir_path.exists() else self.criminal_path

    @property
    def has_new_schema(self) -> bool:
        return self.fir_path.exists()

    def available(self) -> dict[str, bool]:
        return {
            "ksp_crime": self.ksp_path.exists(),
            "criminal": self._criminal_actual.exists(),
            "cases": self.cases_path.exists(),
            "fir": self.fir_path.exists(),
        }

    def execute(self, db_name: str, sql: str, timeout: float | None = None) -> pd.DataFrame:
        from src.chatbot.sql_fix import is_safe_select

        sql = sql.strip().rstrip(";")
        # Full guard: single read-only SELECT, no writes/DDL/ATTACH/file-reads.
        if not is_safe_select(sql):
            raise ValueError("Only a single read-only SELECT query is allowed")

        limit = timeout if timeout is not None else _query_timeout_seconds()

        if db_name == "ksp_crime":
            runner = lambda: self._run_sqlite(self.ksp_path, sql, limit)
        elif db_name == "fir":
            runner = lambda: self._run_duckdb(self.fir_path, sql, limit)
        elif db_name in ("criminal", "cases"):
            path = self._criminal_actual if db_name == "criminal" else self.cases_path
            runner = lambda: self._run_duckdb(path, sql, limit)
        else:
            raise ValueError(f"Unknown database: {db_name}")

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(runner)
            try:
                return future.result(timeout=limit)
            except FuturesTimeoutError as e:
                raise QueryTimeoutError(
                    f"Query exceeded {limit:.0f}s limit. Try a narrower question "
                    f"(add district, year, or crime type)."
                ) from e

    def _run_sqlite(self, path: Path, sql: str, timeout_sec: float) -> pd.DataFrame:
        conn = sqlite3.connect(path)
        try:
            conn.execute(f"PRAGMA busy_timeout = {int(timeout_sec * 1000)}")
            return pd.read_sql_query(sql, conn)
        finally:
            conn.close()

    # Disables ATTACH to remote DBs, extension install/load, and reading
    # arbitrary files via read_csv/read_text/glob etc. — even if a crafted
    # SELECT slips past is_safe_select. Legitimate queries are unaffected.
    _DUCKDB_SAFE_CONFIG = {"enable_external_access": False}

    def _run_duckdb(self, path: Path, sql: str, timeout_sec: float) -> pd.DataFrame:
        conn = duckdb.connect(str(path), read_only=True, config=self._DUCKDB_SAFE_CONFIG)
        try:
            return conn.execute(sql).df()
        finally:
            conn.close()

    def get_langchain_db(self, db_name: str):
        """Return LangChain SQLDatabase for LLM SQL generation."""
        from langchain_community.utilities import SQLDatabase

        if db_name == "ksp_crime":
            uri = f"sqlite:///{self.ksp_path.as_posix()}"
        elif db_name in ("criminal", "fir"):
            uri = f"duckdb:///{self._criminal_actual.as_posix()}"
        elif db_name == "cases":
            uri = f"duckdb:///{self.cases_path.as_posix()}"
        else:
            raise ValueError(f"Unknown database: {db_name}")

        return SQLDatabase.from_uri(uri, sample_rows_in_table_info=2)
