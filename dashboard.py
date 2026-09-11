import json
import os
import time

import pandas as pd
import streamlit as st

from src.hotdata_client import connect as hotdata_connect
from src.insights import INSIGHTS
from src.telemetry import get_telemetry_db, query_telemetry


def _project_root():
    return os.path.dirname(os.path.abspath(__file__))


def _get_connection():
    if "hot_con" not in st.session_state:
        con = hotdata_connect()
        get_telemetry_db(con)
        st.session_state["hot_con"] = con
    return st.session_state["hot_con"]


def _format_sql_for_display(sql):
    text = " ".join(sql.split())

    text = text.replace(" LEFT JOIN ", "\nLEFT JOIN ")
    text = text.replace(" FROM ", "\nFROM ")
    text = text.replace(" WHERE ", "\nWHERE ")
    text = text.replace(" AND ", "\nAND ")
    text = text.replace(" ON ", "\nON ")
    text = text.replace(" GROUP BY ", "\nGROUP BY ")
    text = text.replace(" HAVING ", "\nHAVING ")
    text = text.replace(" ORDER BY ", "\nORDER BY ")
    text = text.replace(" UNION ALL ", "\nUNION ALL ")
    text = text.replace(" UNION ", "\nUNION ")

    if text.startswith("SELECT "):
        text = "SELECT\n  " + text[len("SELECT "):]
    text = text.replace("\nSELECT ", "\nSELECT\n  ")

    clause_prefixes = [
        "FROM ",
        "WHERE ",
        "AND ",
        "ON ",
        "GROUP BY ",
        "ORDER BY ",
        "HAVING ",
        "LEFT JOIN ",
        "UNION ALL ",
        "UNION ",
    ]

    lines = text.split("\n")
    pretty_lines = []
    for line in lines:
        cleaned = line.strip()
        if cleaned == "":
            continue

        if cleaned.startswith("SELECT"):
            pretty_lines.append("SELECT")
            rest = cleaned[len("SELECT"):].strip()
            if rest != "":
                cleaned = rest
            else:
                continue

        is_clause = False
        for prefix in clause_prefixes:
            if cleaned.startswith(prefix):
                is_clause = True

        if is_clause:
            pretty_lines.append(cleaned)
            continue

        if "," in cleaned:
            pieces = cleaned.split(",")
            kept_pieces = []
            for piece in pieces:
                piece_text = piece.strip()
                if piece_text == "":
                    continue
                kept_pieces.append(piece_text)

            piece_index = 0
            for piece_text in kept_pieces:
                if piece_index < len(kept_pieces) - 1:
                    pretty_lines.append("  " + piece_text + ",")
                else:
                    pretty_lines.append("  " + piece_text)
                piece_index = piece_index + 1
            continue

        pretty_lines.append(cleaned)

    pretty = ""
    line_index = 0
    for line in pretty_lines:
        if line_index == 0:
            pretty = line
        else:
            pretty = pretty + "\n" + line
        line_index = line_index + 1
    return pretty


def _run_insight(con, insight):
    start = time.time()
    try:
        df = query_telemetry(con, insight["sql"])
        error = ""
    except Exception as err:
        df = pd.DataFrame()
        error = str(err)
    elapsed_ms = int((time.time() - start) * 1000)
    result = {}
    result["df"] = df
    result["error"] = error
    result["elapsed_ms"] = elapsed_ms
    return result


def _show_chart(insight, df):
    if df is None:
        return
    if len(df) == 0:
        return

    chart_type = insight.get("chart")
    chart_x = insight.get("chart_x")
    chart_y = insight.get("chart_y")
    if chart_type is None:
        return
    if chart_x is None or chart_y is None:
        return
    if chart_x not in df.columns:
        return
    if chart_y not in df.columns:
        return

    plot_df = df[[chart_x, chart_y]].copy()
    plot_df = plot_df.dropna()
    if len(plot_df) == 0:
        return

    indexed = plot_df.set_index(chart_x)
    if chart_type == "line":
        st.line_chart(indexed)
    else:
        st.bar_chart(indexed)


