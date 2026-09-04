"""API contract tests via FastAPI's TestClient.

No network and no model calls: every endpoint asserted here is deterministic.
The LLM-backed endpoints (chat summarisation, /api/investigate, /api/evidence,
/api/intelligence) are covered by scripts/qa_smoke.py against a running server.
"""
import pytest

from conftest import requires_data

pytestmark = requires_data


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from api.main import app
    with TestClient(app) as c:
        yield c


class TestHealth:
    def test_health_reports_every_database(self, client):
        j = client.get("/api/health").json()
        assert j["status"] == "ok"
        assert all(j["databases"].values()), j["databases"]

    def test_models_endpoint_names_the_active_provider(self, client):
        j = client.get("/api/models").json()
        assert j["active"]["provider"]
        assert j["active"]["model"]

    def test_frontend_is_served(self, client):
        r = client.get("/")
        assert r.status_code == 200 and "KSP" in r.text


class TestAnalytics:
    @pytest.mark.parametrize("path", [
        "/api/analytics/trends",
        "/api/analytics/crime-type-trends",
        "/api/analytics/hotspots",
        "/api/analytics/district-breakdown",
        "/api/analytics/predictions",
        "/api/analytics/alerts",
        "/api/analytics/cases-summary",
        "/api/analytics/behavioral-profile",
        "/api/analytics/network",
    ])
    def test_endpoint_responds(self, client, path):
        assert client.get(path).status_code == 200

    def test_day_of_week_has_seven_buckets(self, client):
        """A missing by_day key rendered the day-of-week chart blank."""
        by_day = client.get("/api/analytics/behavioral-profile").json()["by_day"]
        assert len(by_day) == 7

    def test_network_has_no_duplicate_people(self, client):
        """Accused holds one row per case, so the same person arrived as several
        nodes and the graph drew them repeatedly."""
        nodes = client.get("/api/analytics/network").json()["nodes"]
        labels = [n["label"] for n in nodes]
        assert len(labels) == len(set(labels))

    def test_network_fir_counts_are_real(self, client):
        """fir_count was hardcoded to 1 for every node."""
        nodes = client.get("/api/analytics/network").json()["nodes"]
        assert max(int(n["firs"]) for n in nodes) > 1

    def test_network_edges_reference_existing_nodes(self, client):
        j = client.get("/api/analytics/network").json()
        ids = {n["id"] for n in j["nodes"]}
        assert all(e["from"] in ids and e["to"] in ids for e in j["edges"])


class TestMachineLearning:
    @pytest.mark.parametrize("path,key", [
        ("/api/ml/clusters", "clusters"),
        ("/api/ml/anomalies", "anomalies"),
        ("/api/ml/forecast", "forecast"),
    ])
    def test_ml_returns_results(self, client, path, key):
        """These read DuckDB with a different connection config to analytics.
        A mismatch raises into a bare except and silently returns nothing."""
        j = client.get(path).json()
        assert isinstance(j[key], list) and j[key]

    def test_ml_and_analytics_can_interleave(self, client):
        """Reproduces the config-conflict regression: analytics first, then ML."""
        assert client.get("/api/analytics/hotspots").status_code == 200
        assert client.get("/api/ml/clusters").json()["clusters"]


class TestRequestValidation:
    def test_empty_message_is_rejected(self, client):
        assert client.post("/api/chat", json={"message": ""}).status_code == 422

    def test_oversized_message_is_rejected(self, client):
        r = client.post("/api/chat", json={"message": "x" * 5000})
        assert r.status_code == 422

    def test_unknown_database_is_404(self, client):
        assert client.get("/api/browse/not_a_db/schema").status_code == 404


class TestSupportingEndpoints:
    @pytest.mark.parametrize("path", [
        "/api/sessions",
        "/api/audit",
        "/api/case-solver/stats",
        "/api/browse/criminal/schema",
        "/api/investigate/examples",
        "/api/evidence/sample",
    ])
    def test_endpoint_responds(self, client, path):
        assert client.get(path).status_code == 200

    def test_evidence_sample_is_usable(self, client):
        assert len(client.get("/api/evidence/sample").json()["statement"]) > 50

    def test_evidence_requires_input(self, client):
        assert client.post("/api/evidence/analyze", data={"text": ""}).status_code == 400


class TestSessionLifecycleOverHttp:
    def test_create_list_delete(self, client):
        created = client.post("/api/sessions", json={"title": "pytest session"})
        assert created.status_code in (200, 201)
        sid = created.json().get("session_id") or created.json().get("id")
        assert sid
        listed = client.get("/api/sessions").json()
        rows = listed if isinstance(listed, list) else listed.get("sessions", [])
        assert any((r.get("id") or r.get("session_id")) == sid for r in rows)
        assert client.delete(f"/api/sessions/{sid}").status_code in (200, 204)


class TestEvidenceNameExtraction:
    """Names pulled from a statement are offered to the officer as people to
    check, so institutional phrases appearing there read as sloppy work."""

    def test_place_and_institution_phrases_are_not_people(self):
        from src.chatbot.evidence import extract_names
        text = (
            "Police Station : Mysuru City - Devaraja Sub-Division. The seized "
            "material was sent to the Forensic Science Laboratory. The witness "
            "Arjun Fernandes named David Mirza as the rider."
        )
        names = extract_names(text)
        assert "Arjun Fernandes" in names
        assert "David Mirza" in names
        for noise in ("Mysuru City", "Forensic Science", "Science Laboratory"):
            assert noise not in names, f"{noise!r} was offered as a person"

    def test_a_name_does_not_run_across_a_line_break(self):
        """Plain \s let a name swallow the first word of the next line."""
        from src.chatbot.evidence import extract_names
        names = extract_names("The accused is David Mirza\nDate of record : 03/09/2026")
        assert "David Mirza" in names


class TestSpeechEndpoint:
    """Kannada read-aloud cannot depend on the officer's machine having a
    Kannada voice, because Windows ships none. The server generates it."""

    def test_wav_header_is_valid(self):
        """Gemini returns headerless PCM, which no browser will play from an
        <audio> element. It has to be wrapped."""
        from src.tts.gemini_tts import _wav
        wav = _wav(b"\x00\x01" * 100)
        assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
        assert wav[12:16] == b"fmt " and wav[36:40] == b"data"

    def test_same_text_and_language_share_a_cache_entry(self):
        from src.tts.gemini_tts import cached_path
        a = cached_path("ಸಾಕ್ಷ್ಯ ಗುಪ್ತಚರ", "kn")
        b = cached_path("ಸಾಕ್ಷ್ಯ ಗುಪ್ತಚರ", "kn")
        c = cached_path("ಸಾಕ್ಷ್ಯ ಗುಪ್ತಚರ", "en")
        assert a == b and a != c

    def test_empty_text_is_refused_without_calling_out(self):
        from src.tts.gemini_tts import synthesize
        audio, note = synthesize("", "kn")
        assert audio is None and "empty" in note

    def test_a_failure_is_reported_not_raised(self, monkeypatch):
        """Speech is an enhancement; it must never break the page."""
        import src.tts.gemini_tts as t
        monkeypatch.setattr(t, "_api_key", lambda: "")
        audio, note = t.synthesize("ಪರೀಕ್ಷೆ ವಾಕ್ಯ", "kn")
        assert audio is None and "key" in note.lower()
