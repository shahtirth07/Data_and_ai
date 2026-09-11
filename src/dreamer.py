import asyncio
import json
import re
import time
from datetime import datetime, timezone

from src.hotdata_client import create_task_db, destroy_db, make_connection, run_sql
from src.llm import ask_llm
from src.rocketride_client import connect as rocketride_connect
from src.rocketride_client import start_pipeline, stop_pipeline


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


def _distinct_text_values_text(df):
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


def _known_text_values(df):
    known = {}
    text_columns = ["region", "category", "product", "channel"]
    for col_name in text_columns:
        unique_values = df[col_name].dropna().unique()
        for value in unique_values:
            known[str(value)] = True
    return known


def _known_value_lookup(known_values, value):
    if value in known_values:
        return value
    value_lower = value.lower()
    for known in known_values:
        if known.lower() == value_lower:
            return known
    return None


def _canonicalize_capture(known_values, value):
    if value.isdigit():
        as_int = int(value)
        return str(as_int)

    known = _known_value_lookup(known_values, value)
    if known is not None:
        return known

    return None


def _strip_fences(text):
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


def _parse_skill_json(text):
    cleaned = _strip_fences(text)
    data = json.loads(cleaned)
    skill = {}
    skill["question_regex"] = data["question_regex"]
    skill["sql_template"] = data["sql_template"]
    return skill


def _strip_inline_flags(pattern):
    result = ""
    i = 0
    n = len(pattern)
    while i < n:
        matched_flags = False
        if i + 2 < n:
            if pattern[i] == "(":
                if pattern[i + 1] == "?":
                    j = i + 2
                    only_flags = True
                    has_flag = False
                    while j < n:
                        ch = pattern[j]
                        if ch == ")":
                            break
                        if ch == "i":
                            has_flag = True
                        else:
                            if ch == "m":
                                has_flag = True
                            else:
                                if ch == "s":
                                    has_flag = True
                                else:
                                    if ch == "x":
                                        has_flag = True
                                    else:
                                        if ch == "a":
                                            has_flag = True
                                        else:
                                            if ch == "u":
                                                has_flag = True
                                            else:
                                                if ch == "L":
                                                    has_flag = True
                                                else:
                                                    only_flags = False
                                                    break
                        j = j + 1
                    if only_flags:
                        if has_flag:
                            if j < n:
                                if pattern[j] == ")":
                                    i = j + 1
                                    matched_flags = True
        if matched_flags:
            continue
        result = result + pattern[i]
        i = i + 1
    return result


def _compile_regex(pattern):
    cleaned = _strip_inline_flags(pattern)
    compiled = re.compile(cleaned, re.IGNORECASE)
    return compiled


def _build_skill_prompt(question_type, examples, df):
    distinct_values = _distinct_text_values_text(df)

    examples_text = ""
    example_index = 0
    for example in examples:
        example_index = example_index + 1
        question = example["question"]
        sql = example["sql"]
        block = (
            "Example "
            + str(example_index)
            + ":\n"
            + "question: "
            + question
            + "\n"
            + "sql:\n"
            + sql
            + "\n"
        )
        examples_text = examples_text + block

    prompt = (
        "You create a reusable SQL skill for question_type="
        + question_type
        + ".\n"
        "Return JSON only with exactly these keys:\n"
        '  "question_regex": a Python regex with named groups that matches every '
        "example question and captures the values that change\n"
        '  "sql_template": the SQL with {group_name} placeholders for those captures\n'
        "Rules:\n"
        "- Only make a named group for parts that are DIFFERENT between the example "
        'questions. Parts that are the same in every example, like "top 3", "2025", '
        '"Jul-Sep", must stay as literal text in the regex and in the SQL.\n'
        '- Use table "default"."main"."orders".\n'
        "- Use INTEGER not INT64.\n"
        "- Use exact capitalization for text values.\n"
        "- No markdown fences.\n"
        "- No explanation outside JSON.\n"
        "Allowed text values:\n"
        + distinct_values
        + "\n"
        "Examples:\n"
        + examples_text
    )
    return prompt


def _build_retry_prompt(question_type, examples, df, failure_text):
    base = _build_skill_prompt(question_type, examples, df)
    prompt = (
        base
        + "\n"
        + "The previous skill failed verification:\n"
        + failure_text
        + "\n"
        + "Return a corrected JSON skill only."
    )
    return prompt


def _fill_sql_template(sql_template, groups):
    sql = sql_template
    for name in groups:
        value = groups[name]
        placeholder = "{" + name + "}"
        sql = sql.replace(placeholder, value)
    return sql


def _match_question(regex_pattern, question):
    compiled = _compile_regex(regex_pattern)
    match = compiled.fullmatch(question)
    if match is None:
        match = compiled.search(question)
    return match


def _collect_numeric_values(result_df):
    numbers = []
    if result_df is None:
        return numbers

    for col_name in result_df.columns:
        series = result_df[col_name]
        for value in series:
            if value is None:
                continue
            try:
                number = float(value)
            except Exception:
                continue
            rounded = round(number, 2)
            numbers.append(rounded)

    return numbers


