"""Case file document store — upload, extract, retrieve for LLM context."""

import hashlib
import io
import json
import re
import sqlite3
from pathlib import Path


class DocStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init()

    def _init(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""CREATE TABLE IF NOT EXISTS case_docs (
            doc_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            filename   TEXT,
            file_type  TEXT,
            size_bytes INTEGER,
            sha256     TEXT,
            text       TEXT,
            page_count INTEGER DEFAULT 0,
            uploaded_at TEXT DEFAULT (datetime('now'))
        )""")
        conn.commit()
        conn.close()

    # ── extraction ──────────────────────────────────────────────────────────

    @staticmethod
    def extract_text(filename: str, data: bytes) -> tuple[str, int]:
        """Return (text, page_count). Page count meaningful for PDFs only."""
        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            return DocStore._extract_pdf(data)
        if ext in (".docx", ".doc"):
            return DocStore._extract_docx(data)
        if ext in (".txt", ".md", ".csv"):
            return data.decode("utf-8", errors="replace"), 1
        return data.decode("utf-8", errors="replace"), 1

    @staticmethod
    def _extract_pdf(data: bytes) -> tuple[str, int]:
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            pages = []
            for i, page in enumerate(reader.pages):
                txt = page.extract_text() or ""
                if txt.strip():
                    pages.append(f"[Page {i+1}]\n{txt}")
            return "\n\n".join(pages), len(reader.pages)
        except Exception as e:
            return f"[PDF extraction error: {e}]", 0

    @staticmethod
    def _extract_docx(data: bytes) -> tuple[str, int]:
        try:
            import docx
            doc = docx.Document(io.BytesIO(data))
            paras = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paras), 1
        except Exception as e:
            return f"[DOCX extraction error: {e}]", 0

    # ── storage ─────────────────────────────────────────────────────────────

    def save(self, session_id: str, filename: str, data: bytes) -> dict:
        text, pages = self.extract_text(filename, data)
        sha = hashlib.sha256(data).hexdigest()
        ext = Path(filename).suffix.lower().lstrip(".")
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            """INSERT INTO case_docs(session_id, filename, file_type, size_bytes, sha256, text, page_count)
               VALUES (?,?,?,?,?,?,?)""",
            (session_id, filename, ext, len(data), sha, text, pages),
        )
        doc_id = cur.lastrowid
        conn.commit()
        conn.close()
        return {
            "doc_id": doc_id,
            "filename": filename,
            "file_type": ext,
            "size_bytes": len(data),
            "page_count": pages,
            "text_preview": text[:200],
        }

    def list_docs(self, session_id: str) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT doc_id, filename, file_type, size_bytes, page_count, uploaded_at "
            "FROM case_docs WHERE session_id=? ORDER BY doc_id DESC",
            (session_id,),
        ).fetchall()
        conn.close()
        return [
            {"doc_id": r[0], "filename": r[1], "file_type": r[2],
             "size_bytes": r[3], "page_count": r[4], "uploaded_at": r[5]}
            for r in rows
        ]

    def delete(self, session_id: str, doc_id: int) -> bool:
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute(
            "DELETE FROM case_docs WHERE doc_id=? AND session_id=?", (doc_id, session_id)
        )
        conn.commit()
        conn.close()
        return cur.rowcount > 0

    def get_context(self, session_id: str, question: str, max_chars: int = 6000) -> str:
        """Return relevant excerpt from session docs for the given question."""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT filename, text FROM case_docs WHERE session_id=? ORDER BY doc_id",
            (session_id,),
        ).fetchall()
        conn.close()
        if not rows:
            return ""

        # Simple keyword relevance: score each chunk by query word overlap
        q_words = set(re.findall(r"\w+", question.lower()))
        chunks = []
        for fname, text in rows:
            # split into ~500-char chunks
            for i in range(0, len(text), 500):
                chunk = text[i: i + 500]
                words = set(re.findall(r"\w+", chunk.lower()))
                score = len(q_words & words)
                chunks.append((score, fname, chunk))

        chunks.sort(key=lambda x: -x[0])
        budget = max_chars
        selected = []
        seen_files: set[str] = set()
        for score, fname, chunk in chunks:
            if budget <= 0:
                break
            if fname not in seen_files:
                selected.append(f"\n--- From: {fname} ---")
                seen_files.add(fname)
            selected.append(chunk[:budget])
            budget -= len(chunk)

        return "\n".join(selected) if selected else ""
