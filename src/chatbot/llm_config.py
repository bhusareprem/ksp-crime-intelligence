"""Multi-provider LLM configuration — Groq, Gemini, OpenRouter, Ollama, Mistral."""

import os
from typing import Any

from langchain_openai import ChatOpenAI

# ─── Provider catalogue ────────────────────────────────────────────────────

PROVIDERS = {
    "groq": {
        "label": "Groq (Free)",
        "base_url": "https://api.groq.com/openai/v1",
        "env_key": "GROQ_API_KEY",
        "fallback_env": "OPENAI_API_KEY",
        "key_prefix": "gsk_",
        "models": [
            {"id": "llama-3.3-70b-versatile",  "label": "LLaMA 3.3 70B (best)"},
            {"id": "llama-3.1-8b-instant",      "label": "LLaMA 3.1 8B (fast)"},
            {"id": "mixtral-8x7b-32768",         "label": "Mixtral 8x7B"},
            {"id": "gemma2-9b-it",              "label": "Gemma 2 9B"},
        ],
        "driver": "openai_compat",
    },
    "gemini": {
        "label": "Google Gemini (Free)",
        "env_key": "GEMINI_API_KEY",
        "fallback_env": "GOOGLE_API_KEY",
        "models": [
            {"id": "gemini-2.5-flash",           "label": "Gemini 2.5 Flash (free, best)"},
            {"id": "gemini-3.5-flash",           "label": "Gemini 3.5 Flash (free)"},
            {"id": "gemini-2.0-flash",            "label": "Gemini 2.0 Flash (free)"},
            {"id": "gemini-2.0-flash-lite",      "label": "Gemini 2.0 Flash Lite (free)"},
        ],
        "driver": "genai_sdk",
    },
    "openrouter": {
        "label": "OpenRouter (Free models)",
        "base_url": "https://openrouter.ai/api/v1",
        "env_key": "OPENROUTER_API_KEY",
        "models": [
            {"id": "meta-llama/llama-3.1-8b-instruct:free",   "label": "LLaMA 3.1 8B (free)"},
            {"id": "google/gemma-2-9b-it:free",                "label": "Gemma 2 9B (free)"},
            {"id": "mistralai/mistral-7b-instruct:free",       "label": "Mistral 7B (free)"},
            {"id": "qwen/qwen-2-7b-instruct:free",             "label": "Qwen 2 7B (free)"},
        ],
        "driver": "openai_compat",
    },
    "mistral": {
        "label": "Mistral AI (Free tier)",
        "env_key": "MISTRAL_API_KEY",
        "models": [
            {"id": "open-mistral-7b",           "label": "Mistral 7B (free)"},
            {"id": "open-mixtral-8x7b",         "label": "Mixtral 8x7B"},
            {"id": "mistral-small-latest",      "label": "Mistral Small"},
        ],
        "driver": "mistral",
    },
    "ollama": {
        "label": "Ollama (Local / Free)",
        "base_url": "http://localhost:11434",
        "env_key": None,
        "models": [
            {"id": "llama3.2",      "label": "LLaMA 3.2 (local)"},
            {"id": "llama3.1",      "label": "LLaMA 3.1 (local)"},
            {"id": "mistral",       "label": "Mistral (local)"},
            {"id": "gemma2",        "label": "Gemma 2 (local)"},
            {"id": "phi3",          "label": "Phi-3 (local)"},
        ],
        "driver": "ollama",
    },
}

# ─── Global active selection (runtime-switchable) ─────────────────────────

_active_provider: str | None = None
_active_model: str | None = None


def set_active(provider: str, model: str):
    global _active_provider, _active_model
    _active_provider = provider
    _active_model = model


def get_active() -> tuple[str | None, str | None]:
    return _active_provider, _active_model


# ─── Key resolution ────────────────────────────────────────────────────────

def _resolve_key(provider_id: str) -> str:
    cfg = PROVIDERS.get(provider_id, {})
    env_key = cfg.get("env_key")
    fallback = cfg.get("fallback_env")
    key = (os.getenv(env_key, "") if env_key else "") or (os.getenv(fallback, "") if fallback else "")
    # Groq: accept the OPENAI_API_KEY when it starts with gsk_
    if provider_id == "groq" and not key:
        oa = os.getenv("OPENAI_API_KEY", "")
        if oa.startswith("gsk_"):
            key = oa
    return key.strip()


def _provider_available(provider_id: str) -> bool:
    if provider_id == "ollama":
        try:
            import requests
            r = requests.get("http://localhost:11434/api/tags", timeout=2)
            return r.status_code == 200
        except Exception:
            return False
    return bool(_resolve_key(provider_id))


# ─── Auto-detect from .env (backward-compat) ──────────────────────────────

def detect_provider() -> str:
    explicit = os.getenv("LLM_PROVIDER", "").lower().strip()
    if explicit and explicit != "none" and explicit in PROVIDERS:
        return explicit
    # legacy mapping
    if explicit in ("grok", "xai"):
        return "none"
    oa = os.getenv("OPENAI_API_KEY", "").strip()
    if oa.startswith("gsk_"):
        return "groq"
    gem = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
    if gem:
        return "gemini"
    or_key = os.getenv("OPENROUTER_API_KEY", "")
    if or_key:
        return "openrouter"
    mis = os.getenv("MISTRAL_API_KEY", "")
    if mis:
        return "mistral"
    if oa.startswith("sk-"):
        return "openai_compat"
    return "none"


