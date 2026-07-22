"""Optional web search for questions needing current / external context."""

import os
import re

WEB_TRIGGER = re.compile(
    r"\b(latest|recent|newest|news|today|this year|current|currently|"
    r"up[\s-]?to[\s-]?date|updated|nowadays|these days|as of|"
    r"trending|what is happening|outside database|on the internet)\b",
    re.I,
)


def _web_enabled() -> bool:
    return os.getenv("ENABLE_WEB_SEARCH", "1").strip().lower() not in ("0", "false", "no")


def needs_web_search(question: str) -> bool:
    return _web_enabled() and bool(WEB_TRIGGER.search(question))


def _format_hits(hits: list) -> str | None:
    if not hits:
        return None
    parts = []
    for h in hits:
        title = h.get("title", "")
        body = (h.get("body") or h.get("description") or "")[:300]
        href = h.get("href") or h.get("url") or ""
        line = f"- {title}: {body}"
        if href:
            line += f" ({href})"
        parts.append(line)
    text = "\n".join(parts).strip()
    return text or None


def search_web(question: str, max_results: int = 5, bare: bool = False, retries: int = 2) -> str | None:
    """Search the web for supplementary context. Returns None if unavailable.
    bare=True skips the 'Karnataka India crime' prefix (for officer-typed queries).

    Uses the maintained `ddgs` package with a short retry/backoff (DuckDuckGo
    rate-limits bursts), falling back to the legacy `duckduckgo_search` package
    and finally the LangChain tool."""
    import time

    query = (question if bare else f"Karnataka India crime {question}")[:200]

    # 1. Preferred: maintained `ddgs` package, with retry on empty/rate-limit.
    for attempt in range(retries + 1):
        try:
            from ddgs import DDGS

            with DDGS() as ddgs:
                hits = list(ddgs.text(query, max_results=max_results))
            out = _format_hits(hits)
            if out:
                return out
        except ImportError:
            break
        except Exception:
            pass
        if attempt < retries:
            time.sleep(1.2 * (attempt + 1))  # backoff for rate-limits

    # 2. Legacy package fallback.
    try:
        import duckduckgo_search

        with duckduckgo_search.DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=max_results))
        out = _format_hits(hits)
        if out:
            return out
    except Exception:
        pass

    # 3. LangChain tool fallback.
    try:
        from langchain_community.tools import DuckDuckGoSearchRun

        tool = DuckDuckGoSearchRun(max_results=max_results)
        result = tool.run(query)
        return result.strip() if result and result.strip() else None
    except Exception:
        return None
