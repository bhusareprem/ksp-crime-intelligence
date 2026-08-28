# 02. Every Kannada query answered about the wrong district

**Outcome:** three stacked bugs, each producing a confident wrong number. Found by
comparing answers against ground truth, not by any error.

---

## Symptom

Kannada is a headline feature, so the evaluation suite was extended with harder Kannada
cases than "how many districts are there". The first one failed immediately:

```
Q: ಮೈಸೂರು ಜಿಲ್ಲೆಯಲ್ಲಿ 2023 ರಲ್ಲಿ ಎಷ್ಟು ಕಳ್ಳತನ ಪ್ರಕರಣಗಳು ದಾಖಲಾಗಿವೆ?
   (How many theft cases were registered in Mysuru district in 2023?)

A: "Total theft FIRs in Mysore district for 2023: 99,766"
```

99,766 is the **statewide total for 2023**. Ground truth is 1,089.

No error was raised. The number was real, correctly formatted, and attached to the right
district name in the prose. Only a comparison against a figure computed independently
caught it.

## Bug 1: the district-count handler hijacked the question

```python
if re.search(r"how many districts|...", q) or ("ಜಿಲ್ಲೆ" in q and "ಎಷ್ಟು" in q):
    return "SELECT COUNT(DISTINCT DistrictName) FROM District"
```

Kannada is case-marked. `ಜಿಲ್ಲೆ` (district) appears in almost any question that names one,
because the locative "in Mysuru district" is `ಮೈಸೂರು ಜಿಲ್ಲೆಯಲ್ಲಿ`. Combined with `ಎಷ್ಟು`
("how many"), this matched **every** Kannada question mentioning a district, and answered
all of them with "31".

The fix is grammatical. `ಜಿಲ್ಲೆಗಳ-` is the plural stem, used when asking *how many
districts exist*. `ಜಿಲ್ಲೆಯಲ್ಲಿ` is the locative, used when asking *about* one.

```python
kn_district_count = ("ಜಿಲ್ಲೆಗಳ" in q and "ಎಷ್ಟು" in q and not crime_topic and not district)
```

## Bug 2: no Kannada district or crime vocabulary at all

With the hijack removed the answer got worse in a more honest way: it returned the
statewide 2023 total, having dropped both filters. `match_districts` returned `[]` for
every Kannada script name.

The naive fix, a Kannada-to-English dictionary, does not work. Case endings fuse onto the
noun and change the final character:

```
ಮೈಸೂರು      Mysuru (bare)
ಮೈಸೂರಿನಲ್ಲಿ   in Mysuru        <- the ending replaced the final vowel
ಬೆಂಗಳೂರು     Bengaluru
ಬೆಂಗಳೂರಿನಲ್ಲಿ  in Bengaluru
```

Substring-matching `ಮೈಸೂರು` against `ಮೈಸೂರಿನಲ್ಲಿ` fails, because `ರು` became `ರಿ`.

The fix matches on the **consonant stem**, stripping trailing vowel signs, which survives
every case ending:

```python
_KN_MATRA = "".join(chr(c) for c in range(0x0CBE, 0x0CCD + 1)) + "ೕೖ"
def _kn_stem(word): return word.rstrip(_KN_MATRA)
```

31 districts and 40 crime terms were mapped this way, longest stem first so
`ಬೆಂಗಳೂರು ಗ್ರಾಮಾಂತರ` (Bengaluru Rural) is not swallowed by `ಬೆಂಗಳೂರು`.

Result: 7 out of 7 Kannada test phrasings matched the right district and crime head.

## Bug 3: the language directive was read as a district

The worst of the three, and only visible over HTTP.

Via the CLI the Kannada question now returned 1,089, correct. Through the browser it
returned **780**, which matches nothing: Theft alone is 869, Theft plus Vehicle Theft is
1,089, Vehicle Theft alone is 220.

The SQL explained it:

```sql
WHERE csh.CrimeHeadName IN ('Theft','Vehicle Theft')
  AND d.DistrictName ILIKE '%Dakshina Kannada%'     -- asked about Mysuru
```

When a language is selected, the UI prefixes the message:

```
[Respond in Kannada language.] ಮೈಸೂರು ಜಿಲ್ಲೆಯಲ್ಲಿ ...
```

The district matcher scans for district names token by token. `Dakshina Kannada` and
`Uttara Kannada` both contain **Kannada**, and the directive contains the word Kannada.
So every question asked with the Kannada toggle on was silently rewritten to Dakshina
Kannada, and the prose still said "Mysore district".

That is the most dangerous failure mode in this project: right district in the words,
wrong district in the query.

```python
_DIRECTIVE_RE = re.compile(r"^\s*\[[^\]]*\]\s*")
def strip_directive(text): return _DIRECTIVE_RE.sub("", text or "")
```

Applied in `match_districts`, `match_crime_heads`, `unknown_places` and
`fallback_sql._find_district`. The directive is still passed to the model, which needs it
to answer in Kannada. It is only removed where **values** are derived.

## Guarding it

`tests/test_retrieval.py`:

- 5 Kannada phrasings with case endings resolve to the right district
- The directive test asserts `Mysuru` is matched and `Dakshina Kannada` is not
- Kannada crime terms map to real crime heads

`scripts/eval_nlsql.py` carries the full directive-prefixed question as a gold case, with
the checker asserting the district figure and **not** the statewide one.

## What this cost, and what it taught

Three bugs, all producing a plausible number, none raising an error. Two were invisible
from the CLI and only appeared over HTTP with the real request shape.

The general lesson: **test the transport the user actually uses.** Bug 3 was introduced by
the UI's own request format, and no amount of unit testing the matcher would have found it.
