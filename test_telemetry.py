from datetime import datetime, timezone

from src.hotdata_client import connect
from src.telemetry import get_telemetry_db, log_events, query_telemetry

con = connect()
print("Connected to Hotdata")

db = get_telemetry_db(con)
print("Using telemetry db=", db)

created_at = datetime.now(timezone.utc).isoformat()

events = []

events.append(
    {
        "event_id": "test-1",
        "session_id": "test",
        "run_type": "day",
        "agent_id": "agent_a",
        "event_type": "answer",
        "question_type": "aggregate",
        "question": "What is total sales by region?",
        "used_skill": True,
        "llm_tokens": 120,
        "latency_ms": 450,
        "hotdata_queries": 1,
        "success": True,
        "error": "",
        "created_at": created_at,
    }
)

events.append(
    {
        "event_id": "test-2",
        "session_id": "test",
        "run_type": "night",
        "agent_id": "agent_b",
        "event_type": "skill_check",
        "question_type": "trend",
        "question": "Did West grow in Q4?",
        "used_skill": False,
        "llm_tokens": 80,
        "latency_ms": 300,
        "hotdata_queries": 2,
        "success": True,
        "error": "",
        "created_at": created_at,
    }
)

events.append(
    {
        "event_id": "test-3",
        "session_id": "test",
        "run_type": "day",
        "agent_id": "agent_a",
        "event_type": "answer",
        "question_type": "detail",
        "question": "How many zero-quantity orders?",
        "used_skill": True,
        "llm_tokens": 95,
        "latency_ms": 510,
        "hotdata_queries": 1,
        "success": False,
        "error": "timeout",
        "created_at": created_at,
    }
)

log_events(con, events)
print("Logged", len(events), "events")

count_sql = 'SELECT COUNT(*) AS event_count FROM "default"."main"."events"'
count_df = query_telemetry(con, count_sql)
print("Total event count:")
print(count_df)
