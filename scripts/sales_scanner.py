from __future__ import annotations

import hashlib
import html
import json
import os
import re
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from utils import iso_now_sgt
from deal_score import promo_score


# ---------------------------------------------------------------------------
# V&V Deals Scout - Live Sales Scanner
#
# V4 combines discovery feeds with official mall/outlet, direct brand,
# direct retailer and card-linked promotion pages. Official sources are
# validated against live-page markers before a configured offer is published.
#
# Direct-brand coverage includes adidas, Nike, PUMA and ASICS Singapore,
# alongside CapitaLand IMM and COURTS Singapore.
#
# This scanner does NOT call Hotelbeds and therefore does not consume the
# Hotelbeds Evaluation quota.
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/152.0.0.0 Safari/537.36"
)

SOURCE_PAGES = [
    {
        "name": "EverydayOnSales - Sportswear",
        "url": "https://sg.everydayonsales.com/sales-category/fashion-lifestyle-department-store/sportswear/",
        "hint": "sportswear",
    },
    {
        "name": "EverydayOnSales - Computers & Electronics",
        "url": "https://sg.everydayonsales.com/sales-category/computers-electronics/",
        "hint": "electronics",
    },
    {
        "name": "EverydayOnSales - Sports, Leisure & Travel",
        "url": "https://sg.everydayonsales.com/sales-category/sports-leisure-travel/",
        "hint": "travel",
    },
    {
        "name": "EverydayOnSales - Fashion Accessories",
        "url": "https://sg.everydayonsales.com/sales-category/fashion-lifestyle-department-store/fashion-accessories/",
        "hint": "fashion",
    },
    {
        "name": "EverydayOnSales - Happening Now",
        "url": "https://sg.everydayonsales.com/sales-period/sales-happening-now/",
        "hint": "general",
    },
]

DEFAULT_TIMEOUT = 20
DEFAULT_MIN_DISCOUNT = 15
DEFAULT_MAX_ITEMS = 30
MAX_PAGE_BYTES = 2_000_000


# Additional official/direct sources used by Sales V2.
OFFICIAL_SALES_INDEX_SOURCES = [
    {
        "name": "American Express Shopping",
        "url": "https://www.americanexpress.com/en-sg/benefits/promotions/shopping/",
        "source": "American Express Shopping",
        "deal_type": "card_deal",
        "source_confidence": "verified",
        "access_requirement": "Eligible American Express card required",
        "hint": "general",
        "max_results": 8,
    },
    {
        "name": "DBS Home & Electronics",
        "url": "https://www.dbs.com.sg/personal/promotion/cards-home-owners-privileges",
        "source": "DBS/POSB Shopping",
        "deal_type": "card_deal",
        "source_confidence": "verified",
        "access_requirement": "DBS/POSB card or instalment plan may be required",
        "hint": "electronics",
        "max_results": 8,
    },
]

