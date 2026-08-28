"""Shared fixtures.

Every test here runs without an LLM call. The model is a presentation layer over
deterministic SQL, so the behaviour worth regression-testing (routing, retrieval,
safety, persistence, the honesty guards) is all reachable offline. That also keeps
the suite runnable when the free-tier token budget is spent.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data"
FIR_DB = DATA_DIR / "ksp_fir.duckdb"

requires_data = pytest.mark.skipif(
    not FIR_DB.exists(),
    reason="ksp_fir.duckdb not present; run scripts/build_db.py first",
)


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return DATA_DIR


@pytest.fixture(scope="session")
def fir_path() -> str:
    return str(FIR_DB)


@pytest.fixture(scope="session")
def db():
    """Read-only DatabaseManager over the real FIR database."""
    from src.chatbot.db_manager import DatabaseManager
    return DatabaseManager(DATA_DIR)


@pytest.fixture(scope="session")
def bot():
    """Chatbot engine. Tests must only exercise paths that short-circuit the LLM."""
    from src.chatbot.engine import CrimeChatbot
    return CrimeChatbot(DATA_DIR)


@pytest.fixture()
def tmp_store(tmp_path):
    """A ChatStore backed by a throwaway SQLite file."""
    from src.chatbot.chat_store import ChatStore
    return ChatStore(tmp_path / "chats.db")
