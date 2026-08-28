"""Intent routing: which database answers a question, and which handler claims it."""
import pytest

from src.chatbot.router import (
    route_with_reason,
    route_question,
    is_investigative_question,
)


class TestDatabaseRouting:
    @pytest.mark.parametrize("question", [
        "How many FIRs were registered in 2023?",
        "Which district has the highest number of FIRs?",
        "Who are the top repeat offenders by district?",
        "thefts in Mysuru district in 2023",
    ])
    def test_fir_questions_route_to_criminal_db(self, question):
        assert route_with_reason(question).database == "criminal"

    def test_router_explains_itself(self):
        """The reason string is injected into the LLM prompt, so it must be populated."""
        r = route_with_reason("How many murders in Bengaluru?")
        assert r.reason and len(r.reason) > 10
        assert r.confidence in {"low", "medium", "high"}

    def test_accused_questions_route_with_high_confidence(self):
        r = route_with_reason("more details on Thimmaiah")
        assert r.database == "criminal"
        assert r.confidence == "high"

    def test_route_question_matches_route_with_reason(self):
        for q in ["How many districts are covered?", "top offenders in Mysuru"]:
            assert route_question(q) == route_with_reason(q).database


class TestHandlerSelection:
    @pytest.mark.parametrize("question", [
        "How do I investigate a suspicious death case?",
        "What is the procedure for investigating a kidnapping?",
    ])
    def test_procedure_questions_go_to_investigation_guide(self, question):
        assert is_investigative_question(question) is True

    @pytest.mark.parametrize("question", [
        "How many FIRs were registered in 2023?",
        "Which district has the highest number of FIRs?",
        "top repeat offenders",
    ])
    def test_statistical_questions_are_not_procedure_questions(self, question):
        assert is_investigative_question(question) is False
