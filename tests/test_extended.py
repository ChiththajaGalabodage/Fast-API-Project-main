"""Broader deterministic API checks for the LLM-CTF experiment.

These tests expand the sample inventory without relying on external services,
wall-clock timing assertions, or nondeterministic data.
"""

import asyncio
import uuid

import pytest


pytestmark = pytest.mark.asyncio


async def test_health_response_has_typed_operational_fields(client):
    response = await client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert isinstance(data["uptime_seconds"], (int, float))
    assert data["uptime_seconds"] >= 0
    assert isinstance(data["db"]["users"], int)
    assert isinstance(data["db"]["posts"], int)


async def test_response_generates_valid_request_id(client):
    response = await client.get("/api/health")

    assert response.status_code == 200
    request_id = response.headers["X-Request-ID"]
    assert str(uuid.UUID(request_id)) == request_id


async def test_response_preserves_supplied_request_id(client):
    request_id = "research-run-0001"
    response = await client.get("/api/health", headers={"X-Request-ID": request_id})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id


async def test_error_injection_forces_server_error(client):
    enabled = await client.post("/api/error-injection?enabled=true")
    assert enabled.status_code == 200

    response = await client.get("/api/users")
    assert response.status_code == 500
    assert "Forced server error" in response.json()["detail"]


async def test_health_remains_available_during_error_injection(client):
    await client.post("/api/error-injection?enabled=true")

    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_reset_disables_error_injection(client):
    await client.post("/api/error-injection?enabled=true")
    reset_response = await client.post("/api/reset")

    assert reset_response.status_code == 200
    users_response = await client.get("/api/users")
    assert users_response.status_code == 200


async def test_seed_accepts_minimum_user_count(client):
    response = await client.post("/api/seed", json={"num_users": 1})

    assert response.status_code == 200
    data = response.json()
    assert data["users"] == 1
    assert 5 <= data["posts"] <= 10


async def test_seed_is_deterministic(client):
    await client.post("/api/seed", json={"num_users": 3})
    first_users = (await client.get("/api/users")).json()

    await client.post("/api/seed", json={"num_users": 3})
    second_users = (await client.get("/api/users")).json()

    assert second_users == first_users


async def test_seed_updates_pagination_metadata(client):
    await client.post("/api/seed", json={"num_users": 23})
    response = await client.get("/api/users/paginated?page=3&limit=10")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 23
    assert data["pages"] == 3
    assert len(data["data"]) == 3


async def test_pagination_beyond_last_page_returns_empty_data(client):
    response = await client.get("/api/users/paginated?page=999&limit=20")

    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 999
    assert data["data"] == []


async def test_pagination_accepts_maximum_limit(client):
    response = await client.get("/api/users/paginated?page=1&limit=100")

    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 100
    assert len(data["data"]) == 100


async def test_paginated_users_preserve_identifier_order(client):
    response = await client.get("/api/users/paginated?page=1&limit=10")

    assert response.status_code == 200
    ids = [user["id"] for user in response.json()["data"]]
    assert ids == list(range(1, 11))


async def test_user_posts_have_expected_schema(client):
    response = await client.get("/api/users/1")

    assert response.status_code == 200
    posts = response.json()["posts"]
    assert posts
    assert all(set(post) == {"id", "user_id", "title", "content", "created_at"} for post in posts)


async def test_create_post_increments_database_metrics(client):
    before = (await client.get("/api/metrics/db-size")).json()
    created = await client.post(
        "/api/posts",
        json={"user_id": 1, "title": "Metric check", "content": "Content"},
    )
    after = (await client.get("/api/metrics/db-size")).json()

    assert created.status_code == 201
    assert after["users"] == before["users"]
    assert after["posts"] == before["posts"] + 1


async def test_create_post_accepts_maximum_title_length(client):
    title = "t" * 200
    response = await client.post(
        "/api/posts", json={"user_id": 1, "title": title, "content": "Content"}
    )

    assert response.status_code == 201
    assert response.json()["title"] == title


async def test_create_post_accepts_maximum_content_length(client):
    content = "c" * 5000
    response = await client.post(
        "/api/posts", json={"user_id": 1, "title": "Boundary", "content": content}
    )

    assert response.status_code == 201
    assert response.json()["content"] == content


