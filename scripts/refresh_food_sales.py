from utils import read_json, write_json, iso_now_sgt
from food_scanner import scan_food
from sales_scanner import scan_sales


def source_mode(items):
    return "demo" if any(item.get("is_demo") for item in items) else "live"


def apply_best_rules(items, minimum_score):
    for item in items:
        score = float(item.get("deal_score", 0) or 0)
        item["exclude_from_best"] = bool(item.get("is_demo", False)) or score < minimum_score
    return items


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

    apply_best_rules(food_items, minimum)
    apply_best_rules(sales_items, minimum)

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

    best_deals = sum(
        1
        for item in visible
        if (
            not item.get("exclude_from_best", False)
            and not item.get("is_demo", False)
        )
    )

    food_mode = source_mode(food)
    sales_mode = source_mode(sales)

    write_json(
        "data/food.json",
        {
            "updated_at": iso_now_sgt(),
            "mode": food_mode,
            "items": food,
        },
    )

    write_json(
        "data/sales.json",
        {
            "updated_at": iso_now_sgt(),
            "mode": sales_mode,
            "items": sales,
        },
    )

    existing_status = current_deals.get("status", {})
    existing_stats = current_deals.get("stats", {})

    # Preserve updated_at from the last full scan so the dashboard does not
    # imply that Hotelbeds was refreshed by this Food/Sales-only operation.
    full_scan_updated_at = current_deals.get("updated_at")

    write_json(
        "data/deals.json",
        {
            "updated_at": full_scan_updated_at,
            "nonhotel_updated_at": iso_now_sgt(),
            "refresh_scope": "food_sales_only",
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
            },
            "items": visible,
        },
    )

    print()
    print("FOOD + SALES REFRESH COMPLETE")
    print(f"Food live deals:  {len(food_items)}")
    print(f"Sales live deals: {len(sales_items)}")
    print(f"Best deals:       {best_deals}")
    print(f"Hotel cards kept: {sum(1 for x in preserved_items if x.get('category') == 'hotel')}")
    print("Hotelbeds calls:  0")
    print("Hotel history:    unchanged")


if __name__ == "__main__":
    main()