OFFICIAL_SALES_SINGLE_SOURCES = [
    {
        "name": "adidas Singapore Sale Terms",
        "url": "https://www.adidas.com.sg/help/sea-promotions-and-vouchers/sale-terms-and-condition",
        "merchant": "adidas Singapore",
        "source": "adidas Singapore",
        "deal_type": "direct_brand",
        "source_confidence": "verified",
        "access_requirement": "Direct brand promotion; selected products and exclusions apply",
        "hint": "sportswear",
        "subcategory": "sportswear_footwear",
        "location": "Online / selected Singapore stores",
        "offer_text_override": "30% off full-priced items and extra 30% off current markdown prices on outlet/sale items",
        "required_terms": ["30% off their RRP", "extra 30% off their current markdown price"],
    },
    {
        "name": "Nike Singapore Sale",
        "url": "https://www.nike.com/sg/w/sale-3yaepz5k5r2z6fvtl",
        "merchant": "Nike Singapore Sale",
        "source": "Nike Singapore",
        "deal_type": "direct_brand",
        "source_confidence": "verified",
        "access_requirement": "Direct brand sale; selected styles, sizes and stock availability apply",
        "hint": "sportswear",
        "subcategory": "sportswear_footwear",
        "location": "Online / Singapore",
        "offer_text_override": "Selected Nike sale items up to 40% off",
        "required_terms": ["Sale", "40% off"],
    },
    {
        "name": "PUMA Singapore Men's Sale",
        "url": "https://sg.puma.com/sg/en/men/sale",
        "merchant": "PUMA Singapore Sale",
        "source": "PUMA Singapore",
        "deal_type": "direct_brand",
        "source_confidence": "verified",
        "access_requirement": "Direct brand sale; selected styles and stock availability apply",
        "hint": "sportswear",
        "subcategory": "sportswear_footwear",
        "location": "Online / Singapore",
        "offer_text_override": "Selected PUMA sportswear and footwear from 20% off",
        "required_terms": ["PUMA", "20% OFF"],
    },
    {
        "name": "ASICS Singapore 30% Off and Up",
        "url": "https://www.asics.com/sg/en-sg/sale-30-off-above/",
        "merchant": "ASICS Singapore Sale",
        "source": "ASICS Singapore",
        "deal_type": "direct_brand",
        "source_confidence": "verified",
        "access_requirement": "Direct brand sale; selected products, colours and sizes apply",
        "hint": "sportswear",
        "subcategory": "sportswear_footwear",
        "location": "Online / Singapore",
        "offer_text_override": "Selected ASICS footwear and apparel 30% off and up",
        "required_terms": ["Sale 30% Off And Up", "30%"],
    },
    {
        "name": "Under Armour Outlet IMM",
        "url": "https://www.capitaland.com/sg/malls/imm/en/stores/under-armour-outlet.html",
        "merchant": "Under Armour Outlet @ IMM",
        "source": "CapitaLand IMM",
        "deal_type": "mall_outlet",
        "source_confidence": "verified",
        "access_requirement": "Official IMM outlet offer; stock and exclusions apply",
        "hint": "sportswear",
        "subcategory": "sportswear_footwear",
        "location": "IMM / Singapore",
        "offer_text_override": "Up to 70% discount all year round at Under Armour Outlet at IMM",
        "required_terms": ["Under Armour Outlet", "up to 70% discount all year round"],
    },
    {
        "name": "PUMA Outlet IMM",
        "url": "https://www.capitaland.com/sg/malls/imm/en/deals/puma-buy-2-get1freebuy3get3free.html",
        "merchant": "PUMA Outlet @ IMM",
        "source": "CapitaLand IMM",
        "deal_type": "mall_outlet",
        "source_confidence": "verified",
        "access_requirement": "Official IMM outlet deal; exclusions and T&Cs apply",
        "hint": "sportswear",
        "subcategory": "sportswear_footwear",
        "location": "IMM / Singapore",
        "offer_text_override": "Up to 70% off; buy 2 items get 1 free or buy 3 items get 3 free",
        "required_terms": ["Up to 70% off", "Buy 2 items get 1 free"],
    },
    {
        "name": "IMM Outlet Mall",
        "url": "https://www.capitaland.com/sg/malls/imm/en.html",
        "merchant": "IMM Outlet Mall",
        "source": "CapitaLand IMM",
        "deal_type": "mall_outlet",
        "source_confidence": "verified",
        "access_requirement": "Official mall-wide outlet positioning; individual store offers vary",
        "hint": "outlet",
        "subcategory": "outlet_clearance",
        "location": "IMM / Singapore",
        "offer_text_override": "Up to 80% savings all year round across more than 90 outlet stores",
        "required_terms": ["offering up to 80% discount all year round", "outlet stores"],
    },
    {
        "name": "TUMI Outlet August multi-buy",
        "url": "https://www.capitaland.com/sg/en/shop/malls/discover/WestTheSale2026.html",
        "merchant": "TUMI Outlet @ IMM",
        "source": "CapitaLand IMM",
        "deal_type": "mall_outlet",
        "source_confidence": "verified",
        "access_requirement": "Official IMM August multi-buy; exclusions and stock limits apply",
        "hint": "travel",
        "subcategory": "travel_luggage",
        "location": "IMM / Singapore",
        "offer_text_override": "Storewide 30% off with additional multi-buy savings up to 20% through 31 August 2026",
        "required_terms": ["TUMI Outlet", "Storewide 30% Off", "1–31 August 2026"],
        "valid_until": "2026-08-31",
    },
    {
        "name": "COURTS Home Office online promotion",
        "url": "https://www.courts.com.sg/promocode.html",
        "merchant": "COURTS Home Office Online",
        "source": "COURTS Singapore",
        "deal_type": "direct_retailer",
        "source_confidence": "verified",
        "access_requirement": "Online promo code OFFICE20; exclusions apply",
        "hint": "electronics",
        "subcategory": "electronics",
        "location": "Online / Singapore",
        "offer_text_override": "20% off selected Home Office products with no minimum spend",
        "required_terms": ["Home Office", "20% off", "OFFICE20"],
    },
    {
        "name": "COURTS SONA appliance deals",
        "url": "https://www.courts.com.sg/sona",
        "merchant": "COURTS · SONA appliance deals",
        "source": "COURTS Singapore",
        "deal_type": "direct_retailer",
        "source_confidence": "verified",
        "access_requirement": "Direct retailer prices; selected models and stock availability apply",
        "hint": "electronics",
        "subcategory": "electronics",
        "location": "Online / Singapore",
        "offer_text_override": "Selected SONA appliances up to 50% off",
        "required_terms": ["SONA", "50% off"],
    },
    {
        "name": "CLUB21.com - DBS/POSB",
        "url": "https://www.dbs.com.sg/personal/promotion/cards-privileges-ylclub21",
        "merchant": "CLUB21.com",
        "source": "DBS/POSB Shopping",
        "deal_type": "card_deal",
        "source_confidence": "verified",
        "access_requirement": "DBS/POSB card required",
        "hint": "fashion",
        "location": "Online / Singapore",
    },
    {
        "name": "ZALORA - DBS/POSB",
        "url": "https://www.dbs.com.sg/personal/promotion/cards-zalora",
        "merchant": "ZALORA",
        "source": "DBS/POSB Shopping",
        "deal_type": "card_deal",
        "source_confidence": "verified",
        "access_requirement": "DBS/POSB card and promotion code required",
        "hint": "fashion",
        "location": "Online / Singapore",
    },
]

