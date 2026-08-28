# 04. Machine learning results silently empty under concurrent load

**Outcome:** a load-dependent bug that only appears when two components read the database
at once, hidden behind a bare `except`. Found by a UI check, not by any test that existed
at the time.

---

## Symptom

Walking the UI during a pre-deploy QA pass, the AI Brief showed:

```
5 Hotspots   0 ML Clusters   5 Anomalies   6 Live Alerts   6 News Items
```

Zero clusters. But `/api/ml/clusters` returned six, and it had passed the endpoint suite
minutes earlier.

## Diagnosis

Calling `_gather_signals()` in a fresh process gave `clusters: 3`, correct. So the failure
only occurred inside the running server, which meant state rather than logic.

The relevant code:

```python
try: sig["clusters"] = ml.crime_clusters().get("clusters", [])[:3]
except Exception: sig["clusters"] = []
```

Reproduced by holding one connection open before calling the ML layer:

```
held open a default-config connection
ml.crime_clusters FAILED: ConnectionException
    Can't open a connection to same database file with a different
    configuration than existing connections
```

DuckDB refuses a second connection to the same file under a different configuration. The
codebase had two:

```python
# src/ml/patterns.py, evidence.py, db_manager.py, news
duckdb.connect(path, read_only=True, config={"enable_external_access": False})

# api/analytics.py, api/main.py, rag/schema_live.py
duckdb.connect(path, read_only=True)          # default config
```

Whenever an analytics reader held a connection while an ML reader opened one, the ML call
raised, the bare `except` swallowed it, and the caller received an empty list that was
indistinguishable from a genuine zero.

## Why it was dangerous

**It is load-dependent.** Sequential requests each open and close cleanly, so the endpoint
suite passed. It needs overlap, which is exactly what a judge clicking between tabs
produces.

**It fails as data, not as an error.** Nothing appears in a log. The worst case was the
investigation agent reporting "No emerging geographic clusters" as a finding.

## Fix

All four runtime readers now use the same configuration, which also hardens the two that
previously permitted filesystem access from SQL:

```python
# Keep identical to DatabaseManager._DUCKDB_SAFE_CONFIG everywhere.
_DUCKDB_SAFE_CONFIG = {"enable_external_access": False}
```

Verified by holding a connection open and calling every reader through it: all seven
succeeded.

## Guarding it

A concurrency check was added to the QA suite, since sequential testing cannot catch this:

```python
paths = ["/api/ml/clusters", "/api/analytics/hotspots", "/api/analytics/network", ...]
# fired simultaneously on threads; any empty list under load is a failure
```

`tests/test_api.py` asserts each ML endpoint returns a non-empty list, that analytics and
ML can interleave, and that the brief's signal counts are all non-zero.

## Lesson

The bare `except` is the real defect. The connection mismatch was a one-line
inconsistency; what turned it into a silent wrong answer was catching every exception and
substituting an empty list.

Where an empty result is indistinguishable from a real zero, either let the exception
surface or record that the call failed. A test that only asserts HTTP 200 will never
notice the difference.
