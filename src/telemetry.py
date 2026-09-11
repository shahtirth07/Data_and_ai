import os
import time
from datetime import datetime, timezone

import pandas as pd

from src.hotdata_client import run_sql

_telemetry_db_id = None


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_env():
    env_path = os.path.join(_project_root(), ".env")
    from dotenv import load_dotenv

    load_dotenv(env_path)


def _resolve_telemetry_db_id():
    global _telemetry_db_id

    if _telemetry_db_id is not None:
        if _telemetry_db_id != "":
            return _telemetry_db_id

    _load_env()
    db_id = os.getenv("TELEMETRY_DB_ID")
    if db_id is None:
        db_id = ""
    db_id = db_id.strip()

    if db_id == "":
        raise ValueError(
            "TELEMETRY_DB_ID is not set. Call get_telemetry_db(con) first."
        )

    _telemetry_db_id = db_id
    return db_id


def get_telemetry_db(con):
    global _telemetry_db_id

    _load_env()
    db_id = os.getenv("TELEMETRY_DB_ID")
    if db_id is None:
        db_id = ""
    db_id = db_id.strip()

    if db_id != "":
        _telemetry_db_id = db_id
        return db_id

    database_id = con.create_database("telemetry_db", tables=["events"])

    created_at = datetime.now(timezone.utc).isoformat()
    setup_event = {
        "event_id": "setup-1",
        "session_id": "setup",
        "run_type": "day",
        "agent_id": "setup",
        "event_type": "setup",
        "question_type": "",
        "question": "",
        "used_skill": False,
        "llm_tokens": 0,
        "latency_ms": 0,
        "hotdata_queries": 0,
        "success": True,
        "error": "",
        "created_at": created_at,
    }
    setup_df = pd.DataFrame([setup_event])
    con.create_table(
        "events",
        setup_df,
        database=(database_id, "main"),
        overwrite=True,
    )
    time.sleep(2)

    _telemetry_db_id = database_id
    print("Created telemetry_db. Paste this into .env as TELEMETRY_DB_ID=")
    print(database_id)
    return database_id


def log_events(con, events):
    db = _resolve_telemetry_db_id()
    new_df = pd.DataFrame(events)

    used_insert = False
    if hasattr(con, "insert"):
        try:
            con.insert("events", new_df, database=(db, "main"))
            used_insert = True
        except Exception:
            used_insert = False

    if used_insert:
        time.sleep(2)
        return

    con._database_id = db
    con._database_connection_id = None
    existing_table = con.table("events", database=("default", "main"))
    existing_df = existing_table.execute()

    combined = pd.concat([existing_df, new_df], ignore_index=True)
    con.create_table(
        "events",
        combined,
        database=(db, "main"),
        overwrite=True,
    )
    time.sleep(2)


def query_telemetry(con, sql):
    db = _resolve_telemetry_db_id()
    result = run_sql(con, db, sql)
    return result
