INSIGHTS = [
    {
        "title": "Sessions over time",
        "meaning": "For each day session, LLM vs reflex answer counts, total tokens, and average latency, ordered by first event time.",
        "sql": (
            'SELECT '
            "session_id, "
            "SUM(CASE WHEN event_type = 'answer' THEN 1 ELSE 0 END) AS llm_answers, "
            "SUM(CASE WHEN event_type = 'reflex' THEN 1 ELSE 0 END) AS reflex_answers, "
            "SUM(llm_tokens) AS total_llm_tokens, "
            "AVG(latency_ms) AS avg_latency_ms, "
            "MIN(created_at) AS first_created_at "
            'FROM "default"."main"."events" '
            "WHERE run_type = 'day' "
            "AND session_id <> 'test' "
            "AND session_id <> 'setup' "
            "GROUP BY session_id "
            "ORDER BY MIN(created_at)"
        ),
        "chart": "line",
        "chart_x": "session_id",
        "chart_y": "avg_latency_ms",
    },
    {
        "title": "SQL drift",
        "meaning": "How many distinct SQL strings appear per question_type for LLM answers versus reflex answers.",
        "sql": (
            'SELECT '
            "event_type, "
            "question_type, "
            "COUNT(DISTINCT sql) AS distinct_sql_count "
            'FROM "default"."main"."events" '
            "WHERE session_id <> 'test' "
            "AND session_id <> 'setup' "
            "AND event_type IN ('answer', 'reflex') "
            "AND question_type IS NOT NULL "
            "AND CAST(question_type AS VARCHAR) <> '' "
            "GROUP BY event_type, question_type "
            "ORDER BY event_type, question_type"
        ),
        "chart": "bar",
        "chart_x": "question_type",
        "chart_y": "distinct_sql_count",
    },
    {
        "title": "Dreamer comparison",
        "meaning": "Per night dreamer agent: average latency, average DB create time, total tokens, and success rate.",
        "sql": (
            'SELECT '
            "agent_id, "
            "AVG(latency_ms) AS avg_latency_ms, "
            "AVG(db_create_ms) AS avg_db_create_ms, "
            "SUM(llm_tokens) AS total_llm_tokens, "
            "AVG(CASE WHEN success = true THEN 1.0 ELSE 0.0 END) AS success_rate "
            'FROM "default"."main"."events" '
            "WHERE run_type = 'night' "
            "AND event_type = 'dream' "
            "AND session_id <> 'test' "
            "GROUP BY agent_id "
            "ORDER BY agent_id"
        ),
        "chart": "bar",
        "chart_x": "agent_id",
        "chart_y": "avg_latency_ms",
    },
    {
        "title": "Parallel vs sequential",
        "meaning": "For each night session, wall-clock ms and max_parallel from night_summary, plus the sum of dreamer latency_ms.",
        "sql": (
            'SELECT '
            "s.session_id, "
            "s.wall_clock_ms, "
            "s.max_parallel, "
            "d.sum_dreamer_latency_ms, "
            "s.first_created_at "
            "FROM ("
            "  SELECT "
            "    session_id, "
            "    MAX(wall_clock_ms) AS wall_clock_ms, "
            "    MAX(max_parallel) AS max_parallel, "
            "    MIN(created_at) AS first_created_at "
            '  FROM "default"."main"."events" '
            "  WHERE event_type = 'night_summary' "
            "  AND session_id <> 'test' "
            "  GROUP BY session_id"
            ") s "
            "LEFT JOIN ("
            "  SELECT "
            "    session_id, "
            "    SUM(latency_ms) AS sum_dreamer_latency_ms "
            '  FROM "default"."main"."events" '
            "  WHERE event_type = 'dream' "
            "  AND session_id <> 'test' "
            "  GROUP BY session_id"
            ") d "
            "ON s.session_id = d.session_id "
            "ORDER BY s.first_created_at"
        ),
        "chart": "bar",
        "chart_x": "session_id",
        "chart_y": "wall_clock_ms",
    },
    {
        "title": "Failure patterns",
        "meaning": "Failed event counts and retry counts per question_type and session, with the most common non-empty error text.",
        "sql": (
            'SELECT '
            "b.question_type, "
            "b.session_id, "
            "b.failed_count, "
            "b.retry_count, "
            "e.error AS most_common_error, "
            "e.error_count "
            "FROM ("
            "  SELECT "
            "    question_type, "
            "    session_id, "
            "    SUM(CASE WHEN success = false THEN 1 ELSE 0 END) AS failed_count, "
            "    SUM(CASE WHEN hotdata_queries > 1 THEN 1 ELSE 0 END) AS retry_count "
            '  FROM "default"."main"."events" '
            "  WHERE session_id <> 'test' "
            "  AND session_id <> 'setup' "
            "  GROUP BY question_type, session_id "
            "  HAVING SUM(CASE WHEN success = false THEN 1 ELSE 0 END) > 0 "
            "  OR SUM(CASE WHEN hotdata_queries > 1 THEN 1 ELSE 0 END) > 0"
            ") b "
            "LEFT JOIN ("
            "  SELECT "
            "    question_type, "
            "    session_id, "
            "    error, "
            "    COUNT(*) AS error_count "
            '  FROM "default"."main"."events" '
            "  WHERE session_id <> 'test' "
            "  AND session_id <> 'setup' "
            "  AND success = false "
            "  AND error IS NOT NULL "
            "  AND CAST(error AS VARCHAR) <> '' "
            "  GROUP BY question_type, session_id, error"
            ") e "
            "ON b.question_type = e.question_type "
            "AND b.session_id = e.session_id "
            "ORDER BY b.failed_count DESC, e.error_count DESC NULLS LAST"
        ),
        "chart": "bar",
        "chart_x": "question_type",
        "chart_y": "failed_count",
    },
    {
        "title": "Night learning curve",
        "meaning": "For each night session in time order, how many dreamers ran and how many passed.",
        "sql": (
            'SELECT '
            "session_id, "
            "SUM(CASE WHEN event_type = 'dream' THEN 1 ELSE 0 END) AS dreamers_run, "
            "SUM(CASE WHEN event_type = 'dream' AND success = true THEN 1 ELSE 0 END) AS dreamers_passed, "
            "MIN(created_at) AS first_created_at "
            'FROM "default"."main"."events" '
            "WHERE run_type = 'night' "
            "AND session_id <> 'test' "
            "GROUP BY session_id "
            "ORDER BY MIN(created_at)"
        ),
        "chart": "line",
        "chart_x": "session_id",
        "chart_y": "dreamers_passed",
    },
    {
        "title": "Repeat counts",
        "meaning": "Per question type: total successful LLM answers across all day sessions, whether a recipe exists, and tokens spent on LLM answers before the first successful dream.",
        "sql": (
            'SELECT '
            "a.question_type, "
            "a.total_llm_answers, "
            "CASE WHEN d.first_recipe_at IS NOT NULL THEN true ELSE false END AS has_recipe, "
            "COALESCE(t.tokens_before_recipe, a.total_tokens) AS tokens_before_recipe "
            "FROM ("
            "  SELECT "
            "    question_type, "
            "    COUNT(*) AS total_llm_answers, "
            "    SUM(llm_tokens) AS total_tokens "
            '  FROM "default"."main"."events" '
            "  WHERE run_type = 'day' "
            "  AND event_type = 'answer' "
            "  AND success = true "
            "  AND session_id <> 'test' "
            "  AND session_id <> 'setup' "
            "  AND question_type IS NOT NULL "
            "  AND CAST(question_type AS VARCHAR) <> '' "
            "  GROUP BY question_type"
            ") a "
            "LEFT JOIN ("
            "  SELECT "
            "    question_type, "
            "    MIN(created_at) AS first_recipe_at "
            '  FROM "default"."main"."events" '
            "  WHERE run_type = 'night' "
            "  AND event_type = 'dream' "
            "  AND success = true "
            "  AND session_id <> 'test' "
            "  AND question_type IS NOT NULL "
            "  AND CAST(question_type AS VARCHAR) <> '' "
            "  GROUP BY question_type"
            ") d "
            "ON a.question_type = d.question_type "
            "LEFT JOIN ("
            "  SELECT "
            "    a2.question_type, "
            "    SUM(a2.llm_tokens) AS tokens_before_recipe "
            '  FROM "default"."main"."events" a2 '
            "  INNER JOIN ("
            "    SELECT "
            "      question_type, "
            "      MIN(created_at) AS first_recipe_at "
            '    FROM "default"."main"."events" '
            "    WHERE run_type = 'night' "
            "    AND event_type = 'dream' "
            "    AND success = true "
            "    AND session_id <> 'test' "
            "    AND question_type IS NOT NULL "
            "    AND CAST(question_type AS VARCHAR) <> '' "
            "    GROUP BY question_type"
            "  ) d2 "
            "  ON a2.question_type = d2.question_type "
            "  WHERE a2.run_type = 'day' "
            "  AND a2.event_type = 'answer' "
            "  AND a2.success = true "
            "  AND a2.session_id <> 'test' "
            "  AND a2.session_id <> 'setup' "
            "  AND a2.created_at < d2.first_recipe_at "
            "  GROUP BY a2.question_type"
            ") t "
            "ON a.question_type = t.question_type "
            "ORDER BY a.question_type"
        ),
        "chart": "bar",
        "chart_x": "question_type",
        "chart_y": "tokens_before_recipe",
    },
]
