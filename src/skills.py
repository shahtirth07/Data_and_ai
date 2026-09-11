import re


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


def _lookup_known_value(distinct_values, value):
    if value in distinct_values:
        return value
    value_lower = value.lower()
    for known in distinct_values:
        if known.lower() == value_lower:
            return known
    return None


def _fill_sql_template(sql_template, groups):
    sql = sql_template
    for name in groups:
        value = groups[name]
        placeholder = "{" + name + "}"
        sql = sql.replace(placeholder, value)
    return sql


def match_skill(question, skills, distinct_values):
    for question_type in skills:
        skill = skills[question_type]
        regex_pattern = skill["question_regex"]
        sql_template = skill["sql_template"]

        compiled = _compile_regex(regex_pattern)
        match = compiled.fullmatch(question)
        if match is None:
            match = compiled.search(question)
        if match is None:
            continue

        groups = match.groupdict()
        filled_groups = {}
        ok = True
        for name in groups:
            value = groups[name]
            if value is None:
                ok = False
                break

            if value.isdigit():
                as_int = int(value)
                filled_groups[name] = str(as_int)
            else:
                known = _lookup_known_value(distinct_values, value)
                if known is None:
                    ok = False
                    break
                filled_groups[name] = known

        if not ok:
            continue

        filled_sql = _fill_sql_template(sql_template, filled_groups)
        result = {}
        result["question_type"] = question_type
        result["sql"] = filled_sql
        return result

    return None
