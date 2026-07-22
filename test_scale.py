#!/usr/bin/env python3
"""Load, latency, and scale benchmarks for KSP chatbot."""

from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

PROJECT = Path(__file__).parent
sys.path.insert(0, str(PROJECT))

from src.chatbot.chat_store import ChatStore
from src.chatbot.db_manager import DatabaseManager
from src.chatbot.engine import CrimeChatbot
from src.chatbot.fallback_sql import try_fallback_sql
from src.chatbot.llm_config import get_llm_config, load_env

load_env(PROJECT)

API_BASE = "http://127.0.0.1:8000"


@dataclass
class LatencyStats:
    name: str
    times_ms: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def record(self, seconds: float) -> None:
        self.times_ms.append(seconds * 1000)

    def record_error(self, msg: str) -> None:
        self.errors.append(msg)

    def report(self) -> dict:
        if not self.times_ms:
            return {"name": self.name, "count": 0, "errors": len(self.errors)}
        sorted_t = sorted(self.times_ms)
        n = len(sorted_t)
        return {
            "name": self.name,
            "count": n,
            "errors": len(self.errors),
            "min_ms": round(sorted_t[0], 1),
            "p50_ms": round(sorted_t[n // 2], 1),
            "p95_ms": round(sorted_t[int(n * 0.95)], 1) if n >= 2 else round(sorted_t[0], 1),
            "max_ms": round(sorted_t[-1], 1),
            "avg_ms": round(statistics.mean(sorted_t), 1),
        }


def bench_sql_layer(db: DatabaseManager, iterations: int = 50) -> list[dict]:
    """Pure SQL execution — no LLM."""
    queries = [
        ("simple count", "criminal", "SELECT COUNT(*) FROM fir_details"),
        ("district group", "criminal", """
            SELECT d.name, COUNT(*) AS c FROM fir_details f
            JOIN districts d ON f.district_id = d.district_id
            GROUP BY d.name ORDER BY c DESC
        """),
        ("per-district top criminal", "ksp_crime", try_fallback_sql(
            "top criminal in every district"
        ).sql),
        ("person lookup", "criminal", try_fallback_sql(
            "details about rudra narang"
        ).sql),
        ("pocso by district", "criminal", try_fallback_sql(
            "POCSO count by district"
        ).sql),
        ("ncrb cyber", "ksp_crime", try_fallback_sql(
            "NCRB cyber Bengaluru 2024"
        ).sql),
    ]
    results = []
    for label, db_name, sql in queries:
        stats = LatencyStats(label)
        for _ in range(iterations):
            t0 = time.perf_counter()
            try:
                df = db.execute(db_name, sql)
                stats.record(time.perf_counter() - t0)
                if _ == 0:
                    stats._rows = len(df)  # type: ignore[attr-defined]
            except Exception as e:
                stats.record_error(str(e))
        r = stats.report()
        r["rows"] = getattr(stats, "_rows", "?")
        r["iterations"] = iterations
        results.append(r)
    return results


def bench_chat_store(store: ChatStore, sessions: int = 100, msgs_per: int = 10) -> dict:
    t0 = time.perf_counter()
    ids = []
    for i in range(sessions):
        s = store.create_session(title=f"Scale test {i}")
        ids.append(s.id)
        for j in range(msgs_per):
            store.add_message(s.id, "user" if j % 2 == 0 else "assistant", f"msg {j}")
    write_sec = time.perf_counter() - t0

    t1 = time.perf_counter()
    loaded = 0
    for sid in ids[:20]:
        loaded += len(store.get_messages(sid))
    read_sec = time.perf_counter() - t1

    t2 = time.perf_counter()
    for sid in ids:
        store.delete_session(sid)
    delete_sec = time.perf_counter() - t2

    return {
        "sessions_created": sessions,
        "messages_written": sessions * msgs_per,
        "write_sec": round(write_sec, 3),
        "write_msgs_per_sec": round(sessions * msgs_per / write_sec, 0),
        "read_20_sessions_sec": round(read_sec, 3),
        "delete_all_sec": round(delete_sec, 3),
    }


def bench_bot_sequential(bot: CrimeChatbot, questions: list[str], delay_sec: float = 1.5) -> list[dict]:
    """Full pipeline with LLM — spaced to avoid rate limits."""
    results = []
    for q in questions:
        stats = LatencyStats(q[:40])
        t0 = time.perf_counter()
        try:
            resp = bot.ask(q)
            stats.record(time.perf_counter() - t0)
            ok = bool(resp.answer) and "rate limit" not in resp.answer.lower()
            if not ok:
                stats.record_error(resp.answer[:120])
        except Exception as e:
            stats.record_error(str(e))
        r = stats.report()
        r["question"] = q
        results.append(r)
        time.sleep(delay_sec)
    return results


def api_post(path: str, body: dict, timeout: float = 120) -> tuple[float, dict | None, str | None]:
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(
            f"{API_BASE}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            elapsed = time.perf_counter() - t0
            return elapsed, json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        elapsed = time.perf_counter() - t0
        try:
            detail = json.loads(e.read()).get("detail", str(e))
        except Exception:
            detail = str(e)
        return elapsed, None, detail
    except Exception as e:
        return time.perf_counter() - t0, None, str(e)


def bench_api_concurrent(
    question: str,
    workers: int = 3,
    requests_per_worker: int = 2,
) -> dict:
    """Concurrent /api/chat — tests server + DB under parallel load."""
    stats = LatencyStats(f"concurrent x{workers * requests_per_worker}")
    errors = []

    def one_request(_: int) -> tuple[float, bool, str]:
        elapsed, data, err = api_post("/api/chat", {"message": question})
        if err:
            return elapsed, False, err
        if not data or not data.get("answer"):
            return elapsed, False, "empty answer"
        if "rate limit" in data.get("answer", "").lower():
            return elapsed, False, "groq rate limit"
        return elapsed, True, ""

    tasks = workers * requests_per_worker
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one_request, i) for i in range(tasks)]
        for f in as_completed(futures):
            elapsed, ok, err = f.result()
            if ok:
                stats.record(elapsed)
            else:
                stats.record_error(err)

    r = stats.report()
    r["workers"] = workers
    r["total_requests"] = tasks
    r["success_rate"] = round(len(stats.times_ms) / tasks * 100, 1) if tasks else 0
    r["sample_errors"] = stats.errors[:5]
    return r


def data_scale_report(db: DatabaseManager) -> dict:
    report = {}
    checks = [
        ("ksp_crime", "SELECT COUNT(*) AS n FROM fir_records"),
        ("ksp_crime", "SELECT COUNT(*) AS n FROM criminals"),
        ("ksp_crime", "SELECT COUNT(*) AS n FROM districts"),
        ("criminal", "SELECT COUNT(*) AS n FROM fir_details"),
        ("criminal", "SELECT COUNT(*) AS n FROM persons"),
        ("criminal", "SELECT COUNT(*) AS n FROM accused_persons"),
        ("cases", "SELECT COUNT(*) AS n FROM cases"),
    ]
    for db_name, sql in checks:
        df = db.execute(db_name, sql)
        key = f"{db_name}.{sql.split('FROM')[1].strip().split()[0]}"
        report[key] = int(df.iloc[0, 0])
    return report


def print_section(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def main() -> int:
    print_section("KSP CHATBOT — MODEL & SCALE BENCHMARK")
    cfg = get_llm_config()
    print(f"LLM: {cfg['provider']} / {cfg['model']} (enabled={cfg['enabled']})")

    db = DatabaseManager(PROJECT / "data")
    bot = CrimeChatbot(PROJECT / "data")
    store = ChatStore(PROJECT / "data" / "scale_test_chats.db")

    # 1) Data scale
    print_section("1. DATA SCALE")
    scale = data_scale_report(db)
    for k, v in scale.items():
        print(f"  {k}: {v:,}")

    # 2) SQL layer throughput
    print_section("2. SQL LAYER (50 iterations each, no LLM)")
    sql_bench = bench_sql_layer(db, iterations=50)
    for r in sql_bench:
        print(
            f"  {r['name']:28} rows={str(r.get('rows','?')):>5}  "
            f"p50={r.get('p50_ms','?')}ms  p95={r.get('p95_ms','?')}ms  "
            f"max={r.get('max_ms','?')}ms  err={r.get('errors',0)}"
        )

    # 3) Chat store scale
    print_section("3. CHAT STORE (100 sessions x 10 messages)")
    cs = bench_chat_store(store, sessions=100, msgs_per=10)
    for k, v in cs.items():
        print(f"  {k}: {v}")

    # 4) Full bot sequential (LLM)
    print_section("4. FULL PIPELINE — SEQUENTIAL (LLM + SQL, 1.5s gap)")
    llm_questions = [
        "hi",
        "top criminal in Gadag",
        "how many thefts in Bengaluru 2024",
        "NCRB cyber crimes Bengaluru 2024",
        "give me top criminal in every district",
    ]
    if cfg["enabled"]:
        seq = bench_bot_sequential(bot, llm_questions, delay_sec=2.0)
        for r in seq:
            status = "OK" if r.get("errors", 0) == 0 else f"ERR({r['errors']})"
            print(
                f"  [{status}] {r.get('question','')[:45]:45} "
                f"{r.get('avg_ms', r.get('p50_ms', '?'))}ms"
            )
    else:
        print("  Skipped — no LLM key")

    # 5) API concurrent load
    print_section("5. API CONCURRENT LOAD (fallback-heavy query)")
    try:
        urllib.request.urlopen(f"{API_BASE}/api/health", timeout=5)
        api_ok = True
    except Exception:
        api_ok = False
        print("  API offline — start: python run_web.py")

    if api_ok:
        # Light query for concurrent — less LLM pressure
        conc = bench_api_concurrent(
            "top 10 criminal names in Mysuru district",
            workers=3,
            requests_per_worker=2,
        )
        print(
            f"  {conc['total_requests']} requests, {conc['workers']} workers, "
            f"success={conc['success_rate']}%"
        )
        if conc.get("p50_ms"):
            print(
                f"  p50={conc['p50_ms']}ms  p95={conc.get('p95_ms')}ms  "
                f"max={conc.get('max_ms')}ms"
            )
        if conc.get("sample_errors"):
            print(f"  errors: {conc['sample_errors']}")

    # 6) Capacity estimates
    print_section("6. CAPACITY ESTIMATES")
    avg_sql = statistics.mean(
        r["p50_ms"] for r in sql_bench if r.get("p50_ms")
    )
    print(f"  SQL-only queries: ~{1000 / avg_sql:.0f} req/sec theoretical (single thread)")
    if cfg["enabled"] and seq:
        llm_times = [r["avg_ms"] for r in seq if r.get("avg_ms")]
        if llm_times:
            avg_llm = statistics.mean(llm_times)
            print(f"  Full chat (Groq): ~{60000 / avg_llm:.1f} questions/min max (sequential)")
            print(f"  Groq free tier: expect 429 if >~10-15 rapid LLM calls")
    print(f"  Current FIR dataset: {scale.get('criminal.fir_details', 0):,} rows")
    print(f"  Query timeout: 20s (env QUERY_TIMEOUT_SECONDS)")

    # Cleanup scale test db
    try:
        if store.db_path.exists():
            store.db_path.unlink(missing_ok=True)
    except OSError:
        pass

    print_section("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
