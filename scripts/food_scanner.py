from __future__ import annotations

import hashlib
import html
import json
import os
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from utils import iso_now_sgt
from deal_score import promo_score


# ---------------------------------------------------------------------------
# V&V Deals Scout - Multi-source Food Scanner V3
#
# Sources:
#   1. Eatigo Singapore live time-slot promotions (app-based)
#   2. DBS/POSB and Visa official dining promotions
#   3. American Express dining / Love Dining partners
#   4. Direct restaurant and hotel promotion pages
#   5. Eatbook monthly deal roundup (discovery only; requires verification)
#
# V3 expands Indian dining coverage with Nalan, Gupshup, Maharani Table,
# Our Village Curry Hut, Chinatown Teh Tarik, Maharani Heritage and ammākase.
#
# Indian cuisine is a user preference. Indian deals are allowed through at a
# lower discount floor, are tagged as preferred, and are kept visible in the
# published Food list even when their headline discount is smaller than the
# strongest Eatigo slots.
#
# This scanner NEVER calls Hotelbeds.
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/152.0.0.0 Safari/537.36"
)

SGT = ZoneInfo("Asia/Singapore")
DEFAULT_TIMEOUT = 20
DEFAULT_MIN_DISCOUNT = 15
DEFAULT_MAX_ITEMS = 30
INDIAN_MIN_DISCOUNT = 5
MAX_PAGE_BYTES = 3_000_000

REPO_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_FOOD_PATH = REPO_ROOT / "data" / "food.json"

EATIGO_SOURCES = [
    {
        "name": "Eatigo Singapore - Dinner",
        "url": "https://eatigo.com/en/regions/27/themes/15504",
        "meal_period": "dinner",
        "window_start": "17:30",
        "window_end": "21:30",
    },
    {
        "name": "Eatigo Singapore - Lunch",
        "url": "https://eatigo.com/en/regions/27/themes/15505",
        "meal_period": "lunch",
        "window_start": "11:00",
        "window_end": "14:30",
    },
]

# Broad official index pages. Their visible text contains merchant + offer rows,
# which the generic parser reads conservatively.
OFFICIAL_INDEX_SOURCES = [
    {
        "name": "DBS/POSB Dining",
        "url": "https://www.dbs.com.sg/personal/promotion/cards-wonderful-dining",
        "source": "DBS/POSB Dining",
        "deal_type": "card_deal",
        "source_confidence": "verified",
        "access_requirement": "DBS/POSB card required",
        "location": "Singapore",
        "max_results": 10,
    },
    {
        "name": "American Express Dining",
        "url": "https://www.americanexpress.com/en-sg/benefits/promotions/dining/",
        "source": "American Express Dining",
        "deal_type": "card_deal",
        "source_confidence": "verified",
        "access_requirement": "Eligible American Express card required",
        "location": "Singapore",
        "max_results": 8,
    },
]

