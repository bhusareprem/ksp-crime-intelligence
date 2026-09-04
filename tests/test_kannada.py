"""Kannada replies.

The app understood Kannada from the start but answered in English every time:
the "respond in Kannada" directive was only a prompt prefix and the model ignored
it. Measured before the fix: 0 of 5 Kannada questions got a Kannada answer.

Two layers now. Single-figure answers are built by echoing the officer's own
sentence with the number substituted, which needs no model call and survives an
exhausted quota. Anything else goes to the model with a Kannada-dominant prompt.
"""
import pytest

from src.chatbot.kannada import (
    answer_count,
    has_kannada,
    kannada_ratio,
    single_value,
    wants_kannada,
)


class TestDetection:
    def test_script_detection(self):
        assert has_kannada("ಮೈಸೂರು ಜಿಲ್ಲೆ") is True
        assert has_kannada("How many thefts in Mysuru?") is False
        assert has_kannada("") is False

    def test_wants_kannada_from_script(self):
        assert wants_kannada("ಡೇಟಾಬೇಸ್‌ನಲ್ಲಿ ಎಷ್ಟು ಜಿಲ್ಲೆಗಳಿವೆ?") is True
        assert wants_kannada("How many districts?") is False

    def test_wants_kannada_from_ui_directive(self):
        """The UI prefixes this when the language toggle is set."""
        assert wants_kannada("how many districts",
                             "[Respond in Kannada language.] ...") is True

    def test_ratio_is_zero_for_english(self):
        assert kannada_ratio("Total FIRs: 1,089") == 0.0
        assert kannada_ratio("ಡೇಟಾಬೇಸ್‌ನಲ್ಲಿ 31 ಜಿಲ್ಲೆಗಳಿವೆ.") > 0.25


class TestEchoedAnswers:
    """The reply reuses the officer's grammar, so no sentence is composed from
    scratch and the result cannot be ungrammatical Kannada."""

    @pytest.mark.parametrize("question,value,expected", [
        ("ಮೈಸೂರು ಜಿಲ್ಲೆಯಲ್ಲಿ 2023 ರಲ್ಲಿ ಎಷ್ಟು ಕಳ್ಳತನ ಪ್ರಕರಣಗಳು ದಾಖಲಾಗಿವೆ?", 1089,
         "ಮೈಸೂರು ಜಿಲ್ಲೆಯಲ್ಲಿ 2023 ರಲ್ಲಿ 1,089 ಕಳ್ಳತನ ಪ್ರಕರಣಗಳು ದಾಖಲಾಗಿವೆ."),
        ("ಡೇಟಾಬೇಸ್‌ನಲ್ಲಿ ಎಷ್ಟು ಜಿಲ್ಲೆಗಳಿವೆ?", 31,
         "ಡೇಟಾಬೇಸ್‌ನಲ್ಲಿ 31 ಜಿಲ್ಲೆಗಳಿವೆ."),
        ("ಬೆಂಗಳೂರಿನಲ್ಲಿ ಎಷ್ಟು ಕೊಲೆ ಪ್ರಕರಣಗಳಿವೆ?", 1317,
         "ಬೆಂಗಳೂರಿನಲ್ಲಿ 1,317 ಕೊಲೆ ಪ್ರಕರಣಗಳಿವೆ."),
    ])
    def test_produces_the_expected_sentence(self, question, value, expected):
        assert answer_count(question, value) == expected

    def test_thousands_are_grouped(self):
        out = answer_count("2023 ರಲ್ಲಿ ಎಷ್ಟು FIR ದಾಖಲಾಗಿವೆ?", 99766)
        assert "99,766" in out

    def test_question_mark_becomes_a_full_stop(self):
        out = answer_count("ಡೇಟಾಬೇಸ್‌ನಲ್ಲಿ ಎಷ್ಟು ಜಿಲ್ಲೆಗಳಿವೆ?", 31)
        assert out.endswith(".") and "?" not in out


class TestDeclinesWhenTheEchoWouldNotFit:
    """Returning None hands the question to the model rather than producing a
    sentence that does not answer it."""

    def test_english_question(self):
        assert answer_count("How many thefts in Mysuru in 2023?", 1089) is None

    @pytest.mark.parametrize("question", [
        "ಕರ್ನಾಟಕದಲ್ಲಿ ಅತಿ ಹೆಚ್ಚು ಅಪರಾಧ ನಡೆಯುವ ಜಿಲ್ಲೆ ಯಾವುದು?",   # which
        "ಟಾಪ್ 5 ಜಿಲ್ಲೆಗಳು ಯಾವುವು?",                                  # which (plural)
    ])
    def test_non_count_questions(self, question):
        assert answer_count(question, 5) is None

    def test_no_interrogative_to_replace(self):
        assert answer_count("ಮೈಸೂರು ಜಿಲ್ಲೆ", 5) is None

    def test_non_numeric_value(self):
        assert answer_count("ಎಷ್ಟು ಜಿಲ್ಲೆಗಳಿವೆ?", "Bengaluru Urban") is None
        assert answer_count("ಎಷ್ಟು ಜಿಲ್ಲೆಗಳಿವೆ?", None) is None


