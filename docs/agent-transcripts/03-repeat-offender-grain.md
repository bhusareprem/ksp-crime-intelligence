# 03. A schema misunderstanding that disabled the flagship feature

**Outcome:** one wrong `GROUP BY`, replicated across seven places, including the examples
that taught the model to reproduce it.

---

## Symptom

Reported from the running app:

```
Q: Who are the top repeat offenders by district?
A: Not found in the KSP crime database, answering from a web search:
   ...the sources discuss repeat-offender rates in Victoria and New York City...
```

The first read was "the database is not connected". It was connected. Everything else
answered fine.

## Diagnosis

Routing was correct (`criminal`, high confidence) and a deterministic query existed. So
the query itself was run directly:

```sql
SELECT a.AccusedName, COUNT(DISTINCT a.CaseMasterID) AS fir_count
FROM Accused a
GROUP BY a.AccusedMasterID, a.AccusedName, ...
HAVING COUNT(DISTINCT a.CaseMasterID) > 1
```

Zero rows. Not an error, zero rows, which the engine treats as "the database has nothing"
and falls through to the web.

The cause is a property of the schema:

```
rows in Accused          : 895,927
distinct AccusedMasterID : 895,927     <- unique per row
distinct AccusedName     : 3,525
```

`Accused` holds **one row per person per case**. `AccusedMasterID` identifies the row, not
the person. Grouping by it gives every group exactly one case, so
`HAVING COUNT(DISTINCT CaseMasterID) > 1` eliminates every row in the table.

Grouped by `AccusedName` instead:

```
Thimmaiah Begum    260
Rashid Rao         256
Basavraj Salian    256
```

## The spread

The same mistake appeared in seven places:

| Location | Effect |
|---|---|
| `_top_accused_statewide` | 0 rows, fell through to web search |
| `_top_accused_in_district` | every offender showed 1 FIR |
| `_top_accused_per_district` | every offender showed 1 FIR |
| `investigator.t_offenders_in_district` | agent tool reported 1 FIR each |
| `rag/examples.py` | **taught the model the broken pattern** |
| `schemas.py` schema hints | same, in the prompt |
| `analytics.criminal_network` | `1 AS fir_count` hardcoded |

The two prompt files are the interesting ones. Fixing only the Python would have left the
model generating the same broken SQL, because the few-shot example demonstrated it. The
examples now carry an inline warning:

```sql
-- Group by AccusedName: AccusedMasterID is one row per case, so grouping
-- on it gives every person exactly 1 FIR and finds no repeat offenders.
```

## Two further problems in the same area

**The graph drew people twice.** Node identity was `AccusedMasterID`, so one person
appearing in several cases became several nodes with the same label and their links split
across the duplicates. Fixed by collapsing on name and remapping edges. 150 nodes with
duplicates became 129 distinct people, 0 repeated labels.

**`MAX(District)` implied the wrong home.** Grouping by name needs an aggregate for the
other columns, and `MAX` picks alphabetically. Every top offender appeared to be from
Yadgir. Replaced with `mode()` for the most frequent district, plus a
`districts_active` count, which turned a misleading field into a useful one:
*Thimmaiah Begum, main district Bengaluru Urban, active in 31 districts.*

## Guarding it

`tests/test_honesty_guards.py`

```python
def test_repeat_offenders_are_grouped_by_person_not_row(self, db):
    fb = try_fallback_sql("Who are the top repeat offenders by district?")
    out = db.execute(fb.db, fb.sql)
    assert len(out) > 0
    assert int(out.iloc[0]["fir_count"]) > 100
```

`tests/test_api.py` asserts the network graph has no duplicate labels and that FIR counts
are not all 1. `tests/test_retrieval.py` asserts the few-shot examples do not teach the
broken grain.

## Lesson

A wrong `GROUP BY` does not raise. It returns fewer rows, or the same rows with wrong
counts, and both look like data.

Worth checking on any unfamiliar schema: **is this key unique per row, or per entity?**
One query against the table would have answered it:

```sql
SELECT COUNT(*), COUNT(DISTINCT AccusedMasterID), COUNT(DISTINCT AccusedName) FROM Accused
```
