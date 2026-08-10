from utils import iso_now_sgt
from deal_score import promo_score


def scan_sales():
    items = [
        {
            "id": "sale-demo-01",
            "category": "sale",
            "name": "Outlet Additional Discount",
            "location": "IMM / Singapore",
            "description": "Illustrative outlet deal used to test the sales section.",
            "discount_percent": 40,
            "quality_score": 8,
            "relevance_score": 8.5,
            "source": "Demo data",
            "url": "",
            "is_demo": True
        },
        {
            "id": "sale-demo-02",
            "category": "sale",
            "name": "Travel & Luggage Sale",
            "location": "Singapore",
            "description": "Illustrative travel-related sale.",
            "discount_percent": 35,
            "quality_score": 7.5,
            "relevance_score": 8,
            "source": "Demo data",
            "url": "",
            "is_demo": True
        }
    ]
    for x in items:
        x["deal_score"] = promo_score(x, "sale")
        x["observed_at"] = iso_now_sgt()
    return items