def load_env(project_root=None):
    try:
        from dotenv import load_dotenv
        if project_root:
            env_path = project_root / ".env"
            if env_path.exists():
                load_dotenv(env_path, override=True)
        else:
            load_dotenv(override=True)
    except ImportError:
        pass


def get_llm_config() -> dict:
    prov, model = get_active()
    if not prov:
        prov = detect_provider()
    if prov == "none":
        return {"enabled": False, "provider": "none", "model": None}
    cfg = PROVIDERS.get(prov, {})
    if not model:
        models = cfg.get("models", [])
        model = os.getenv("LLM_MODEL") or (models[0]["id"] if models else None)
    return {"enabled": True, "provider": prov, "model": model, "label": cfg.get("label", prov)}


def list_providers() -> list[dict]:
    result = []
    for pid, cfg in PROVIDERS.items():
        available = _provider_available(pid)
        result.append({
            "id": pid,
            "label": cfg["label"],
            "available": available,
            "models": cfg["models"],
        })
    return result


# ─── google-genai SDK wrapper (LangChain-compatible interface) ─────────────

class _GoogleGenAIChat:
    """google-genai SDK wrapped to match LangChain's invoke(messages)->response.content."""

    def __init__(self, model: str, api_key: str, temperature: float = 0.3):
        from google import genai
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._temp = temperature

    def invoke(self, messages):
        from google import genai

        system_parts: list[str] = []
        chat_contents: list[dict] = []

        for m in messages:
            mtype = getattr(m, "type", None) or type(m).__name__.lower()
            content = m.content if hasattr(m, "content") else str(m)
            if mtype in ("system", "systemmessage"):
                system_parts.append(content)
            elif mtype in ("human", "humanmessage"):
                chat_contents.append({"role": "user", "parts": [{"text": content}]})
            else:
                chat_contents.append({"role": "model", "parts": [{"text": content}]})

        if not chat_contents:
            chat_contents = [{"role": "user", "parts": [{"text": "\n\n".join(system_parts)}]}]
            system_parts = []

        cfg = genai.types.GenerateContentConfig(temperature=self._temp)
        if system_parts:
            cfg.system_instruction = "\n\n".join(system_parts)

        response = self._client.models.generate_content(
            model=self._model,
            contents=chat_contents,
            config=cfg,
        )

        class _R:
            def __init__(self, text: str):
                self.content = text

        return _R(response.text)


# ─── LLM factory ──────────────────────────────────────────────────────────

def create_llm(temperature: float = 0.3, provider: str | None = None, model: str | None = None):
    if provider is None:
        ap, am = get_active()
        provider = ap or detect_provider()
        model = model or am
    if provider == "none":
        return None

    cfg = PROVIDERS.get(provider, {})
    if not model:
        models = cfg.get("models", [])
        model = os.getenv("LLM_MODEL") or (models[0]["id"] if models else None)
    if not model:
        return None

    driver = cfg.get("driver", "openai_compat")
    try:
        timeout = max(10.0, float(os.getenv("LLM_TIMEOUT_SECONDS", "45")))
    except ValueError:
        timeout = 45.0

    try:
        if driver == "genai_sdk":
            api_key = _resolve_key(provider)
            if not api_key:
                return None
            return _GoogleGenAIChat(model=model, api_key=api_key, temperature=temperature)

        if driver == "mistral":
            from langchain_mistralai import ChatMistral
            api_key = _resolve_key(provider)
            if not api_key:
                return None
            return ChatMistral(
                model=model,
                mistral_api_key=api_key,
                temperature=temperature,
                timeout=timeout,
            )

        if driver == "ollama":
            try:
                from langchain_ollama import ChatOllama
            except ImportError:
                from langchain_community.chat_models import ChatOllama
            base = cfg.get("base_url", "http://localhost:11434")
            return ChatOllama(model=model, base_url=base, temperature=temperature)

        # openai_compat — Groq, OpenRouter, plain OpenAI
        api_key = _resolve_key(provider)
        if not api_key and provider != "ollama":
            # try legacy OPENAI_API_KEY
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None
        base_url = cfg.get("base_url") or os.getenv("OPENAI_BASE_URL", "")
        headers: dict[str, Any] = {}
        if provider == "openrouter":
            headers = {
                "HTTP-Referer": "https://ksp-crime-ai.local",
                "X-Title": "KSP Crime Intelligence AI",
            }
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url or None,
            temperature=temperature,
            timeout=timeout,
            max_retries=1,
            default_headers=headers if headers else None,
        )
    except Exception:
        return None


def create_llm_with_fallback(temperature: float = 0.3):
    """Try the active provider first; fall back to any available provider on 429/404."""
    ap, am = get_active()
    primary = ap or detect_provider()
    order = [primary] + [p for p in PROVIDERS if p != primary and _provider_available(p)]
    for provider in order:
        llm = create_llm(temperature=temperature, provider=provider)
        if llm is not None:
            return llm, provider
    return None, "none"
