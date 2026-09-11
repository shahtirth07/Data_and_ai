import os
import time
from datetime import datetime, timezone

import pandas as pd

from data.questions import QUESTIONS
from src.hotdata_client import connect as hotdata_connect
from src.hotdata_client import create_task_db, destroy_db, run_sql
from src.llm import ask_llm
from src.rocketride_client import connect as rocketride_connect
from src.rocketride_client import start_pipeline, stop_pipeline
from src.telemetry import get_telemetry_db, log_events


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _use_rocketride():
    flag = os.getenv("USE_ROCKETRIDE")
    if flag is None:
        flag = ""
    flag = flag.strip().lower()
    if flag == "true":
        return True
    return False


def _column_description(df):
    lines = []
    for col_name in df.columns:
        dtype_name = str(df[col_name].dtype)
        line = col_name + " (" + dtype_name + ")"
        lines.append(line)

    text = ""
    i = 0
    for line in lines:
        if i == 0:
            text = line
        else:
            text = text + ", " + line
        i = i + 1
    return text


def _join_values(values):
    text = ""
    i = 0
    for value in values:
        value_text = str(value)
        if i == 0:
            text = value_text
        else:
            text = text + ", " + value_text
        i = i + 1
    return text


def _distinct_text_values(df):
    text_columns = ["region", "category", "product", "channel"]
    lines = []
    for col_name in text_columns:
        unique_values = sorted(df[col_name].dropna().unique())
        values_text = _join_values(unique_values)
        line = col_name + ": " + values_text
        lines.append(line)

    text = ""
    i = 0
    for line in lines:
        if i == 0:
            text = line
        else:
            text = text + "\n" + line
        i = i + 1
    return text


def _build_sql_prompt(df, question_text):
    columns = _column_description(df)
    distinct_values = _distinct_text_values(df)
    prompt = (
        "You write SQL for a Hotdata table.\n"
        'The table is "default"."main"."orders".\n'
        "Columns and types: " + columns + ".\n"
        "Allowed text values (use these exact values with exact capitalization):\n"
        + distinct_values
        + "\n"
        "Question: " + question_text + "\n"
        "Reply with ONLY one SQL query.\n"
        "No explanation.\n"
        "No markdown fences."
    )
    return prompt


def _build_fix_prompt(bad_sql, error_text):
    prompt = (
        "The previous SQL failed.\n"
        "SQL:\n"
        + bad_sql
        + "\n"
        "Error:\n"
        + error_text
        + "\n"
        "Reply with ONLY one corrected SQL query.\n"
        "No explanation.\n"
        "No markdown fences."
    )
    return prompt


def _strip_sql_fences(text):
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


async def run_day_shift(session_id):
    from dotenv import load_dotenv

    env_path = os.path.join(_project_root(), ".env")
    load_dotenv(env_path)

    csv_path = os.path.join(_project_root(), "data", "orders.csv")
    df = pd.read_csv(csv_path)
    print("Loaded", len(df), "orders rows")

    hot_con = hotdata_connect()
    print("Connected to Hotdata")

    get_telemetry_db(hot_con)
    print("Telemetry database ready")

    db_name = "day_" + session_id
    task_db = create_task_db(db_name, df)
    print("Created task database id=", task_db)

    use_rr = _use_rocketride()
    rr_client = None
    rr_token = None
    if use_rr:
        rr_client = await rocketride_connect()
        print("Connected to RocketRide")
        rr_token = await start_pipeline(rr_client)
        print("Started RocketRide pipeline token=", rr_token)

    events = []
    success_count = 0
    total_tokens = 0
    run_start = time.time()

    question_index = 0
    for item in QUESTIONS:
        question_index = question_index + 1
        question_type = item["question_type"]
        question_text = item["question"]

        print("")
        print("Question", question_index, "/", len(QUESTIONS))
        print("Type:", question_type)
        print("Question:", question_text)

        question_start = time.time()
        llm_tokens = 0
        tokens_estimated = True
        hotdata_queries = 0
        success = False
        error_text = ""
        sql_text = ""
        result_df = None
        rows_returned = 0

        prompt = _build_sql_prompt(df, question_text)
        llm_result = await ask_llm(rr_client, rr_token, prompt)
        llm_tokens = llm_tokens + llm_result["tokens"]
        tokens_estimated = llm_result["tokens_estimated"]

        sql_text = _strip_sql_fences(llm_result["text"])
        print("SQL:", sql_text)

        try:
            result_df = run_sql(hot_con, task_db, sql_text)
            hotdata_queries = hotdata_queries + 1
            success = True
        except Exception as first_error:
            hotdata_queries = hotdata_queries + 1
            error_text = str(first_error)
            print("SQL error:", error_text)

            retry_prompt = _build_fix_prompt(sql_text, error_text)
            retry_result = await ask_llm(rr_client, rr_token, retry_prompt)
            llm_tokens = llm_tokens + retry_result["tokens"]
            tokens_estimated = retry_result["tokens_estimated"]

            sql_text = _strip_sql_fences(retry_result["text"])
            print("Retry SQL:", sql_text)

            try:
                result_df = run_sql(hot_con, task_db, sql_text)
                hotdata_queries = hotdata_queries + 1
                success = True
                error_text = ""
            except Exception as second_error:
                hotdata_queries = hotdata_queries + 1
                error_text = str(second_error)
                print("Retry SQL error:", error_text)
                success = False

        if success:
            success_count = success_count + 1
            rows_returned = len(result_df)
            print("First 3 rows:")
            print(result_df.head(3))
        else:
            rows_returned = 0
            print("No result rows")

        latency_ms = int((time.time() - question_start) * 1000)
        total_tokens = total_tokens + llm_tokens

        created_at = datetime.now(timezone.utc).isoformat()
        event = {
            "event_id": session_id + "-" + str(question_index),
            "session_id": session_id,
            "run_type": "day",
            "agent_id": "worker",
            "event_type": "answer",
            "question_type": question_type,
            "question": question_text,
            "used_skill": False,
            "llm_tokens": llm_tokens,
            "tokens_estimated": tokens_estimated,
            "latency_ms": latency_ms,
            "hotdata_queries": hotdata_queries,
            "success": success,
            "error": error_text,
            "sql": sql_text,
            "rows_returned": rows_returned,
            "created_at": created_at,
        }
        events.append(event)

    if use_rr:
        await stop_pipeline(rr_client, rr_token)
        print("Stopped RocketRide pipeline")
        await rr_client.disconnect()
        print("Disconnected from RocketRide")

    destroy_db(hot_con, task_db)
    print("Destroyed task database")

    log_events(hot_con, events)
    print("Logged", len(events), "events to telemetry")

    total_seconds = time.time() - run_start
    print("")
    print("Summary")
    print("questions answered=", len(events))
    print("successes=", success_count)
    print("total tokens=", total_tokens)
    print("total seconds=", round(total_seconds, 2))
