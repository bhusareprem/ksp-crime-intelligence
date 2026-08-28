# 05. Running out of tokens, and what it forced

**Outcome:** the most useful failure in the project. Exhausting the free tier during
development produced the architecture that makes the product demonstrable.

---

## The wall

Mid-session, every model call began failing:

```
Error code: 429 - Rate limit reached for model `openai/gpt-oss-120b`
on tokens per day (TPD): Limit 200000, Used 199166, Requested 4508.
Please try again in 26m27s.
```

The binding constraint was not requests per minute, which had been the assumption. It was
**200,000 tokens per day per organisation**, roughly 40 to 80 substantial questions. The
QA suite alone spends about a dozen model calls per run.

## Three problems this exposed

### The auto-fallback pointed at itself

```python
if "429" in err:
    if _provider_available("groq"):
        set_active("groq", ...)     # already on groq, which just 429'd
```

On a Groq quota error it switched to Groq. It now moves to a different provider, and
passes that provider's own model id, since falling back to the `LLM_MODEL` environment
variable would have handed Gemini a Groq model name.

### One query was spending 8,293 characters

The offender profile returned one row, but `pandas.to_string()` pads every column to its
widest value. A 600-character crime-type list made the header 600 characters wide too:

```
data_str length: 8293      # for a single row
```

Two fixes. The query now returns the **top six crime types by count** rather than all 35,
and the payload handed to the model is capped by characters, not only by row count:

```
8,293 characters -> 503 characters       16x cheaper, and better output:
"Theft (49), Cheating & Fraud (18), Missing Person (17), Burglary (16)"
```

### Routine QA was eating the demo budget

Called out directly: *"just dont smoke api limits"*. Fair. The QA suite gained a
`--no-llm` flag that skips every check reaching a model:

```
RESULT: 32/32 passed   (11 skipped, no tokens spent)
```

That still covers all analytics, ML, the network graph, news, security, concurrency and
the deterministic honesty guards, because none of those call a model.

## What it forced, and why it made the product better

The real response was not to buy more tokens. It was to stop depending on them.

**A deterministic SQL layer.** Common questions, including Kannada ones, are answered by a
query builder with no model call at all. The model is a presentation layer over it.

**Guards ahead of generation.** Unknown districts, out-of-coverage years and absent schema
fields are refused before any SQL is written, so honesty does not depend on quota.

**Graceful degradation everywhere.** When summarisation fails, the result table is
returned rather than an error. Figures intact, prose plain.

The measurement that matters:

```
Gold evaluation suite, model quota fully exhausted:   21/21 (100%)
```

Every number correct with no model available. That is a far better answer to *"what
happens when the AI is down?"* than any amount of uptime would have been.

## Key rotation

Groq meters per organisation, so a key from a second account is a second budget. Rather
than swapping keys by hand, `_CleanChat` discovers every `gsk_` key in the environment
and rotates mid-request on a quota **or** authentication error.

Tested by putting a deliberately invalid key first:

```
starting key: ...XXXXXX (invalid)
RESULT: ROTATED
final key idx=1 -> ...nBwmay
>>> FAILOVER WORKED
```

Authentication errors are included on purpose. A key had previously been believed revoked,
so a dead key failing over to a live one is a real scenario, not a hypothetical.

## The secret that was not

While testing rotation, the "revoked" key worked. It had never been revoked. A 403 from a
missing user-agent header had been misread as revocation (see entry 01), and the key,
which had been publicly exposed in an early commit, had been live the whole time.

**Two lessons.** An exposed key must be revoked in the provider console, and confirmed
revoked, not assumed dead because a request failed. And a failing request is evidence
about the request, not about the credential.