def _count_numbers(numbers):
    counts = {}
    for number in numbers:
        if number in counts:
            counts[number] = counts[number] + 1
        else:
            counts[number] = 1
    return counts


def _counts_contained(small_counts, big_counts):
    for key in small_counts:
        if key not in big_counts:
            return False
        if small_counts[key] > big_counts[key]:
            return False
    return True


def _numeric_results_match(original_nums, template_nums):
    if len(original_nums) == 0:
        if len(template_nums) == 0:
            return True

    original_counts = _count_numbers(original_nums)
    template_counts = _count_numbers(template_nums)

    if _counts_contained(original_counts, template_counts):
        return True
    if _counts_contained(template_counts, original_counts):
        return True
    return False


def _join_failure_lines(failures):
    text = ""
    i = 0
    for item in failures:
        if i == 0:
            text = item
        else:
            text = text + "\n" + item
        i = i + 1
    return text


def _verify_skill(skill, examples, hot_con, task_db, known_values):
    failures = []
    short_failures = []
    hotdata_queries = 0

    example_index = 0
    for example in examples:
        example_index = example_index + 1
        question = example["question"]
        original_sql = example["sql"]

        match = _match_question(skill["question_regex"], question)
        if match is None:
            msg = (
                "Example "
                + str(example_index)
                + ": regex did not match question: "
                + question
            )
            print(msg)
            failures.append(msg)
            short_failures.append(
                "Example " + str(example_index) + ": regex did not match"
            )
            continue

        groups = match.groupdict()
        bad_capture = False
        canonical_groups = {}
        for name in groups:
            value = groups[name]
            if value is None:
                msg = (
                    "Example "
                    + str(example_index)
                    + ": capture group "
                    + name
                    + " was missing"
                )
                print(msg)
                failures.append(msg)
                short_failures.append(
                    "Example " + str(example_index) + ": missing capture " + name
                )
                bad_capture = True
            else:
                canonical = _canonicalize_capture(known_values, value)
                if canonical is None:
                    msg = (
                        "Example "
                        + str(example_index)
                        + ": captured value "
                        + value
                        + " is not a known text value or digit value"
                    )
                    print(msg)
                    failures.append(msg)
                    short_failures.append(
                        "Example "
                        + str(example_index)
                        + ": unknown capture "
                        + value
                    )
                    bad_capture = True
                else:
                    canonical_groups[name] = canonical

        if bad_capture:
            continue

        filled_sql = _fill_sql_template(skill["sql_template"], canonical_groups)

        try:
            original_df = run_sql(hot_con, task_db, original_sql)
            hotdata_queries = hotdata_queries + 1
        except Exception as err:
            hotdata_queries = hotdata_queries + 1
            msg = (
                "Example "
                + str(example_index)
                + ": original SQL failed: "
                + str(err)
            )
            print(msg)
            failures.append(msg)
            short_failures.append(
                "Example " + str(example_index) + ": original SQL failed"
            )
            continue

        try:
            template_df = run_sql(hot_con, task_db, filled_sql)
            hotdata_queries = hotdata_queries + 1
        except Exception as err:
            hotdata_queries = hotdata_queries + 1
            msg = (
                "Example "
                + str(example_index)
                + ": template SQL failed: "
                + str(err)
                + " SQL="
                + filled_sql
            )
            print(msg)
            failures.append(msg)
            short_failures.append(
                "Example " + str(example_index) + ": template SQL failed"
            )
            continue

        day_nums = _collect_numeric_values(original_df)
        skill_nums = _collect_numeric_values(template_df)
        matched = _numeric_results_match(day_nums, skill_nums)
        if matched:
            continue

        print(
            "Example",
            example_index,
            "FAILED numeric match. question=",
            question,
        )
        print("day result numbers=", day_nums)
        print("skill result numbers=", skill_nums)

        msg = (
            "Example "
            + str(example_index)
            + ": numeric results did not match. "
            + "question="
            + question
            + " filled_sql="
            + filled_sql
            + " day="
            + str(day_nums)
            + " skill="
            + str(skill_nums)
        )
        failures.append(msg)
        short_failures.append(
            "Example "
            + str(example_index)
            + ": numbers mismatch day="
            + str(day_nums)
            + " skill="
            + str(skill_nums)
        )

    passed = False
    if len(failures) == 0:
        passed = True

    result = {}
    result["passed"] = passed
    result["failures"] = failures
    result["short_failures"] = short_failures
    result["hotdata_queries"] = hotdata_queries
    return result


async def _connect_rocketride_with_retry(question_type):
    attempts = 0
    last_error = None
    while attempts < 6:
        attempts = attempts + 1
        try:
            client = await rocketride_connect()
            unique_token = (
                "tk_dream_"
                + question_type
                + "_"
                + str(int(time.time()))
                + "_"
                + str(attempts)
            )
            token = await start_pipeline(client, token=unique_token, ttl=300)
            result = {}
            result["client"] = client
            result["token"] = token
            return result
        except Exception as err:
            last_error = err
            wait_seconds = attempts * 2
            print(
                "RocketRide connect/start failed attempt",
                attempts,
                "waiting",
                wait_seconds,
                "s:",
                err,
            )
            await asyncio.sleep(wait_seconds)

    raise last_error