REPO_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_SALES_PATH = REPO_ROOT / "data" / "sales.json"
SGT = ZoneInfo("Asia/Singapore")

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
MONTH_PATTERN = "(?:" + "|".join(MONTHS) + ")"

PREFERRED_BRANDS = {
    "nike",
    "adidas",
    "under armour",
    "new balance",
    "puma",
    "skechers",
    "asics",
    "timberland",
    "crocs",
    "oakley",
    "wilson",
    "champion",
    "fila",
    "samsonite",
    "american tourister",
    "tumi",
    "rimowa",
    "challenger",
    "best denki",
    "harvey norman",
    "courts",
    "dyson",
    "samsung",
    "apple",
    "sony",
    "lg",
    "lenovo",
    "asus",
    "acer",
    "dell",
    "hp",
}

SPORTS_WORDS = {
    "sportswear",
    "running",
    "running shoes",
    "sneakers",
    "footwear",
    "shoes",
    "fitness",
    "compression",
    "athleisure",
    "jersey",
    "sports",
}

ELECTRONICS_WORDS = {
    "electronics",
    "electronic",
    "laptop",
    "monitor",
    "smartphone",
    "phone",
    "tablet",
    "headphone",
    "earbuds",
    "audio",
    "charger",
    "charging",
    "power bank",
    "tech",
    "gadget",
    "camera",
    "television",
    "tv",
    "computer",
}

TRAVEL_WORDS = {
    "travel",
    "luggage",
    "suitcase",
    "carry-on",
    "carry on",
    "backpack",
    "travel bag",
    "airline",
    "flight",
    "holiday",
}

OUTLET_WORDS = {
    "imm",
    "outlet",
    "warehouse sale",
    "clearance",
    "moving out",
    "closing down",
    "atrium sale",
    "factory outlet",
}

SALE_WORDS = {
    "sale",
    "promotion",
    "discount",
    "off",
    "clearance",
    "warehouse",
    "deal",
    "savings",
    "save",
    "buy 1 get 1",
    "buy 2 get",
    "free",
}

IGNORE_WORDS = {
    "food",
    "restaurant",
    "buffet",
    "cafe",
    "café",
    "coffee",
    "hotpot",
    "meal",
    "groceries",
    "supermarket",
    "beer",
    "wine",
}

KNOWN_LOCATIONS = [
    "IMM",
    "Westgate",
    "JEM",
    "Jurong Point",
    "Lot One",
    "Bukit Panjang Plaza",
    "Bedok Mall",
    "Takashimaya",
    "Changi City Point",
    "Marina Square",
    "Suntec City",
    "VivoCity",
    "Plaza Singapura",
    "NEX",
    "Funan",
    "Bugis Junction",
    "Bugis+",
    "Orchard",
    "Singapore EXPO",
]


