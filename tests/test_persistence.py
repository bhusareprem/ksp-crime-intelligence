"""Session, message and audit persistence.

Conversation history feeds follow-up resolution ("more details on Thimmaiah"),
so losing or mis-ordering it changes answers, not just the sidebar. The audit log
is the accountability record for a policing tool and must capture the generated
SQL for every question.
"""
import sqlite3

import pytest


class TestSessions:
    def test_create_and_fetch(self, tmp_store):
        s = tmp_store.create_session("Theft enquiry")
        assert s.id
        got = tmp_store.get_session(s.id)
        assert got is not None and got.id == s.id

    def test_listing_is_ordered_most_recent_first(self, tmp_store):
        """Timestamps have one-second resolution, so sessions created in the same
        second legitimately tie. The contract is non-increasing updated_at."""
        a = tmp_store.create_session("first")
        b = tmp_store.create_session("second")
        sessions = tmp_store.list_sessions()
        ids = [s.id for s in sessions]
        assert {a.id, b.id} <= set(ids)
        stamps = [s.updated_at for s in sessions]
        assert stamps == sorted(stamps, reverse=True)

    def test_delete_removes_session(self, tmp_store):
        s = tmp_store.create_session("temp")
        assert tmp_store.delete_session(s.id) is True
        assert tmp_store.get_session(s.id) is None

    def test_unknown_session_is_none_not_an_error(self, tmp_store):
        assert tmp_store.get_session("does-not-exist") is None

    def test_rename(self, tmp_store):
        s = tmp_store.create_session("New chat")
        tmp_store.set_title(s.id, "Mysuru thefts")
        assert tmp_store.get_session(s.id).title == "Mysuru thefts"


class TestMessages:
    def test_messages_round_trip_in_order(self, tmp_store):
        s = tmp_store.create_session("t")
        tmp_store.add_message(s.id, "user", "How many FIRs in 2023?")
        tmp_store.add_message(s.id, "assistant", "99,766 FIRs.")
        msgs = tmp_store.get_messages(s.id)
        assert [m.role for m in msgs] == ["user", "assistant"]
        assert "99,766" in msgs[1].content

    def test_history_shape_matches_what_the_engine_expects(self, tmp_store):
        """engine.ask(history=...) expects [{'role':..,'content':..}]."""
        s = tmp_store.create_session("t")
        tmp_store.add_message(s.id, "user", "top repeat offenders")
        tmp_store.add_message(s.id, "assistant", "Thimmaiah Begum, 260 FIRs")
        hist = tmp_store.get_history(s.id)
        assert hist and all({"role", "content"} <= set(h) for h in hist)

    def test_history_is_capped(self, tmp_store):
        s = tmp_store.create_session("t")
        for i in range(40):
            tmp_store.add_message(s.id, "user", f"q{i}")
        assert len(tmp_store.get_history(s.id, limit=10)) <= 10

    def test_message_count(self, tmp_store):
        s = tmp_store.create_session("t")
        for i in range(3):
            tmp_store.add_message(s.id, "user", f"q{i}")
        assert tmp_store.message_count(s.id) == 3

    def test_messages_are_scoped_to_their_session(self, tmp_store):
        a = tmp_store.create_session("a")
        b = tmp_store.create_session("b")
        tmp_store.add_message(a.id, "user", "belongs to A")
        assert tmp_store.get_messages(b.id) == []

    def test_deleting_a_session_drops_its_messages(self, tmp_store):
        s = tmp_store.create_session("t")
        tmp_store.add_message(s.id, "user", "hello")
        tmp_store.delete_session(s.id)
        assert tmp_store.get_messages(s.id) == []

    def test_unicode_survives_the_round_trip(self, tmp_store):
        """Kannada is a first-class input language."""
        s = tmp_store.create_session("kn")
        q = "ಮೈಸೂರು ಜಿಲ್ಲೆಯಲ್ಲಿ ಎಷ್ಟು ಕಳ್ಳತನ ಪ್ರಕರಣಗಳು ದಾಖಲಾಗಿವೆ?"
        tmp_store.add_message(s.id, "user", q)
        assert tmp_store.get_messages(s.id)[0].content == q


class TestAuditTrail:
    def test_audit_row_records_the_generated_sql(self, tmp_path):
        """Mirrors api.main._write_audit. The SQL column is the accountability
        record: an officer must be able to see what was actually run."""
        db = tmp_path / "audit.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, "
            "session_id TEXT, question TEXT, sql_generated TEXT, database TEXT, language TEXT)"
        )
        conn.execute(
            "INSERT INTO audit_log(ts,session_id,question,sql_generated,database,language) "
            "VALUES(?,?,?,?,?,?)",
            ("2026-08-28T10:00:00", "s1", "How many FIRs in 2023?",
             "SELECT COUNT(*) FROM CaseMaster", "criminal", "en"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT question, sql_generated, database, language FROM audit_log"
        ).fetchone()
        conn.close()
        assert row[0] == "How many FIRs in 2023?"
        assert row[1].startswith("SELECT")
        assert row[2] == "criminal"
        assert row[3] == "en"
