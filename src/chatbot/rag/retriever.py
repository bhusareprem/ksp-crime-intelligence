"""Retrieve schema + similar SQL examples for a question (RAG context)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.chatbot.rag.examples import EXAMPLES_BY_DB, QueryExample
from src.chatbot.rag.schema_live import get_live_schema, get_value_hints, ground_values
from src.chatbot.schemas import SCHEMAS


@dataclass
class RAGContext:
    database: str
    routing_reason: str
    live_schema: str
    value_hints: str
    static_schema: str
    value_grounding: str = ""
    examples: list[QueryExample] = field(default_factory=list)
    web_snippet: str | None = None

    def to_prompt_block(self) -> str:
        lines = [
            f"=== TARGET DATABASE: {self.database} ===",
            f"Why this database: {self.routing_reason}",
            "",
            self.value_hints,
        ]
        if self.value_grounding:
            lines += ["", self.value_grounding]
        lines += [
            "",
            self.static_schema,
            "",
            self.live_schema,
        ]
        if self.examples:
            lines.append("\n=== SIMILAR WORKING SQL EXAMPLES (follow these patterns) ===")
            for i, ex in enumerate(self.examples, 1):
                lines.append(f"\nExample {i} — Q: {ex.question}")
                lines.append(f"SQL:\n{ex.sql.strip()}")
        if self.web_snippet:
            lines.append("\n=== RECENT WEB CONTEXT (supplement DB data; cite as external) ===")
            lines.append(self.web_snippet)
        return "\n".join(lines)


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _score_example(question: str, example: QueryExample) -> float:
    q = _tokenize(question)
    if not q:
        return 0.0
    ex = _tokenize(example.question) | _tokenize(" ".join(example.tags))
    overlap = len(q & ex)
    tag_bonus = sum(2 for t in example.tags if t in question.lower())
    return overlap + tag_bonus


def retrieve_similar_examples(question: str, db_name: str, top_k: int = 3) -> list[QueryExample]:
    pool = EXAMPLES_BY_DB.get(db_name, [])
    scored = [( _score_example(question, ex), ex) for ex in pool]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [ex for score, ex in scored[:top_k] if score > 0] or pool[:top_k]


def retrieve_context(
    question: str,
    db_name: str,
    routing_reason: str,
    data_dir,
    web_snippet: str | None = None,
    top_examples: int = 3,
) -> RAGContext:
    from pathlib import Path

    data_dir = Path(data_dir)
    # The 'criminal' DB is the CCTNS ksp_fir.duckdb (fall back to old unified criminal.db).
    fir_path = next(
        (p for p in [data_dir / "ksp_fir.duckdb", data_dir / "unified" / "ksp_fir.duckdb"] if p.exists()),
        data_dir / "ksp_fir.duckdb",
    )
    paths = {
        "ksp_crime": data_dir / "ksp_crime.db",
        "criminal": fir_path if fir_path.exists() else data_dir / "criminal.db",
        "cases": data_dir / "cases.db",
    }
    db_path = paths.get(db_name, data_dir / "ksp_crime.db")
    live = get_live_schema(db_path, db_name)
    grounding = ground_values(question, str(db_path)) if db_name == "criminal" else ""
    return RAGContext(
        database=db_name,
        routing_reason=routing_reason,
        live_schema=live,
        value_hints=get_value_hints(db_name),
        static_schema=SCHEMAS.get(db_name, ""),
        value_grounding=grounding,
        examples=retrieve_similar_examples(question, db_name, top_k=top_examples),
        web_snippet=web_snippet,
    )
