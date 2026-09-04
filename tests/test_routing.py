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


class TestChargesheetIsOneNumber:
    """The same question answered 71% from a small NCRB sample and 25% from the
    500k FIRs, depending only on how it was phrased. A judge who asks twice and
    gets two answers stops trusting the rest of the screen."""

    def test_every_phrasing_reaches_the_fir_database(self):
        from src.chatbot.router import route_with_reason
        for q in ["What is the chargesheet rate?",
                  "What percentage of cases are chargesheeted?",
                  "What proportion of FIRs end in a charge sheet?",
                  "chargesheet rate by district"]:
            assert route_with_reason(q).database == "criminal", q

    def test_ncrb_benchmark_still_goes_to_ncrb(self):
        """Asking for the national benchmark is a different question."""
        from src.chatbot.router import route_with_reason
        assert route_with_reason(
            "What is the NCRB chargesheet rate for Karnataka?").database == "ksp_crime"

    def test_crime_rate_still_goes_to_ncrb(self):
        """A per-100k rate needs population, which the FIR database does not hold."""
        from src.chatbot.router import route_with_reason
        assert route_with_reason("What is the crime rate in Bengaluru?").database == "ksp_crime"

    def test_answered_deterministically_not_by_the_model(self):
        """Generation is already at temperature 0, so the only way to make a
        headline figure repeatable is to stop generating it."""
        from src.chatbot.fallback_sql import try_fallback_sql
        for q in ["What is the chargesheet rate?",
                  "What percentage of cases are chargesheeted?",
                  "What proportion of FIRs end in a charge sheet?"]:
            fb = try_fallback_sql(q)
            assert fb is not None, q
            assert "Charge Sheeted" in fb.sql, q

    def test_a_district_question_still_gets_the_breakdown(self):
        from src.chatbot.fallback_sql import try_fallback_sql
        assert "DistrictName" in try_fallback_sql("chargesheet rate by district").sql


class TestPersonNameExtraction:
    def test_on_inside_a_word_is_not_a_name(self):
        """"proporti-on of FIRs end" was read as a person called "of FIRs end"."""
        from src.chatbot.fallback_sql import _extract_person_name
        for q in ["What proportion of FIRs end in a charge sheet?",
                  "Comparison of theft and robbery",
                  "Crime in the region of Mysuru"]:
            assert _extract_person_name(q) is None, q

    def test_real_name_lookups_still_work(self):
        from src.chatbot.fallback_sql import _extract_person_name
        assert _extract_person_name("more details on thimmaiah") == "thimmaiah"
        assert _extract_person_name("tell me about Rashid Rao") == "Rashid Rao"
        assert _extract_person_name("who is David Mirza") == "David Mirza"


class TestFirNumberLookup:
    """The scope guard tells the officer "give me the FIR number and I can pull
    that case". That offer was kept by generated SQL, so it held for "pull up
    case number X" and returned aggregate crime counts for "show me the details
    of FIR number X". An offer made in writing should not depend on phrasing."""

    def test_every_phrasing_pulls_the_case(self):
        from src.chatbot.fallback_sql import try_fallback_sql
        for q in ["Show me the details of FIR number 202200001 in Mysuru",
                  "Pull up case number 202200001 and everyone recorded on it",
                  "FIR 202200001",
                  "details on crime no 100030242202200001",
                  "case no. 214/2026"]:
            fb = try_fallback_sql(q)
            assert fb is not None and "CaseNo" in fb.sql, q

    def test_a_named_district_narrows_the_case(self):
        """CaseNo is unique per station, not statewide, so the same number exists
        in most districts. Ignoring the district returned 200 rows from
        everywhere the officer had not asked about."""
        from src.chatbot.fallback_sql import try_fallback_sql
        fb = try_fallback_sql("FIR number 202200001 in Mysuru")
        assert "Mysuru" in fb.sql
        assert "Mysuru" in (fb.note or "")

    def test_ordinary_questions_are_not_case_lookups(self):
        from src.chatbot.fallback_sql import try_fallback_sql
        for q in ["How many thefts in Mysuru in 2023?",
                  "How many FIRs were registered in 2024?",
                  "What is the chargesheet rate?"]:
            fb = try_fallback_sql(q)
            assert fb is None or "cm.CaseNo =" not in fb.sql, q

    def test_a_case_number_is_not_read_as_a_person(self):
        """Checked before the name extractor: "details on FIR 202200001" was
        otherwise a profile request for someone called "FIR 202200001"."""
        from src.chatbot.fallback_sql import try_fallback_sql
        fb = try_fallback_sql("details on FIR 202200001")
        assert "CaseNo" in fb.sql

    def test_history_expansion_keeps_the_case_number(self):
        """The expansion is for vague follow-ups ("more details on that"). It was
        also firing on "case details: FIR number 202200001", rewriting it to
        "murder case details in Belagavi district" and discarding the one
        identifier that made the question answerable."""
        from src.chatbot.fallback_sql import expand_question_with_history, try_fallback_sql
        q = ("who is behind the murder in belagavi?\n\n"
             "case details: fir number 202200001 in belagavi")
        assert expand_question_with_history(q, []) == q
        assert "cm.CaseNo" in try_fallback_sql(expand_question_with_history(q, [])).sql

    def test_vague_followups_still_expand(self):
        from src.chatbot.fallback_sql import expand_question_with_history
        assert expand_question_with_history("more details on that", []) != "more details on that"
        assert "thimmaiah" in expand_question_with_history("details on thimmaiah", []).lower()
