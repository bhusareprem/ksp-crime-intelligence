"""Matching a person named in Kannada script against English CCTNS names.

A statement written properly in Kannada used to extract no names at all, so the
Evidence cross-reference came back empty in the one language the product claims
as a differentiator.

The risk running the other way is worse. 17.7% of the 3,525 accused names share
a consonant skeleton, so a confident single answer would sooner or later hand an
officer the wrong Patil. These tests pin the behaviour that keeps that from
happening: candidates, ranked, with the ambiguity visible.
"""
import pytest

from src.chatbot.kannada_names import (
    extract_kannada_names,
    match_candidates,
    skeleton,
    transliterate,
)

# A slice of real accused names, including the collision clusters.
DB = [
    "Arun Patil", "Arun Patel", "Eranna Patil", "Eranna Patel", "Farhan Patil",
    "David Mirza", "Pushpa Shaikh", "Thomas Shaikh", "Rashid Rao",
    "Thimmaiah Begum", "Basavraj Salian", "Srinivas Bandi", "Suresh Gowda",
    "Meena Dias", "Amina Desai",
]


class TestTransliteration:
    def test_consonant_and_matra(self):
        assert transliterate("ಡೇವಿಡ್") == "devid"

    def test_virama_removes_inherent_vowel(self):
        """Without the virama rule every word gains a trailing 'a'."""
        assert not transliterate("ಅರುಣ್").endswith("na")

    def test_anusvara_is_m_before_a_labial(self):
        """ಬೇಗಂ is recorded as Begum, not Begun."""
        assert transliterate("ಬೇಗಂ").endswith("m")

    def test_latin_text_passes_through(self):
        assert "David" in transliterate("David Mirza")


class TestSkeleton:
    @pytest.mark.parametrize("a,b", [
        ("mirza", "mirja"),        # ja romanised as j or z
        ("begum", "begun"),        # anusvara written either way
        ("thomas", "tomas"),       # aspirate written th or t
    ])
    def test_spelling_variants_share_a_skeleton(self, a, b):
        assert skeleton(a) == skeleton(b)

    def test_different_names_do_not(self):
        assert skeleton("David Mirza") != skeleton("Suresh Gowda")


class TestExtraction:
    def test_finds_a_name_before_a_marker(self):
        got = extract_kannada_names("ಬೈಕ್ ಚಲಾಯಿಸುತ್ತಿದ್ದವನನ್ನು ಡೇವಿಡ್ ಮಿರ್ಜಾ ಎಂದು ಗುರುತಿಸಿದೆ.")
        assert "ಡೇವಿಡ್ ಮಿರ್ಜಾ" in got

    def test_does_not_swallow_an_inflected_verb(self):
        """Kannada piles suffixes onto a stem, so a long word is a verb, not a
        surname. This one was being read as part of the driver's name."""
        got = extract_kannada_names("ಬೈಕ್ ಚಲಾಯಿಸುತ್ತಿದ್ದವನನ್ನು ಡೇವಿಡ್ ಮಿರ್ಜಾ ಎಂದು ಗುರುತಿಸಿದೆ.")
        assert not any("ಚಲಾಯಿಸುತ್ತಿದ್ದವನನ್ನು" in g for g in got)

    def test_does_not_keep_the_marker_in_the_name(self):
        got = extract_kannada_names("ಆರೋಪಿ ಅರುಣ್ ಪಾಟೀಲ್ ಎಂಬುವವರು ಬಂದರು.")
        assert "ಅರುಣ್ ಪಾಟೀಲ್" in got
        assert not any("ಎಂಬುವವರು" in g for g in got)

    def test_one_person_yields_one_span(self):
        """The bare and marker-suffixed readings both matched, so one man
        appeared twice in the officer's list."""
        got = extract_kannada_names("ಆರೋಪಿ ಅರುಣ್ ಪಾಟೀಲ್ ಎಂಬುವವರು ಬಂದರು.")
        assert len([g for g in got if "ಅರುಣ್" in g]) == 1


class TestCandidates:
    def test_finds_the_right_person(self):
        got = [c["name"] for c in match_candidates("ಡೇವಿಡ್ ಮಿರ್ಜಾ", DB)]
        assert "David Mirza" in got

    def test_ambiguity_is_surfaced_not_resolved(self):
        """ಅರುಣ್ ಪಾಟೀಲ್ fits four real people. Returning only the best one is
        how the wrong man acquires a criminal history."""
        got = [c["name"] for c in match_candidates("ಅರುಣ್ ಪಾಟೀಲ್", DB)]
        assert len(got) > 1
        assert "Arun Patil" in got and "Arun Patel" in got

    def test_best_candidate_ranks_first(self):
        got = match_candidates("ಅರುಣ್ ಪಾಟೀಲ್", DB)
        assert got[0]["name"] == "Arun Patil"

    def test_a_name_not_in_the_database_returns_nothing(self):
        """Silence is a real answer. Forcing a nearest match would invent one."""
        assert match_candidates("ಕ್ಸಿಯಾವೊ ಲಿ", DB) == []

    def test_a_bystander_phrase_does_not_become_an_accused(self):
        """ಸಹ ಅಲ್ಲಿದ್ದರు ("also were there") matched Usha Ali at 0.60 before the
        similarity floor was raised."""
        assert match_candidates("ಸಹ ಅಲ್ಲಿದ್ದರು", DB + ["Usha Ali"]) == []

    def test_weak_transliterations_still_match(self):
        """CCTNS drops the y glide (Salian) and writes ಯ್ಯ as 'aiah'."""
        for kn, expect in [("ಬಸವರಾಜ್ ಸಾಲಿಯಾನ್", "Basavraj Salian"),
                           ("ತಿಮ್ಮಯ್ಯ ಬೇಗಂ", "Thimmaiah Begum")]:
            assert expect in [c["name"] for c in match_candidates(kn, DB)], kn


class TestEvidenceIntegration:
    def test_candidates_are_kept_apart_from_confirmed_matches(self):
        from src.chatbot.evidence import analyze
        r = analyze("ಆರೋಪಿ ಅರುಣ್ ಪಾಟೀಲ್ ಎಂಬುವವರು ಬಂದರು.", use_llm=False, kannada=True)
        assert "name_candidates" in r
        # A transliterated guess must never be what escalates a case.
        assert r["high_risk"] is False
