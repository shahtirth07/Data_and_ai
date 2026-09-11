REGIONS = ["Northeast", "Midwest", "South", "West", "East"]
CATEGORIES = ["Electronics", "Apparel", "Grocery", "Home"]


def _find_known_value(question, candidates):
    ordered = sorted(candidates, key=len, reverse=True)
    question_lower = question.lower()
    for value in ordered:
        if value.lower() in question_lower:
            return value
    return None


def _round_sort_numbers(values):
    numbers = []
    for value in values:
        number = round(float(value), 2)
        numbers.append(number)
    numbers = sorted(numbers)
    return numbers


def _region_total(df, region):
    subset = df[df["region"] == region]
    total = subset["amount"].sum()
    return _round_sort_numbers([total])


def _top_products(df, category):
    subset = df[df["category"] == category]
    grouped = subset.groupby("product")["amount"].sum()
    top = grouped.nlargest(3)
    values = []
    for value in top:
        values.append(value)
    return _round_sort_numbers(values)


def _monthly_trend(df, region):
    subset = df[df["region"] == region].copy()
    date_text = subset["order_date"].astype(str)
    subset = subset[date_text.str.startswith("2025")].copy()
    if len(subset) == 0:
        return []
    subset["month"] = subset["order_date"].astype(str).str.slice(0, 7)
    grouped = subset.groupby("month")["amount"].sum()
    values = []
    for value in grouped:
        values.append(value)
    return _round_sort_numbers(values)


def _returns(df, category):
    subset = df[df["category"] == category]
    subset = subset[subset["quantity"] == 0]
    if len(subset) == 0:
        return []
    grouped = subset.groupby("product").size()
    values = []
    for value in grouped:
        values.append(value)
    return _round_sort_numbers(values)


def _channel_split(df, region):
    subset = df[df["region"] == region]
    grouped = subset.groupby("channel")["amount"].sum()
    values = []
    for value in grouped:
        values.append(value)
    return _round_sort_numbers(values)


def _quarter_growth(df, category):
    subset = df[df["category"] == category].copy()
    if len(subset) == 0:
        return []

    months = subset["order_date"].astype(str).str.slice(5, 7).astype(int)
    q3 = subset[(months >= 7) & (months <= 9)]
    q4 = subset[(months >= 10) & (months <= 12)]
    q3_total = q3["amount"].sum()
    q4_total = q4["amount"].sum()
    return _round_sort_numbers([q3_total, q4_total])


def _avg_order_value(df, region):
    subset = df[df["region"] == region]
    if len(subset) == 0:
        return []
    average = subset["amount"].mean()
    return _round_sort_numbers([average])


def _channel_count(df, category):
    subset = df[df["category"] == category]
    if len(subset) == 0:
        return []
    grouped = subset.groupby("channel").size()
    values = []
    for value in grouped:
        values.append(value)
    return _round_sort_numbers(values)


def get_true_numbers(question_type, question, df):
    region = _find_known_value(question, REGIONS)
    category = _find_known_value(question, CATEGORIES)

    if question_type == "region_total":
        if region is None:
            return []
        return _region_total(df, region)

    if question_type == "top_products":
        if category is None:
            return []
        return _top_products(df, category)

    if question_type == "monthly_trend":
        if region is None:
            return []
        return _monthly_trend(df, region)

    if question_type == "returns":
        if category is None:
            return []
        return _returns(df, category)

    if question_type == "channel_split":
        if region is None:
            return []
        return _channel_split(df, region)

    if question_type == "quarter_growth":
        if category is None:
            return []
        return _quarter_growth(df, category)

    if question_type == "avg_order_value":
        if region is None:
            return []
        return _avg_order_value(df, region)

    if question_type == "channel_count":
        if category is None:
            return []
        return _channel_count(df, category)

    return []
