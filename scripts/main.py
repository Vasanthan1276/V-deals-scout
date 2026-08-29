from utils import (
    read_json,
    write_json,
    iso_now_sgt,
)

from hotel_scanner import scan_hotels
from food_scanner import scan_food
from sales_scanner import scan_sales


def update_history(hotels):
    history = read_json(
        "data/history.json",
        {"observations": []},
    )

    observations = history.setdefault(
        "observations",
        [],
    )

    for hotel in hotels:
        observations.append(
            {
                "id": hotel.get("id"),
                "provider": hotel.get(
                    "provider"
                ),
                "hotelbeds_code": hotel.get(
                    "hotelbeds_code"
                ),
                "name": hotel.get("name"),
                "destination": hotel.get(
                    "destination"
                ),
                "check_in": hotel.get(
                    "check_in"
                ),
                "check_out": hotel.get(
                    "check_out"
                ),
                "nights": hotel.get(
                    "nights"
                ),
                "price": hotel.get(
                    "current_price"
                ),
                "total_price": hotel.get(
                    "total_price"
                ),
                "currency": hotel.get(
                    "currency",
                    "SGD",
                ),
                "price_type": hotel.get(
                    "price_type"
                ),
                "observed_at": hotel.get(
                    "observed_at"
                ),
                "is_demo": hotel.get(
                    "is_demo",
                    False,
                ),
                "is_evaluation": hotel.get(
                    "is_evaluation",
                    False,
                ),
            }
        )

    history["observations"] = (
        observations[-5000:]
    )

    history["updated_at"] = (
        iso_now_sgt()
    )

    write_json(
        "data/history.json",
        history,
    )


def build_ideas(
    hotels,
    food,
    sales,
):
    ideas = []

    regional = [
        h
        for h in hotels
        if h.get(
            "sub_category"
        ) == "regional"
    ]

    staycations = [
        h
        for h in hotels
        if h.get(
            "sub_category"
        ) == "staycation"
    ]

    if regional:
        hotel = sorted(
            regional,
            key=lambda x: x.get(
                "deal_score",
                0,
            ),
            reverse=True,
        )[0]

        ideas.append(
            {
                "id": (
                    "idea-regional-01"
                ),
                "category": "idea",
                "name": (
                    f"{hotel['destination']} "
                    f"getaway"
                ),
                "description": (
                    f"{hotel['nights']}-night "
                    f"stay at "
                    f"{hotel['name']}"
                ),
                "deal_score": hotel[
                    "deal_score"
                ],
                "estimated_cost": hotel.get(
                    "total_price"
                ),
                "currency": hotel[
                    "currency"
                ],
                "why": (
                    "Highest-scoring regional "
                    "hotel opportunity in the "
                    "current scan."
                ),
                "is_demo": False,
                "is_evaluation": hotel.get(
                    "is_evaluation",
                    False,
                ),
            }
        )

    if staycations:
        hotel = sorted(
            staycations,
            key=lambda x: x.get(
                "deal_score",
                0,
            ),
            reverse=True,
        )[0]

        ideas.append(
            {
                "id": (
                    "idea-staycation-01"
                ),
                "category": "idea",
                "name": (
                    "Singapore staycation"
                ),
                "description": (
                    f"{hotel['name']} — "
                    f"{hotel['nights']} night"
                ),
                "deal_score": hotel[
                    "deal_score"
                ],
                "estimated_cost": hotel.get(
                    "total_price"
                ),
                "currency": hotel[
                    "currency"
                ],
                "why": (
                    "Highest-scoring Singapore "
                    "hotel opportunity in the "
                    "current scan."
                ),
                "is_demo": False,
                "is_evaluation": hotel.get(
                    "is_evaluation",
                    False,
                ),
            }
        )

    return ideas


def main():
    hotels = scan_hotels()
    food = scan_food()
    sales = scan_sales()

    ideas = build_ideas(
        hotels,
        food,
        sales,
    )

    prefs = read_json(
        "config/preferences.json",
        {},
    )

    settings = prefs.get(
        "search_settings",
        {},
    )

    minimum = settings.get(
        "minimum_deal_score",
        70,
    )

    maximum = settings.get(
        "maximum_results_per_category",
        20,
    )

    qualifying_hotels = [
        h
        for h in hotels
        if h.get(
            "deal_score",
            0,
        ) >= minimum
    ][:maximum]

    qualifying_food = [
        x
        for x in food
        if x.get(
            "deal_score",
            0,
        ) >= minimum
    ][:maximum]

    qualifying_sales = [
        x
        for x in sales
        if x.get(
            "deal_score",
            0,
        ) >= minimum
    ][:maximum]

    visible = (
        qualifying_hotels
        + qualifying_food
        + qualifying_sales
        + ideas
    )

    visible.sort(
        key=lambda x: x.get(
            "deal_score",
            0,
        ),
        reverse=True,
    )

    write_json(
        "data/hotels.json",
        {
            "updated_at": iso_now_sgt(),
            "provider": "hotelbeds",
            "environment": "evaluation",
            "items": hotels,
        },
    )

    write_json(
        "data/food.json",
        {
            "updated_at": iso_now_sgt(),
            "items": food,
        },
    )

    write_json(
        "data/sales.json",
        {
            "updated_at": iso_now_sgt(),
            "items": sales,
        },
    )

    write_json(
        "data/deals.json",
        {
            "updated_at": iso_now_sgt(),
            "demo_mode": any(
                d.get("is_demo")
                for d in visible
            ),
            "hotel_evaluation_mode": any(
                h.get(
                    "is_evaluation"
                )
                for h in hotels
            ),
            "items": visible,
        },
    )

    update_history(hotels)

    print(
        f"Deals Scout updated: "
        f"{len(visible)} visible deals"
    )


if __name__ == "__main__":
    main()
