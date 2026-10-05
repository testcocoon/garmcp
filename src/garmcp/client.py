"""Client Garmin avec stockage local des données par date."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from garminconnect import Garmin

from .auth import GarminAuthError

DATA_DIR = Path.home() / ".garmcp"


class GarminClient:
    """Enveloppe le client garminconnect avec un cache JSON local optionnel."""

    def __init__(self, client: Garmin) -> None:
        self._client = client

    def get(self) -> Garmin:
        """Retourne le client garminconnect brut."""
        return self._client

    def _cache_path(self, kind: str, day: str) -> Path:
        return DATA_DIR / kind / f"{day}.json"

    def _load_cache(self, kind: str, day: str) -> dict[str, Any] | None:
        path = self._cache_path(kind, day)
        if path.exists():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                return None
        return None

    def _save_cache(self, kind: str, day: str, data: dict[str, Any]) -> None:
        path = self._cache_path(kind, day)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False))

    def _get_by_date(self, kind: str, fetch, day: str, cache: bool = False) -> dict[str, Any]:
        """Récupère une donnée datée, via le cache local si activé."""
        if cache:
            cached = self._load_cache(kind, day)
            if cached is not None:
                return cached
        try:
            data = fetch(day)
        except Exception as exc:
            raise GarminAuthError(f"Erreur Garmin ({kind}, {day}) : {exc}") from exc
        if cache and day != date.today().isoformat():
            self._save_cache(kind, day, data)
        return data

    def get_summary(self, day: str, cache: bool = False) -> dict[str, Any]:
        return self._get_by_date("summary", self._client.get_user_summary, day, cache)

    def get_sleep(self, day: str, cache: bool = False) -> dict[str, Any]:
        return self._get_by_date("sleep", self._client.get_sleep_data, day, cache)

    def get_steps(self, day: str, cache: bool = False) -> dict[str, Any]:
        summary = self.get_summary(day, cache)
        return {
            "date": summary.get("calendarDate"),
            "steps": summary.get("totalSteps"),
            "goal": summary.get("dailyStepGoal"),
        }

    def get_heart_rate(self, day: str, cache: bool = False) -> dict[str, Any]:
        return self._get_by_date("heart_rate", self._client.get_heart_rates, day, cache)

    def get_body_battery(self, day: str, cache: bool = False) -> dict[str, Any]:
        return self._get_by_date("body_battery", self._client.get_body_battery, day, cache)

    def get_stress(self, day: str, cache: bool = False) -> dict[str, Any]:
        return self._get_by_date("stress", self._client.get_stress_data, day, cache)

    def get_activities(self, limit: int = 10) -> list[dict[str, Any]]:
        try:
            return self._client.get_activities(0, max(1, min(limit, 100)))
        except Exception as exc:
            raise GarminAuthError(f"Erreur Garmin (activités) : {exc}") from exc

    def _activity_date_at(self, index: int, probes: dict[int, str | None]) -> str | None:
        """Date de d\u00e9but de l'activit\u00e9 \u00e0 l'index donn\u00e9 (None si hors liste)."""
        if index not in probes:
            try:
                page = self._client.get_activities(index, 1)
            except Exception as exc:
                raise GarminAuthError(f"Erreur Garmin (activit\u00e9s, index {index}) : {exc}") from exc
            probes[index] = self._start_date(page[0]) if page else None
        return probes[index]

    @staticmethod
    def _start_date(activity: dict[str, Any]) -> str:
        raw = activity.get("startTimeLocal") or activity.get("startTimeGMT") or ""
        return str(raw)[:10]

    def _dichotomy(self, target: str, probes: dict[int, str | None]) -> int:
        """Premier index dont la date est strictement ant\u00e9rieure \u00e0 `target`.

        Les activit\u00e9s \u00e9tant tri\u00e9es de la plus r\u00e9cente \u00e0 la plus ancienne,
        recherche exponentielle puis dichotomie sur cet index.
        """
        hi = 1
        while True:
            day = self._activity_date_at(hi, probes)
            if day is None or day < target:
                break
            hi *= 2
        lo = hi // 2
        while lo < hi:
            mid = (lo + hi) // 2
            day = self._activity_date_at(mid, probes)
            if day is None or day < target:
                hi = mid
            else:
                lo = mid + 1
        return lo

    def get_activities_between(self, start: str, end: str) -> list[dict[str, Any]]:
        """Activit\u00e9s entre deux dates (incluses), bornes d\u00e9termin\u00e9es par dichotomie.

        Args:
            start: Date de d\u00e9but au format ISO (YYYY-MM-DD), incluse.
            end: Date de fin au format ISO (YYYY-MM-DD), incluse.
        """
        if date.fromisoformat(start) > date.fromisoformat(end):
            raise GarminAuthError("Date de d\u00e9but post\u00e9rieure \u00e0 la date de fin.")
        probes: dict[int, str | None] = {}
        first = self._activity_date_at(0, probes)
        if first is None or first < start:
            return []
        end_exclusive = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
        begin = self._dichotomy(end_exclusive, probes)
        stop = self._dichotomy(start, probes)
        activities: list[dict[str, Any]] = []
        index = begin
        while index < stop:
            try:
                page = self._client.get_activities(index, 100)
            except Exception as exc:
                raise GarminAuthError(f"Erreur Garmin (activit\u00e9s, index {index}) : {exc}") from exc
            if not page:
                break
            activities.extend(page)
            index += len(page)
        return [a for a in activities if start <= self._start_date(a) <= end]

    def get_activity(self, activity_id: str | int) -> dict[str, Any]:
        try:
            return self._client.get_activity(activity_id)
        except Exception as exc:
            raise GarminAuthError(f"Erreur Garmin (activité {activity_id}) : {exc}") from exc

    def get_devices(self) -> list[dict[str, Any]]:
        try:
            return self._client.get_devices()
        except Exception as exc:
            raise GarminAuthError(f"Erreur Garmin (appareils) : {exc}") from exc

    def get_body_weight(self) -> list[dict[str, Any]]:
        try:
            return self._client.get_body_weight()
        except Exception as exc:
            raise GarminAuthError(f"Erreur Garmin (poids) : {exc}") from exc
