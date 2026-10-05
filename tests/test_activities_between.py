from datetime import date, timedelta

import pytest

from garmcp.auth import GarminAuthError
from garmcp.client import GarminClient


def make_client(dates):
    """Client factice : la liste des activités va de la plus récente à la plus ancienne."""

    class FakeGarmin:
        def __init__(self, dates):
            self.dates = dates
            self.calls = []

        def get_activities(self, start, limit):
            self.calls.append((start, limit))
            return [
                {"startTimeLocal": f"{d}T10:00:00.0", "activityId": 1000 + i}
                for i, d in enumerate(self.dates[start : start + limit])
            ]

    return GarminClient(FakeGarmin(dates))


def d(n):
    return (date(2025, 6, 30) - timedelta(days=n)).isoformat()


def test_between_fetches_full_range():
    dates = [d(i) for i in range(40)] + ["2024-01-01"] * 5
    client = make_client(dates)
    result = client.get_activities_between(d(10), d(5))
    assert [a["startTimeLocal"][:10] for a in result] == [d(i) for i in range(5, 11)]
    assert len(result) == 6


def test_between_inclusive_bounds():
    dates = [d(i) for i in range(20)]
    result = make_client(dates).get_activities_between(d(0), d(0))
    assert len(result) == 1
    assert result[0]["startTimeLocal"][:10] == d(0)


def test_between_empty_when_out_of_range():
    dates = [d(i) for i in range(10)]
    client = make_client(dates)
    assert client.get_activities_between(d(-2), d(-5)) == []
    assert client.get_activities_between("2030-01-01", "2030-12-31") == []
    assert client.get_activities_between("2020-01-01", "2020-12-31") == []


def test_between_invalid_range():
    with pytest.raises(GarminAuthError):
        make_client([d(0)]).get_activities_between(d(5), d(10))


def test_between_duplicates_same_date():
    dates = [d(3), d(3), d(3), d(7), d(7), d(20)]
    result = make_client(dates).get_activities_between(d(7), d(3))
    assert len(result) == 5


def test_dichotomy_limits_probes():
    dates = [d(i) for i in range(200)]
    client = make_client(dates)
    client.get_activities_between(d(150), d(140))
    single_probes = [c for c in client._client.calls if c[1] == 1]
    assert len(single_probes) < 40
