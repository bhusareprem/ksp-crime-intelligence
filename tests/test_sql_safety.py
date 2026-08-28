"""SQL execution guard.

Generated SQL reaches a live database, so the guard is the last line of defence
against a prompt-injected or hallucinated statement. It must allow ordinary
analytical reads and reject everything else.
"""
import pytest

from conftest import requires_data
from src.chatbot.sql_fix import is_safe_select


class TestAllowedStatements:
    @pytest.mark.parametrize("sql", [
        "SELECT COUNT(*) FROM CaseMaster",
        "SELECT d.DistrictName, COUNT(*) FROM CaseMaster cm "
        "JOIN Unit u ON cm.PoliceStationID=u.UnitID "
        "JOIN District d ON u.DistrictID=d.DistrictID GROUP BY 1",
        "WITH x AS (SELECT 1 AS n) SELECT n FROM x",           # CTEs are used by the app
        "SELECT COUNT(*) FROM CaseMaster WHERE CrimeNo LIKE '%2024%'",
    ])
    def test_read_only_queries_pass(self, sql):
        assert is_safe_select(sql) is True


class TestRejectedStatements:
    @pytest.mark.parametrize("sql", [
        "DROP TABLE CaseMaster",
        "DELETE FROM Accused",
        "UPDATE CaseMaster SET CrimeNo='x'",
        "INSERT INTO District VALUES (99,'X')",
        "ALTER TABLE Accused ADD COLUMN x INT",
        "CREATE TABLE evil (id INT)",
        "TRUNCATE TABLE Victim",
    ])
    def test_writes_and_ddl_are_rejected(self, sql):
        assert is_safe_select(sql) is False

    @pytest.mark.parametrize("sql", [
        "SELECT 1; DROP TABLE CaseMaster",
        "SELECT * FROM CaseMaster; DELETE FROM Accused",
    ])
    def test_stacked_statements_are_rejected(self, sql):
        assert is_safe_select(sql) is False

    @pytest.mark.parametrize("sql", [
        "SELECT * FROM read_csv('C:/Windows/win.ini')",
        "SELECT * FROM read_parquet('/etc/passwd')",
        "SELECT * FROM glob('C:/Users/**')",
        "ATTACH 'other.db' AS o",
        "COPY CaseMaster TO 'out.csv'",
    ])
    def test_filesystem_escapes_are_rejected(self, sql):
        """DuckDB can read the filesystem from SQL. That must never be reachable."""
        assert is_safe_select(sql) is False

    def test_non_select_leading_token_is_rejected(self):
        assert is_safe_select("-- comment\nSELECT 1") is False
        assert is_safe_select("PRAGMA table_info('Accused')") is False


class TestGuardIsEnforcedAtExecution:
    @requires_data
    def test_database_manager_refuses_unsafe_sql(self, db):
        """The guard is enforced in DatabaseManager, not only at the call site."""
        with pytest.raises(ValueError):
            db.execute("criminal", "DROP TABLE CaseMaster")

    @requires_data
    def test_database_manager_runs_safe_sql(self, db):
        out = db.execute("criminal", "SELECT COUNT(*) AS n FROM CaseMaster")
        assert int(out.iloc[0, 0]) > 0
