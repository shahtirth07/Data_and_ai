# Agents That Sleep

## The problem

AI agents call the LLM for every question, even ones they have answered many times before. Our telemetry shows the same question type produced 3 different SQL queries across sessions.

## The idea

By day the agent answers questions with the LLM through RocketRide and runs the SQL on its own Hotdata database. At night, one dreamer agent per question type runs in parallel, each with its own RocketRide pipeline and its own Hotdata database, and turns the day's work into a verified SQL recipe with named placeholders. The next day, matching questions are answered from the recipe with no LLM call.

## Results

Same 12 questions, run twice:

| | Baseline | With recipes |
| --- | --- | --- |
| LLM calls | 12 | 0 |
| Tokens | 2595 | 0 |
| Total seconds | 32.12 | 13.43 |
| Seconds per question | 2.68 | 1.12 |
| Correct | 12/12 | 12/12 |

Correctness is checked against an independent answer key computed with pandas, which never uses SQL or the LLM.

## How recipes are verified

A recipe is only saved if it reproduces the day's answers on the dreamer's own isolated database. Captured placeholder values must be a known column value or digits, so nothing else can be injected into the SQL.

## Architecture

1. Day shift: load questions, match a recipe or ask RocketRide for SQL, run SQL on a task Hotdata DB, log events, score against the answer key.
2. Night shift: group successful day answers by question type, run one dreamer per type in parallel.
3. Each dreamer: create its own Hotdata DB and RocketRide pipeline, propose a regex + SQL template, verify on its DB, log the result.
4. Passed recipes merge into `skills.json`. The next day shift uses them as reflexes.

### Files

- `src/answer_key.py` — pandas ground truth for each question type
- `src/day_shift.py` — day worker: LLM or recipe, SQL, scoring, telemetry
- `src/dreamer.py` — one night agent that builds and verifies a recipe
- `src/hotdata_client.py` — Hotdata connect, create DB, run SQL, destroy DB
- `src/insights.py` — six dashboard SQL insights
- `src/llm.py` — RocketRide or OpenAI LLM calls
- `src/night_shift.py` — parallel dreamers and skills merge
- `src/rocketride_client.py` — RocketRide connect, pipeline start/stop, ask
- `src/skills.py` — match a question to a saved recipe
- `src/telemetry.py` — long-lived events DB create, insert, query
- `run_day.py` — CLI for the day shift
- `run_night.py` — CLI for the night shift
- `dashboard.py` — Streamlit telemetry dashboard

## Telemetry

One long-lived Hotdata database holds every event from every run across the day. The dashboard runs live SQL against it.

Insights:

- Sessions over time — LLM vs reflex counts, tokens, and latency per day session
- SQL drift — distinct SQL strings per question type for LLM vs reflex answers
- Dreamer comparison — latency, DB create time, tokens, and success rate per dreamer
- Parallel vs sequential — night wall-clock time vs sum of dreamer latencies
- Failure patterns — failed and retry counts with the most common error text
- Night learning curve — dreamers run vs passed per night session

## What the telemetry changed

Dreamers were failing because the LLM put placeholders on parts of the question that never change. Failure events also showed inline regex flags that broke matching. Both were found in the failure events and fixed. The pass rate went from 4 of 6 to 6 of 6.

## How to run

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python data/make_data.py
```

### `.env` variables

`HOTDATA_API_KEY`, `HOTDATA_WORKSPACE_ID`, `ROCKETRIDE_API_KEY`, `ROCKETRIDE_URI`, `TELEMETRY_DB_ID`, `USE_ROCKETRIDE`

If `TELEMETRY_DB_ID` is empty, the first day run creates a telemetry database and prints the id to paste into `.env`.

### Day shift

```bash
python run_day.py --questions day1 --skills off --day 1
```

### Night shift

```bash
python run_night.py <day_session_id> 6
```

### Fair test

```bash
python run_day.py --questions day1 --skills off --day 1 --label baseline
python run_day.py --questions day1 --skills on --day 2 --label recipes
```

### Dashboard

```bash
streamlit run dashboard.py
```

## Limitations

Recipes match on question wording, so a differently worded question still goes to the LLM. The answer key only exists because we generated the dataset. Token counts for RocketRide are estimated because the response does not include usage.

## Sponsor usage

RocketRide runs the LLM for day answers and for each night dreamer. The day shift starts one pipeline. Each dreamer starts its own pipeline with a unique token, asks for a recipe, then stops the pipeline.

Hotdata holds the orders data and the telemetry events. The day shift creates a task database, runs SQL, then destroys it. Each dreamer creates its own isolated database, verifies the recipe there, then destroys it. Telemetry uses one long-lived database that keeps every event across runs.
