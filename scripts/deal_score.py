def clamp(value, low=0, high=100):
    return max(low, min(high, value))


def score_band(score):
    score = float(score or 0)
    if score >= 90:
        return "Exceptional"
    if score >= 80:
        return "Strong"
    if score >= 70:
        return "Worth a look"
    if score >= 60:
        return "Moderate"
    return "Low priority"


def hotel_score_details(item):
    """Return the Hotel score and exact component breakdown used by hotel_score()."""
    current = float(item.get("current_price", 0) or 0)
    median = float(item.get("historical_median", current) or current or 1)

    saving_pct = 0.0
    if median > 0 and current > 0:
        saving_pct = max(0.0, (median - current) / median * 100.0)

    price_points = min(40.0, (saving_pct / 35.0) * 40.0)

    stars = float(item.get("stars", 4) or 4)
    quality_points = clamp((stars - 3.0) / 2.0 * 15.0, 0, 15)

    room_points = 0.0
    room_points += 4.0 if item.get("bathtub") else 0.0
    room_points += 3.0 if item.get("quiet_relaxing") else 0.0
    room_points += 3.0 if item.get("couples_friendly") else 0.0

    extras_points = 0.0
    extras_points += 5.0 if item.get("breakfast") else 0.0
    extras_points += 5.0 if item.get("lounge") else 0.0

    getaway_points = 10.0 if item.get("couples_friendly") else 5.0
    location_points = 5.0 if item.get("good_location") else 2.0
    cancel_points = 5.0 if item.get("flexible_cancellation") else 1.0
    date_points = 5.0 if item.get("convenient_date") else 2.0

    total = round(
        clamp(
            price_points
            + quality_points
            + room_points
            + extras_points
            + getaway_points
            + location_points
            + cancel_points
            + date_points
        ),
        1,
    )

    details = {
        "model": "hotel_v1",
        "total": total,
        "scale_max": 100,
        "band": score_band(total),
        "components": [
            {
                "key": "price",
                "label": "Price saving",
                "points": round(price_points, 1),
                "max_points": 40,
                "detail": f"{saving_pct:.1f}% below the available reference price",
            },
            {
                "key": "quality",
                "label": "Hotel quality",
                "points": round(quality_points, 1),
                "max_points": 15,
                "detail": f"{stars:.1f}-star quality input",
            },
            {
                "key": "room",
                "label": "Room suitability",
                "points": round(room_points, 1),
                "max_points": 10,
                "detail": "Bathtub, quiet/relaxing and couple-friendly attributes",
            },
            {
                "key": "extras",
                "label": "Included extras",
                "points": round(extras_points, 1),
                "max_points": 10,
                "detail": "Breakfast and lounge attributes",
            },
            {
                "key": "getaway",
                "label": "Getaway fit",
                "points": round(getaway_points, 1),
                "max_points": 10,
                "detail": "Suitability as a couple getaway",
            },
            {
                "key": "location",
                "label": "Location",
                "points": round(location_points, 1),
                "max_points": 5,
                "detail": "Convenience of the hotel location",
            },
            {
                "key": "cancellation",
                "label": "Cancellation flexibility",
                "points": round(cancel_points, 1),
                "max_points": 5,
                "detail": "Flexibility of cancellation terms",
            },
            {
                "key": "date",
                "label": "Date convenience",
                "points": round(date_points, 1),
                "max_points": 5,
                "detail": "Convenience of the stay dates",
            },
        ],
        "notes": [
            "Hotel scoring may also be constrained by the hotel engine's peer/history rules.",
        ],
    }
    return details


def hotel_score(item):
    """Return a 0-100 Hotel score and attach an explainable breakdown."""
    details = hotel_score_details(item)
    if isinstance(item, dict):
        item["score_breakdown"] = details
    return details["total"]


SOURCE_CONFIDENCE_POINTS = {
    "verified": 10.0,
    "app_live": 8.0,
    "discovered": 5.0,
}

SOURCE_CONFIDENCE_LABELS = {
    "verified": "Verified official/direct source",
    "app_live": "Live app source",
    "discovered": "Discovery source; verify with merchant",
}

