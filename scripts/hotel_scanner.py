from datetime import timedelta
from utils import read_json, iso_now_sgt, now_sgt
from deal_score import hotel_score


def _demo_hotels():
    """
    Demo observations used until a permitted live hotel pricing provider
    is connected. Prices here are illustrative only.
    """
    today = now_sgt().date()
    return [
        {
            "id": "hotel-pan-pacific-sg-01",
            "category": "hotel",
            "sub_category": "staycation",
            "name": "Pan Pacific Singapore",
            "destination": "Singapore",
            "check_in": str(today + timedelta(days=12)),
            "check_out": str(today + timedelta(days=13)),
            "nights": 1,
            "stars": 5,
            "current_price": 368,
            "historical_median": 478,
            "currency": "SGD",
            "breakfast": True,
            "lounge": False,
            "bathtub": True,
            "quiet_relaxing": True,
            "couples_friendly": True,
            "good_location": True,
            "flexible_cancellation": True,
            "convenient_date": True,
            "booking_url": "",
            "source": "Demo data",
            "is_demo": True
        },
        {
            "id": "hotel-eo-penang-01",
            "category": "hotel",
            "sub_category": "regional",
            "name": "Eastern & Oriental Hotel",
            "destination": "Penang",
            "check_in": str(today + timedelta(days=25)),
            "check_out": str(today + timedelta(days=28)),
            "nights": 3,
            "stars": 5,
            "current_price": 245,
            "historical_median": 335,
            "currency": "SGD",
            "breakfast": True,
            "lounge": False,
            "bathtub": True,
            "quiet_relaxing": True,
            "couples_friendly": True,
            "good_location": True,
            "flexible_cancellation": True,
            "convenient_date": True,
            "booking_url": "",
            "source": "Demo data",
            "is_demo": True
        },
        {
            "id": "hotel-ruma-kl-01",
            "category": "hotel",
            "sub_category": "regional",
            "name": "The RuMa Hotel and Residences",
            "destination": "Kuala Lumpur",
            "check_in": str(today + timedelta(days=18)),
            "check_out": str(today + timedelta(days=20)),
            "nights": 2,
            "stars": 5,
            "current_price": 285,
            "historical_median": 345,
            "currency": "SGD",
            "breakfast": True,
            "lounge": False,
            "bathtub": True,
            "quiet_relaxing": True,
            "couples_friendly": True,
            "good_location": True,
            "flexible_cancellation": True,
            "convenient_date": True,
            "booking_url": "",
            "source": "Demo data",
            "is_demo": True
        }
    ]


def scan_hotels():
    cfg = read_json("config/hotels.json", {})
    mode = cfg.get("provider_mode", "demo")

    # Provider abstraction point:
    # Replace/add provider-specific logic here when live API credentials exist.
    if mode == "demo":
        hotels = _demo_hotels()
    else:
        hotels = []

    for h in hotels:
        h["deal_score"] = hotel_score(h)
        h["observed_at"] = iso_now_sgt()

    return hotels