class TestSingleValueExtraction:
    def test_one_by_one_frame(self):
        pd = pytest.importorskip("pandas")
        assert int(single_value(pd.DataFrame({"n": [31]}))) == 31

    def test_rejects_wider_or_longer_frames(self):
        pd = pytest.importorskip("pandas")
        assert single_value(pd.DataFrame({"a": [1], "b": [2]})) is None
        assert single_value(pd.DataFrame({"a": [1, 2]})) is None
        assert single_value(pd.DataFrame()) is None
        assert single_value(None) is None


class TestModelPromptStaysKannada:
    """A Kannada instruction inside an English prompt lost every time. The whole
    turn has to be Kannada, using the officer's wording rather than the planner's
    English rewrite."""

    def test_summarize_accepts_the_language_flag(self):
        import inspect
        from src.chatbot.agent import ConversationalAgent
        sig = inspect.signature(ConversationalAgent.summarize)
        assert "kannada" in sig.parameters
        assert "display_question" in sig.parameters

    def test_kannada_branch_builds_a_kannada_turn(self):
        from pathlib import Path
        src = Path(__file__).resolve().parents[1] / "src/chatbot/agent.py"
        text = src.read_text(encoding="utf-8")
        assert "ಪ್ರಶ್ನೆ:" in text, "user turn must be labelled in Kannada"
        assert "ಡೇಟಾ:" in text
        assert "ಕನ್ನಡದಲ್ಲಿಯೇ ಉತ್ತರಿಸಿ" in text, "system prompt must be Kannada-dominant"


class TestDataNotes:
    """A Kannada answer used to end with an English footnote from the SQL layer."""

    def test_prefix_note_is_translated_but_db_values_are_not(self):
        from src.chatbot.kannada import localize_note
        out = localize_note("Matched crime types: Theft, Vehicle Theft")
        assert "ಹೊಂದಿಕೆಯಾದ" in out
        # Crime heads are the literal values stored in the database and appear
        # unchanged in the SQL the officer can expand, so they stay English.
        assert "Theft, Vehicle Theft" in out

    def test_exact_notes_are_translated(self):
        import re as _re
        from src.chatbot.kannada import localize_note
        out = localize_note("Accused with 2+ FIRs — proxy for repeat offenders.")
        assert _re.search(r"[ಀ-೿]", out)
        assert "FIR" in out          # acronym preserved

    def test_unknown_note_passes_through(self):
        from src.chatbot.kannada import localize_note
        assert localize_note("Something new") == "Something new"
        assert localize_note(None) is None


class TestScriptHygiene:
    """A real Kannada answer came back starting "ತদন্তಿ" - the middle three
    characters are Bengali. It renders as mismatched glyphs and reads, to a
    Kannada speaker, as though the system does not know the language."""

    def test_stray_bengali_is_mapped_to_kannada(self):
        from src.chatbot.kannada import normalize_script
        assert normalize_script("ತদন্তಿ") == "ತದನ್ತಿ"

    def test_mapping_is_phonetically_correct(self):
        """The Indic blocks share an order, so the same offset is the same
        letter: Bengali da -> Kannada da, not an arbitrary character."""
        from src.chatbot.kannada import normalize_script
        assert normalize_script("\u09a6") == "\u0ca6"   # da
        assert normalize_script("\u09a8") == "\u0ca8"   # na

    def test_devanagari_is_mapped_too(self):
        from src.chatbot.kannada import normalize_script
        assert normalize_script("\u0926") == "\u0ca6"   # Devanagari da

    def test_kannada_latin_and_digits_are_untouched(self):
        from src.chatbot.kannada import normalize_script
        s = "ಮೈಸೂರಿನಲ್ಲಿ 2023 ರಲ್ಲಿ 3,472 Theft"
        assert normalize_script(s) == s

    def test_detector_reports_offenders(self):
        from src.chatbot.kannada import foreign_script_chars
        assert foreign_script_chars("ತদন্তಿ")
        assert foreign_script_chars("ಮೈಸೂರು") == []