DEAL_TYPE_CONVENIENCE_POINTS = {
    "direct": 5.0,
    "direct_brand": 5.0,
    "direct_retailer": 5.0,
    "mall_outlet": 4.5,
    "card_deal": 4.0,
    "membership_deal": 3.5,
    "app_deal": 3.0,
    "discovery": 2.0,
}

DEAL_TYPE_LABELS = {
    "direct": "Direct merchant",
    "direct_brand": "Direct brand",
    "direct_retailer": "Direct retailer",
    "mall_outlet": "Mall / outlet",
    "card_deal": "Card-linked deal",
    "membership_deal": "Membership deal",
    "app_deal": "App deal",
    "discovery": "Discovery listing",
}


def promo_score_details(item, kind="food"):
    """
    Explainable 0-100 promotion score.

    55 pts  headline saving strength
    15 pts  venue / brand quality
    15 pts  personal relevance / usefulness
    10 pts  source confidence
     5 pts  convenience / restrictions
    ------
    100 pts maximum

    Indian cuisine preference is intentionally handled by Best-list curation
    and scanner relevance rather than adding bonus points above 100.
    """
    discount = float(item.get("discount_percent", 0) or 0)
    discount_points = min(55.0, discount / 50.0 * 55.0)

    quality_input = float(item.get("quality_score", 7) or 7)
    quality_points = quality_input / 10.0 * 15.0

    relevance_input = float(item.get("relevance_score", 7) or 7)
    relevance_points = relevance_input / 10.0 * 15.0

    confidence_key = item.get("source_confidence") or "unknown"
    confidence_points = SOURCE_CONFIDENCE_POINTS.get(confidence_key, 6.0)

    deal_type = item.get("deal_type") or "unknown"
    convenience_points = DEAL_TYPE_CONVENIENCE_POINTS.get(deal_type, 3.0)

    total = round(
        clamp(
            discount_points
            + quality_points
            + relevance_points
            + confidence_points
            + convenience_points
        ),
        1,
    )

    notes = [
        "The score is a ranking aid, not a guarantee of final value or availability.",
    ]
    if kind == "food" and item.get("food_category") == "indian":
        notes.append(
            "Indian cuisine is prioritised in the Best shortlist, but no extra points are added to the /100 score."
        )

    return {
        "model": "promotion_v4",
        "total": total,
        "scale_max": 100,
        "band": score_band(total),
        "components": [
            {
                "key": "discount",
                "label": "Discount strength",
                "points": round(discount_points, 1),
                "max_points": 55,
                "detail": f"{discount:g}% advertised saving; 50%+ earns the full 55 points",
            },
            {
                "key": "quality",
                "label": "Venue / brand quality",
                "points": round(quality_points, 1),
                "max_points": 15,
                "detail": f"Scanner quality estimate {quality_input:.1f}/10",
            },
            {
                "key": "relevance",
                "label": "Relevance / usefulness",
                "points": round(relevance_points, 1),
                "max_points": 15,
                "detail": f"Scanner relevance estimate {relevance_input:.1f}/10",
            },
            {
                "key": "confidence",
                "label": "Source confidence",
                "points": round(confidence_points, 1),
                "max_points": 10,
                "detail": SOURCE_CONFIDENCE_LABELS.get(
                    confidence_key,
                    f"Source confidence: {confidence_key or 'unspecified'}",
                ),
            },
            {
                "key": "convenience",
                "label": "Convenience / restrictions",
                "points": round(convenience_points, 1),
                "max_points": 5,
                "detail": DEAL_TYPE_LABELS.get(
                    deal_type,
                    f"Deal type: {deal_type or 'unspecified'}",
                ),
            },
        ],
        "notes": notes,
    }


def promo_score(item, kind="food"):
    """Return a 0-100 promotion score and attach its score breakdown."""
    details = promo_score_details(item, kind)
    if isinstance(item, dict):
        item["score_breakdown"] = details
    return details["total"]


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

    Food and Sales source diversity is protected so the Best page cannot be
    filled entirely by one app, card programme or discovery feed.
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

        # Indian food preference is handled here rather than by inflating the
        # numerical score beyond its 100-point design.
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
