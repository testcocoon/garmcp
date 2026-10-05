
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


class FakeBodyGarmin:
    def get_body_composition(self, startdate, enddate=None):
        if enddate is None:
            return {"date": startdate, "weight": 75.3, "bmi": 22.1}
        return {"startDate": startdate, "endDate": enddate, "totalWeight": 75.3}


def test_body_weight_for_day():
    client = GarminClient(FakeBodyGarmin())
    data = client.get_body_weight_for_day("2025-10-05")
    assert data["weight"] == 75.3
    assert data["date"] == "2025-10-05"


def test_body_composition_range():
    client = GarminClient(FakeBodyGarmin())
    data = client.get_body_composition("2025-09-28", "2025-10-05")
    assert data["startDate"] == "2025-09-28"
    assert data["endDate"] == "2025-10-05"


class FakePaginatedGarmin:
    """Simule 250 activités côté Garmin : pages de 100 max."""

    def __init__(self):
        self.total = 250
        self.calls = []

    def count_activities(self):
        return self.total

    def get_activities(self, start, limit):
        self.calls.append((start, limit))
        page = [{"activityId": i} for i in range(start, min(start + limit, self.total))]
        return page


def test_get_all_activities_paginates():
    fake = FakePaginatedGarmin()
    client = GarminClient(fake)
    activities = client.get_all_activities()
    assert len(activities) == 250
    # pages demandees : start=0, 100, 200 (3 requetes de 100)
    assert fake.calls == [(0, 100), (100, 100), (200, 100)]


def test_get_all_activities_with_max():
    fake = FakePaginatedGarmin()
    client = GarminClient(fake)
    activities = client.get_all_activities(max_activities=150)
    assert len(activities) == 150
    assert fake.calls == [(0, 100), (100, 100)]


def test_get_all_activities_stops_on_short_page():
    class ShortFake:
        def count_activities(self):
            return 500  # compte annonce plus grand que la realite

        def get_activities(self, start, limit):
            if start == 0:
                return [{"id": 1}]  # page incomplete -> arret anticipe
            return []

    client = GarminClient(ShortFake())
    activities = client.get_all_activities()
    assert len(activities) == 1


def test_get_activities_delegates_over_100():
    fake = FakePaginatedGarmin()
    client = GarminClient(fake)
    activities = client.get_activities(limit=150)
    assert len(activities) == 150
    # delegation vers la pagination : requetes start=0 puis 100
    assert fake.calls == [(0, 100), (100, 100)]


def test_get_activities_single_page_under_100():
    class SingleFake:
        def __init__(self):
            self.calls = []

        def get_activities(self, start, limit):
            self.calls.append((start, limit))
            return [{"id": 1}] * limit

    fake = SingleFake()
    client = GarminClient(fake)
    activities = client.get_activities(limit=50)
    assert len(activities) == 50
    assert fake.calls == [(0, 50)]  # une seule requete, pas de count


def test_get_activities_invalid_limit():
    client = GarminClient(FakePaginatedGarmin())
    import pytest

    with pytest.raises(GarminAuthError):
        client.get_activities(limit=0)


def test_get_activities_with_start_offset():
    fake = FakePaginatedGarmin()
    client = GarminClient(fake)
    activities = client.get_activities(start=120, limit=10)
    assert activities == [{"activityId": i} for i in range(120, 130)]
    assert fake.calls == [(120, 10)]  # une seule requete avec le start demande


def test_get_activities_with_start_paginates():
    fake = FakePaginatedGarmin()
    client = GarminClient(fake)
    activities = client.get_activities(start=120, limit=150)
    assert len(activities) == 130  # il reste 130 activites a partir de l'offset 120
    assert fake.calls == [(120, 100), (220, 100)]


def test_get_activities_invalid_start():
    client = GarminClient(FakePaginatedGarmin())
    import pytest

    with pytest.raises(GarminAuthError):
        client.get_activities(start=-1)
