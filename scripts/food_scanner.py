from __future__ import annotations

import hashlib
import html
import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from utils import iso_now_sgt
from deal_score import promo_score


# ---------------------------------------------------------------------------
# V&V Deals Scout - Live Food Scanner
#
# First live source: Eatigo Singapore.
# This scanner does NOT call Hotelbeds and therefore does not consume the
# Hotelbeds Evaluation quota.
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/152.0.0.0 Safari/537.36"
)

EATIGO_SOURCES = [
    {
        "name": "Eatigo Singapore - 50% Off Dinner",
        "url": "https://eatigo.com/en/regions/27/themes/15504",
        "meal_period": "dinner",
        "window_start": "17:30",
        "window_end": "21:30",
    },
    {
        "name": "Eatigo Singapore - 50% Off Lunch",
        "url": "https://eatigo.com/en/regions/27/themes/15505",
        "meal_period": "lunch",
        "window_start": "11:00",
        "window_end": "14:30",
    },
]

DEFAULT_TIMEOUT = 20
DEFAULT_MIN_DISCOUNT = 30
DEFAULT_MAX_ITEMS = 24

DATE_NIGHT_WORDS = (
    "hotel",
    "marriott",
    "shangri-la",
    "pan pacific",
    "copthorne",
    "holiday inn",
    "paradox",
    "dusit",
    "buffet",
    "terrace",
    "atrium",
    "mosella",
)

IGNORE_NAME_LINES = {
    "hot",
    "new",
    "more",
    "recommended",
    "today",
    "tomorrow",
    "all",
    "price",
    "discount",
    "rating",
    "party size",
    "now",
    "date",
    "time",
}

REPO_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_FOOD_PATH = REPO_ROOT / "data" / "food.json"


