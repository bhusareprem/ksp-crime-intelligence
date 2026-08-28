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
