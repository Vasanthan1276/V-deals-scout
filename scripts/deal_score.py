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


SOURCE_CONFIDENCE_POINTS = {
    "verified": 10.0,
    "app_live": 8.0,
    "discovered": 5.0,
}

DEAL_TYPE_CONVENIENCE_POINTS = {
    "direct": 5.0,
    "direct_brand": 5.0,
    "mall_outlet": 4.5,
    "card_deal": 4.0,
    "membership_deal": 3.5,
    "app_deal": 3.0,
    "discovery": 2.0,
}


def promo_score(item, kind="food"):
    """
    Multi-source promotion score.

    55 pts  headline saving strength
    15 pts  venue / brand quality
    15 pts  personal relevance
    10 pts  source confidence
     5 pts  convenience / restrictions

    This prevents a large headline percentage from automatically outranking a
    similarly strong offer published directly by a merchant or bank.
    """
    discount = float(item.get("discount_percent", 0) or 0)
    discount_points = min(55.0, discount / 50.0 * 55.0)

    quality = float(item.get("quality_score", 7) or 7) / 10.0 * 15.0
    relevance = float(item.get("relevance_score", 7) or 7) / 10.0 * 15.0

    confidence = SOURCE_CONFIDENCE_POINTS.get(
        item.get("source_confidence"),
        6.0,
    )

    convenience = DEAL_TYPE_CONVENIENCE_POINTS.get(
        item.get("deal_type"),
        3.0,
    )

    # Small preference nudge for Indian cuisine. This improves ordering inside
    # the Food tab but is deliberately modest; a weak deal should not become a
    # Best deal solely because it matches the preferred cuisine.
    preference_bonus = 2.0 if (
        kind == "food"
        and item.get("food_category") == "indian"
    ) else 0.0

    return round(
        clamp(
            discount_points
            + quality
            + relevance
            + confidence
            + convenience
            + preference_bonus
        ),
        1,
    )


DEFAULT_BEST_LIMITS = {
    "hotel": 3,
    "food": 5,
    "sale": 5,
    "idea": 1,
}


def _source_family(item):
    return (
        item.get("deal_type")
        or item.get("source")
        or item.get("provider")
        or "other"
    )


def _take_diverse(candidates, limit, max_per_source_family=2):
    selected = []
    counts = {}

    for item in candidates:
        family = _source_family(item)
        if counts.get(family, 0) >= max_per_source_family:
            continue
        selected.append(item)
        counts[family] = counts.get(family, 0) + 1
        if len(selected) >= limit:
            return selected

    # Fill any unused slots if diversity limits were too restrictive.
    selected_ids = {id(item) for item in selected}
    for item in candidates:
        if id(item) in selected_ids:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break

    return selected


def curate_best_items(
    items,
    minimum_score=70,
    category_limits=None,
    total_limit=14,
):
    """
    Mark a small, balanced Best shortlist.

    V2 also protects source diversity: Food and Sales cannot be filled entirely
    by one app, card programme or discovery feed simply because that source
    publishes many similarly scored promotions.
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
                item.get("source_confidence") == "verified",
                float(item.get("discount_percent", 0) or 0),
            ),
            reverse=True,
        )

        limit = limits.get(category, 2)

        if category in {"food", "sale"}:
            category_selected = _take_diverse(
                candidates,
                limit,
                max_per_source_family=2,
            )
        else:
            category_selected = candidates[:limit]

        # If a genuinely good Indian-food deal is available, ensure it is not
        # displaced solely by source balancing. It must still clear the normal
        # Best score threshold.
        if category == "food":
            preferred = next(
                (
                    item
                    for item in candidates
                    if item.get("food_category") == "indian"
                ),
                None,
            )
            if preferred and preferred not in category_selected:
                if category_selected:
                    category_selected[-1] = preferred
                else:
                    category_selected.append(preferred)

        selected.extend(category_selected)

    selected.sort(
        key=lambda item: (
            float(item.get("deal_score", 0) or 0),
            item.get("source_confidence") == "verified",
            float(item.get("discount_percent", 0) or 0),
        ),
        reverse=True,
    )
    selected = selected[: max(1, int(total_limit))]

    for rank, item in enumerate(selected, start=1):
        item["exclude_from_best"] = False
        item["best_rank"] = rank

    return selected