class TextExtractor(HTMLParser):
    """Dependency-free HTML-to-visible-text helper."""

    BLOCK_TAGS = {
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "p",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
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
        return response.read().decode("utf-8", errors="replace")


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
    value = re.sub(r"\s+", " ", value).strip(" -|•·")
    value = re.sub(r"\s+(?:HOT|NEW)$", "", value, flags=re.IGNORECASE).strip()
    return value


def plausible_name(value):
    if not value or len(value) < 3 or len(value) > 140:
        return False

    if value.casefold() in IGNORE_NAME_LINES:
        return False

    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?%?", value):
        return False

    if re.fullmatch(r"\d{1,2}:\d{2}", value):
        return False

    return any(char.isalpha() for char in value)


def reservation_count(value):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(k?)", value.lower().replace(",", ""))
    if not match:
        return None

    number = float(match.group(1))
    if match.group(2) == "k":
        number *= 1000

    return int(number)


def find_restaurants(lines):
    """
    Find Eatigo restaurant headers.

    Supported layouts:
      Restaurant Name 4.5 9.4k reservations

    and:
      Restaurant Name
      4.5
      9.4k reservations
    """
    direct_re = re.compile(
        r"^(?P<name>.+?)\s+"
        r"(?P<rating>[1-5](?:\.\d)?)\s+"
        r"(?P<count>\d+(?:\.\d+)?k?)\s+reservations$",
        re.IGNORECASE,
    )
    rating_re = re.compile(r"^[1-5](?:\.\d)?$")
    rating_count_re = re.compile(
        r"^(?P<rating>[1-5](?:\.\d)?)\s+"
        r"(?P<count>\d+(?:\.\d+)?k?)\s+reservations$",
        re.IGNORECASE,
    )
    count_re = re.compile(
        r"^(?P<count>\d+(?:\.\d+)?k?)\s+reservations$",
        re.IGNORECASE,
    )

    found = []

    for index, line in enumerate(lines):
        match = direct_re.match(line)
        if match:
            name = clean_name(match.group("name"))
            if plausible_name(name):
                found.append(
                    {
                        "start": index,
                        "name": name,
                        "rating": float(match.group("rating")),
                        "reservation_count": reservation_count(match.group("count")),
                    }
                )
            continue

        combined = rating_count_re.match(line)
        if combined and index >= 1:
            name = clean_name(lines[index - 1])
            if plausible_name(name):
                found.append(
                    {
                        "start": index - 1,
                        "name": name,
                        "rating": float(combined.group("rating")),
                        "reservation_count": reservation_count(combined.group("count")),
                    }
                )
            continue

        if index >= 2 and count_re.match(line) and rating_re.match(lines[index - 1]):
            name = clean_name(lines[index - 2])
            if plausible_name(name):
                found.append(
                    {
                        "start": index - 2,
                        "name": name,
                        "rating": float(lines[index - 1]),
                        "reservation_count": reservation_count(
                            count_re.match(line).group("count")
                        ),
                    }
                )

    unique = []
    seen = set()

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
    slot_re = re.compile(
        r"(?P<time>\d{1,2}:\d{2})\s*[-–—]\s*(?P<discount>\d{1,3})\s*%"
    )

    start_minutes = time_to_minutes(start_time)
    end_minutes = time_to_minutes(end_time)
    slots = []
    seen = set()

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


def stable_id(name, meal_period):
    value = f"eatigo|{name.casefold()}|{meal_period}".encode("utf-8")
    return "food-eatigo-" + hashlib.sha1(value).hexdigest()[:12]


def relevance_score(name, meal_period, rating, discount):
    score = 7.0
    score += 1.0 if meal_period == "dinner" else 0.5

    lowered = name.casefold()
    if any(word in lowered for word in DATE_NIGHT_WORDS):
        score += 0.75

    if rating >= 4.5:
        score += 0.5
    elif rating >= 4.2:
        score += 0.25

    if discount >= 50:
        score += 0.5
    elif discount >= 40:
        score += 0.25

    return round(min(score, 10.0), 1)


def parse_eatigo(source, raw_html, min_discount):
    lines = html_to_lines(raw_html)
    restaurants = find_restaurants(lines)
    items = []

    for position, restaurant in enumerate(restaurants):
        start = restaurant["start"]
        end = (
            restaurants[position + 1]["start"]
            if position + 1 < len(restaurants)
            else len(lines)
        )

        slots = extract_slots(
            lines[start:end],
            source["window_start"],
            source["window_end"],
        )

        if not slots:
            continue

        best_discount = max(discount for _, discount in slots)
        if best_discount < min_discount:
            continue

        best_times = sorted(
            {
                time_text
                for time_text, discount in slots
                if discount == best_discount
            },
            key=time_to_minutes,
        )

        rating = restaurant["rating"]
        meal = source["meal_period"]
        times_text = ", ".join(best_times[:4])

        description = (
            f"Up to {best_discount}% off {meal} time slots on Eatigo. "
            f"Rating {rating:.1f}/5."
        )
        if times_text:
            description += f" Best observed slot(s): {times_text}."
        description += " Verify the live slot and conditions before booking."

        item = {
            "id": stable_id(restaurant["name"], meal),
            "category": "food",
            "name": f"{restaurant['name']} — {meal.capitalize()}",
            "restaurant_name": restaurant["name"],
            "location": "Singapore",
            "description": description,
            "discount_percent": best_discount,
            "quality_score": round(min(10.0, rating * 2.0), 1),
            "relevance_score": relevance_score(
                restaurant["name"],
                meal,
                rating,
                best_discount,
            ),
            "rating": rating,
            "reservation_count": restaurant["reservation_count"],
            "meal_period": meal,
            "best_discount_times": best_times[:8],
            "source": "Eatigo Singapore",
            "source_detail": source["name"],
            "source_type": "official_promotion_page",
            "reference_source": "eatigo_live_page",
            "url": source["url"],
            "is_demo": False,
            "is_live": True,
            "price_type": "time_slot_discount",
        }

        items.append(item)

    return items


def load_previous_live_food():
    """
    If every live source is unreachable, keep the previous live Food dataset.
    Demo entries are never restored.
    """
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

    return [
        dict(item)
        for item in payload
        if isinstance(item, dict)
        and item.get("category") == "food"
        and not item.get("is_demo", False)
    ]


def scan_food():
    """
    Return live Singapore Food deals.

    Environment overrides:
      FOOD_SCAN_TIMEOUT_SECONDS  default 20
      FOOD_SCAN_MIN_DISCOUNT     default 30
      FOOD_SCAN_MAX_ITEMS        default 24
    """
    timeout = env_int("FOOD_SCAN_TIMEOUT_SECONDS", DEFAULT_TIMEOUT, 5, 60)
    min_discount = env_int(
        "FOOD_SCAN_MIN_DISCOUNT",
        DEFAULT_MIN_DISCOUNT,
        0,
        100,
    )
    max_items = env_int("FOOD_SCAN_MAX_ITEMS", DEFAULT_MAX_ITEMS, 1, 100)

    print("")
    print("=" * 68)
    print("FOOD LIVE SCAN")
    print("=" * 68)
    print(f"Sources planned:       {len(EATIGO_SOURCES)}")
    print(f"Minimum discount:      {min_discount}%")
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

        except HTTPError as exc:
            failed += 1
            print(f"  FAILED - HTTP {exc.code}: {exc.reason}")

        except URLError as exc:
            failed += 1
            print(f"  FAILED - network error: {exc.reason}")

        except Exception as exc:
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

    deduped = {}
    for item in all_items:
        existing = deduped.get(item["id"])
        if existing is None or item["discount_percent"] > existing["discount_percent"]:
            deduped[item["id"]] = item

    observed_at = iso_now_sgt()
    final_items = []

    for item in deduped.values():
        item["deal_score"] = promo_score(item, "food")
        item["observed_at"] = observed_at
        final_items.append(item)

    final_items.sort(
        key=lambda item: (
            item.get("deal_score", 0),
            item.get("discount_percent", 0),
            item.get("rating", 0),
        ),
        reverse=True,
    )

    final_items = final_items[:max_items]

    print("")
    print("FOOD SCAN INTEGRITY CHECK")
    print(f"Sources succeeded:     {succeeded}")
    print(f"Sources failed:        {failed}")
    print(f"Qualified live deals:  {len(final_items)}")
    print("FOOD SCAN COMPLETED")
    print("")

    return final_items
