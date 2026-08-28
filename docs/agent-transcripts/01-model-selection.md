# 01. Picking a model by reputation instead of measuring

**Outcome:** the recommendation was wrong, and running the comparison overturned it in
about four minutes.

---

## The wrong answer, given confidently

Asked which free-tier model to use for an app that needs English, Kannada, JSON tool
planning and DuckDB SQL, the agent reasoned from general knowledge:

> Qwen is the strongest multilingual open model, so it should handle Kannada best.
> Recommendation: `qwen/qwen3-32b` on Groq.

Two errors in one sentence.

**First, `qwen/qwen3-32b` did not exist.** Groq's catalogue had moved on. Probing the API
showed the actual list, and four models the codebase still referenced were retired:
`llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `mixtral-8x7b-32768`, `gemma2-9b-it`.
One of them was hardcoded in `api/main.py` as the quota fallback, so the fallback path
could only ever 404.

**Second, the reasoning was untested.** Rather than settle it by argument, the three
candidates were run against the three things the app actually does.

## The measurement

```
                      Kannada output   JSON tool plan   DuckDB SQL
openai/gpt-oss-120b        pass             pass           pass
qwen/qwen3.6-27b           fail             fail           fail
openai/gpt-oss-20b         fail             fail           pass
```

Qwen scored zero. It is a **reasoning model**: it emitted hundreds of tokens inside
`<think>`, reasoning in English about the Kannada question, and hit the token ceiling
before producing an answer. Sample output, truncated at 700 completion tokens:

```
<think>
We need to answer in Kannada. The user asks: ...
Translation: "I want to know how many theft cases were registered in Bengaluru in 2024..."
So the user wants a summary of their question in one sentence. But note: the user is
asking for information, but then says ...
```

That is the entire response. No answer, ever.

Shipping it would have broken the investigation agent's planner, which parses JSON from
the model, and burned roughly 700 tokens per call against a 200,000 per day budget.

`gpt-oss-120b` answered the same Kannada prompt in 157 tokens and 0.7 seconds, correctly.

## Fixes

1. `LLM_MODEL=openai/gpt-oss-120b`
2. Replaced the retired model list in `llm_config.py` with the live catalogue
3. Removed the hardcoded retired model from the quota fallback in `api/main.py`
4. Added `_CleanChat`, a proxy that strips `<think>` blocks from any response, so a
   reasoning model can never poison SQL or JSON parsing again even if one is selected

## A second mistake, corrected later

While probing the model list, the API returned `403 Forbidden` and the agent concluded the
key was revoked. That conclusion was recorded, acted on, and **was wrong**.

Groq rejects Python's default `urllib` user agent. Sending a browser user agent returned
the model list normally. The key had been working the entire time.

This mattered beyond the immediate confusion: an earlier session had reached the same
false conclusion and migrated the whole app to a different provider on the strength of it.
A previously exposed key that everyone believed was dead was in fact live, and had to be
revoked for real.

**Lesson:** an HTTP status is a symptom, not a diagnosis. Read the response body before
concluding anything about credentials.

## Guarding it

- `README.md` documents the user-agent trap and the probe command
- `docs/architecture.md` records that switching model requires re-running the comparison
- The model catalogue lives in one module, so a retirement is a one-line change