async def test_create_post_rejects_empty_content(client):
    response = await client.post(
        "/api/posts", json={"user_id": 1, "title": "Boundary", "content": ""}
    )

    assert response.status_code == 422
    assert any("content" in error["loc"] for error in response.json()["detail"])


async def test_create_post_rejects_malformed_json(client):
    response = await client.post(
        "/api/posts",
        content=b"{not-valid-json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422


async def test_update_post_accepts_maximum_title_length(client):
    created = await client.post(
        "/api/posts", json={"user_id": 1, "title": "Original", "content": "Content"}
    )
    post_id = created.json()["id"]
    title = "u" * 200

    response = await client.put(
        f"/api/posts/{post_id}", json={"title": title, "content": "Updated"}
    )

    assert response.status_code == 200
    assert response.json()["post"]["title"] == title


async def test_update_post_accepts_maximum_content_length(client):
    created = await client.post(
        "/api/posts", json={"user_id": 1, "title": "Original", "content": "Content"}
    )
    post_id = created.json()["id"]
    content = "u" * 5000

    response = await client.put(
        f"/api/posts/{post_id}", json={"title": "Updated", "content": content}
    )

    assert response.status_code == 200
    assert response.json()["post"]["content"] == content


async def test_update_post_rejects_missing_content(client):
    response = await client.put("/api/posts/1", json={"title": "Incomplete"})

    assert response.status_code == 422
    assert any("content" in error["loc"] for error in response.json()["detail"])


async def test_delete_post_decrements_database_metrics(client):
    created = await client.post(
        "/api/posts", json={"user_id": 1, "title": "Delete", "content": "Content"}
    )
    before = (await client.get("/api/metrics/db-size")).json()

    deleted = await client.delete(f"/api/posts/{created.json()['id']}")
    after = (await client.get("/api/metrics/db-size")).json()

    assert deleted.status_code == 200
    assert after["posts"] == before["posts"] - 1


async def test_missing_delete_does_not_change_database_metrics(client):
    before = (await client.get("/api/metrics/db-size")).json()
    response = await client.delete("/api/posts/999999")
    after = (await client.get("/api/metrics/db-size")).json()

    assert response.status_code == 404
    assert after == before


async def test_large_payload_accepts_minimum_size(client):
    response = await client.get("/api/large-payload?size=10")

    assert response.status_code == 200
    data = response.json()
    assert data["item_count"] == 10
    assert len(data["items"]) == 10


async def test_large_payload_rejects_non_integer_size(client):
    response = await client.get("/api/large-payload?size=10.5")

    assert response.status_code == 422


@pytest.mark.parametrize("delay", ["0.49", "5.01", "not-a-number"])
async def test_slow_data_rejects_invalid_delay_values(client, delay):
    response = await client.get(f"/api/slow-data?delay_seconds={delay}")

    assert response.status_code == 422


async def test_openapi_documents_all_research_endpoints(client):
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    expected = {
        "/api/health",
        "/api/reset",
        "/api/seed",
        "/api/error-injection",
        "/api/users",
        "/api/users/paginated",
        "/api/users/{user_id}",
        "/api/posts",
        "/api/posts/{post_id}",
        "/api/slow-data",
        "/api/large-payload",
        "/api/metrics/db-size",
    }
    assert expected <= set(paths)


async def test_cors_preflight_allows_configured_frontend(client):
    response = await client.options(
        "/api/users",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "GET" in response.headers["access-control-allow-methods"]


async def test_concurrent_read_requests_preserve_consistent_user(client):
    responses = await asyncio.gather(*(client.get("/api/users/1") for _ in range(5)))

    assert all(response.status_code == 200 for response in responses)
    users = [response.json()["user"] for response in responses]
    assert all(user == users[0] for user in users)


async def test_reset_recreates_the_same_database_counts(client):
    first = (await client.get("/api/metrics/db-size")).json()
    await client.post(
        "/api/posts", json={"user_id": 1, "title": "Temporary", "content": "Content"}
    )
    await client.post("/api/reset")
    second = (await client.get("/api/metrics/db-size")).json()

    assert second == first
