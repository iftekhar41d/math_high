"""The walking-skeleton round trip: SPA -> API -> DB, plus the liveness probe."""

from datetime import timedelta


def test_health_is_a_dependency_free_liveness_probe(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_meta_round_trips_through_the_db_and_the_clock(client, fake_clock):
    response = client.get("/meta")

    assert response.status_code == 200
    body = response.json()
    assert body["app"] == "MentisQ"
    assert body["database"] == "ok"  # the SELECT 1 succeeded
    # server_time comes from the injected Clock, not the wall clock.
    assert body["server_time"].startswith("2026-01-01T12:00:00")


def test_meta_reflects_an_advanced_clock(client, fake_clock):
    fake_clock.advance(timedelta(hours=3))
    body = client.get("/meta").json()
    assert body["server_time"].startswith("2026-01-01T15:00:00")