async def run_dreamer(question_type, examples, df, session_id):
    dream_start = time.time()
    llm_tokens = 0
    tokens_estimated = True
    hotdata_queries = 0
    success = False
    error_text = ""
    skill = None
    db_create_ms = 0
    db_destroy_ms = 0

    rr_client = None
    rr_token = None
    hot_con = None
    task_db = None

    try:
        rr = await _connect_rocketride_with_retry(question_type)
        rr_client = rr["client"]
        rr_token = rr["token"]
        print("Dreamer", question_type, "pipeline token=", rr_token)

        hot_con = make_connection()
        db_name = "dream_" + question_type

        create_start = time.time()
        task_db = create_task_db(db_name, df, con=hot_con)
        db_create_ms = int((time.time() - create_start) * 1000)
        print(
            "Dreamer",
            question_type,
            "created db id=",
            task_db,
            "ms=",
            db_create_ms,
        )

        known_values = _known_text_values(df)

        prompt = _build_skill_prompt(question_type, examples, df)
        llm_result = await ask_llm(rr_client, rr_token, prompt)
        llm_tokens = llm_tokens + llm_result["tokens"]
        tokens_estimated = llm_result["tokens_estimated"]

        try:
            skill = _parse_skill_json(llm_result["text"])
        except Exception as err:
            error_text = "Failed to parse skill JSON: " + str(err)
            skill = None

        if skill is not None:
            verify = _verify_skill(
                skill, examples, hot_con, task_db, known_values
            )
            hotdata_queries = hotdata_queries + verify["hotdata_queries"]
            if verify["passed"]:
                success = True
                error_text = ""
            else:
                error_text = _join_failure_lines(verify["short_failures"])
                skill = None
                success = False

        need_retry = True
        if success:
            need_retry = False

        if need_retry:
            if error_text == "":
                failure_for_retry = "Skill verification failed."
            else:
                failure_for_retry = error_text

            retry_prompt = _build_retry_prompt(
                question_type, examples, df, failure_for_retry
            )
            retry_result = await ask_llm(rr_client, rr_token, retry_prompt)
            llm_tokens = llm_tokens + retry_result["tokens"]
            tokens_estimated = retry_result["tokens_estimated"]

            try:
                skill = _parse_skill_json(retry_result["text"])
            except Exception as err:
                error_text = "Retry failed to parse skill JSON: " + str(err)
                skill = None
                success = False

            if skill is not None:
                verify2 = _verify_skill(
                    skill, examples, hot_con, task_db, known_values
                )
                hotdata_queries = hotdata_queries + verify2["hotdata_queries"]
                if verify2["passed"]:
                    success = True
                    error_text = ""
                else:
                    success = False
                    error_text = _join_failure_lines(verify2["short_failures"])
                    skill = None

        if skill is None:
            success = False

    except Exception as err:
        success = False
        skill = None
        error_text = str(err)
        print("Dreamer", question_type, "crashed:", error_text)

    finally:
        if task_db is not None:
            if hot_con is not None:
                destroy_start = time.time()
                try:
                    destroy_db(hot_con, task_db)
                except Exception as destroy_err:
                    print(
                        "Dreamer",
                        question_type,
                        "destroy_db failed:",
                        destroy_err,
                    )
                db_destroy_ms = int((time.time() - destroy_start) * 1000)
                print(
                    "Dreamer",
                    question_type,
                    "destroyed db ms=",
                    db_destroy_ms,
                )

        if rr_client is not None:
            if rr_token is not None:
                try:
                    await stop_pipeline(rr_client, rr_token)
                    print(
                        "Dreamer",
                        question_type,
                        "stopped pipeline success=",
                        success,
                    )
                except Exception as stop_err:
                    print(
                        "Dreamer",
                        question_type,
                        "stop_pipeline failed:",
                        stop_err,
                    )
            try:
                await rr_client.disconnect()
            except Exception as disconnect_err:
                print(
                    "Dreamer",
                    question_type,
                    "disconnect failed:",
                    disconnect_err,
                )

    latency_ms = int((time.time() - dream_start) * 1000)
    created_at = datetime.now(timezone.utc).isoformat()

    event = {
        "event_id": session_id + "-" + question_type,
        "session_id": session_id,
        "run_type": "night",
        "agent_id": "dreamer_" + question_type,
        "event_type": "dream",
        "question_type": question_type,
        "question": "",
        "used_skill": False,
        "llm_tokens": llm_tokens,
        "tokens_estimated": tokens_estimated,
        "latency_ms": latency_ms,
        "hotdata_queries": hotdata_queries,
        "success": success,
        "error": error_text,
        "created_at": created_at,
        "db_create_ms": db_create_ms,
        "db_destroy_ms": db_destroy_ms,
    }

    events = []
    events.append(event)

    if success:
        return skill, events
    return None, events
