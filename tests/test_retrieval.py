"""RAG value grounding.

The retriever maps a question onto the exact literals present in the database
(district names, crime heads) before any SQL is written. Every bug this file
guards against produced a *plausible wrong number* rather than an error, which is
the failure mode that matters most for a policing tool.
"""
import pytest

from conftest import requires_data
from src.chatbot.rag.schema_live import (
    match_districts,
    match_crime_heads,
    unknown_places,
    ground_values,
    strip_directive,
)
from src.chatbot.rag.retriever import retrieve_context, retrieve_similar_examples


pytestmark = requires_data


class TestDistrictMatching:
    @pytest.mark.parametrize("question,expected", [
        ("How many FIRs in Bengaluru Urban district?", "Bengaluru Urban"),
        ("thefts in Mysuru district 2023", "Mysuru"),
        ("crimes in Bangalore", "Bengaluru Urban"),      # colloquial alias
        ("cases in Mangalore", "Dakshina Kannada"),      # city to district
        ("FIRs in Hubli", "Dharwad"),
    ])
    def test_english_and_aliases(self, question, expected, fir_path):
        assert expected in match_districts(question, fir_path)

    @pytest.mark.parametrize("question,expected", [
        ("ಮೈಸೂರು ಜಿಲ್ಲೆಯಲ್ಲಿ ಎಷ್ಟು ಪ್ರಕರಣಗಳು?", "Mysuru"),
        ("ಬೆಂಗಳೂರಿನಲ್ಲಿ ಎಷ್ಟು ಕೊಲೆ ಪ್ರಕರಣಗಳಿವೆ?", "Bengaluru Urban"),
        ("ಬೆಳಗಾವಿಯಲ್ಲಿ ದರೋಡೆ", "Belagavi"),
        ("ಶಿವಮೊಗ್ಗದಲ್ಲಿ ಅತ್ಯಾಚಾರ", "Shivamogga"),
        ("ತುಮಕೂರಿನಲ್ಲಿ ಸೈಬರ್ ಅಪರಾಧ", "Tumakuru"),
    ])
    def test_kannada_survives_case_endings(self, question, expected, fir_path):
        """Kannada fuses case endings onto names (ಮೈಸೂರು -> ಮೈಸೂರಿನಲ್ಲಿ).

        Matching the bare name misses every real question and silently drops the
        district filter, turning a district answer into a statewide total.
        """
        assert expected in match_districts(question, fir_path)

    def test_language_directive_is_not_a_district(self, fir_path):
        """The UI prefixes '[Respond in Kannada language.]'.

        The word 'Kannada' in it matched the districts Dakshina/Uttara Kannada and
        rewrote every Kannada question to the wrong district.
        """
        q = "[Respond in Kannada language.] ಮೈಸೂರು ಜಿಲ್ಲೆಯಲ್ಲಿ ಎಷ್ಟು ಕಳ್ಳತನ?"
        matched = match_districts(q, fir_path)
        assert "Mysuru" in matched
        assert "Dakshina Kannada" not in matched
        assert "Uttara Kannada" not in matched

    def test_strip_directive_removes_only_the_prefix(self):
        assert strip_directive("[Respond in Kannada language.] hello") == "hello"
        assert strip_directive("no directive here") == "no directive here"


class TestCrimeHeadMatching:
    @pytest.mark.parametrize("question,expected", [
        ("how many drug cases", {"NDPS - Possession", "NDPS - Trafficking"}),
        ("cyber crime in Bengaluru", {"Cyber Crime - Hacking", "Cyber Crime - Online Fraud"}),
        ("ಮಾದಕ ವಸ್ತು ಪ್ರಕರಣಗಳು", {"NDPS - Possession", "NDPS - Trafficking"}),
        ("ಕಳ್ಳತನ ಪ್ರಕರಣಗಳು", {"Theft"}),
    ])
    def test_synonyms_map_to_real_heads(self, question, expected, fir_path):
        """'drug' is not a CrimeHeadName; unmapped it filters to zero rows."""
        assert expected.issubset(set(match_crime_heads(question, fir_path)))

    def test_attempt_is_not_the_completed_offence(self, fir_path):
        """Counting 'Attempt to Murder' under 'murders' inflated the figure."""
        heads = match_crime_heads("how many murders in Bengaluru", fir_path)
        assert "Murder" in heads
        assert "Attempt to Murder" not in heads

    def test_attempt_is_returned_when_asked_for(self, fir_path):
        heads = match_crime_heads("attempt to murder cases", fir_path)
        assert "Attempt to Murder" in heads


class TestUnknownPlaceDetection:
    @pytest.mark.parametrize("question", [
        "How many thefts were reported in Wakanda district in 2023?",
        "show me murders in Gotham district",
        "murders in the district of Atlantis",
    ])
    def test_fictional_districts_are_flagged(self, question, fir_path):
        assert unknown_places(question, fir_path)

    @pytest.mark.parametrize("question", [
        "How many FIRs are there in Bengaluru Urban district across all years?",
        "Which district has the highest number of FIRs?",
        "total FIRs per district",
        "How many districts are covered in the crime database?",
        "top 5 districts by crime",
        "compare Belagavi district and Kalaburagi district",
        "drug cases in Dakshina Kannada district",
        "What is the crime rate in the district of Hassan?",
        "district wise crime count",
    ])
    def test_real_questions_are_not_flagged(self, question, fir_path):
        """False positives here would refuse legitimate questions."""
        assert unknown_places(question, fir_path) == []


class TestGroundingBlock:
    def test_grounding_names_exact_literals(self, fir_path):
        block = ground_values("drug cases in Mysuru district", fir_path)
        assert "Mysuru" in block
        assert "NDPS" in block

    def test_grounding_warns_loudly_about_unknown_places(self, fir_path):
        block = ground_values("thefts in Wakanda district", fir_path)
        assert "Wakanda" in block
        assert "CRITICAL" in block


class TestContextAssembly:
    def test_criminal_context_targets_the_cctns_schema(self, data_dir):
        ctx = retrieve_context("how many FIRs in Mysuru", "criminal", "test", data_dir)
        assert ctx.database == "criminal"
        assert "CaseMaster" in ctx.live_schema
        # The old unified schema must not resurface; it silently returns 0 rows.
        assert "fir_details" not in ctx.live_schema

    def test_examples_are_retrieved_and_ranked(self):
        ex = retrieve_similar_examples("top repeat offenders", "criminal", top_k=3)
        assert ex and len(ex) <= 3

    def test_repeat_offender_example_teaches_the_right_grain(self):
        """Accused holds one row per case. Examples grouping by AccusedMasterID
        taught the model a query that can never find a repeat offender."""
        ex = retrieve_similar_examples("top repeat offenders statewide", "criminal", top_k=5)
        sql = " ".join(e.sql for e in ex)
        if "GROUP BY" in sql and "Accused" in sql:
            assert "GROUP BY a.AccusedMasterID" not in sql
