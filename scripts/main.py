from utils import (
    read_json,
    write_json,
    iso_now_sgt,
)

from hotel_scanner import (
    scan_hotels,
)

from food_scanner import (
    scan_food,
)

from sales_scanner import (
    scan_sales,
)


def update_history(hotels):
    history = read_json(
        "data/history.json",
        {
            "observations": []
        },
    )

    observations = (
        history.setdefault(
            "observations",
            [],
        )
    )

    for hotel in hotels:
        observations.append(
            {
                "id": (
                    hotel.get("id")
                ),

                "provider": (
                    hotel.get(
                        "provider"
                    )
                ),

                "hotelbeds_code": (
                    hotel.get(
                        "hotelbeds_code"
                    )
                ),

                "name": (
                    hotel.get("name")
                ),

                "destination": (
                    hotel.get(
                        "destination"
                    )
                ),

                "check_in": (
                    hotel.get(
                        "check_in"
                    )
                ),

                "check_out": (
                    hotel.get(
                        "check_out"
                    )
                ),

                "nights": (
                    hotel.get(
                        "nights"
                    )
                ),

                "price": (
                    hotel.get(
                        "current_price"
                    )
                ),

                "total_price": (
                    hotel.get(
                        "total_price"
                    )
                ),

                "currency": (
                    hotel.get(
                        "currency",
                        "SGD",
                    )
                ),

                "score_basis": (
                    hotel.get(
                        "score_basis"
                    )
                ),

                "reference_source": (
                    hotel.get(
                        "reference_source"
                    )
                ),

                "price_type": (
                    hotel.get(
                        "price_type"
                    )
                ),

                "observed_at": (
                    hotel.get(
                        "observed_at"
                    )
                ),

                "is_demo": (
                    hotel.get(
                        "is_demo",
                        False,
                    )
                ),

                "is_evaluation": (
                    hotel.get(
                        "is_evaluation",
                        False,
                    )
                ),
            }
        )

    history[
        "observations"
    ] = observations[-5000:]

    history[
        "updated_at"
    ] = iso_now_sgt()

    write_json(
        "data/history.json",
        history,
    )


def build_ideas(
    hotels,
    minimum_score,
):
    ideas = []

    eligible = [
        hotel
        for hotel
        in hotels
        if hotel.get(
            "deal_score",
            0,
        ) >= minimum_score
    ]

    regional = [
        hotel
        for hotel
        in eligible
        if hotel.get(
            "sub_category"
        ) == "regional"
    ]

    staycations = [
        hotel
        for hotel
        in eligible
        if hotel.get(
            "sub_category"
        ) == "staycation"
    ]

    if regional:
        hotel = regional[0]

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

                "deal_score": (
                    hotel[
                        "deal_score"
                    ]
                ),

                "estimated_cost": (
                    hotel.get(
                        "total_price"
                    )
                ),

                "currency": (
                    hotel[
                        "currency"
                    ]
                ),

                "why": (
                    "Highest-scoring "
                    "regional hotel "
                    "opportunity in the "
                    "current scan."
                ),

                "score_basis": (
                    hotel.get(
                        "score_basis"
                    )
                ),

                "reference_source": (
                    hotel.get(
                        "reference_source"
                    )
                ),

                "is_demo": False,

                "is_evaluation": (
                    hotel.get(
                        "is_evaluation",
                        False,
                    )
                ),
            }
        )

    if staycations:
        hotel = staycations[0]

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

                "deal_score": (
                    hotel[
                        "deal_score"
                    ]
                ),

                "estimated_cost": (
                    hotel.get(
                        "total_price"
                    )
                ),

                "currency": (
                    hotel[
                        "currency"
                    ]
                ),

                "why": (
                    "Highest-scoring "
                    "Singapore hotel "
                    "opportunity in the "
                    "current scan."
                ),

                "score_basis": (
                    hotel.get(
                        "score_basis"
                    )
                ),

                "reference_source": (
                    hotel.get(
                        "reference_source"
                    )
                ),

                "is_demo": False,

                "is_evaluation": (
                    hotel.get(
                        "is_evaluation",
                        False,
                    )
                ),
            }
        )

    return ideas


