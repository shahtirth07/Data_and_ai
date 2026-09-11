import asyncio
import json
import os
import time
from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv

from src.dreamer import run_dreamer
from src.hotdata_client import connect as hotdata_connect
from src.llm import ask_llm
from src.playbook import load_playbook, lessons_text, save_playbook
from src.rocketride_client import connect as rocketride_connect
from src.rocketride_client import start_pipeline, stop_pipeline
from src.telemetry import get_telemetry_db, log_events, query_telemetry


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _min_repeats():
    env_path = os.path.join(_project_root(), ".env")
    load_dotenv(env_path)
    raw = os.getenv("MIN_REPEATS")
    if raw is None:
        return 2
    raw = raw.strip()
    if raw == "":
        return 2
    try:
        value = int(raw)
    except Exception:
        return 2
    if value < 1:
        return 2
    return value


def _group_answer_examples_by_type(day_events_df):
    grouped = {}
    for _, row in day_events_df.iterrows():
        event_type = row["event_type"]
        if event_type is None:
            continue
        if str(event_type) != "answer":
            continue

        success = row["success"]
        if success is not True:
            if str(success).strip().lower() != "true":
                continue

        question_type = row["question_type"]
        question = row["question"]
        sql = row["sql"]

        if question is None:
            continue
        if sql is None:
            continue
        question_text = str(question)
        sql_text = str(sql)
        if question_text == "" or question_text == "nan":
            continue
        if sql_text == "" or sql_text == "nan":
            continue

        example = {}
        example["question"] = question_text
        example["sql"] = sql_text

        if question_type not in grouped:
            grouped[question_type] = []
        grouped[question_type].append(example)

    return grouped


def _count_answer_events_by_type(day_events_df):
    counts = {}
    for _, row in day_events_df.iterrows():
        event_type = row["event_type"]
        if event_type is None:
            continue
        event_type_text = str(event_type)
        if event_type_text != "answer":
            continue

        success = row["success"]
        if success is not True:
            if str(success).strip().lower() != "true":
                continue

        question_type = row["question_type"]
        if question_type is None:
            continue
        question_type_text = str(question_type)
        if question_type_text == "" or question_type_text == "nan":
            continue

        if question_type_text not in counts:
            counts[question_type_text] = 0
        counts[question_type_text] = counts[question_type_text] + 1

    return counts


def _all_question_types(day_events_df):
    types = {}
    for _, row in day_events_df.iterrows():
        question_type = row["question_type"]
        if question_type is None:
            continue
        question_type_text = str(question_type)
        if question_type_text == "" or question_type_text == "nan":
            continue
        types[question_type_text] = True

    result = []
    for question_type in types:
        result.append(question_type)
    result = sorted(result)
    return result


