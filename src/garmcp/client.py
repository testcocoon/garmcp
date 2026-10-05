"""Client Garmin avec stockage local des données par date."""

from __future__ import annotations

import json
from datetime import date
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

    PAGE_SIZE = 100

    def get_activities(self, start: int = 0, limit: int = 10) -> list[dict[str, Any]]:
        """Activités à partir de l'index `start`, au plus `limit`.

        Interroge /activitylist-service/activities/search/activities
        avec ?start=<start>&limit=<limit>. Si limit dépasse 100 (maximum
        d'une requête Garmin), pagine automatiquement depuis `start`.
        """
        if limit <= 0:
            raise GarminAuthError("limit doit être un entier positif")
        if start < 0:
            raise GarminAuthError("start doit être un entier positif ou nul")
        if limit <= self.PAGE_SIZE:
            try:
                return self._client.get_activities(start, limit)
            except Exception as exc:
                raise GarminAuthError(f"Erreur Garmin (activités) : {exc}") from exc
        activities: list[dict[str, Any]] = []
        offset = start
        while len(activities) < limit:
            try:
                page = self._client.get_activities(offset, self.PAGE_SIZE)
            except Exception as exc:
                raise GarminAuthError(f"Erreur Garmin (activités, offset {offset}) : {exc}") from exc
            if not page:
                break
            activities.extend(page)
            if len(page) < self.PAGE_SIZE:
                break
            offset += self.PAGE_SIZE
        return activities[:limit]

    def get_all_activities(self, max_activities: int | None = None) -> list[dict[str, Any]]:
        """Toutes les activités, en paginant par requêtes de 100.

        Interroge /activitylist-service/activities/search/activities
        avec start=0, 100, 200, ... et limit=100 jusqu'à épuiser le
        compte total d'activités du compte (count_activities).

        Args:
            max_activities: Arrêter après ce nombre d'activités
                (None = télécharger tout l'historique).
        """
        try:
            total = self._client.count_activities()
        except Exception as exc:
            raise GarminAuthError(f"Erreur Garmin (compte d'activités) : {exc}") from exc
        if max_activities is not None:
            total = min(total, max(0, max_activities))

        activities: list[dict[str, Any]] = []
        start = 0
        while start < total:
            try:
                page = self._client.get_activities(start, self.PAGE_SIZE)
            except Exception as exc:
                raise GarminAuthError(
                    f"Erreur Garmin (activités, offset {start}) : {exc}"
                ) from exc
            if not page:
                break
            activities.extend(page)
            if len(page) < self.PAGE_SIZE:
                break
            start += self.PAGE_SIZE
        return activities[:total] if max_activities is not None else activities

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

    def get_body_composition(self, startdate: str, enddate: str | None = None) -> dict[str, Any]:
        """Composition corporelle (poids, IMC, masse musculaire...) entre deux dates."""
        try:
            return self._client.get_body_composition(startdate, enddate)
        except Exception as exc:
            raise GarminAuthError(f"Erreur Garmin (composition corporelle) : {exc}") from exc

    def get_body_weight_for_day(self, day: str) -> dict[str, Any]:
        """Poids et composition corporelle pour une journée donnée."""
        try:
            return self._client.get_body_composition(day)
        except Exception as exc:
            raise GarminAuthError(f"Erreur Garmin (poids du {day}) : {exc}") from exc

    def get_scheduled_workouts(self, year: int, month: int) -> dict[str, Any]:
        """Entraînements planifiés pour un mois donné (calendrier Garmin)."""
        try:
            return self._client.get_scheduled_workouts(year, month)
        except Exception as exc:
            raise GarminAuthError(
                f"Erreur Garmin (entraînements planifiés {month}/{year}) : {exc}"
            ) from exc

    def get_next_scheduled_workout(self) -> dict[str, Any]:
        """Prochain entraînement planifié (aujourd'hui ou plus tard)."""
        try:
            return self._client.get_next_scheduled_workout()
        except Exception as exc:
            raise GarminAuthError(
                f"Erreur Garmin (prochain entraînement planifié) : {exc}"
            ) from exc

    def get_scheduled_workout_by_id(self, workout_id: str | int) -> dict[str, Any]:
        """Détails d'un entraînement planifié par son identifiant."""
        try:
            return self._client.get_scheduled_workout_by_id(workout_id)
        except Exception as exc:
            raise GarminAuthError(
                f"Erreur Garmin (entraînement planifié {workout_id}) : {exc}"
            ) from exc
