def clamp(value, low=0, high=100):
    return max(low, min(high, value))


def hotel_score(item):
    """
    Expected item keys:
    current_price, historical_median, stars, breakfast, lounge,
    bathtub, quiet_relaxing, couples_friendly, good_location,
    flexible_cancellation, convenient_date
    """
    current = float(item.get("current_price", 0) or 0)
    median = float(item.get("historical_median", current) or current or 1)

    saving_pct = 0
    if median > 0 and current > 0:
        saving_pct = max(0, (median - current) / median * 100)

    # 40 pts: price saving. 35%+ gets full points.
    price_points = min(40, (saving_pct / 35) * 40)

    stars = float(item.get("stars", 4) or 4)
    quality_points = clamp((stars - 3) / 2 * 15, 0, 15)

    room_points = 0
    room_points += 4 if item.get("bathtub") else 0
    room_points += 3 if item.get("quiet_relaxing") else 0
    room_points += 3 if item.get("couples_friendly") else 0

    extras_points = 0
    extras_points += 5 if item.get("breakfast") else 0
    extras_points += 5 if item.get("lounge") else 0

    getaway_points = 10 if item.get("couples_friendly") else 5
    location_points = 5 if item.get("good_location") else 2
    cancel_points = 5 if item.get("flexible_cancellation") else 1
    date_points = 5 if item.get("convenient_date") else 2

    total = (
        price_points
        + quality_points
        + room_points
        + extras_points
        + getaway_points
        + location_points
        + cancel_points
        + date_points
    )
    return round(clamp(total), 1)


def promo_score(item, kind="food"):
    """
    Category score used inside Food and Sales tabs.

    The Best tab is separately curated by curate_best_items(), so a strong
    category score does not automatically mean every promotion appears in the
    Best shortlist.
    """
    discount = float(item.get("discount_percent", 0) or 0)

    # 50% discount = 60 base points. This preserves the scoring behaviour
    # already validated by the live Food and Sales scanner tests.
    base = min(60, discount / 50 * 60)
    quality = float(item.get("quality_score", 7) or 7) / 10 * 20
    relevance = float(item.get("relevance_score", 7) or 7) / 10 * 20

    return round(clamp(base + quality + relevance), 1)


DEFAULT_BEST_LIMITS = {
    "hotel": 3,
    "food": 5,
    "sale": 5,
    "idea": 1,
}


def curate_best_items(
    items,
    minimum_score=70,
    category_limits=None,
    total_limit=14,
):
    """
    Mark a deliberately small, balanced Best shortlist.

    Every item remains visible in its own category tab. The Best tab is capped
    so Food or Sales cannot flood the front page simply because many entries
    have similar high promotion scores.

    Default maximums:
      Hotels 3
      Food   5
      Sales  5
      Ideas  1
      Total 14
    """
    limits = dict(DEFAULT_BEST_LIMITS)
    if category_limits:
        limits.update(category_limits)

    for item in items:
        item["exclude_from_best"] = True
        item.pop("best_rank", None)

    grouped = {}

    for item in items:
        if item.get("is_demo", False):
            continue

        score = float(item.get("deal_score", 0) or 0)
        if score < float(minimum_score or 0):
            continue

        category = item.get("category", "other")
        grouped.setdefault(category, []).append(item)

    selected = []

    for category, candidates in grouped.items():
        candidates.sort(
            key=lambda item: (
                float(item.get("deal_score", 0) or 0),
                float(item.get("discount_percent", 0) or 0),
            ),
            reverse=True,
        )

        limit = limits.get(category, 2)
        selected.extend(candidates[:limit])

    selected.sort(
        key=lambda item: (
            float(item.get("deal_score", 0) or 0),
            float(item.get("discount_percent", 0) or 0),
        ),
        reverse=True,
    )

    selected = selected[: max(1, int(total_limit))]

    for rank, item in enumerate(selected, start=1):
        item["exclude_from_best"] = False
        item["best_rank"] = rank

    return selected
