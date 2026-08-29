import os
import ssl
import json
import time
import base64
import hashlib
import statistics
import tempfile
import urllib.request
import urllib.error

from datetime import timedelta
from pathlib import Path

from utils import read_json, iso_now_sgt, now_sgt
from deal_score import hotel_score


API_URL = (
    "https://api-mtls.test.hotelbeds.com/"
    "hotel-api/1.0/hotels"
)


def _require_secret(name):
    value = os.environ.get(name)

    if not value:
        raise RuntimeError(
            f"Required GitHub secret/environment variable "
            f"{name} is missing."
        )

    return value


def _build_ssl_context():
    cert_b64 = _require_secret(
        "HOTELBEDS_CLIENT_CERT_B64"
    )

    key_b64 = _require_secret(
        "HOTELBEDS_CLIENT_KEY_B64"
    )

    key_password = _require_secret(
        "HOTELBEDS_CLIENT_KEY_PASSWORD"
    )

    cert_bytes = base64.b64decode(cert_b64)
    key_bytes = base64.b64decode(key_b64)

    context = ssl.create_default_context()

    with tempfile.TemporaryDirectory() as temp_dir:
        cert_path = Path(temp_dir) / "client.pem"
        key_path = Path(temp_dir) / "client.key"

        cert_path.write_bytes(cert_bytes)
        key_path.write_bytes(key_bytes)

        context.load_cert_chain(
            certfile=str(cert_path),
            keyfile=str(key_path),
            password=key_password,
        )

    return context


def _signature():
    api_key = _require_secret(
        "HOTELBEDS_API_KEY"
    )

    secret = _require_secret(
        "HOTELBEDS_SECRET"
    )

    timestamp = str(int(time.time()))

    return hashlib.sha256(
        f"{api_key}{secret}{timestamp}".encode(
            "utf-8"
        )
    ).hexdigest()


def _next_weekday(start_date, weekday):
    """
    Monday = 0
    Friday = 4
    Saturday = 5

    Always returns a future date.
    """
    days = (
        weekday - start_date.weekday()
    ) % 7

    if days == 0:
        days = 7

    return start_date + timedelta(days=days)


def _search_windows(profile, weeks):
    today = now_sgt().date()

    first = _next_weekday(
        today,
        int(profile["checkin_weekday"]),
    )

    nights = int(profile["nights"])

    windows = []

    for week in range(weeks):
        check_in = first + timedelta(
            weeks=week
        )

        check_out = check_in + timedelta(
            days=nights
        )

        windows.append(
            {
                "check_in": check_in,
                "check_out": check_out,
                "nights": nights,
            }
        )

    return windows


def _availability_request(
    context,
    check_in,
    check_out,
    hotel_codes,
):
    api_key = _require_secret(
        "HOTELBEDS_API_KEY"
    )

    payload = {
        "stay": {
            "checkIn": str(check_in),
            "checkOut": str(check_out),
        },
        "occupancies": [
            {
                "rooms": 1,
                "adults": 2,
                "children": 0,
            }
        ],
        "hotels": {
            "hotel": hotel_codes
        },
    }

    body = json.dumps(
        payload
    ).encode("utf-8")

    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "Content-Type": "application/json",
            "Api-key": api_key,
            "X-Signature": _signature(),
            "User-Agent": "V-deals-scout/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            context=context,
            timeout=60,
        ) as response:

            raw = response.read()

            if (
                response.headers.get(
                    "Content-Encoding"
                )
                == "gzip"
            ):
                import gzip

                raw = gzip.decompress(raw)

            data = json.loads(
                raw.decode("utf-8")
            )

            return response.status, data

    except urllib.error.HTTPError as exc:
        message = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        print(
            f"Hotelbeds HTTP {exc.code}: "
            f"{message[:1000]}"
        )

        return exc.code, None

    except Exception as exc:
        print(
            f"Hotelbeds request failed: {exc}"
        )

        return 0, None


def _extract_hotels(data):
    if not isinstance(data, dict):
        return [], "SGD"

    block = data.get(
        "hotels",
        {}
    )

    currency = "SGD"

    if isinstance(block, dict):
        currency = (
            block.get("currency")
            or currency
        )

        hotels = block.get(
            "hotels",
            []
        )

        if isinstance(hotels, list):
            return hotels, currency

    return [], currency


