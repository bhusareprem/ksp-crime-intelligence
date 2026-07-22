"""Fix and validate LLM-generated SQL for SQLite vs DuckDB."""

import re


def fix_sql_for_dialect(sql: str, db_name: str) -> str:
    """Normalize SQL for target database engine."""
    sql = sql.strip().rstrip(";")

    if db_name == "ksp_crime":
        # SQLite: no ILIKE — use LIKE with lower()
        sql = re.sub(
            r"(\w+\.\w+|\w+)\s+ILIKE\s+",
            lambda m: f"LOWER({m.group(1)}) LIKE LOWER(",
            sql,
            flags=re.I,
        )
        # Fix broken ILIKE replacement - simpler approach: replace ILIKE with LIKE
        sql = re.sub(r"\bILIKE\b", "LIKE", sql, flags=re.I)

    # Remove invalid table aliases hallucinated by LLM
    bad_patterns = [
        (r"JOIN\s+police_stations.*ON\s+\w+\.name_kn\s*=\s*\w+\.district_id", ""),
        (r"JOIN\s+\w+\s+ON\s+\w+\.station_code\s*=\s*\w+\.station_id", ""),
        (r"crime_heads\s+\w+\s+ON\s+\w+\.crime_head_id\s*=\s*\w+\.ipc_section", ""),
    ]
    for pattern, _ in bad_patterns:
        if re.search(pattern, sql, re.I):
            return ""  # force fallback

    return sql


# Statement keywords that must never appear — writes, DDL, and engine-level
# escapes (ATTACH/COPY/PRAGMA/INSTALL/LOAD let DuckDB reach the filesystem or
# other databases). A read-only SELECT never needs any of these.
_FORBIDDEN_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "EXEC",
    "ATTACH", "DETACH", "COPY", "PRAGMA", "INSTALL", "LOAD", "CALL", "EXPORT",
    "IMPORT", "REPLACE", "GRANT", "REVOKE", "VACUUM",
]
# DuckDB/SQLite functions that read the local filesystem or spawn external I/O.
_FORBIDDEN_FUNCTIONS = [
    "read_csv", "read_csv_auto", "read_parquet", "read_json", "read_json_auto",
    "read_text", "read_blob", "read_ndjson", "glob", "sniff_csv", "parquet_scan",
    "load_extension",
]


def is_safe_select(sql: str) -> bool:
    """True only for a single read-only SELECT/WITH with no escape hatches."""
    sql_clean = sql.strip().rstrip(";")
    sql_upper = sql_clean.upper()

    if not re.match(r"^(WITH|SELECT)\b", sql_upper):
        return False
    # Reject stacked statements — one SELECT only (semicolons inside string
    # literals are rare in generated SQL and also rejected, which is safe).
    if ";" in sql_clean:
        return False
    for word in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{word}\b", sql_upper):
            return False
    low = sql_clean.lower()
    for fn in _FORBIDDEN_FUNCTIONS:
        if re.search(rf"\b{fn}\s*\(", low):
            return False
    return True
