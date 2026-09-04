"""UI localisation.

Switching the toggle to Kannada used to change only the input placeholder, so an
officer working in Kannada still read an English interface. The chrome strings
now carry Kannada translations.

The script check is not theoretical: the first machine translation returned
"Investigate" as ತদন্তಿ, which mixes Bengali characters into a Kannada word. It
renders without error and looks plausible unless you check the code points.
"""
import json
import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "index.html"

# Indic blocks that must never appear in a Kannada string.
_FOREIGN_SCRIPTS = {
    "Devanagari": (0x0900, 0x0980), "Bengali": (0x0980, 0x0A00),
    "Gurmukhi": (0x0A00, 0x0A80), "Gujarati": (0x0A80, 0x0B00),
    "Oriya": (0x0B00, 0x0B80), "Tamil": (0x0B80, 0x0C00),
    "Telugu": (0x0C00, 0x0C80), "Malayalam": (0x0D00, 0x0D80),
}


@pytest.fixture(scope="module")
def ui_kn() -> dict:
    html = FRONTEND.read_text(encoding="utf-8")
    m = re.search(r"const UI_KN = \{(.*?)\n\};", html, re.S)
    assert m, "UI_KN dictionary not found in the frontend"
    out = {}
    for line in m.group(1).splitlines():
        pair = re.match(r"\s*'((?:[^'\\]|\\.)*)'\s*:\s*'((?:[^'\\]|\\.)*)'\s*,", line)
        if pair:
            out[pair.group(1).replace("\\'", "'")] = pair.group(2).replace("\\'", "'")
    assert out, "UI_KN parsed but empty"
    return out


class TestTranslations:
    def test_dictionary_is_populated(self, ui_kn):
        assert len(ui_kn) >= 40

    def test_no_foreign_indic_script(self, ui_kn):
        """A machine translation returned Bengali characters inside a Kannada
        word. It renders fine and reads as Kannada at a glance."""
        offenders = []
        for english, kannada in ui_kn.items():
            for ch in kannada:
                cp = ord(ch)
                for name, (lo, hi) in _FOREIGN_SCRIPTS.items():
                    if lo <= cp < hi:
                        offenders.append(f"{english!r} -> {kannada!r} has {name} {ch!r}")
                        break
        assert not offenders, "foreign script in translations: " + "; ".join(offenders)

    def test_every_value_contains_kannada(self, ui_kn):
        """Guards against an untranslated string being left in the map."""
        kn = re.compile(r"[ಀ-೿]")
        missing = [k for k, v in ui_kn.items() if not kn.search(v)]
        assert not missing, f"no Kannada characters in: {missing}"

    def test_key_navigation_labels_are_present(self, ui_kn):
        for label in ["Analytics", "Investigate", "Evidence Intel", "Intel Map",
                      "New Chat", "Audit Trail", "Case Solver"]:
            assert label in ui_kn, f"missing translation for {label!r}"

    def test_acronyms_are_preserved(self, ui_kn):
        """FIR, AI and ML are read as-is by officers and must not be transliterated."""
        assert "FIR" in ui_kn["Total FIRs"]
        assert "FIR" in ui_kn["Top Districts by FIR Count"]
        assert "ML" in ui_kn["ML Clusters"]

    def test_distinct_crimes_have_distinct_words(self, ui_kn):
        """Burglary first came back identical to Theft, which would make two
        different case categories read the same in the sidebar."""
        assert ui_kn.get("Burglary") != ui_kn.get("Theft")


@pytest.fixture(scope="module")
def kn_district() -> dict:
    html = FRONTEND.read_text(encoding="utf-8")
    m = re.search(r"const KN_DISTRICT = \{(.*?)\n\};", html, re.S)
    assert m, "KN_DISTRICT map not found in the frontend"
    return dict(re.findall(r"'([^']+)':\s*'([^']+)'", m.group(1)))


class TestShellIsTranslated:
    """The toggle used to leave the masthead, the welcome screen and the alert
    strip in English, so the app still read as an English product in Kannada."""

    def test_masthead_and_welcome(self, ui_kn):
        for label in ["Crime Intelligence", "Karnataka State Police",
                      "KSP Crime Intelligence AI",
                      "Karnataka State Police · Internal System"]:
            assert label in ui_kn, f"missing translation for {label!r}"

    def test_example_questions_are_translated(self, ui_kn):
        """fillExample() puts the card's own text in the input box, so an
        English question there would come back with an English answer."""
        for q in ["How many thefts in Bengaluru in 2023?",
                  "Who are the top repeat offenders by district?",
                  "Conviction rate by district in 2017?"]:
            assert q in ui_kn, f"example question not translated: {q!r}"

    def test_status_text_is_not_translated(self):
        """#statusText is overwritten at runtime with the live provider id, so
        caching its first value would replace that with a stale label."""
        html = FRONTEND.read_text(encoding="utf-8")
        sels = re.search(r"function applyUiLanguage\(lang\) \{(.*?)\n  sels\.forEach", html, re.S)
        assert sels, "applyUiLanguage selector list not found"
        assert "'#statusText'" not in sels.group(1)


class TestDistrictMap:
    def test_covers_every_district(self, kn_district):
        assert len(kn_district) == 31, f"expected 31 districts, got {len(kn_district)}"

    def test_values_are_kannada_only(self, kn_district):
        kn = re.compile(r"[ಀ-೿]")
        for en, name in kn_district.items():
            assert kn.search(name), f"{en!r} has no Kannada characters"
            for ch in name:
                for script, (lo, hi) in _FOREIGN_SCRIPTS.items():
                    assert not (lo <= ord(ch) < hi), f"{en!r} -> {name!r} has {script}"

    def test_matches_the_backend_spelling(self, kn_district):
        """The strip must show the spelling the backend parser accepts, or an
        officer who reads a district name and types it back gets no match."""
        from src.chatbot.rag.schema_live import _KN_DISTRICTS
        for english, kannada in kn_district.items():
            assert _KN_DISTRICTS.get(kannada) == english, \
                f"{kannada!r} is not the backend's Kannada name for {english!r}"


class TestWiring:
    def test_alert_strip_redraws_on_toggle(self):
        """The strip is rebuilt by innerHTML on a 60s timer, so without an
        explicit redraw it stayed English for up to a minute after switching."""
        html = FRONTEND.read_text(encoding="utf-8")
        setlang = re.search(r"function setLang\(lang\) \{(.*?)\n\}", html, re.S)
        assert setlang and "renderAlerts(" in setlang.group(1)

    def test_alert_click_asks_in_kannada(self):
        """The question decides the reply's language, so a Kannada UI must send
        a Kannada question or the officer gets an English answer."""
        html = FRONTEND.read_text(encoding="utf-8")
        fn = re.search(r"function askAlertInChat\((.*?)\n\}", html, re.S)
        assert fn, "askAlertInChat not found"
        assert re.search(r"[ಀ-೿]", fn.group(1)), "no Kannada branch in askAlertInChat"

    def test_apply_runs_on_toggle(self):
        html = FRONTEND.read_text(encoding="utf-8")
        setlang = re.search(r"function setLang\(lang\) \{(.*?)\n\}", html, re.S)
        assert setlang, "setLang not found"
        assert "applyUiLanguage(lang)" in setlang.group(1), \
            "the toggle must apply the UI language, not just the placeholder"

    def test_english_original_is_retained_for_restore(self):
        """Switching back to English must restore the exact original text."""
        html = FRONTEND.read_text(encoding="utf-8")
        assert "dataset.enText" in html
