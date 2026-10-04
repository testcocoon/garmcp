import asyncio
import json
from datetime import date, timedelta

from garmcp import server


def test_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    expected = {
        "garmin_login",
        "garmin_logout",
        "garmin_status",
        "garmin_daily_summary",
        "garmin_activities",
        "garmin_activity",
        "garmin_sleep",
        "garmin_steps",
        "garmin_heart_rate",
        "garmin_body_battery",
        "garmin_stress",
        "garmin_weight",
        "garmin_devices",
    }
    assert expected.issubset(names)


def test_json_serialization():
    assert server._json({"a": 1}) == json.dumps({"a": 1}, ensure_ascii=False, indent=2)
    assert server._json(None) == "{}"
    assert server._json("plain text") == "plain text"


def test_days_ago():
    assert server._days_ago(0) == date.today().isoformat()
    assert server._days_ago(1) == (date.today() - timedelta(days=1)).isoformat()