# Dedicated official pages for sources we especially want to keep in view.
# Nalan is included explicitly because Indian food is a user preference.
OFFICIAL_SINGLE_SOURCES = [
    {
        "name": "Nalan Restaurant - DBS/POSB",
        "url": "https://www.dbs.com.sg/personal/promotion/card-privileges-ylnalan",
        "merchant": "Nalan Restaurant @ Capitol Singapore",
        "source": "DBS/POSB Dining",
        "deal_type": "card_deal",
        "source_confidence": "verified",
        "access_requirement": "DBS/POSB card required",
        "location": "Capitol Singapore",
        "food_category": "indian",
        "min_discount": INDIAN_MIN_DISCOUNT,
        "offer_text_override": "10% off total bill",
        "required_terms": ["Nalan Restaurant", "10% off total bill"],
    },
    {
        "name": "Gupshup - Amex Love Dining",
        "url": "https://www.americanexpress.com/sg/benefits/love-dining/love-restaurants.html",
        "merchant": "Gupshup @ The Serangoon House",
        "source": "American Express Love Dining",
        "deal_type": "membership_deal",
        "source_confidence": "verified",
        "access_requirement": "Eligible American Express Love Dining card required; advance reservation required",
        "location": "The Serangoon House, Little India",
        "food_category": "indian",
        "min_discount": INDIAN_MIN_DISCOUNT,
        "offer_text_override": "Up to 50% off total food bill with Love Dining privileges",
        "required_terms": ["Gupshup", "Cuisine: Indian", "up to 50%"],
    },
    {
        "name": "Maharani Table - Visa Dine & Save",
        "url": "https://dineandsave.visa.com/outlets/maharani-table/",
        "merchant": "Maharani Table",
        "source": "Visa Dine & Save",
        "deal_type": "card_deal",
        "source_confidence": "verified",
        "access_requirement": "Eligible Visa card required; quote Dine and Save with Visa",
        "location": "Boat Quay",
        "food_category": "indian",
        "min_discount": INDIAN_MIN_DISCOUNT,
        "offer_text_override": "20% off food bill",
        "required_terms": ["Maharani Table", "20% off on Food Bill"],
    },
    {
        "name": "Our Village Curry Hut - Visa Dine & Save",
        "url": "https://dineandsave.visa.com/outlets/our-village-curry-hut/",
        "merchant": "Our Village Curry Hut",
        "source": "Visa Dine & Save",
        "deal_type": "card_deal",
        "source_confidence": "verified",
        "access_requirement": "Eligible Visa card required; quote Dine and Save with Visa",
        "location": "Boat Quay",
        "food_category": "indian",
        "min_discount": INDIAN_MIN_DISCOUNT,
        "offer_text_override": "20% off food bill",
        "required_terms": ["Our Village Curry Hut", "20% off on Food Bill"],
    },
    {
        "name": "Chinatown Teh Tarik - Visa Dine & Save",
        "url": "https://dineandsave.visa.com/outlets/chinatown-teh-tarik/",
        "merchant": "Chinatown Teh Tarik",
        "source": "Visa Dine & Save",
        "deal_type": "card_deal",
        "source_confidence": "verified",
        "access_requirement": "Eligible Visa card required; quote Dine and Save with Visa",
        "location": "Chinatown",
        "food_category": "indian",
        "min_discount": INDIAN_MIN_DISCOUNT,
        "offer_text_override": "20% off food bill",
        "required_terms": ["Chinatown Teh Tarik", "20% off on Food Bill"],
    },
    {
        "name": "Maharani Heritage direct promotion",
        "url": "https://www.maharaniheritage.com/",
        "merchant": "Maharani Heritage",
        "source": "Maharani Heritage",
        "deal_type": "direct",
        "source_confidence": "verified",
        "access_requirement": "Online reservation required for advertised opening promotion",
        "location": "Singapore",
        "food_category": "indian",
        "min_discount": INDIAN_MIN_DISCOUNT,
        "offer_text_override": "20% off dining menu for online reservations Monday to Thursday; 10% Friday to Sunday",
        "required_terms": ["Opening Promotion", "20% OFF", "Monday"],
    },
    {
        "name": "ammakase weekday dinner promotion",
        "url": "https://www.ammakase.com/promo-now",
        "merchant": "ammakase",
        "source": "ammakase",
        "deal_type": "direct",
        "source_confidence": "verified",
        "access_requirement": "Direct reservation required; Wednesday/Thursday 10-course promotion",
        "location": "Singapore",
        "food_category": "indian",
        "min_discount": INDIAN_MIN_DISCOUNT,
        "offer_text_override": "1-for-1 10-course experience on Wednesdays and Thursdays",
        "required_terms": ["1-for-1", "10-course", "Wednesday"],
    },
    {
        "name": "Seasonal Tastes - DBS/POSB",
        "url": "https://www.dbs.com.sg/personal/promotion/card-privileges-seasonaltastes",
        "merchant": "Seasonal Tastes @ The Westin Singapore",
        "source": "DBS/POSB Dining",
        "deal_type": "card_deal",
        "source_confidence": "verified",
        "access_requirement": "DBS/POSB card required",
        "location": "The Westin Singapore",
        "food_category": "hotel_dining",
    },
    {
        "name": "Atrium Restaurant - DBS/POSB",
        "url": "https://www.dbs.com.sg/personal/promotion/card-privileges-hisaatrium",
        "merchant": "Atrium Restaurant @ Holiday Inn Singapore Atrium",
        "source": "DBS/POSB Dining",
        "deal_type": "card_deal",
        "source_confidence": "verified",
        "access_requirement": "DBS/POSB card required",
        "location": "Holiday Inn Singapore Atrium",
        "food_category": "hotel_dining",
    },
    {
        "name": "Royale - DBS/POSB",
        "url": "https://www.dbs.com.sg/personal/promotion/card-privileges-royale",
        "merchant": "Royale @ Mercure Singapore Bugis",
        "source": "DBS/POSB Dining",
        "deal_type": "card_deal",
        "source_confidence": "verified",
        "access_requirement": "DBS/POSB card required",
        "location": "Mercure Singapore Bugis",
        "food_category": "hotel_dining",
    },
    {
        "name": "Cook & Brew - American Express",
        "url": "https://www.americanexpress.com/en-sg/benefits/promotions/dining/cook-and-brew/",
        "merchant": "Cook & Brew @ The Westin Singapore",
        "source": "American Express Dining",
        "deal_type": "card_deal",
        "source_confidence": "verified",
        "access_requirement": "Eligible American Express card required",
        "location": "The Westin Singapore",
        "food_category": "hotel_dining",
    },
    {
        "name": "Ginger direct dining page",
        "url": "https://www.panpacific.com/en/hotels-and-resorts/pr-beach-road/eat/ginger.html",
        "merchant": "Ginger @ PARKROYAL on Beach Road",
        "source": "PARKROYAL on Beach Road",
        "deal_type": "direct",
        "source_confidence": "verified",
        "access_requirement": "Direct hotel offer",
        "location": "PARKROYAL on Beach Road",
        "food_category": "hotel_dining",
    },
    {
        "name": "Crossroads Buffet direct promotion",
        "url": "https://www.crossroadssg.com/",
        "merchant": "Crossroads Buffet @ Singapore Marriott Tang Plaza Hotel",
        "source": "Singapore Marriott Tang Plaza Hotel",
        "deal_type": "direct",
        "source_confidence": "verified",
        "access_requirement": "Quote CR20OFF when reserving; blackout dates apply",
        "location": "Singapore Marriott Tang Plaza Hotel",
        "food_category": "hotel_dining",
        "offer_text_override": "20% off adult buffet price from 6 July to 30 September 2026",
        "required_terms": ["20% off", "CR20OFF", "30 September 2026"],
    },
    {
        "name": "Estate direct dining page",
        "url": "https://www.hilton.com/en/hotels/sinorhi-hilton-singapore-orchard/dining/estate/",
        "merchant": "Estate @ Hilton Singapore Orchard",
        "source": "Hilton Singapore Orchard",
        "deal_type": "membership_deal",
        "source_confidence": "verified",
        "access_requirement": "Hilton Honors membership tier may be required",
        "location": "Hilton Singapore Orchard",
        "food_category": "hotel_dining",
    },
]