def _count_saved_recipes():
    skills_path = os.path.join(_project_root(), "skills.json")
    if not os.path.exists(skills_path):
        return 0
    with open(skills_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return 0
    count = 0
    for key in data:
        count = count + 1
    return count


def _empty_session_stats():
    result = {}
    result["session_id"] = None
    result["llm_calls"] = None
    result["total_tokens"] = None
    result["total_seconds"] = None
    result["avg_seconds"] = None
    result["correct_count"] = None
    result["events"] = pd.DataFrame()
    return result


def _latest_session_id_for_label(con, run_label):
    sql = (
        'SELECT '
        "session_id, "
        "MAX(created_at) AS last_created_at "
        'FROM "default"."main"."events" '
        "WHERE run_type = 'day' "
        "AND session_id <> 'test' "
        "AND session_id <> 'setup' "
        "AND run_label = '"
        + run_label
        + "' "
        "GROUP BY session_id "
        "ORDER BY MAX(created_at) DESC"
    )
    df = query_telemetry(con, sql)
    if df is None:
        return None
    if len(df) == 0:
        return None
    return str(df.iloc[0]["session_id"])


def _load_session_events(con, session_id):
    sql = (
        'SELECT '
        "question, "
        "question_type, "
        "event_type, "
        "llm_tokens, "
        "latency_ms, "
        "result_numbers, "
        "true_numbers, "
        "correct, "
        "created_at "
        'FROM "default"."main"."events" '
        "WHERE session_id = '"
        + session_id
        + "' "
        "AND run_type = 'day' "
        "ORDER BY created_at"
    )
    df = query_telemetry(con, sql)
    if df is None:
        return pd.DataFrame()
    return df


def _session_stats_from_events(session_id, events_df):
    result = _empty_session_stats()
    result["session_id"] = session_id
    result["events"] = events_df

    if events_df is None:
        return result
    if len(events_df) == 0:
        return result

    llm_calls = 0
    total_tokens = 0
    total_latency_ms = 0
    correct_count = 0
    question_count = 0

    for index, row in events_df.iterrows():
        question_count = question_count + 1
        event_type = str(row["event_type"])
        if event_type == "answer":
            llm_calls = llm_calls + 1
        total_tokens = total_tokens + int(row["llm_tokens"])
        total_latency_ms = total_latency_ms + int(row["latency_ms"])
        correct_value = row["correct"]
        is_correct = False
        if correct_value is True:
            is_correct = True
        else:
            if str(correct_value).strip().lower() == "true":
                is_correct = True
        if is_correct:
            correct_count = correct_count + 1

    total_seconds = total_latency_ms / 1000.0
    avg_seconds = 0.0
    if question_count > 0:
        avg_seconds = total_seconds / question_count

    result["llm_calls"] = llm_calls
    result["total_tokens"] = total_tokens
    result["total_seconds"] = total_seconds
    result["avg_seconds"] = avg_seconds
    result["correct_count"] = correct_count
    return result


def _load_labeled_session(con, run_label):
    result = _empty_session_stats()
    session_id = _latest_session_id_for_label(con, run_label)
    if session_id is None:
        return result
    events_df = _load_session_events(con, session_id)
    return _session_stats_from_events(session_id, events_df)


def _numbers_match_answer_key(result_numbers, true_numbers):
    result_text = ""
    if result_numbers is not None:
        result_text = str(result_numbers).strip()
    true_text = ""
    if true_numbers is not None:
        true_text = str(true_numbers).strip()

    if true_text == "":
        if result_text == "":
            return True
        return False

    true_parts = true_text.split(",")
    result_parts = []
    if result_text != "":
        result_parts = result_text.split(",")

    for true_part in true_parts:
        true_piece = true_part.strip()
        found = False
        for result_part in result_parts:
            if result_part.strip() == true_piece:
                found = True
        if not found:
            return False
    return True


def _build_fair_test_table(baseline_events, recipes_events):
    rows = []
    if baseline_events is None:
        baseline_events = pd.DataFrame()
    if recipes_events is None:
        recipes_events = pd.DataFrame()

    recipes_by_question = {}
    for index, row in recipes_events.iterrows():
        question_text = str(row["question"])
        recipes_by_question[question_text] = row

    used_questions = {}
    for index, row in baseline_events.iterrows():
        question_text = str(row["question"])
        used_questions[question_text] = True
        baseline_numbers = ""
        if row["result_numbers"] is not None:
            baseline_numbers = str(row["result_numbers"])
        true_numbers = ""
        if row["true_numbers"] is not None:
            true_numbers = str(row["true_numbers"])

        recipe_numbers = ""
        if question_text in recipes_by_question:
            recipe_row = recipes_by_question[question_text]
            if recipe_row["result_numbers"] is not None:
                recipe_numbers = str(recipe_row["result_numbers"])
            if true_numbers == "":
                if recipe_row["true_numbers"] is not None:
                    true_numbers = str(recipe_row["true_numbers"])

        baseline_match = _numbers_match_answer_key(baseline_numbers, true_numbers)
        recipe_match = _numbers_match_answer_key(recipe_numbers, true_numbers)

        item = {}
        item["question"] = question_text
        item["baseline_numbers"] = baseline_numbers
        item["recipe_numbers"] = recipe_numbers
        item["answer_key_numbers"] = true_numbers
        item["baseline_matches"] = baseline_match
        item["recipe_matches"] = recipe_match
        rows.append(item)

    for index, row in recipes_events.iterrows():
        question_text = str(row["question"])
        if question_text in used_questions:
            continue
        recipe_numbers = ""
        if row["result_numbers"] is not None:
            recipe_numbers = str(row["result_numbers"])
        true_numbers = ""
        if row["true_numbers"] is not None:
            true_numbers = str(row["true_numbers"])
        baseline_numbers = ""
        baseline_match = _numbers_match_answer_key(baseline_numbers, true_numbers)
        recipe_match = _numbers_match_answer_key(recipe_numbers, true_numbers)

        item = {}
        item["question"] = question_text
        item["baseline_numbers"] = baseline_numbers
        item["recipe_numbers"] = recipe_numbers
        item["answer_key_numbers"] = true_numbers
        item["baseline_matches"] = baseline_match
        item["recipe_matches"] = recipe_match
        rows.append(item)

    return pd.DataFrame(rows)


def _format_metric_number(value):
    if value is None:
        return "—"
    return str(value)


def _format_seconds(value):
    if value is None:
        return "—"
    return str(round(value, 2))


st.set_page_config(page_title="Agents That Sleep", layout="wide")
st.title("Agents That Sleep")
st.write("Telemetry insights from the Hotdata events table.")

con = None
try:
    con = _get_connection()
    st.success("Connected to Hotdata telemetry")
except Exception as err:
    st.error("Could not connect to Hotdata: " + str(err))

baseline = _empty_session_stats()
recipes = _empty_session_stats()
fair_test_error = ""

if con is not None:
    try:
        baseline = _load_labeled_session(con, "baseline")
        recipes = _load_labeled_session(con, "recipes")
    except Exception as fair_err:
        fair_test_error = str(fair_err)

st.subheader("Fair test: same 12 questions")
if fair_test_error != "":
    st.warning("Could not load fair test sessions: " + fair_test_error)
else:
    if baseline["session_id"] is None and recipes["session_id"] is None:
        st.info(
            "No labeled runs yet. Run with --label baseline and --label recipes."
        )
    else:
        st.caption(
            "Baseline session: "
            + _format_metric_number(baseline["session_id"])
            + " | Recipes session: "
            + _format_metric_number(recipes["session_id"])
        )

        compare_cols = st.columns(2)
        with compare_cols[0]:
            st.markdown("**Baseline**")
            st.write("LLM calls: " + _format_metric_number(baseline["llm_calls"]))
            st.write(
                "Total tokens: " + _format_metric_number(baseline["total_tokens"])
            )
            st.write(
                "Total seconds: " + _format_seconds(baseline["total_seconds"])
            )
            st.write(
                "Average seconds per question: "
                + _format_seconds(baseline["avg_seconds"])
            )
            st.write(
                "Correct answers: "
                + _format_metric_number(baseline["correct_count"])
                + " / 12"
            )

        with compare_cols[1]:
            st.markdown("**Recipes**")
            st.write("LLM calls: " + _format_metric_number(recipes["llm_calls"]))
            st.write(
                "Total tokens: " + _format_metric_number(recipes["total_tokens"])
            )
            st.write(
                "Total seconds: " + _format_seconds(recipes["total_seconds"])
            )
            st.write(
                "Average seconds per question: "
                + _format_seconds(recipes["avg_seconds"])
            )
            st.write(
                "Correct answers: "
                + _format_metric_number(recipes["correct_count"])
                + " / 12"
            )

        fair_table = _build_fair_test_table(baseline["events"], recipes["events"])
        if len(fair_table) > 0:
            st.dataframe(fair_table, use_container_width=True)

st.subheader("Headline metrics")
metric_cols = st.columns(3)

baseline_llm_label = _format_metric_number(baseline["llm_calls"])
recipes_llm_label = _format_metric_number(recipes["llm_calls"])
llm_delta = None
baseline_tokens_label = _format_metric_number(baseline["total_tokens"])
recipes_tokens_label = _format_metric_number(recipes["total_tokens"])
tokens_delta = None
recipes_count = _count_saved_recipes()

if baseline["llm_calls"] is not None and recipes["llm_calls"] is not None:
    llm_delta = recipes["llm_calls"] - baseline["llm_calls"]
if baseline["total_tokens"] is not None and recipes["total_tokens"] is not None:
    tokens_delta = recipes["total_tokens"] - baseline["total_tokens"]

if baseline["session_id"] is not None or recipes["session_id"] is not None:
    st.caption(
        "Baseline session: "
        + _format_metric_number(baseline["session_id"])
        + " | Recipes session: "
        + _format_metric_number(recipes["session_id"])
    )

with metric_cols[0]:
    st.metric(
        label="LLM calls (recipes vs baseline)",
        value=recipes_llm_label,
        delta=llm_delta,
        delta_color="inverse",
        help="Latest recipes run LLM answer count vs latest baseline run",
    )
    st.caption("Baseline: " + baseline_llm_label)

with metric_cols[1]:
    st.metric(
        label="Total tokens (recipes vs baseline)",
        value=recipes_tokens_label,
        delta=tokens_delta,
        delta_color="inverse",
        help="Latest recipes run total llm_tokens vs latest baseline run",
    )
    st.caption("Baseline: " + baseline_tokens_label)

with metric_cols[2]:
    st.metric(
        label="Saved recipes",
        value=str(recipes_count),
        help="Number of skills saved in skills.json",
    )

run_all = st.button("Run all", type="primary")

insight_index = 0
for insight in INSIGHTS:
    insight_index = insight_index + 1
    st.divider()
    st.subheader(insight["title"])
    st.write(insight["meaning"])
    pretty_sql = _format_sql_for_display(insight["sql"])
    st.code(pretty_sql, language="sql")

    button_key = "run_" + str(insight_index)
    run_clicked = st.button("Run live", key=button_key)

    should_run = False
    if run_all:
        should_run = True
    if run_clicked:
        should_run = True

    if should_run:
        if con is None:
            st.warning("No Hotdata connection available.")
        else:
            with st.spinner("Running query..."):
                result = _run_insight(con, insight)

            if result["error"] != "":
                st.error(result["error"])
            else:
                st.caption("Query time: " + str(result["elapsed_ms"]) + " ms")
                st.dataframe(result["df"], use_container_width=True)
                _show_chart(insight, result["df"])
