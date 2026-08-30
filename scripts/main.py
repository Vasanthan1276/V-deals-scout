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


from deal_score import (
    curate_best_items,
)


def update_history(hotels):
    history = read_json(
        "data/history.json",
        {
            "observations": []
        },
    )

    observations = history.setdefault(
        "observations",
        [],
    )

    for hotel in hotels:
        observations.append(
            {
                "id": hotel.get("id"),
                "provider": hotel.get("provider"),
                "hotelbeds_code": hotel.get("hotelbeds_code"),
                "name": hotel.get("name"),
                "destination": hotel.get("destination"),
                "check_in": hotel.get("check_in"),
                "check_out": hotel.get("check_out"),
                "nights": hotel.get("nights"),
                "price": hotel.get("current_price"),
                "total_price": hotel.get("total_price"),
                "currency": hotel.get(
                    "currency",
                    "SGD",
                ),
                "score_basis": hotel.get("score_basis"),
                "reference_source": hotel.get("reference_source"),
                "price_type": hotel.get("price_type"),
                "observed_at": hotel.get("observed_at"),
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

    history["observations"] = observations[-5000:]
    history["updated_at"] = iso_now_sgt()

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
        for hotel in hotels
        if hotel.get(
            "deal_score",
            0,
        ) >= minimum_score
    ]

    regional = [
        hotel
        for hotel in eligible
        if hotel.get("sub_category") == "regional"
    ]

    staycations = [
        hotel
        for hotel in eligible
        if hotel.get("sub_category") == "staycation"
    ]

    if regional:
        hotel = regional[0]

        ideas.append(
            {
                "id": "idea-regional-01",
                "category": "idea",
                "name": f"{hotel['destination']} getaway",
                "description": (
                    f"{hotel['nights']}-night stay at "
                    f"{hotel['name']}"
                ),
                "deal_score": hotel["deal_score"],
                "estimated_cost": hotel.get("total_price"),
                "currency": hotel["currency"],
                "why": (
                    "Highest-scoring regional hotel "
                    "opportunity in the current scan."
                ),
                "score_basis": hotel.get("score_basis"),
                "reference_source": hotel.get("reference_source"),
                "is_demo": False,
                "is_evaluation": hotel.get(
                    "is_evaluation",
                    False,
                ),
            }
        )

    if staycations:
        hotel = staycations[0]

        ideas.append(
            {
                "id": "idea-staycation-01",
                "category": "idea",
                "name": "Singapore staycation",
                "description": (
                    f"{hotel['name']} — "
                    f"{hotel['nights']} night"
                ),
                "deal_score": hotel["deal_score"],
                "estimated_cost": hotel.get("total_price"),
                "currency": hotel["currency"],
                "why": (
                    "Highest-scoring Singapore hotel "
                    "opportunity in the current scan."
                ),
                "score_basis": hotel.get("score_basis"),
                "reference_source": hotel.get("reference_source"),
                "is_demo": False,
                "is_evaluation": hotel.get(
                    "is_evaluation",
                    False,
                ),
            }
        )

    return ideas


def source_mode(items):
    """
    Report whether a category still contains demo content.

    An empty live scan is still a live source; it simply means there were no
    qualifying deals in that scan.
    """
    return (
        "demo"
        if any(
            item.get("is_demo")
            for item in items
        )
        else "live"
    )


def main():
    #
    # IMPORTANT HOTELBEDS INTEGRITY RULE:
    #
    # scan_hotels() runs BEFORE any JSON output is written.
    #
    # If Hotelbeds is incomplete, quota-limited, or errors out,
    # hotel_scanner.py raises here. The program exits and the previous
    # published data remains intact.
    #
    # Do not catch that exception here until the fresh-quota Hotelbeds
    # integrity validation has been completed.
    #
    hotels = scan_hotels()

    # Food and Sales are live/beta scanners and do not call Hotelbeds.
    food = scan_food()
    sales = scan_sales()

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

    # Food and Sales now have useful sub-filters and multiple source families,
    # so keep a larger browseable pool while preserving the existing Hotel cap.
    food_maximum = settings.get("maximum_food_results", 30)
    sales_maximum = settings.get("maximum_sales_results", 30)

    hotel_items = hotels[:maximum]
    food_items = food[:food_maximum]
    sales_items = sales[:sales_maximum]

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
        key=lambda item: float(
            item.get("deal_score", 0) or 0
        ),
        reverse=True,
    )

    # Best is a curated front-page shortlist, not every item over threshold.
    # Default balance: up to 3 Hotels, 5 Food, 5 Sales and 1 Idea.
    best_items = curate_best_items(
        visible,
        minimum_score=minimum,
        total_limit=14,
    )

    history_ready = sum(
        1
        for hotel in hotels
        if hotel.get("score_basis") == "observed_history"
    )

    peer_only = sum(
        1
        for hotel in hotels
        if hotel.get("score_basis") == "peer_comparison"
    )

    best_deals = len(best_items)
    food_mode = source_mode(food)
    sales_mode = source_mode(sales)
    food_source_types = len({item.get("deal_type", "other") for item in food_items})
    sales_source_types = len({item.get("deal_type", "other") for item in sales_items})
    indian_food_deals = sum(1 for item in food_items if item.get("food_category") == "indian")
    scan_time = iso_now_sgt()

    write_json(
        "data/hotels.json",
        {
            "updated_at": scan_time,
            "provider": "hotelbeds",
            "environment": "evaluation",
            "availability_results": len(hotels),
            "items": hotels,
        },
    )

    write_json(
        "data/food.json",
        {
            "updated_at": scan_time,
            "mode": food_mode,
            "items": food,
        },
    )

    write_json(
        "data/sales.json",
        {
            "updated_at": scan_time,
            "mode": sales_mode,
            "items": sales,
        },
    )

    write_json(
        "data/deals.json",
        {
            "updated_at": scan_time,
            "nonhotel_updated_at": scan_time,
            "refresh_scope": "full",
            "source_updated_at": {
                "hotels": scan_time,
                "food": scan_time,
                "sales": scan_time,
            },
            "demo_mode": False,
            "status": {
                "hotels": "evaluation",
                "food": food_mode,
                "sales": sales_mode,
            },
            "stats": {
                "availability_results": len(hotels),

                # Retained for compatibility with older app.js versions.
                "hotel_results": len(hotels),

                "food_results": len(food_items),
                "sales_results": len(sales_items),
                "food_source_types": food_source_types,
                "sales_source_types": sales_source_types,
                "indian_food_deals": indian_food_deals,
                "live_promos": len(food_items) + len(sales_items),
                "history_ready": history_ready,
                "peer_comparison": peer_only,
                "best_deals": best_deals,
                "best_deal_limit": 14,
            },
            "items": visible,
        },
    )

    update_history(hotels)

    print()
    print("=" * 70)
    print("V&V DEALS SCOUT UPDATE COMPLETE")
    print("=" * 70)
    print(f"Hotel availability: {len(hotels)}")
    print(f"Food live deals:     {len(food_items)} across {food_source_types} deal types")
    print(f"Indian food deals:   {indian_food_deals}")
    print(f"Sales live deals:    {len(sales_items)} across {sales_source_types} deal types")
    print(f"History-ready:       {history_ready}")
    print(f"Peer-comparison:      {peer_only}")
    print(f"Best shortlist:       {best_deals} / 14 max")
    print(f"Dashboard items:      {len(visible)}")


if __name__ == "__main__":
    main()
