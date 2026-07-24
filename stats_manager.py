"""
Usage-time stats.

Tracks how long "blocking active" sessions (study timer and/or Lock-In
Mode — whichever, or both together, without double-counting overlaps)
have run, bucketed by calendar day, so the Stats page can show today's
total plus daily/monthly/yearly breakdowns of focused time.
"""
import json
import os
from datetime import date, datetime, timedelta

import app_paths

app_paths.migrate_legacy_file("stats.json", os.path.dirname(__file__))
STATS_FILE = os.path.join(app_paths.data_dir(), "stats.json")


def load_stats() -> dict:
    """{'daily': {'YYYY-MM-DD': seconds, ...}}"""
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r") as f:
                data = json.load(f)
            data.setdefault("daily", {})
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"daily": {}}


def save_stats(data: dict) -> None:
    app_paths.atomic_write_json(STATS_FILE, data)


def add_focused_seconds(seconds: float, on_date: date | None = None) -> None:
    """Add elapsed focused-session time to a day's bucket (today by default)."""
    if seconds <= 0:
        return
    data = load_stats()
    key = (on_date or date.today()).isoformat()
    data["daily"][key] = data["daily"].get(key, 0) + seconds
    save_stats(data)


def _parse(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


def get_summary() -> dict:
    """
    Returns today / this-week / this-month / this-year / all-time totals
    (in seconds), plus a last-14-days daily breakdown, a last-12-months
    breakdown, and a full yearly breakdown.
    """
    data = load_stats()
    daily = data.get("daily", {})
    today = date.today()

    def sum_where(pred) -> float:
        return sum(v for k, v in daily.items() if pred(_parse(k)))

    today_total = daily.get(today.isoformat(), 0)
    week_total = sum_where(lambda d: 0 <= (today - d).days < 7)
    month_total = sum_where(lambda d: d.year == today.year and d.month == today.month)
    year_total = sum_where(lambda d: d.year == today.year)
    all_time_total = sum(daily.values())

    last_14_days = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        last_14_days.append((d.isoformat(), daily.get(d.isoformat(), 0)))

    monthly = {}
    for k, v in daily.items():
        d = _parse(k)
        mk = f"{d.year}-{d.month:02d}"
        monthly[mk] = monthly.get(mk, 0) + v
    monthly_sorted = sorted(monthly.items())[-12:]

    yearly = {}
    for k, v in daily.items():
        d = _parse(k)
        yearly[d.year] = yearly.get(d.year, 0) + v
    yearly_sorted = sorted(yearly.items())

    return {
        "today": today_total,
        "week": week_total,
        "month": month_total,
        "year": year_total,
        "all_time": all_time_total,
        "last_14_days": last_14_days,
        "monthly": monthly_sorted,
        "yearly": yearly_sorted,
    }


def format_duration(seconds: float) -> str:
    """3725 -> '1h 2m'. Whole seconds only shown under a minute."""
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s" if s and m < 10 else f"{m}m"
    return f"{s}s"


MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