def _rate_value(rate):
    """
    Hotelbeds Evaluation/Booking API primarily
    provides a net amount.

    Use sellingRate if explicitly supplied;
    otherwise use net.
    """
    raw = (
        rate.get("sellingRate")
        or rate.get("net")
    )

    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _cheapest_rate(hotel):
    cheapest = None

    for room in hotel.get(
        "rooms",
        []
    ) or []:

        for rate in room.get(
            "rates",
            []
        ) or []:

            value = _rate_value(rate)

            if value is None:
                continue

            if (
                cheapest is None
                or value
                < cheapest["value"]
            ):
                cheapest = {
                    "value": value,
                    "room_name": (
                        room.get("name")
                        or room.get("code")
                        or ""
                    ),
                    "board_name": (
                        rate.get("boardName")
                        or rate.get("boardCode")
                        or ""
                    ),
                    "board_code": (
                        rate.get("boardCode")
                        or ""
                    ),
                    "rate_class": (
                        rate.get("rateClass")
                        or ""
                    ),
                    "rate_type": (
                        rate.get("rateType")
                        or ""
                    ),
                    "cancellation_policies": (
                        rate.get(
                            "cancellationPolicies"
                        )
                        or []
                    ),
                }

    return cheapest


def _includes_breakfast(rate):
    board = (
        rate.get(
            "board_name",
            ""
        )
        .upper()
    )

    board_code = (
        rate.get(
            "board_code",
            ""
        )
        .upper()
    )

    if "BREAKFAST" in board:
        return True

    return board_code in {
        "BB",
        "HB",
        "FB",
        "AI",
    }


def _flexible_cancellation(rate):
    rate_class = (
        rate.get(
            "rate_class",
            ""
        )
        .upper()
    )

    if "NRF" in rate_class:
        return False

    policies = rate.get(
        "cancellation_policies",
        []
    )

    return bool(policies)


def _historical_median(
    hotel_name,
    currency,
):
    history = read_json(
        "data/history.json",
        {"observations": []},
    )

    prices = []

    for observation in history.get(
        "observations",
        []
    ):
        if observation.get(
            "is_demo"
        ):
            continue

        if (
            observation.get("name")
            != hotel_name
        ):
            continue

        if (
            observation.get(
                "currency"
            )
            != currency
        ):
            continue

        value = observation.get(
            "price"
        )

        try:
            value = float(value)
        except (TypeError, ValueError):
            continue

        if value > 0:
            prices.append(value)

    if len(prices) < 3:
        return None

    return round(
        statistics.median(
            prices[-30:]
        ),
        2,
    )


def _apply_reference_prices(items):
    """
    Prefer the historical median.

    Until enough history exists, use the
    median of comparable hotels for the
    same destination and dates.
    """
    groups = {}

    for item in items:
        key = (
            item["destination"],
            item["check_in"],
            item["check_out"],
            item["currency"],
        )

        groups.setdefault(
            key,
            []
        ).append(item)

    for group in groups.values():
        peer_prices = [
            float(x["current_price"])
            for x in group
            if x.get("current_price")
        ]

        peer_median = None

        if peer_prices:
            peer_median = round(
                statistics.median(
                    peer_prices
                ),
                2,
            )

        for item in group:
            historical = (
                _historical_median(
                    item["name"],
                    item["currency"],
                )
            )

            if historical:
                item[
                    "historical_median"
                ] = historical

                item[
                    "reference_source"
                ] = "observed price history"

            elif peer_median:
                item[
                    "historical_median"
                ] = peer_median

                item[
                    "reference_source"
                ] = (
                    "same-date peer median"
                )

            else:
                item[
                    "historical_median"
                ] = item[
                    "current_price"
                ]

                item[
                    "reference_source"
                ] = "current observation"


