from utils import read_json, write_json, iso_now_sgt
from food_scanner import scan_food
from sales_scanner import scan_sales
from deal_score import curate_best_items


def source_mode(items):
    return "demo" if any(item.get("is_demo") for item in items) else "live"


def main():
    print("=" * 70)
    print("V&V DEALS SCOUT — FOOD + SALES REFRESH ONLY")
    print("NO HOTELBEDS API CALLS WILL BE MADE")
    print("=" * 70)

    current_deals = read_json(
        "data/deals.json",
        {
            "updated_at": None,
            "status": {"hotels": "evaluation"},
            "stats": {},
            "items": [],
        },
    )

    hotels_payload = read_json(
        "data/hotels.json",
        {"updated_at": None, "items": []},
    )

    prefs = read_json("config/preferences.json", {})
    settings = prefs.get("search_settings", {})
    minimum = settings.get("minimum_deal_score", 70)
    maximum = settings.get("maximum_results_per_category", 20)

    food = scan_food()
    sales = scan_sales()

    food_items = food[:maximum]
    sales_items = sales[:maximum]

    # Preserve the last successfully published Hotel/Idea cards exactly as-is.
    # This refresh intentionally does not call Hotelbeds, rewrite hotels.json,
    # or append to hotel price history.
    preserved_items = [
        item
        for item in current_deals.get("items", [])
        if item.get("category") not in {"food", "sale"}
    ]

    visible = preserved_items + food_items + sales_items
    visible.sort(
        key=lambda item: float(item.get("deal_score", 0) or 0),
        reverse=True,
    )

    # Rebuild the Best shortlist across preserved Hotels/Ideas plus fresh Food
    # and Sales. This keeps the front page balanced after a non-hotel refresh.
    best_items = curate_best_items(
        visible,
        minimum_score=minimum,
        total_limit=14,
    )

    hotel_items = hotels_payload.get("items", [])

    history_ready = sum(
        1
        for hotel in hotel_items
        if hotel.get("score_basis") == "observed_history"
    )

    peer_only = sum(
        1
        for hotel in hotel_items
        if hotel.get("score_basis") == "peer_comparison"
    )

    best_deals = len(best_items)
    food_mode = source_mode(food)
    sales_mode = source_mode(sales)
    refresh_time = iso_now_sgt()

    write_json(
        "data/food.json",
        {
            "updated_at": refresh_time,
            "mode": food_mode,
            "items": food,
        },
    )

    write_json(
        "data/sales.json",
        {
            "updated_at": refresh_time,
            "mode": sales_mode,
            "items": sales,
        },
    )

    existing_status = current_deals.get("status", {})
    existing_stats = current_deals.get("stats", {})
    existing_source_times = current_deals.get("source_updated_at", {})

    # Preserve the full-scan timestamp and the Hotel timestamp. Food/Sales get
    # their own fresh timestamp so the dashboard no longer implies that Hotel
    # data was refreshed by this safe workflow.
    full_scan_updated_at = current_deals.get("updated_at")
    hotel_updated_at = (
        existing_source_times.get("hotels")
        or hotels_payload.get("updated_at")
        or full_scan_updated_at
    )

    write_json(
        "data/deals.json",
        {
            "updated_at": full_scan_updated_at,
            "nonhotel_updated_at": refresh_time,
            "refresh_scope": "food_sales_only",
            "source_updated_at": {
                "hotels": hotel_updated_at,
                "food": refresh_time,
                "sales": refresh_time,
            },
            "demo_mode": False,
            "status": {
                "hotels": existing_status.get("hotels", "evaluation"),
                "food": food_mode,
                "sales": sales_mode,
            },
            "stats": {
                "availability_results": existing_stats.get(
                    "availability_results",
                    len(hotel_items),
                ),
                "hotel_results": existing_stats.get(
                    "hotel_results",
                    len(hotel_items),
                ),
                "food_results": len(food_items),
                "sales_results": len(sales_items),
                "live_promos": len(food_items) + len(sales_items),
                "history_ready": existing_stats.get(
                    "history_ready",
                    history_ready,
                ),
                "peer_comparison": existing_stats.get(
                    "peer_comparison",
                    peer_only,
                ),
                "best_deals": best_deals,
                "best_deal_limit": 14,
            },
            "items": visible,
        },
    )

    print()
    print("FOOD + SALES REFRESH COMPLETE")
    print(f"Food live deals:  {len(food_items)}")
    print(f"Sales live deals: {len(sales_items)}")
    print(f"Best shortlist:   {best_deals} / 14 max")
    print(
        "Hotel cards kept: "
        f"{sum(1 for x in preserved_items if x.get('category') == 'hotel')}"
    )
    print("Hotelbeds calls:  0")
    print("Hotel history:    unchanged")


if __name__ == "__main__":
    main()
