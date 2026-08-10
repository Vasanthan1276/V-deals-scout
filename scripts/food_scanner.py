from utils import iso_now_sgt
from deal_score import promo_score


def scan_food():
    """
    V1 uses curated demo entries to validate the dashboard and scoring.
    A permitted promotion parser/API can replace this list later without
    changing the dashboard.
    """
    items = [
        {
            "id": "food-demo-01",
            "category": "food",
            "name": "Hotel Sunday Brunch Promotion",
            "location": "Singapore",
            "description": "Illustrative dining offer used to test the dashboard.",
            "discount_percent": 30,
            "quality_score": 8.5,
            "relevance_score": 9,
            "source": "Demo data",
            "url": "",
            "is_demo": True
        },
        {
            "id": "food-demo-02",
            "category": "food",
            "name": "1-for-1 Dinner Idea",
            "location": "Singapore",
            "description": "Illustrative couple dining offer.",
            "discount_percent": 50,
            "quality_score": 8,
            "relevance_score": 9.5,
            "source": "Demo data",
            "url": "",
            "is_demo": True
        }
    ]
    for x in items:
        x["deal_score"] = promo_score(x, "food")
        x["observed_at"] = iso_now_sgt()
    return items
