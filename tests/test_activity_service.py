from __future__ import annotations

import unittest
from unittest.mock import patch

from mcp_server.models.enums import SortField, SortOrder, SportType
from mcp_server.services import activity_service


def _activity(
    activity_id: int,
    name: str,
    distance: float,
    sport_type: str,
    start_date: str,
) -> dict:
    return {
        "id": activity_id,
        "name": name,
        "distance": distance,
        "moving_time": 1800,
        "elapsed_time": 1800,
        "total_elevation_gain": 0.0,
        "sport_type": sport_type,
        "start_date": start_date,
        "start_date_local": start_date,
        "timezone": "(GMT+00:00) UTC",
        "average_speed": 3.0,
    }


class ListActivitiesTests(unittest.TestCase):
    def test_extreme_sort_scans_before_slicing(self) -> None:
        pages = {
            1: [
                _activity(1, "recent short run", 5_000.0, "Run", "2026-06-03T06:00:00Z"),
                _activity(2, "recent ride", 40_000.0, "Ride", "2026-06-02T06:00:00Z"),
            ],
            2: [
                _activity(3, "older long run", 17_000.0, "Run", "2026-05-23T06:00:00Z"),
            ],
        }
        calls: list[dict] = []

        def fake_get(_endpoint: str, params: dict) -> list[dict]:
            calls.append(params.copy())
            return pages.get(params["page"], [])

        with (
            patch.object(activity_service, "_API_BATCH_SIZE", 2),
            patch.object(activity_service, "get", side_effect=fake_get),
        ):
            result = activity_service.list_activities(
                per_page=1,
                sport_types=[SportType.RUN],
                sort_by=SortField.DISTANCE,
                sort_order=SortOrder.DESC,
            )

        self.assertEqual(result[0]["id"], 3)
        self.assertEqual(result[0]["distance_km"], 17.0)
        self.assertEqual([call["page"] for call in calls], [1, 2])

    def test_default_date_desc_filter_can_stop_after_enough_matches(self) -> None:
        pages = {
            1: [
                _activity(1, "recent short run", 5_000.0, "Run", "2026-06-03T06:00:00Z"),
                _activity(2, "recent ride", 40_000.0, "Ride", "2026-06-02T06:00:00Z"),
            ],
            2: [
                _activity(3, "older long run", 17_000.0, "Run", "2026-05-23T06:00:00Z"),
            ],
        }
        calls: list[dict] = []

        def fake_get(_endpoint: str, params: dict) -> list[dict]:
            calls.append(params.copy())
            return pages.get(params["page"], [])

        with (
            patch.object(activity_service, "_API_BATCH_SIZE", 2),
            patch.object(activity_service, "get", side_effect=fake_get),
        ):
            result = activity_service.list_activities(
                per_page=1,
                sport_types=[SportType.RUN],
            )

        self.assertEqual(result[0]["id"], 1)
        self.assertEqual([call["page"] for call in calls], [1])


if __name__ == "__main__":
    unittest.main()