FOOD_CATEGORY_RULES = [
    (
        "indian",
        (
            "indian", "nalan", "biryani", "briyani", "tandoor", "tandoori",
            "masala", "dosa", "dosai", "naan", "prata", "roti", "thali",
            "punjabi", "chettinad", "mughlai", "hyderabadi", "banana leaf",
            "north indian", "south indian", "curry",
        ),
    ),
    (
        "japanese",
        (
            "japanese", "sushi", "sashimi", "yakitori", "ramen", "izakaya",
            "tempura", "omakase", "teppan", "yakiniku", "udon", "soba",
        ),
    ),
    (
        "korean",
        (
            "korean", "seorae", "kimchi", "jjigae", "samgyeopsal", "k-bbq",
            "k bbq",
        ),
    ),
    (
        "chinese_hotpot",
        (
            "chinese", "hot pot", "hotpot", "sichuan", "szechuan", "mala",
            "dim sum", "cantonese", "grilled fish", "wok", "hunan", "haidilao",
        ),
    ),
    (
        "southeast_asian",
        (
            "thai", "vietnamese", "pho", "peranakan", "nyonya", "indonesian",
            "malay", "nasi", "laksa", "ayam",
        ),
    ),
    (
        "western_international",
        (
            "italian", "pizza", "pasta", "steak", "steakhouse", "bistro",
            "french", "mediterranean", "spanish", "tapas", "mexican", "burger",
            "western", "grill", "international",
        ),
    ),
    (
        "cafe_casual",
        ("cafe", "café", "bakery", "coffee", "dessert", "patisserie"),
    ),
]

HOTEL_DINING_WORDS = (
    "hotel", "marriott", "shangri-la", "shangri la", "pan pacific", "fullerton",
    "dusit", "jen singapore", "grand pacific", "holiday inn", "copthorne",
    "mercure", "novotel", "hilton", "conrad", "intercontinental", "parkroyal",
    "raffles", "westin", "fairmont", "mandarin oriental",
)

DATE_NIGHT_WORDS = (
    "hotel", "marriott", "shangri-la", "pan pacific", "copthorne", "holiday inn",
    "paradox", "dusit", "buffet", "terrace", "atrium", "mosella", "westin",
    "hilton", "fairmont",
)

GENERIC_MERCHANT_WORDS = {
    "learn more", "view all", "dining promotions", "food and groceries", "at a glance",
    "savings for every dining moment", "popular dining deals", "hotel buffet deals",
    "exclusive 1-for-1 dining deals", "offer detail", "terms and conditions",
    "promotion period", "validity", "book now", "reserve here", "image",
}

IGNORE_NAME_LINES = {
    "hot", "new", "more", "recommended", "today", "tomorrow", "all", "price",
    "discount", "rating", "party size", "now", "date", "time",
}


