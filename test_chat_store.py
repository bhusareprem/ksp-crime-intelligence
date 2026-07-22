"""Tests for persistent chat sessions."""

from pathlib import Path
import tempfile

from src.chatbot.chat_store import ChatStore


def test_session_lifecycle():
    with tempfile.TemporaryDirectory() as tmp:
        store = ChatStore(Path(tmp) / "chats.db")
        session = store.create_session()
        assert session.title == "New chat"

        store.add_message(session.id, "user", "Top criminal in Bagalkot?")
        store.add_message(
            session.id,
            "assistant",
            "Rudra Narang has 26 linked FIRs.",
            metadata={"database": "ksp_crime", "sql": "SELECT ..."},
        )

        history = store.get_history(session.id)
        assert len(history) == 2
        assert history[0]["role"] == "user"

        title = store.auto_title_from_message(session.id, "Top criminal in Bagalkot?")
        assert title == "Top criminal in Bagalkot?"

        sessions = store.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].message_count == 2

        messages = store.get_messages(session.id)
        assert messages[1].metadata["database"] == "ksp_crime"

        assert store.delete_session(session.id)
        assert store.get_session(session.id) is None


if __name__ == "__main__":
    test_session_lifecycle()
    print("chat_store tests passed")