def _load_skills(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    return {}


def _save_skills(path, skills):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(skills, f, indent=2)
        f.write("\n")


def _use_rocketride():
    flag = os.getenv("USE_ROCKETRIDE")
    if flag is None:
        flag = ""
    flag = flag.strip().lower()
    if flag == "true":
        return True
    return False


def _strip_json_fences(text):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        kept = []
        line_index = 0
        for line in lines:
            if line_index == 0:
                line_index = line_index + 1
                continue
            kept.append(line)
            line_index = line_index + 1
        if len(kept) > 0:
            last_line = kept[len(kept) - 1].strip()
            if last_line.startswith("```"):
                kept.pop()
        cleaned = "\n".join(kept)
        cleaned = cleaned.strip()
    return cleaned


def _parse_lessons_json(text):
    cleaned = _strip_json_fences(text)
    data = json.loads(cleaned)
    if not isinstance(data, list):
        return []
    lessons = []
    for item in data:
        lesson = str(item).strip()
        if lesson == "":
            continue
        lessons.append(lesson)
        if len(lessons) >= 8:
            break
    return lessons


def _merge_lessons(existing, new_lessons):
    merged = []
    seen = {}
    for lesson in existing:
        text = str(lesson).strip()
        if text == "":
            continue
        key = text.lower()
        if key in seen:
            continue
        seen[key] = True
        merged.append(text)
        if len(merged) >= 8:
            return merged
    for lesson in new_lessons:
        text = str(lesson).strip()
        if text == "":
            continue
        key = text.lower()
        if key in seen:
            continue
        seen[key] = True
        merged.append(text)
        if len(merged) >= 8:
            break
    return merged


def _gather_playbook_context(hot_con):
    failed_sql = (
        'SELECT question_type, question, error, sql, created_at '
        'FROM "default"."main"."events" '
        "WHERE session_id <> 'test' "
        "AND session_id <> 'setup' "
        "AND success = false "
        "AND error IS NOT NULL "
        "AND CAST(error AS VARCHAR) <> '' "
        "ORDER BY created_at DESC"
    )
    retry_sql = (
        'SELECT question_type, question, error, sql, hotdata_queries, created_at '
        'FROM "default"."main"."events" '
        "WHERE session_id <> 'test' "
        "AND session_id <> 'setup' "
        "AND hotdata_queries > 1 "
        "ORDER BY created_at DESC"
    )
    distinct_sql = (
        'SELECT question_type, sql, COUNT(*) AS times_seen '
        'FROM "default"."main"."events" '
        "WHERE session_id <> 'test' "
        "AND session_id <> 'setup' "
        "AND event_type IN ('answer', 'reflex') "
        "AND sql IS NOT NULL "
        "AND CAST(sql AS VARCHAR) <> '' "
        "AND question_type IS NOT NULL "
        "AND CAST(question_type AS VARCHAR) <> '' "
        "GROUP BY question_type, sql "
        "ORDER BY question_type, times_seen DESC"
    )

    failed_df = query_telemetry(hot_con, failed_sql)
    retry_df = query_telemetry(hot_con, retry_sql)
    distinct_df = query_telemetry(hot_con, distinct_sql)

    lines = []
    lines.append("Failed events with error text:")
    failed_count = 0
    if failed_df is not None:
        for _, row in failed_df.iterrows():
            if failed_count >= 40:
                break
            qtype = str(row["question_type"])
            error = str(row["error"])
            sql = ""
            if row["sql"] is not None:
                sql = str(row["sql"])
            lines.append(
                "- type="
                + qtype
                + " error="
                + error
                + " sql="
                + sql
            )
            failed_count = failed_count + 1
    if failed_count == 0:
        lines.append("- none")

    lines.append("")
    lines.append("Events that needed a retry (hotdata_queries > 1):")
    retry_count = 0
    if retry_df is not None:
        for _, row in retry_df.iterrows():
            if retry_count >= 40:
                break
            qtype = str(row["question_type"])
            error = ""
            if row["error"] is not None:
                error = str(row["error"])
            sql = ""
            if row["sql"] is not None:
                sql = str(row["sql"])
            queries = str(row["hotdata_queries"])
            lines.append(
                "- type="
                + qtype
                + " queries="
                + queries
                + " error="
                + error
                + " sql="
                + sql
            )
            retry_count = retry_count + 1
    if retry_count == 0:
        lines.append("- none")

    lines.append("")
    lines.append("Distinct SQL written per question_type:")
    distinct_count = 0
    if distinct_df is not None:
        for _, row in distinct_df.iterrows():
            if distinct_count >= 80:
                break
            qtype = str(row["question_type"])
            sql = str(row["sql"])
            times = str(row["times_seen"])
            lines.append(
                "- type="
                + qtype
                + " times="
                + times
                + " sql="
                + sql
            )
            distinct_count = distinct_count + 1
    if distinct_count == 0:
        lines.append("- none")

    text = ""
    line_index = 0
    for line in lines:
        if line_index == 0:
            text = line
        else:
            text = text + "\n" + line
        line_index = line_index + 1
    return text


def _build_playbook_prompt(context_text, existing_lessons):
    existing_text = lessons_text(existing_lessons)
    if existing_text == "":
        existing_block = "None yet."
    else:
        existing_block = existing_text

    prompt = (
        "You write short lessons that help an agent write correct Hotdata SQL "
        "for an orders table on the first try.\n"
        "Use the telemetry below.\n"
        "Return ONLY a JSON list of strings.\n"
        "At most 8 lessons.\n"
        "Each lesson must be one sentence and specific, for example about exact "
        "column values or SQL types this engine rejects.\n"
        "No markdown fences.\n"
        "No explanation.\n"
        "\n"
        "Existing lessons:\n"
        + existing_block
        + "\n\n"
        "Telemetry:\n"
        + context_text
    )
    return prompt


async def _update_playbook(hot_con, session_id):
    playbook_start = time.time()
    existing = load_playbook()
    context_text = _gather_playbook_context(hot_con)
    prompt = _build_playbook_prompt(context_text, existing)

    llm_tokens = 0
    tokens_estimated = False
    success = False
    error_text = ""
    new_lessons = []
    merged = existing

    rr_client = None
    rr_token = None
    use_rr = _use_rocketride()

    try:
        if use_rr:
            rr_client = await rocketride_connect()
            rr_token = await start_pipeline(
                rr_client, token="tk_playbook_" + session_id, ttl=300
            )
            print("Started playbook RocketRide pipeline token=", rr_token)

        llm_result = await ask_llm(rr_client, rr_token, prompt)
        llm_tokens = llm_result["tokens"]
        tokens_estimated = llm_result["tokens_estimated"]
        new_lessons = _parse_lessons_json(llm_result["text"])
        merged = _merge_lessons(existing, new_lessons)
        save_playbook(merged)
        success = True
    except Exception as err:
        error_text = str(err)
        success = False
        print("Playbook update failed:", error_text)
    finally:
        if use_rr:
            if rr_token is not None:
                try:
                    await stop_pipeline(rr_client, rr_token)
                    print("Stopped playbook RocketRide pipeline")
                except Exception as stop_err:
                    print("Playbook stop_pipeline failed:", stop_err)
            if rr_client is not None:
                try:
                    await rr_client.disconnect()
                except Exception as disconnect_err:
                    print("Playbook disconnect failed:", disconnect_err)

    latency_ms = int((time.time() - playbook_start) * 1000)
    lessons_count = len(merged)

    print("")
    print("Playbook lessons:")
    if lessons_count == 0:
        print("(none)")
    else:
        print(lessons_text(merged))

    event = {
        "event_id": session_id + "-playbook",
        "session_id": session_id,
        "run_type": "night",
        "agent_id": "playbook",
        "event_type": "playbook",
        "question_type": "",
        "question": "",
        "used_skill": False,
        "llm_tokens": llm_tokens,
        "tokens_estimated": tokens_estimated,
        "latency_ms": latency_ms,
        "hotdata_queries": 0,
        "success": success,
        "error": error_text,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "db_create_ms": 0,
        "db_destroy_ms": 0,
        "lessons_count": lessons_count,
    }
    return event


async def run_night_shift(day_session_id, session_id, max_parallel):
    run_start = time.time()
    min_repeats = _min_repeats()
    print("MIN_REPEATS=", min_repeats)

    csv_path = os.path.join(_project_root(), "data", "orders.csv")
    df = pd.read_csv(csv_path)
    print("Loaded", len(df), "orders rows")

    hot_con = hotdata_connect()
    get_telemetry_db(hot_con)
    print("Connected to Hotdata telemetry")

    all_day_sql = (
        'SELECT * FROM "default"."main"."events" '
        "WHERE run_type = 'day' "
        "AND event_type = 'answer' "
        "AND success = true "
        "AND session_id <> 'test' "
        "AND session_id <> 'setup'"
    )
    day_events_df = query_telemetry(hot_con, all_day_sql)
    print("Loaded", len(day_events_df), "successful LLM answers across all day sessions")
    print("Night triggered from day_session_id=", day_session_id)

    answer_counts = _count_answer_events_by_type(day_events_df)
    all_types = _all_question_types(day_events_df)
    grouped = _group_answer_examples_by_type(day_events_df)

    question_types = []
    for question_type in all_types:
        answer_count = 0
        if question_type in answer_counts:
            answer_count = answer_counts[question_type]

        met_threshold = False
        if answer_count >= min_repeats:
            met_threshold = True

        print(
            question_type,
            "total=",
            answer_count,
            "met_threshold=",
            met_threshold,
        )

        if met_threshold:
            question_types.append(question_type)

    question_types = sorted(question_types)
    print("Dreamer types:", question_types)
    print("max_parallel=", max_parallel)

    semaphore = asyncio.Semaphore(max_parallel)
    all_events = []
    skills_path = os.path.join(_project_root(), "skills.json")
    passed_skills = {}

    async def run_one(question_type, stagger_index):
        async with semaphore:
            if stagger_index > 0:
                await asyncio.sleep(stagger_index * 1.5)
            examples = grouped[question_type]
            print("")
            print("Starting dreamer for", question_type, "examples=", len(examples))
            skill, events = await run_dreamer(
                question_type, examples, df, session_id
            )
            result = {}
            result["question_type"] = question_type
            result["skill"] = skill
            result["events"] = events
            return result

    tasks = []
    stagger_index = 0
    for question_type in question_types:
        task = asyncio.create_task(run_one(question_type, stagger_index))
        tasks.append(task)
        stagger_index = stagger_index + 1

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            print("Dreamer task failed:", result)
            error_event = {
                "event_id": session_id + "-dreamer_error",
                "session_id": session_id,
                "run_type": "night",
                "agent_id": "dreamer_error",
                "event_type": "dream",
                "question_type": "",
                "question": "",
                "used_skill": False,
                "llm_tokens": 0,
                "tokens_estimated": False,
                "latency_ms": 0,
                "hotdata_queries": 0,
                "success": False,
                "error": str(result),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "db_create_ms": 0,
                "db_destroy_ms": 0,
            }
            all_events.append(error_event)
            continue

        question_type = result["question_type"]
        skill = result["skill"]
        events = result["events"]

        for event in events:
            all_events.append(event)

        if skill is None:
            print("Dreamer", question_type, "FAILED")
        else:
            passed_skills[question_type] = skill
            print("Dreamer", question_type, "PASSED")
            print(json.dumps(skill, indent=2))

    existing_skills = _load_skills(skills_path)
    for question_type in passed_skills:
        existing_skills[question_type] = passed_skills[question_type]
    _save_skills(skills_path, existing_skills)
    print("Saved skills to", skills_path)
    print("Updated skill types:", list(passed_skills.keys()))

    playbook_event = await _update_playbook(hot_con, session_id)
    all_events.append(playbook_event)

    wall_clock_ms = int((time.time() - run_start) * 1000)
    created_at = datetime.now(timezone.utc).isoformat()
    summary_event = {
        "event_id": session_id + "-night_summary",
        "session_id": session_id,
        "run_type": "night",
        "agent_id": "night_shift",
        "event_type": "night_summary",
        "question_type": "",
        "question": "",
        "used_skill": False,
        "llm_tokens": 0,
        "tokens_estimated": False,
        "latency_ms": wall_clock_ms,
        "hotdata_queries": 0,
        "success": True,
        "error": "",
        "created_at": created_at,
        "db_create_ms": 0,
        "db_destroy_ms": 0,
        "max_parallel": max_parallel,
        "wall_clock_ms": wall_clock_ms,
        "day_session_id": day_session_id,
    }
    all_events.append(summary_event)

    log_events(hot_con, all_events)
    print("Logged", len(all_events), "night events")

    print("")
    print("Night shift wall-clock ms=", wall_clock_ms)
    print("Night shift wall-clock seconds=", round(wall_clock_ms / 1000.0, 2))
