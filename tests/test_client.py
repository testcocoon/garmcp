
import pytest

from garmcp.auth import GarminAuthError
from garmcp.client import GarminClient


class FakeGarmin:
    def get_scheduled_workouts(self, year, month):
        return {"calendarItems": [{"itemType": "workout", "date": f"{year}-{month:02d}-05"}]}

    def get_next_scheduled_workout(self):
        return {"itemType": "workout", "date": "2025-10-06"}

    def get_scheduled_workout_by_id(self, wid):
        if wid == "404":
            raise RuntimeError("introuvable")
        return {"id": wid, "itemType": "workout"}


def test_scheduled_workouts():
    client = GarminClient(FakeGarmin())
    data = client.get_scheduled_workouts(2025, 10)
    assert data["calendarItems"][0]["date"] == "2025-10-05"


def test_next_scheduled_workout():
    client = GarminClient(FakeGarmin())
    data = client.get_next_scheduled_workout()
    assert data["date"] == "2025-10-06"


def test_scheduled_workout_by_id():
    client = GarminClient(FakeGarmin())
    data = client.get_scheduled_workout_by_id("123")
    assert data["id"] == "123"


def test_scheduled_workout_error_wrapped():
    client = GarminClient(FakeGarmin())
    with pytest.raises(GarminAuthError):
        client.get_scheduled_workout_by_id("404")
