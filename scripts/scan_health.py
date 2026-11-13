"""Public scan status contains no raw exceptions, headers or credentials."""
from utils import iso_now_sgt, read_json, write_json


class EmptyHotelScan(RuntimeError):
    """A complete but suspicious zero-result hotel scan: retain prior data."""


class ScanResult(list):
    def __init__(self, items, sources, retained=False):
        super().__init__(items)
        self.sources = sources
        self.retained = retained
        failures = sum(s["status"] == "failed" for s in sources)
        self.state = ("failed_retained" if retained and items else "failed") if failures == len(sources) and failures else (
            "partial" if failures else "success" if items else "empty")


def source_record(source, count=None, failed=False):
    return {"name": source["name"], "url": source["url"],
            "status": "failed" if failed else "success" if count else "empty",
            "results": count, "last_attempt": iso_now_sgt()}


def record_scan(category, result=None, state=None, previous_payload=None):
    payload = read_json("data/scan-status.json", {"sources": {}})
    old = payload.setdefault("sources", {}).get(category, {})
    previous_data = previous_payload if previous_payload is not None else read_json(f"data/{category}.json", {})
    now = iso_now_sgt()
    status = state or getattr(result, "state", "success" if result else "empty")
    retained = status in {"failed_retained", "empty_retained", "failed"}
    previous_success = old.get("last_success") or previous_data.get("updated_at")
    source_rows = getattr(result, "sources", [])
    old_rows = {r.get("url"): r for r in old.get("sources", [])}
    for row in source_rows:
        row["last_success"] = (old_rows.get(row["url"], {}).get("last_success")
                               if row["status"] == "failed" else row["last_attempt"])
    entry = {"state": status, "last_attempt": now,
             "last_success": previous_success if retained or status == "partial" else now,
             "last_partial": now if status == "partial" else old.get("last_partial"),
             "data_updated_at": previous_data.get("updated_at") if retained else now,
             "retained_data": retained and bool(previous_data.get("items")),
             "result_count": len(result) if result is not None else None,
             "sources": source_rows}
    if retained:
        entry["message"] = ("All requests completed with no hotel results; previous data retained for review."
                            if status == "empty_retained" else "Refresh failed or was incomplete; previous data retained where available.")
    elif status == "partial":
        entry["message"] = "Some sources failed. Results cover successful sources only."
    elif status == "empty":
        entry["message"] = "Sources fetched successfully; no qualifying offers parsed. This does not prove no offers exist."
    payload["sources"][category] = entry
    payload["updated_at"] = now
    write_json("data/scan-status.json", payload)
    return entry


def data_time(result, previous, current):
    return previous if getattr(result, "retained", False) else current
