# Agent Transcripts

This project was built with heavy use of a coding agent (Claude Code). This folder is the
development log, written up from those sessions.

It is organised around **failures**, because that is where the useful information is. Each
entry records the symptom, the first diagnosis (usually wrong), how the real cause was
found, the fix, and the regression test that now guards it. Where an early conclusion
turned out to be mistaken, the mistake is left in rather than tidied away.

## Method

The agent had shell, file and browser access, and could run the app, drive the UI, query
the databases and read live API responses. That mattered: most of the bugs below were
found by **executing** something and comparing the result against ground truth computed
directly from the database, not by reading code.

The pattern that produced almost every finding here:

1. Run the thing end to end
2. Compare the output against a figure computed independently
3. When they disagree, find out why before changing anything
4. Fix the cause, then write a test that fails without the fix

Step 2 is the one that matters. Every serious bug in this project produced a
**plausible number**, not an error. Nothing in a stack trace would have caught them.

## Entries

| # | Failure | Cost if shipped |
|---|---|---|
| [01](01-model-selection.md) | Picked a model by reputation instead of measurement | Agent planner broken, token budget burned |
| [02](02-kannada-grounding.md) | Every Kannada query answered about the wrong district | Confident wrong figures in half the demo |
| [03](03-repeat-offender-grain.md) | Repeat-offender queries silently returned nothing | Flagship feature fell through to a web search |
| [04](04-duckdb-config-conflict.md) | Machine learning results silently empty under load | Empty panels during judging |
| [05](05-quota-and-resilience.md) | Free tier exhausted mid-development | Total outage on demo day |
| [06](06-map-tiles.md) | Third-party map provider started demanding a key | "API KEY REQUIRED" across the map |

## Secrets

No API keys, tokens or credentials appear in this folder. Keys are referred to by prefix
only (`gsk_...`). The repository is checked with `git grep -nE "gsk_|AIza|AQ\."` before
every push, and `.env`, `app-config.json` and `dist_appsail/app-config.json` are
gitignored.

One incident worth recording: an API key was committed early in the project's life and
had to be treated as compromised. The lesson taken from it is in entry 05.