def mark_demo_items(
    items,
):
    for item in items:
        if item.get(
            "is_demo"
        ):
            # Demo records remain visible
            # inside their own Food/Sales
            # tabs, but never appear in
            # Best Deals.
            item[
                "exclude_from_best"
            ] = True

    return items


def main():
    hotels = scan_hotels()
    food = mark_demo_items(
        scan_food()
    )

    sales = mark_demo_items(
        scan_sales()
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

    #
    # Hotels
    #
    # Keep the top hotels available
    # in the Hotels tab even if their
    # score is below 70.
    #

    hotel_items = (
        hotels[:maximum]
    )

    for hotel in hotel_items:
        hotel[
            "exclude_from_best"
        ] = (
            hotel.get(
                "deal_score",
                0,
            )
            < minimum
        )

    #
    # Demo Food/Sales
    #
    # Still useful to preview those
    # tabs, but never rank against
    # live Hotelbeds results.
    #

    food_items = (
        food[:maximum]
    )

    sales_items = (
        sales[:maximum]
    )

    ideas = build_ideas(
        hotels,
        minimum,
    )

    visible = (
        hotel_items
        + food_items
        + sales_items
        + ideas
    )

    visible.sort(
        key=lambda x: x.get(
            "deal_score",
            0,
        ),
        reverse=True,
    )

    history_ready = sum(
        1
        for hotel
        in hotels
        if hotel.get(
            "score_basis"
        ) == "observed_history"
    )

    peer_only = sum(
        1
        for hotel
        in hotels
        if hotel.get(
            "score_basis"
        ) == "peer_comparison"
    )

    write_json(
        "data/hotels.json",
        {
            "updated_at": (
                iso_now_sgt()
            ),

            "provider": (
                "hotelbeds"
            ),

            "environment": (
                "evaluation"
            ),

            "items": hotels,
        },
    )

    write_json(
        "data/food.json",
        {
            "updated_at": (
                iso_now_sgt()
            ),

            "mode": (
                "demo"
                if any(
                    x.get(
                        "is_demo"
                    )
                    for x in food
                )
                else "live"
            ),

            "items": food,
        },
    )

    write_json(
        "data/sales.json",
        {
            "updated_at": (
                iso_now_sgt()
            ),

            "mode": (
                "demo"
                if any(
                    x.get(
                        "is_demo"
                    )
                    for x in sales
                )
                else "live"
            ),

            "items": sales,
        },
    )

    write_json(
        "data/deals.json",
        {
            "updated_at": (
                iso_now_sgt()
            ),

            "demo_mode": (
                False
            ),

            "status": {
                "hotels": (
                    "evaluation"
                ),

                "food": (
                    "demo"
                    if any(
                        x.get(
                            "is_demo"
                        )
                        for x in food
                    )
                    else "live"
                ),

                "sales": (
                    "demo"
                    if any(
                        x.get(
                            "is_demo"
                        )
                        for x in sales
                    )
                    else "live"
                ),
            },

            "stats": {
                "hotel_results": (
                    len(hotels)
                ),

                "history_ready": (
                    history_ready
                ),

                "peer_comparison": (
                    peer_only
                ),

                "best_deals": (
                    sum(
                        1
                        for x
                        in visible
                        if (
                            not x.get(
                                "exclude_from_best",
                                False,
                            )
                            and not x.get(
                                "is_demo",
                                False,
                            )
                        )
                    )
                ),
            },

            "items": visible,
        },
    )

    update_history(
        hotels
    )

    print(
        "Deals Scout updated:"
    )

    print(
        f"  Hotel availability "
        f"results: {len(hotels)}"
    )

    print(
        f"  History-ready hotel "
        f"results: {history_ready}"
    )

    print(
        f"  Peer-comparison hotel "
        f"results: {peer_only}"
    )

    print(
        f"  Dashboard items: "
        f"{len(visible)}"
    )


if __name__ == "__main__":
    main()
