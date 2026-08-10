from utils import read_json, write_json, iso_now_sgt
from hotel_scanner import scan_hotels
from food_scanner import scan_food
from sales_scanner import scan_sales


def update_history(hotels):
    history = read_json("data/history.json", {"observations": []})
    observations = history.setdefault("observations", [])

    for h in hotels:
        observations.append({
            "id": h.get("id"),
            "name": h.get("name"),
            "destination": h.get("destination"),
            "check_in": h.get("check_in"),
            "check_out": h.get("check_out"),
            "price": h.get("current_price"),
            "currency": h.get("currency", "SGD"),
            "observed_at": h.get("observed_at"),
            "is_demo": h.get("is_demo", False)
        })

    # Keep recent history compact.
    history["observations"] = observations[-3000:]
    history["updated_at"] = iso_now_sgt()
    write_json("data/history.json", history)


def build_ideas(hotels, food, sales):
    ideas = []
    regional = [h for h in hotels if h.get("sub_category") == "regional"]
    staycations = [h for h in hotels if h.get("sub_category") == "staycation"]

    if regional:
        h = sorted(regional, key=lambda x: x.get("deal_score", 0), reverse=True)[0]
        ideas.append({
            "id": "idea-regional-01",
            "category": "idea",
            "name": f"{h['destination']} getaway",
            "description": f"{h['nights']}-night stay at {h['name']}",
            "deal_score": h["deal_score"],
            "estimated_cost": round(h["current_price"] * h["nights"], 2),
            "currency": h["currency"],
            "why": "Strong hotel value compared with its observed reference price.",
            "is_demo": h.get("is_demo", False)
        })

    if staycations:
        h = sorted(staycations, key=lambda x: x.get("deal_score", 0), reverse=True)[0]
        ideas.append({
            "id": "idea-staycation-01",
            "category": "idea",
            "name": "Singapore staycation",
            "description": f"{h['name']} — {h['nights']} night",
            "deal_score": h["deal_score"],
            "estimated_cost": round(h["current_price"] * h["nights"], 2),
            "currency": h["currency"],
            "why": "High-scoring local couple getaway.",
            "is_demo": h.get("is_demo", False)
        })

    return ideas


def main():
    hotels = scan_hotels()
    food = scan_food()
    sales = scan_sales()
    ideas = build_ideas(hotels, food, sales)

    prefs = read_json("config/preferences.json", {})
    minimum = prefs.get("search_settings", {}).get("minimum_deal_score", 70)

    all_deals = hotels + food + sales + ideas
    visible = [d for d in all_deals if d.get("deal_score", 0) >= minimum]
    visible.sort(key=lambda d: d.get("deal_score", 0), reverse=True)

    write_json("data/hotels.json", {"updated_at": iso_now_sgt(), "items": hotels})
    write_json("data/food.json", {"updated_at": iso_now_sgt(), "items": food})
    write_json("data/sales.json", {"updated_at": iso_now_sgt(), "items": sales})
    write_json("data/deals.json", {
        "updated_at": iso_now_sgt(),
        "demo_mode": any(d.get("is_demo") for d in all_deals),
        "items": visible
    })

    update_history(hotels)
    print(f"Deals Scout updated: {len(visible)} visible deals")


if __name__ == "__main__":
    main()