class AnchorExtractor(HTMLParser):
    """Collect visible link text and href values without third-party packages."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.current_href = None
        self.current_parts = []
        self.hidden_depth = 0
        self.links = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden_depth += 1
            return

        if self.hidden_depth == 0 and tag == "a":
            attr_map = dict(attrs)
            self.current_href = attr_map.get("href")
            self.current_parts = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden_depth = max(0, self.hidden_depth - 1)
            return

        if self.hidden_depth == 0 and tag == "a" and self.current_href:
            text = re.sub(r"\s+", " ", " ".join(self.current_parts)).strip()
            if text:
                self.links.append((self.current_href, text))
            self.current_href = None
            self.current_parts = []

    def handle_data(self, data):
        if self.hidden_depth == 0 and self.current_href is not None and data:
            self.current_parts.append(data)


def env_int(name, default, minimum, maximum):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default

    try:
        value = int(raw)
    except ValueError:
        print(f"Sales scanner: invalid {name}={raw!r}; using {default}.")
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


def clean_text(value):
    value = html.unescape(value).replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \t\r\n-|•·")


def extract_candidate_links(source, raw_html):
    parser = AnchorExtractor()
    parser.feed(raw_html)
    parser.close()

    output = []
    seen = set()

    for href, text in parser.links:
        title = clean_text(text)
        if len(title) < 28 or len(title) > 260:
            continue

        lowered = title.casefold()
        if "2026" not in lowered and "onwards" not in lowered:
            continue
        if not any(word in lowered for word in SALE_WORDS):
            continue

        full_url = urljoin(source["url"], href)
        parsed = urlparse(full_url)
        if parsed.scheme not in {"http", "https"}:
            continue
        if "everydayonsales.com" not in parsed.netloc.casefold():
            continue

        key = (full_url.split("#", 1)[0], title.casefold())
        if key in seen:
            continue
        seen.add(key)

        output.append(
            {
                "title": title,
                "url": full_url.split("#", 1)[0],
                "source_detail": source["name"],
                "source_hint": source["hint"],
            }
        )

    return output


def _month_number(name):
    return MONTHS[name.casefold()]


def _safe_date(year, month, day):
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_validity(title, today):
    """
    Parse the common date prefixes used by Singapore sales listings.

    Returns (start_date, end_date). An end date of None means "onwards".
    Unknown formats return (None, None); they are accepted only when they
    clearly contain an "onwards" marker.
    """
    text = clean_text(title)

    # Now till 31 August 2026
    match = re.search(
        rf"\bnow\s+till\s+(\d{{1,2}})\s+({MONTH_PATTERN})\s+(20\d{{2}})\b",
        text,
        re.IGNORECASE,
    )
    if match:
        end = _safe_date(int(match.group(3)), _month_number(match.group(2)), int(match.group(1)))
        return None, end

    # 19 August-1 September 2026 / 14 August–13 September 2026
    match = re.search(
        rf"\b(\d{{1,2}})\s+({MONTH_PATTERN})\s*[-–—]\s*(\d{{1,2}})\s+({MONTH_PATTERN})\s+(20\d{{2}})\b",
        text,
        re.IGNORECASE,
    )
    if match:
        year = int(match.group(5))
        start = _safe_date(year, _month_number(match.group(2)), int(match.group(1)))
        end = _safe_date(year, _month_number(match.group(4)), int(match.group(3)))
        return start, end

    # 24-30 August 2026
    match = re.search(
        rf"\b(\d{{1,2}})\s*[-–—]\s*(\d{{1,2}})\s+({MONTH_PATTERN})\s+(20\d{{2}})\b",
        text,
        re.IGNORECASE,
    )
    if match:
        year = int(match.group(4))
        month = _month_number(match.group(3))
        return (
            _safe_date(year, month, int(match.group(1))),
            _safe_date(year, month, int(match.group(2))),
        )

    # 25 August 2026 onwards
    match = re.search(
        rf"\b(\d{{1,2}})\s+({MONTH_PATTERN})\s+(20\d{{2}})\s+onwards\b",
        text,
        re.IGNORECASE,
    )
    if match:
        start = _safe_date(int(match.group(3)), _month_number(match.group(2)), int(match.group(1)))
        return start, None

    # 1-31 August 2026 with varying dash placement already handled above.
    # A single dated promotion such as 30 August 2026 is valid that day only.
    match = re.search(
        rf"\b(\d{{1,2}})\s+({MONTH_PATTERN})\s+(20\d{{2}})\b",
        text,
        re.IGNORECASE,
    )
    if match:
        one_day = _safe_date(int(match.group(3)), _month_number(match.group(2)), int(match.group(1)))
        return one_day, one_day

    if "onwards" in text.casefold():
        return None, None

    return None, None


def is_active(start, end, today, title):
    if start and today < start:
        return False
    if end and today > end:
        return False

    # If no date could be parsed, only allow explicit ongoing wording.
    if start is None and end is None:
        lowered = title.casefold()
        return "onwards" in lowered or "now till" in lowered

    return True


def extract_discount_percent(title):
    text = clean_text(title)

    # Prefer the largest explicitly advertised percentage.
    percentages = [
        int(value)
        for value in re.findall(r"(?<!\d)(\d{1,3})\s*%\s*(?:off|discount|savings?)?", text, re.IGNORECASE)
        if 0 < int(value) <= 100
    ]

    # Buy N Get M Free -> equivalent headline saving for an equal-value basket.
    for buy, free in re.findall(
        r"buy\s+(\d+)\s+(?:selected\s+\w+\s+)?get\s+(\d+)\s+free",
        text,
        re.IGNORECASE,
    ):
        buy_n = int(buy)
        free_n = int(free)
        if buy_n > 0 and free_n > 0:
            percentages.append(round(100 * free_n / (buy_n + free_n)))

    # 1-for-1 / 1 for 1 approximates 50% on two equal-value items.
    if re.search(r"\b1\s*[- ]?for\s*[- ]?1\b", text, re.IGNORECASE):
        percentages.append(50)

    return max(percentages) if percentages else 0


def detect_subcategory(title, hint):
    lowered = title.casefold()

    if any(word in lowered for word in ELECTRONICS_WORDS):
        return "electronics"
    if any(word in lowered for word in TRAVEL_WORDS):
        return "travel_luggage"
    if any(word in lowered for word in SPORTS_WORDS):
        return "sportswear_footwear"
    if any(word in lowered for word in OUTLET_WORDS):
        return "outlet_clearance"

    if hint == "electronics":
        return "electronics"
    if hint == "travel":
        return "travel_luggage"
    if hint == "sportswear":
        return "sportswear_footwear"

    return "fashion_clearance"


def is_relevant(title, hint):
    lowered = title.casefold()

    if any(word in lowered for word in IGNORE_WORDS) and not any(
        word in lowered for word in PREFERRED_BRANDS | ELECTRONICS_WORDS | SPORTS_WORDS | TRAVEL_WORDS
    ):
        return False

    if any(word in lowered for word in PREFERRED_BRANDS):
        return True
    if any(word in lowered for word in SPORTS_WORDS):
        return True
    if any(word in lowered for word in ELECTRONICS_WORDS):
        return True
    if any(word in lowered for word in TRAVEL_WORDS):
        return True
    if any(word in lowered for word in OUTLET_WORDS):
        return True

    return hint in {"sportswear", "electronics", "travel"}


def infer_location(title):
    lowered = title.casefold()
    for location in KNOWN_LOCATIONS:
        if location.casefold() in lowered:
            return f"{location} / Singapore"
    return "Singapore"


def brand_quality_score(title):
    lowered = title.casefold()
    score = 7.2

    if any(brand in lowered for brand in PREFERRED_BRANDS):
        score += 1.0
    if any(word in lowered for word in OUTLET_WORDS):
        score += 0.4
    if "clearance" in lowered or "warehouse sale" in lowered:
        score += 0.4

    return round(min(score, 10.0), 1)


def relevance_score(title, subcategory, discount):
    lowered = title.casefold()
    score = 7.0

    if subcategory in {"sportswear_footwear", "electronics", "travel_luggage"}:
        score += 0.8
    if "imm" in lowered:
        score += 0.7
    elif any(word in lowered for word in OUTLET_WORDS):
        score += 0.4

    if any(brand in lowered for brand in PREFERRED_BRANDS):
        score += 0.5

    if discount >= 60:
        score += 0.8
    elif discount >= 50:
        score += 0.6
    elif discount >= 40:
        score += 0.3

    return round(min(score, 10.0), 1)


def stable_id(url, title):
    value = f"sales|{url}|{title.casefold()}".encode("utf-8")
    return "sale-live-" + hashlib.sha1(value).hexdigest()[:12]


def concise_name(title):
    # Remove the date prefix while preserving the actual promotion wording.
    value = re.sub(r"^\s*(?:now\s+till\s+)?[^:]{0,70}:\s*", "", title, count=1, flags=re.IGNORECASE)
    value = clean_text(value)
    return value if value else clean_text(title)


def build_item(candidate, today, min_discount):
    title = candidate["title"]
    discount = extract_discount_percent(title)
    if discount < min_discount:
        return None

    if not is_relevant(title, candidate["source_hint"]):
        return None

    start, end = parse_validity(title, today)
    if not is_active(start, end, today, title):
        return None

    subcategory = detect_subcategory(title, candidate["source_hint"])
    location = infer_location(title)
    item_name = concise_name(title)

    validity_text = ""
    if end:
        validity_text = f" Listed as valid through {end.isoformat()}."
    elif start:
        validity_text = f" Listed from {start.isoformat()} onwards."

    description = (
        f"Discovery listing advertising up to {discount}% savings."
        f"{validity_text} Verify stock, eligible products, membership requirements, "
        "and final price with the retailer before purchase."
    )

    return {
        "id": stable_id(candidate["url"], title),
        "category": "sale",
        "subcategory": subcategory,
        "name": item_name,
        "location": location,
        "description": description,
        "discount_percent": discount,
        "quality_score": brand_quality_score(title),
        "relevance_score": relevance_score(title, subcategory, discount),
        "source": "EverydayOnSales Singapore",
        "source_detail": candidate["source_detail"],
        "source_type": "promotion_aggregator",
        "reference_source": "everydayonsales_live_page",
        "url": candidate["url"],
        "valid_from": start.isoformat() if start else None,
        "valid_until": end.isoformat() if end else None,
        "verification_required": True,
        "is_demo": False,
        "is_live": True,
        "price_type": "advertised_discount",
    }


def load_previous_live_sales():
    """Preserve prior live Sales data if every source becomes unusable."""
    if not PREVIOUS_SALES_PATH.exists():
        return []

    try:
        payload = json.loads(PREVIOUS_SALES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if isinstance(payload, dict):
        payload = payload.get("items", [])

    if not isinstance(payload, list):
        return []

    return [
        dict(item)
        for item in payload
        if isinstance(item, dict)
        and item.get("category") == "sale"
        and not item.get("is_demo", False)
    ]


class VisibleTextExtractor(HTMLParser):
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


def html_to_lines(raw_html):
    parser = VisibleTextExtractor()
    parser.feed(raw_html)
    parser.close()
    text = html.unescape(parser.get_text()).replace("\xa0", " ")
    output = []
    for raw in text.splitlines():
        line = clean_text(raw)
        if line:
            output.append(line)
    return output


def extract_effective_discount(text):
    values = [extract_discount_percent(text)]
    lowered = clean_text(text).casefold()
    dollar = re.search(
        r"(?:s\$|\$)\s*(\d+(?:\.\d+)?)\s*off[^.]{0,90}min(?:imum)?\.?\s*(?:spend|charge)(?:\s+of)?\s*(?:s\$|\$)\s*(\d+(?:\.\d+)?)",
        lowered,
    )
    if dollar:
        amount = float(dollar.group(1))
        minimum = float(dollar.group(2))
        if minimum > 0:
            values.append(round(amount / minimum * 100))
    return max(values)


def official_deal_signal(text):
    lowered = clean_text(text).casefold()
    return (
        "% off" in lowered
        or "% savings" in lowered
        or "% discount" in lowered
        or "1-for-1" in lowered
        or "buy 1 get 1" in lowered
        or re.search(r"(?:s\$|\$)\s*\d+\s*off", lowered) is not None
    )


def find_official_merchant(lines, index):
    generic = {
        "shopping promotions", "view offer details", "limited time offers", "shopping",
        "offer detail", "promotion period", "terms and conditions", "learn more",
        "view all offers", "image",
    }
    for offset in range(1, 6):
        pos = index - offset
        if pos < 0:
            break
        candidate = clean_text(lines[pos])
        lowered = candidate.casefold()
        if not candidate or len(candidate) > 120 or lowered in generic:
            continue
        if official_deal_signal(candidate):
            continue
        if any(token in lowered for token in ("validity", "promotion period", "terms", "from now", "click here")):
            continue
        if any(ch.isalpha() for ch in candidate):
            return candidate
    return ""


def official_quality_score(text, confidence):
    base = brand_quality_score(text)
    if confidence == "verified":
        base += 0.5
    return round(min(base, 10.0), 1)


def build_official_sales_item(source, merchant, offer_text, min_discount):
    discount = extract_effective_discount(offer_text)
    floor = source.get("min_discount", min_discount)
    if discount < floor:
        return None

    combined = f"{merchant} {offer_text}"
    subcategory = source.get("subcategory") or detect_subcategory(combined, source.get("hint", "general"))
    location = source.get("location") or infer_location(combined)
    confidence = source.get("source_confidence", "verified")
    deal_type = source.get("deal_type", "card_deal")

    description = (
        f"Official promotion: {clean_text(offer_text)}. "
        f"{source.get('access_requirement', 'Check source terms')}. "
        "Verify current exclusions, eligible products, stock and final checkout price before purchase."
    )

    return {
        "id": stable_id(source["url"], f"{merchant}|{offer_text}"),
        "category": "sale",
        "subcategory": subcategory,
        "name": merchant,
        "location": location,
        "description": description,
        "discount_percent": discount,
        "quality_score": official_quality_score(combined, confidence),
        "relevance_score": relevance_score(combined, subcategory, discount),
        "source": source.get("source", source["name"]),
        "source_detail": source["name"],
        "source_type": "official_promotion_page",
        "reference_source": source["url"],
        "source_confidence": confidence,
        "deal_type": deal_type,
        "access_requirement": source.get("access_requirement", "Check source terms"),
        "url": source["url"],
        "verification_required": True,
        "is_demo": False,
        "is_live": True,
        "price_type": "advertised_discount",
    }


def parse_official_index(source, raw_html, min_discount):
    lines = html_to_lines(raw_html)
    items, seen = [], set()
    for index, line in enumerate(lines):
        if not official_deal_signal(line):
            continue
        merchant = find_official_merchant(lines, index)
        if not merchant:
            continue
        key = (merchant.casefold(), clean_text(line).casefold())
        if key in seen:
            continue
        seen.add(key)
        item = build_official_sales_item(source, merchant, line, min_discount)
        if item:
            items.append(item)
    items.sort(key=lambda row: (row["discount_percent"], row["relevance_score"]), reverse=True)
    return items[: source.get("max_results", 8)]


def parse_official_single(source, raw_html, min_discount, today):
    valid_from = source.get("valid_from")
    valid_until = source.get("valid_until")
    if valid_from and today < date.fromisoformat(valid_from):
        return []
    if valid_until and today > date.fromisoformat(valid_until):
        return []

    page_text = html.unescape(raw_html).replace("\xa0", " ").casefold()
    for required in source.get("required_terms", []):
        if required.casefold() not in page_text:
            print(f"  SKIP - expected live-page marker not found: {required!r}")
            return []

    override = source.get("offer_text_override")
    if override:
        item = build_official_sales_item(
            source,
            source["merchant"],
            override,
            min_discount,
        )
        if item:
            item["valid_from"] = valid_from
            item["valid_until"] = valid_until
        return [item] if item else []

    lines = html_to_lines(raw_html)
    candidates = []
    # Direct brand/retailer pages may include discount filters deep in the page.
    # Prefer an early live promotional headline, but only after page validation.
    for index, line in enumerate(lines[:450]):
        if not official_deal_signal(line):
            continue
        discount = extract_effective_discount(line)
        if discount < source.get("min_discount", min_discount):
            continue
        candidates.append((-index, discount, clean_text(line)))
    if not candidates:
        return []
    candidates.sort(reverse=True)
    _, _, offer = candidates[0]
    item = build_official_sales_item(source, source["merchant"], offer, min_discount)
    if item:
        item["valid_from"] = valid_from
        item["valid_until"] = valid_until
    return [item] if item else []


def enrich_discovery_item(item):
    item.setdefault("deal_type", "discovery")
    item.setdefault("source_confidence", "discovered")
    item.setdefault("access_requirement", "Verify directly with retailer")
    return item


def select_diverse_sales(items, max_items):
    # These are hard publication caps, not just first-pass targets. Discovery
    # is deliberately limited so official/direct sources cannot be crowded out.
    quotas = {
        "discovery": 12,
        "card_deal": 8,
        "direct_brand": 6,
        "direct_retailer": 5,
        "mall_outlet": 7,
    }
    for item in items:
        item["deal_score"] = promo_score(item, "sale")

    ordered = sorted(
        items,
        key=lambda row: (
            row.get("deal_score", 0),
            row.get("source_confidence") == "verified",
            row.get("discount_percent", 0),
        ),
        reverse=True,
    )
    selected, seen = [], set()
    counts = {}
    for row in ordered:
        if len(selected) >= max_items:
            break
        dtype = row.get("deal_type", "discovery")
        if counts.get(dtype, 0) >= quotas.get(dtype, 5):
            continue
        key = (clean_text(row.get("name", "")).casefold(), row.get("subcategory"), dtype)
        if key in seen:
            continue
        selected.append(row)
        seen.add(key)
        counts[dtype] = counts.get(dtype, 0) + 1

    # Do not refill beyond source caps just to force the list to exactly
    # max_items. A shorter, better-balanced Sales list is preferable to
    # padding the dashboard with aggregator results.
    return selected[:max_items]


def scan_sales():
    """Return multi-source live Singapore shopping / retail deals.

    Environment overrides:
      SALES_SCAN_TIMEOUT_SECONDS  default 20
      SALES_SCAN_MIN_DISCOUNT     default 15
      SALES_SCAN_MAX_ITEMS        default 30
    """
    timeout = env_int("SALES_SCAN_TIMEOUT_SECONDS", DEFAULT_TIMEOUT, 5, 60)
    min_discount = env_int("SALES_SCAN_MIN_DISCOUNT", DEFAULT_MIN_DISCOUNT, 0, 100)
    max_items = env_int("SALES_SCAN_MAX_ITEMS", DEFAULT_MAX_ITEMS, 1, 100)
    today = datetime.now(SGT).date()

    print("")
    print("=" * 72)
    print("SALES MULTI-SOURCE LIVE SCAN")
    print("=" * 72)
    print(f"Discovery pages:       {len(SOURCE_PAGES)}")
    print(f"Official index pages:  {len(OFFICIAL_SALES_INDEX_SOURCES)}")
    print(f"Official direct pages: {len(OFFICIAL_SALES_SINGLE_SOURCES)}")
    print(f"Minimum discount:      {min_discount}%")
    print(f"Maximum published:     {max_items}")
    print(f"Singapore date:        {today.isoformat()}")
    print("")

    all_items = []
    all_candidates = []
    succeeded = 0
    failed = 0

    # Existing EverydayOnSales discovery feed.
    for source in SOURCE_PAGES:
        print(f"Sales source: {source['name']}")
        try:
            raw_html = fetch_html(source["url"], timeout)
            candidates = extract_candidate_links(source, raw_html)
            all_candidates.extend(candidates)
            succeeded += 1
            print(f"  OK - candidate listings found: {len(candidates)}")
        except (HTTPError, URLError, Exception) as exc:
            failed += 1
            print(f"  FAILED - {type(exc).__name__}: {exc}")

    unique_candidates = {}
    for candidate in all_candidates:
        key = candidate["url"].rstrip("/").casefold()
        existing = unique_candidates.get(key)
        if existing is None or len(candidate["title"]) > len(existing["title"]):
            unique_candidates[key] = candidate

    for candidate in unique_candidates.values():
        item = build_item(candidate, today, min_discount)
        if item:
            all_items.append(enrich_discovery_item(item))

    # Official card / retailer index pages.
    for source in OFFICIAL_SALES_INDEX_SOURCES:
        print(f"Sales source: {source['name']}")
        try:
            raw_html = fetch_html(source["url"], timeout)
            items = parse_official_index(source, raw_html, min_discount)
            all_items.extend(items)
            succeeded += 1
            print(f"  OK - qualified deals found: {len(items)}")
        except (HTTPError, URLError, Exception) as exc:
            failed += 1
            print(f"  FAILED - {type(exc).__name__}: {exc}")

    # Dedicated direct / official pages.
    for source in OFFICIAL_SALES_SINGLE_SOURCES:
        print(f"Sales source: {source['name']}")
        try:
            raw_html = fetch_html(source["url"], timeout)
            items = parse_official_single(source, raw_html, min_discount, today)
            all_items.extend(items)
            succeeded += 1
            print(f"  OK - qualified deals found: {len(items)}")
        except (HTTPError, URLError, Exception) as exc:
            failed += 1
            print(f"  FAILED - {type(exc).__name__}: {exc}")

    if succeeded == 0 and failed > 0:
        previous = load_previous_live_sales()
        print("")
        print("SALES SCAN INTEGRITY CHECK")
        print(f"Sources succeeded:     {succeeded}")
        print(f"Sources failed:        {failed}")
        if previous:
            print(f"Preserving {len(previous)} previous live Sales result(s).")
            return previous
        print("No previous live Sales data exists. Returning no Sales deals.")
        return []

    if not all_items:
        previous = load_previous_live_sales()
        if previous:
            print("Live sources produced zero qualified items; preserving previous Sales data.")
            return previous

    observed_at = iso_now_sgt()
    items = select_diverse_sales(all_items, max_items)
    for item in items:
        item["observed_at"] = observed_at

    mix = {}
    for item in items:
        dtype = item.get("deal_type", "other")
        mix[dtype] = mix.get(dtype, 0) + 1

    print("")
    print("SALES SCAN INTEGRITY CHECK")
    print(f"Sources succeeded:     {succeeded}")
    print(f"Sources failed:        {failed}")
    print(f"Discovery candidates:  {len(unique_candidates)}")
    print(f"Published live deals:  {len(items)}")
    print(f"Deal type mix:         {mix}")
    print("SALES SCAN COMPLETED")
    print("")

    return items