class TextExtractor(HTMLParser):
    BLOCK_TAGS = {
        "article", "aside", "blockquote", "br", "div", "footer", "h1", "h2", "h3",
        "h4", "h5", "h6", "header", "li", "main", "p", "section", "table", "td",
        "th", "tr", "ul",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden_depth += 1
        elif self.hidden_depth == 0 and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden_depth = max(0, self.hidden_depth - 1)
        elif self.hidden_depth == 0 and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.hidden_depth == 0 and data:
            self.parts.append(" " + data + " ")

    def get_text(self):
        return "".join(self.parts)


def env_int(name, default, minimum, maximum):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        print(f"Food scanner: invalid {name}={raw!r}; using {default}.")
        return default
    return max(minimum, min(maximum, value))


def fetch_html(url, timeout):
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-SG,en;q=0.9",
            "Cache-Control": "no-cache",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        if status != 200:
            raise RuntimeError(f"Unexpected HTTP status {status}")
        payload = response.read(MAX_PAGE_BYTES + 1)
        if len(payload) > MAX_PAGE_BYTES:
            raise RuntimeError("Source page exceeded safe size limit")
        return payload.decode("utf-8", errors="replace")


def html_to_lines(raw_html):
    parser = TextExtractor()
    parser.feed(raw_html)
    parser.close()
    text = html.unescape(parser.get_text()).replace("\xa0", " ")
    lines = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if line:
            lines.append(line)
    return lines


def clean_name(value):
    value = re.sub(r"\s+", " ", value or "").strip(" -|•·")
    value = re.sub(r"\s+(?:HOT|NEW)$", "", value, flags=re.IGNORECASE).strip()
    return value


def plausible_name(value):
    if not value or len(value) < 3 or len(value) > 140:
        return False
    if value.casefold() in IGNORE_NAME_LINES or value.casefold() in GENERIC_MERCHANT_WORDS:
        return False
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?%?", value):
        return False
    if re.fullmatch(r"\d{1,2}:\d{2}", value):
        return False
    return any(char.isalpha() for char in value)


def stable_id(prefix, source, name, extra=""):
    value = f"{prefix}|{source}|{name.casefold()}|{extra}".encode("utf-8")
    return f"food-{prefix}-" + hashlib.sha1(value).hexdigest()[:12]


def infer_food_category(text):
    lowered = clean_name(text).casefold()
    for category, keywords in FOOD_CATEGORY_RULES:
        if any(keyword in lowered for keyword in keywords):
            return category
    if any(keyword in lowered for keyword in HOTEL_DINING_WORDS):
        return "hotel_dining"
    return "other_dining"


def extract_discount_equivalent(text):
    """Return an approximate two-person equivalent saving percentage."""
    lowered = clean_name(text).casefold()
    values = []

    if re.search(r"\b1\s*[- ]?for\s*[- ]?1\b", lowered):
        values.append(50)
    if re.search(r"\bdine\s*4\s*pay\s*3\b", lowered):
        values.append(25)
    if re.search(r"\b4\s*(?:dine|diners?)\s*(?:pay|for)\s*3\b", lowered):
        values.append(25)

    for value in re.findall(r"(?<!\d)(\d{1,3})\s*%\s*(?:off|savings?|discount)?", lowered):
        number = int(value)
        if 0 < number <= 100:
            values.append(number)

    # 50% off the second diner is effectively 25% across two equal-price diners.
    second_diner = re.search(r"(\d{1,3})\s*%\s*off[^.]{0,35}(?:2nd|second)\s+diner", lowered)
    if second_diner:
        values.append(round(int(second_diner.group(1)) / 2))

    # Dollar-off with explicit minimum spend.
    dollar = re.search(r"(?:s\$|\$)\s*(\d+(?:\.\d+)?)\s*off[^.]{0,80}min(?:imum)?\.?\s*spend(?:\s+of)?\s*(?:s\$|\$)\s*(\d+(?:\.\d+)?)", lowered)
    if dollar:
        amount = float(dollar.group(1))
        minimum = float(dollar.group(2))
        if minimum > 0:
            values.append(round(amount / minimum * 100))

    return max(values) if values else 0


def deal_signal(text):
    lowered = text.casefold()
    return (
        "% off" in lowered
        or "% savings" in lowered
        or "% discount" in lowered
        or "1-for-1" in lowered
        or "1 for 1" in lowered
        or "dine 4 pay 3" in lowered
        or re.search(r"s\$\s*\d+\s*off", lowered) is not None
    )


def find_previous_merchant(lines, index):
    for offset in range(1, 6):
        pos = index - offset
        if pos < 0:
            break
        candidate = clean_name(lines[pos])
        lowered = candidate.casefold()
        if not plausible_name(candidate):
            continue
        if deal_signal(candidate):
            continue
        if any(token in lowered for token in ("promotion period", "terms", "validity", "from now", "click here")):
            continue
        return candidate
    return ""


def food_relevance(name, category, discount, deal_type, rating=None):
    score = 7.0
    lowered = name.casefold()

    if category == "indian":
        score += 1.8
    if deal_type == "direct":
        score += 0.6
    elif deal_type in {"card_deal", "membership_deal"}:
        score += 0.35
    elif deal_type == "app_deal":
        score += 0.15

    if any(word in lowered for word in DATE_NIGHT_WORDS):
        score += 0.5
    if rating is not None:
        if rating >= 4.5:
            score += 0.5
        elif rating >= 4.2:
            score += 0.25
    if discount >= 50:
        score += 0.5
    elif discount >= 30:
        score += 0.25

    return round(min(score, 10.0), 1)


def quality_for_source(source_confidence, rating=None):
    if rating is not None:
        return round(min(10.0, rating * 2.0), 1)
    return {
        "verified": 8.8,
        "app_live": 8.4,
        "discovered": 7.4,
    }.get(source_confidence, 7.5)


def build_generic_food_item(source, merchant, offer_text, min_discount):
    combined = f"{merchant} {offer_text}"
    category = source.get("food_category") or infer_food_category(combined)
    floor = source.get("min_discount", min_discount)
    if category == "indian":
        floor = min(floor, INDIAN_MIN_DISCOUNT)

    discount = extract_discount_equivalent(offer_text)
    if discount < floor:
        return None

    deal_type = source.get("deal_type", "card_deal")
    confidence = source.get("source_confidence", "verified")
    access = source.get("access_requirement", "Check source terms")

    description = (
        f"{offer_text}. Source: {source.get('source', source['name'])}. "
        f"{access}. Verify current dates, blackout periods and booking conditions before dining."
    )

    return {
        "id": stable_id("multi", source.get("source", source["name"]), merchant, offer_text),
        "category": "food",
        "name": merchant,
        "restaurant_name": merchant,
        "location": source.get("location", "Singapore"),
        "description": description,
        "discount_percent": discount,
        "quality_score": quality_for_source(confidence),
        "relevance_score": food_relevance(merchant, category, discount, deal_type),
        "food_category": category,
        "food_category_inferred": source.get("food_category") is None,
        "deal_type": deal_type,
        "source": source.get("source", source["name"]),
        "source_detail": source["name"],
        "source_type": "official_promotion_page" if confidence == "verified" else "promotion_aggregator",
        "source_confidence": confidence,
        "access_requirement": access,
        "reference_source": source["url"],
        "url": source["url"],
        "verification_required": True,
        "is_demo": False,
        "is_live": True,
        "price_type": "advertised_promotion",
        "preferred_cuisine": category == "indian",
        "preference_priority": 1 if category == "indian" else 0,
    }


def parse_index_source(source, raw_html, min_discount):
    lines = html_to_lines(raw_html)
    items = []
    seen = set()

    for index, line in enumerate(lines):
        if not deal_signal(line):
            continue
        merchant = find_previous_merchant(lines, index)
        if not merchant:
            continue

        key = (merchant.casefold(), clean_name(line).casefold())
        if key in seen:
            continue
        seen.add(key)

        item = build_generic_food_item(source, merchant, clean_name(line), min_discount)
        if item:
            items.append(item)

    items.sort(key=lambda row: (row["discount_percent"], row["relevance_score"]), reverse=True)
    return items[: source.get("max_results", 10)]


def parse_single_source(source, raw_html, min_discount):
    merchant = source["merchant"]
    page_text = html.unescape(raw_html).replace("\xa0", " ").casefold()

    # Curated official/direct sources can define live-page markers. We only use
    # the configured offer while those markers are still present on the page.
    # If the merchant removes or changes the promotion, the deal disappears
    # automatically instead of becoming stale.
    for required in source.get("required_terms", []):
        if required.casefold() not in page_text:
            print(f"  SKIP - expected live-page marker not found: {required!r}")
            return []

    override = source.get("offer_text_override")
    if override:
        item = build_generic_food_item(source, merchant, override, min_discount)
        return [item] if item else []

    lines = html_to_lines(raw_html)
    candidates = []

    # Prefer the strongest concise offer line found on the current live page.
    for index, line in enumerate(lines[:500]):
        if not deal_signal(line):
            continue
        discount = extract_discount_equivalent(line)
        if discount <= 0:
            continue
        candidates.append((discount, -index, clean_name(line)))

    if not candidates:
        return []

    candidates.sort(reverse=True)
    _, _, offer_text = candidates[0]
    item = build_generic_food_item(source, merchant, offer_text, min_discount)
    return [item] if item else []


def monthly_eatbook_source(today):
    month = today.strftime("%B").casefold()
    year = today.year
    return {
        "name": f"Eatbook Singapore food deals - {today.strftime('%B %Y')}",
        "url": f"https://eatbook.sg/food-deals-singapore-{month}-{year}/",
        "source": "Eatbook Singapore",
        "deal_type": "discovery",
        "source_confidence": "discovered",
        "access_requirement": "Verify directly with the restaurant before booking",
        "location": "Singapore",
        "max_results": 5,
    }


# ---------------------------- Eatigo parser -------------------------------

def reservation_count(value):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(k?)", value.lower().replace(",", ""))
    if not match:
        return None
    number = float(match.group(1))
    if match.group(2) == "k":
        number *= 1000
    return int(number)


def find_restaurants(lines):
    direct_re = re.compile(
        r"^(?P<name>.+?)\s+(?P<rating>[1-5](?:\.\d)?)\s+(?P<count>\d+(?:\.\d+)?k?)\s+reservations$",
        re.IGNORECASE,
    )
    rating_re = re.compile(r"^[1-5](?:\.\d)?$")
    rating_count_re = re.compile(
        r"^(?P<rating>[1-5](?:\.\d)?)\s+(?P<count>\d+(?:\.\d+)?k?)\s+reservations$",
        re.IGNORECASE,
    )
    count_re = re.compile(r"^(?P<count>\d+(?:\.\d+)?k?)\s+reservations$", re.IGNORECASE)

    found = []
    for index, line in enumerate(lines):
        match = direct_re.match(line)
        if match:
            name = clean_name(match.group("name"))
            if plausible_name(name):
                found.append({"start": index, "name": name, "rating": float(match.group("rating")), "reservation_count": reservation_count(match.group("count"))})
            continue
        combined = rating_count_re.match(line)
        if combined and index >= 1:
            name = clean_name(lines[index - 1])
            if plausible_name(name):
                found.append({"start": index - 1, "name": name, "rating": float(combined.group("rating")), "reservation_count": reservation_count(combined.group("count"))})
            continue
        if index >= 2 and count_re.match(line) and rating_re.match(lines[index - 1]):
            name = clean_name(lines[index - 2])
            if plausible_name(name):
                found.append({"start": index - 2, "name": name, "rating": float(lines[index - 1]), "reservation_count": reservation_count(count_re.match(line).group("count"))})

    unique, seen = [], set()
    for item in sorted(found, key=lambda row: row["start"]):
        key = (item["start"], item["name"].casefold())
        if key not in seen:
            unique.append(item)
            seen.add(key)
    return unique


def time_to_minutes(value):
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)