def _scan_live():
    cfg = read_json(
        "config/hotels.json",
        {},
    )

    weeks = int(
        cfg.get(
            "search_weeks",
            8,
        )
    )

    max_requests = int(
        cfg.get(
            "max_requests_per_run",
            24,
        )
    )

    watchlist = cfg.get(
        "watchlist",
        []
    )

    profiles = cfg.get(
        "search_profiles",
        []
    )

    by_code = {
        int(h["hotelbeds_code"]): h
        for h in watchlist
        if h.get("hotelbeds_code")
    }

    context = _build_ssl_context()

    results = []
    request_count = 0
    successful_requests = 0

    for profile in profiles:

        destinations = set(
            profile.get(
                "destinations",
                []
            )
        )

        relevant = [
            h
            for h in watchlist
            if h.get(
                "destination"
            ) in destinations
        ]

        hotel_codes = [
            int(h["hotelbeds_code"])
            for h in relevant
        ]

        if not hotel_codes:
            continue

        windows = _search_windows(
            profile,
            weeks,
        )

        for window in windows:

            if (
                request_count
                >= max_requests
            ):
                print(
                    "Hotelbeds request "
                    "safety limit reached."
                )
                break

            print()
            print(
                f"Scanning "
                f"{profile['name']}: "
                f"{window['check_in']} "
                f"→ {window['check_out']} "
                f"({len(hotel_codes)} hotels)"
            )

            status, data = (
                _availability_request(
                    context,
                    window["check_in"],
                    window["check_out"],
                    hotel_codes,
                )
            )

            request_count += 1

            if (
                status != 200
                or not data
            ):
                continue

            successful_requests += 1

            hotels, currency = (
                _extract_hotels(data)
            )

            print(
                f"Availability returned: "
                f"{len(hotels)} hotels"
            )

            for hotel in hotels:

                try:
                    code = int(
                        hotel.get("code")
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    continue

                config_hotel = (
                    by_code.get(code)
                )

                if not config_hotel:
                    continue

                rate = _cheapest_rate(
                    hotel
                )

                if not rate:
                    continue

                nights = int(
                    window["nights"]
                )

                total_price = round(
                    rate["value"],
                    2,
                )

                nightly_price = round(
                    total_price / nights,
                    2,
                )

                item = {
                    "id": (
                        f"hotelbeds-"
                        f"{code}-"
                        f"{window['check_in']}"
                    ),
                    "category": "hotel",
                    "sub_category": (
                        profile[
                            "sub_category"
                        ]
                    ),
                    "provider": "hotelbeds",
                    "provider_environment": (
                        "evaluation"
                    ),
                    "hotelbeds_code": code,
                    "name": (
                        hotel.get("name")
                        or config_hotel[
                            "name"
                        ]
                    ),
                    "destination": (
                        config_hotel[
                            "destination"
                        ]
                    ),
                    "destination_code": (
                        config_hotel[
                            "destination_code"
                        ]
                    ),
                    "check_in": str(
                        window["check_in"]
                    ),
                    "check_out": str(
                        window["check_out"]
                    ),
                    "nights": nights,
                    "stars": (
                        config_hotel.get(
                            "stars",
                            5,
                        )
                    ),
                    "current_price": (
                        nightly_price
                    ),
                    "total_price": (
                        total_price
                    ),
                    "currency": currency,
                    "room_name": (
                        rate[
                            "room_name"
                        ]
                    ),
                    "board_name": (
                        rate[
                            "board_name"
                        ]
                    ),
                    "breakfast": (
                        _includes_breakfast(
                            rate
                        )
                    ),
                    "lounge": False,
                    "bathtub": False,
                    "quiet_relaxing": True,
                    "couples_friendly": True,
                    "good_location": True,
                    "flexible_cancellation": (
                        _flexible_cancellation(
                            rate
                        )
                    ),
                    "convenient_date": True,
                    "booking_url": "",
                    "source": (
                        "Hotelbeds "
                        "Evaluation API"
                    ),
                    "price_type": (
                        "Hotelbeds "
                        "evaluation/net rate"
                    ),
                    "is_demo": False,
                    "is_evaluation": True,
                    "observed_at": (
                        iso_now_sgt()
                    ),
                }

                results.append(item)

            time.sleep(0.3)

    print()
    print(
        f"Hotelbeds requests: "
        f"{request_count}"
    )

    print(
        f"Successful requests: "
        f"{successful_requests}"
    )

    print(
        f"Available hotel/date "
        f"combinations: "
        f"{len(results)}"
    )

    if successful_requests == 0:
        raise RuntimeError(
            "All Hotelbeds availability "
            "requests failed."
        )

    _apply_reference_prices(
        results
    )

    for item in results:
        item["deal_score"] = (
            hotel_score(item)
        )

    results.sort(
        key=lambda x: (
            -x.get(
                "deal_score",
                0
            ),
            x.get(
                "current_price",
                999999,
            ),
        )
    )

    return results


def scan_hotels():
    cfg = read_json(
        "config/hotels.json",
        {},
    )

    mode = cfg.get(
        "provider_mode",
        "demo",
    )

    if mode != "hotelbeds":
        raise RuntimeError(
            "Hotel scanner is configured "
            f"for unsupported mode: {mode}"
        )

    return _scan_live()
