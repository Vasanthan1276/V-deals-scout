import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def read_json(relative_path, default=None):
    p = ROOT / relative_path
    if not p.exists():
        return default if default is not None else {}
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(relative_path, data):
    p = ROOT / relative_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def now_sgt():
    return datetime.now(ZoneInfo("Asia/Singapore"))


def iso_now_sgt():
    return now_sgt().isoformat(timespec="seconds")