def extract_slots(block_lines, start_time, end_time):
    block = " ".join(block_lines)
    slot_re = re.compile(r"(?P<time>\d{1,2}:\d{2})\s*[-–—]\s*(?P<discount>\d{1,3})\s*%")
    start_minutes = time_to_minutes(start_time)
    end_minutes = time_to_minutes(end_time)
    slots, seen = [], set()
    for match in slot_re.finditer(block):
        time_text = match.group("time")
        discount = int(match.group("discount"))
        if not 0 <= discount <= 100:
            continue
        minutes = time_to_minutes(time_text)
        slot = (time_text, discount)
        if start_minutes <= minutes <= end_minutes and slot not in seen:
            slots.append(slot)
            seen.add(slot)
    return slots


def parse_eatigo(source, raw_html, min_discount):
    lines = html_to_lines(raw_html)
    restaurants = find_restaurants(lines)
    items = []
    for position, restaurant in enumerate(restaurants):
        start = restaurant["start"]
        end = restaurants[position + 1]["start"] if position + 1 < len(restaurants) else len(lines)
        slots = extract_slots(lines[start:end], source["window_start"], source["window_end"])
        if not slots:
            continue
        best_discount = max(discount for _, discount in slots)
        category = infer_food_category(restaurant["name"])
        floor = min_discount if category != "indian" else min(min_discount, INDIAN_MIN_DISCOUNT)
        if best_discount < floor:
            continue
        best_times = sorted({time_text for time_text, discount in slots if discount == best_discount}, key=time_to_minutes)
        rating = restaurant["rating"]
        meal = source["meal_period"]
        times_text = ", ".join(best_times[:4])
        description = f"Up to {best_discount}% off {meal} time slots on Eatigo. Rating {rating:.1f}/5."
        if times_text:
            description += f" Best observed slot(s): {times_text}."
        description += " Verify the live slot and conditions before booking."
        items.append({
            "id": stable_id("eatigo", "Eatigo Singapore", restaurant["name"], meal),
            "category": "food",
            "name": f"{restaurant['name']} — {meal.capitalize()}",
            "restaurant_name": restaurant["name"],
            "location": "Singapore",
            "description": description,
            "discount_percent": best_discount,
            "quality_score": quality_for_source("app_live", rating),
            "relevance_score": food_relevance(restaurant["name"], category, best_discount, "app_deal", rating),
            "rating": rating,
            "reservation_count": restaurant["reservation_count"],
            "meal_period": meal,
            "food_category": category,
            "food_category_inferred": True,
            "best_discount_times": best_times[:8],
            "deal_type": "app_deal",
            "source": "Eatigo Singapore",
            "source_detail": source["name"],
            "source_type": "official_promotion_page",
            "source_confidence": "app_live",
            "access_requirement": "Eatigo booking required",
            "reference_source": "eatigo_live_page",
            "url": source["url"],
            "verification_required": True,
            "is_demo": False,
            "is_live": True,
            "price_type": "time_slot_discount",
            "preferred_cuisine": category == "indian",
            "preference_priority": 1 if category == "indian" else 0,
        })
    return items


