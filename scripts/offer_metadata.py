"""Conservative offer metadata. Unknown validity is never invented."""
import re
import json
from datetime import date
from utils import now_sgt


def offer_identity(item):
    # Do not collapse different meals, locations, card terms or dated offers.
    fields = ("category", "name", "restaurant_name", "location", "url", "booking_url",
              "description", "offer_text", "deal_type", "meal_period", "valid_from",
              "valid_until", "check_in", "check_out", "access_requirement",
              "discount_percent", "current_price", "currency")
    return json.dumps([item.get(k) for k in fields], sort_keys=True, ensure_ascii=False)


def enrich_offer(item):
    text = " ".join(str(item.get(k) or "") for k in ("offer_text", "name", "description"))
    if item.get("discount_percent"):
        if re.search(r"up\s+to", text, re.I) or item.get("price_type") == "time_slot_discount":
            qualifier = "up_to"
        elif re.search(r"1[- ]for[- ]1|buy\s+1\s+get\s+1", text, re.I):
            qualifier = "equivalent"
        else:
            qualifier = "advertised"
        item["discount_qualifier"] = qualifier
    if item.get("category") == "hotel":
        kind = "evaluation_rate" if item.get("is_evaluation") else "dated_rate"
    elif item.get("category") == "idea":
        kind = "inspiration"
    elif re.search(r"all year|year.round|mall.wide|outlet positioning", text, re.I):
        kind = "ongoing_promotion"
    elif item.get("valid_until") or item.get("meal_period") or item.get("deal_type") in {"direct", "card_deal", "membership_deal"}:
        kind = "specific_offer"
    else:
        kind = "promotion_lead"
    item.setdefault("offer_kind", kind)
    item.setdefault("verification_level", "source_observed_terms_unconfirmed")
    return item


def is_expired(item, today=None):
    today = today or now_sgt().date()
    # Hotel dates are stay dates, not an inferred booking expiry.
    value = item.get("valid_until") or item.get("check_in")
    try:
        return date.fromisoformat(value) < today if value else False
    except (TypeError, ValueError):
        return False