def load_previous_live_food():
    if not PREVIOUS_FOOD_PATH.exists():
        return []
    try:
        payload = json.loads(PREVIOUS_FOOD_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(payload, dict):
        payload = payload.get("items", [])
    if not isinstance(payload, list):
        return []
    preserved = []
    for item in payload:
        if not isinstance(item, dict) or item.get("category") != "food" or item.get("is_demo", False):
            continue
        row = dict(item)
        if not row.get("food_category"):
            row["food_category"] = infer_food_category(row.get("restaurant_name") or row.get("name", ""))
            row["food_category_inferred"] = True
        row.setdefault("deal_type", "app_deal" if "eatigo" in str(row.get("source", "")).casefold() else "discovery")
        row.setdefault("source_confidence", "app_live" if row["deal_type"] == "app_deal" else "discovered")
        row["preferred_cuisine"] = row.get("food_category") == "indian"
        row["preference_priority"] = 1 if row["preferred_cuisine"] else 0
        preserved.append(row)
    return preserved


def dedupe_food(items):
    deduped = {}
    for item in items:
        restaurant = clean_name(item.get("restaurant_name") or item.get("name", ""))
        restaurant = re.split(r"\s*(?:@|\()", restaurant, maxsplit=1)[0].casefold()
        deal_type = item.get("deal_type", "")
        key = (restaurant, deal_type)
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = item
            continue
        # Prefer the stronger discount; on ties prefer verified source.
        current_rank = (
            item.get("discount_percent", 0),
            item.get("source_confidence") == "verified",
            not item.get("food_category_inferred", True),
        )
        existing_rank = (
            existing.get("discount_percent", 0),
            existing.get("source_confidence") == "verified",
            not existing.get("food_category_inferred", True),
        )
        if current_rank > existing_rank:
            deduped[key] = item
    return list(deduped.values())


def select_diverse_food(items, max_items):
    """Keep Indian preference visible and prevent one source from flooding the tab."""
    quotas = {
        "app_deal": 10,
        "card_deal": 12,
        "direct": 7,
        "membership_deal": 5,
        "discovery": 5,
    }

    for item in items:
        item["deal_score"] = promo_score(item, "food")

    indian = sorted(
        [row for row in items if row.get("food_category") == "indian"],
        key=lambda row: (row.get("deal_score", 0), row.get("discount_percent", 0)),
        reverse=True,
    )
    remaining = sorted(
        [row for row in items if row.get("food_category") != "indian"],
        key=lambda row: (
            row.get("deal_score", 0),
            row.get("source_confidence") == "verified",
            row.get("discount_percent", 0),
        ),
        reverse=True,
    )

    selected, seen_ids, used = [], set(), {}

    # Reserve up to six Indian food deals when available.
    for row in indian[:6]:
        selected.append(row)
        seen_ids.add(row["id"])
        used[row.get("deal_type", "discovery")] = used.get(row.get("deal_type", "discovery"), 0) + 1

    # Then fill with best remaining deals subject to source-type quotas.
    for row in remaining + indian[6:]:
        if len(selected) >= max_items:
            break
        if row["id"] in seen_ids:
            continue
        deal_type = row.get("deal_type", "discovery")
        if used.get(deal_type, 0) >= quotas.get(deal_type, 4):
            continue
        selected.append(row)
        seen_ids.add(row["id"])
        used[deal_type] = used.get(deal_type, 0) + 1

    # If quotas left empty slots, fill strictly by score.
    if len(selected) < max_items:
        leftovers = sorted(
            [row for row in items if row["id"] not in seen_ids],
            key=lambda row: row.get("deal_score", 0),
            reverse=True,
        )
        selected.extend(leftovers[: max_items - len(selected)])

    return selected[:max_items]


def scan_food():
    timeout = env_int("FOOD_SCAN_TIMEOUT_SECONDS", DEFAULT_TIMEOUT, 5, 60)
    min_discount = env_int("FOOD_SCAN_MIN_DISCOUNT", DEFAULT_MIN_DISCOUNT, 0, 100)
    max_items = env_int("FOOD_SCAN_MAX_ITEMS", DEFAULT_MAX_ITEMS, 1, 100)
    today = datetime.now(SGT).date()

    sources_planned = len(EATIGO_SOURCES) + len(OFFICIAL_INDEX_SOURCES) + len(OFFICIAL_SINGLE_SOURCES) + 1

    print("")
    print("=" * 72)
    print("FOOD MULTI-SOURCE LIVE SCAN")
    print("=" * 72)
    print(f"Sources planned:       {sources_planned}")
    print(f"General min discount:  {min_discount}%")
    print(f"Indian min discount:   {min(INDIAN_MIN_DISCOUNT, min_discount)}%")
    print(f"Maximum published:     {max_items}")
    print("")

    all_items = []
    succeeded = 0
    failed = 0

    for source in EATIGO_SOURCES:
        print(f"Food source: {source['name']}")
        try:
            raw_html = fetch_html(source["url"], timeout)
            items = parse_eatigo(source, raw_html, min_discount)
            all_items.extend(items)
            succeeded += 1
            print(f"  OK - qualified deals found: {len(items)}")
        except (HTTPError, URLError, Exception) as exc:
            failed += 1
            label = f"HTTP {getattr(exc, 'code', '')}" if isinstance(exc, HTTPError) else type(exc).__name__
            print(f"  FAILED - {label}: {exc}")

    for source in OFFICIAL_INDEX_SOURCES:
        print(f"Food source: {source['name']}")
        try:
            raw_html = fetch_html(source["url"], timeout)
            items = parse_index_source(source, raw_html, min_discount)
            all_items.extend(items)
            succeeded += 1
            print(f"  OK - qualified deals found: {len(items)}")
        except (HTTPError, URLError, Exception) as exc:
            failed += 1
            print(f"  FAILED - {type(exc).__name__}: {exc}")

    for source in OFFICIAL_SINGLE_SOURCES:
        print(f"Food source: {source['name']}")
        try:
            raw_html = fetch_html(source["url"], timeout)
            items = parse_single_source(source, raw_html, min_discount)
            all_items.extend(items)
            succeeded += 1
            print(f"  OK - qualified deals found: {len(items)}")
        except (HTTPError, URLError, Exception) as exc:
            failed += 1
            print(f"  FAILED - {type(exc).__name__}: {exc}")

    # Current-month Eatbook article is discovery only. Failure is non-fatal.
    discovery = monthly_eatbook_source(today)
    print(f"Food source: {discovery['name']}")
    try:
        raw_html = fetch_html(discovery["url"], timeout)
        items = parse_index_source(discovery, raw_html, max(min_discount, 25))
        all_items.extend(items)
        succeeded += 1
        print(f"  OK - discovery deals found: {len(items)}")
    except (HTTPError, URLError, Exception) as exc:
        failed += 1
        print(f"  FAILED - {type(exc).__name__}: {exc}")

    if succeeded == 0 and failed > 0:
        previous = load_previous_live_food()
        print("")
        print("FOOD SCAN INTEGRITY CHECK")
        print(f"Sources succeeded:     {succeeded}")
        print(f"Sources failed:        {failed}")
        if previous:
            print(f"Preserving {len(previous)} previous live Food result(s).")
            return previous
        print("No previous live Food data exists. Returning no Food deals.")
        return []

    unique = dedupe_food(all_items)
    observed_at = iso_now_sgt()
    selected = select_diverse_food(unique, max_items)
    for item in selected:
        item["observed_at"] = observed_at

    counts = {}
    for item in selected:
        counts[item.get("deal_type", "other")] = counts.get(item.get("deal_type", "other"), 0) + 1
    indian_count = sum(1 for item in selected if item.get("food_category") == "indian")

    print("")
    print("FOOD SCAN INTEGRITY CHECK")
    print(f"Sources succeeded:     {succeeded}")
    print(f"Sources failed:        {failed}")
    print(f"Unique live deals:     {len(unique)}")
    print(f"Published live deals:  {len(selected)}")
    print(f"Indian food deals:     {indian_count}")
    print(f"Deal type mix:         {counts}")
    print("FOOD SCAN COMPLETED")
    print("")

    return selected
