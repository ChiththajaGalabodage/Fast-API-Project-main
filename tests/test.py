import pytest
from httpx import ASGITransport, AsyncClient

from main import app

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    """Async HTTP client for the FastAPI app using ASGI transport."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture(autouse=True)
async def reset_db(client):
    """Reset the database before each test to ensure isolation."""
    response = await client.post("/api/reset")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "reset"
    # Return the user/post counts for optional checks
    return data


# ---------------------------------------------------------------------------
# Happy path tests
# ---------------------------------------------------------------------------


async def test_get_users(client):
    response = await client.get("/api/users")
    assert response.status_code == 200
    users = response.json()
    assert isinstance(users, list)
    assert len(users) > 0
    user = users[0]
    assert "id" in user
    assert "name" in user
    assert "email" in user
    assert "city" in user
    assert "company" in user


async def test_get_users_paginated(client):
    response = await client.get("/api/users/paginated?page=1&limit=20")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["limit"] == 20
    assert data["total"] > 0
    assert data["pages"] > 0
    assert len(data["data"]) == min(20, data["total"])

    total = data["total"]
    last_page = (total + 19) // 20
    response = await client.get(f"/api/users/paginated?page={last_page}&limit=20")
    assert response.status_code == 200
    data_last = response.json()
    assert data_last["page"] == last_page
    assert len(data_last["data"]) == total - (last_page - 1) * 20


async def test_get_user_with_posts(client):
    user_id = 1
    response = await client.get(f"/api/users/{user_id}")
    assert response.status_code == 200
    data = response.json()
    assert "user" in data
    assert "posts" in data
    assert data["user"]["id"] == user_id
    for post in data["posts"]:
        assert post["user_id"] == user_id


async def test_create_post(client):
    payload = {
        "user_id": 1,
        "title": "Test Post Title",
        "content": "This is the post content.",
    }
    response = await client.post("/api/posts", json=payload)
    assert response.status_code == 200
    new_post = response.json()
    assert new_post["user_id"] == 1
    assert new_post["title"] == payload["title"]
    assert new_post["content"] == payload["content"]
    assert "id" in new_post
    assert "created_at" in new_post


async def test_update_post(client):
    create_payload = {
        "user_id": 1,
        "title": "Original Title",
        "content": "Original content",
    }
    create_resp = await client.post("/api/posts", json=create_payload)
    post_id = create_resp.json()["id"]

    update_payload = {"title": "Updated Title", "content": "Updated content"}
    resp = await client.put(f"/api/posts/{post_id}", json=update_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    updated = data["post"]
    assert updated["title"] == update_payload["title"]
    assert updated["content"] == update_payload["content"]


async def test_delete_post(client):
    create_payload = {
        "user_id": 1,
        "title": "To Delete",
        "content": "This post will be deleted",
    }
    create_resp = await client.post("/api/posts", json=create_payload)
    post_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/posts/{post_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["deleted_id"] == post_id

    user_posts_resp = await client.get("/api/users/1")
    posts = user_posts_resp.json()["posts"]
    post_ids = [p["id"] for p in posts]
    assert post_id not in post_ids


# ---------------------------------------------------------------------------
# Edge cases / validation errors
# ---------------------------------------------------------------------------


async def test_get_user_not_found(client):
    response = await client.get("/api/users/999999")
    assert response.status_code == 404
    assert "detail" in response.json()


async def test_create_post_user_not_found(client):
    payload = {"user_id": 999999, "title": "Test", "content": "Content"}
    response = await client.post("/api/posts", json=payload)
    assert response.status_code == 404
    assert "User not found" in response.json()["detail"]


async def test_create_post_blank_title(client):
    payload = {"user_id": 1, "title": "   ", "content": "Content"}
    response = await client.post("/api/posts", json=payload)
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any("title" in e["loc"] for e in errors)


async def test_create_post_title_too_long(client):
    payload = {"user_id": 1, "title": "a" * 201, "content": "Content"}
    response = await client.post("/api/posts", json=payload)
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any("title" in e["loc"] for e in errors)


async def test_create_post_content_too_long(client):
    payload = {"user_id": 1, "title": "Valid title", "content": "a" * 5001}
    response = await client.post("/api/posts", json=payload)
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any("content" in e["loc"] for e in errors)


async def test_update_post_not_found(client):
    payload = {"title": "New", "content": "New content"}
    response = await client.put("/api/posts/999999", json=payload)
    assert response.status_code == 404
    assert "Post not found" in response.json()["detail"]


async def test_delete_post_not_found(client):
    response = await client.delete("/api/posts/999999")
    assert response.status_code == 404
    assert "Post not found" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Reset / Seed tests (isolation)
# ---------------------------------------------------------------------------


async def test_reset_db_restores_initial_state(client):
    resp1 = await client.get("/api/metrics/db-size")
    initial_counts = resp1.json()

    payload = {"user_id": 1, "title": "Temp", "content": "Temp content"}
    await client.post("/api/posts", json=payload)

    resp2 = await client.get("/api/metrics/db-size")
    modified_counts = resp2.json()
    assert modified_counts["posts"] == initial_counts["posts"] + 1

    reset_resp = await client.post("/api/reset")
    assert reset_resp.status_code == 200

    resp3 = await client.get("/api/metrics/db-size")
    reset_counts = resp3.json()
    assert reset_counts == initial_counts


async def test_seed_db_with_custom_number(client):
    payload = {"num_users": 10}
    response = await client.post("/api/seed", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "seeded"
    assert data["users"] == 10
    assert data["posts"] >= 50

    metrics = await client.get("/api/metrics/db-size")
    metrics_data = metrics.json()
    assert metrics_data["users"] == 10


async def test_seed_db_max_limit(client):
    payload = {"num_users": 1000}
    response = await client.post("/api/seed", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["users"] == 1000


async def test_seed_db_invalid_limit(client):
    # 0 is invalid (ge=1)
    payload = {"num_users": 0}
    response = await client.post("/api/seed", json=payload)
    assert response.status_code == 422
    # 1001 > 1000
    payload = {"num_users": 1001}
    response = await client.post("/api/seed", json=payload)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Additional failure-path / negative test cases
# These tests help prove defect detection ability in the research experiment.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "page=0&limit=20",      # page must be >= 1
        "page=-1&limit=20",     # negative page is invalid
        "page=1&limit=0",       # limit must be >= 1
        "page=1&limit=-5",      # negative limit is invalid
    ],
)
async def test_get_users_paginated_invalid_values(client, query):
    """
    The pagination endpoint should reject invalid page/limit values.
    If this test fails, it means pagination validation is weak.
    """
    response = await client.get(f"/api/users/paginated?{query}")
    assert response.status_code == 422


async def test_get_user_id_must_be_integer(client):
    """
    User ID should be an integer.
    Non-numeric user IDs should be rejected by FastAPI validation.
    """
    response = await client.get("/api/users/abc")
    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload, expected_field",
    [
        ({"title": "Missing user", "content": "Content"}, "user_id"),
        ({"user_id": 1, "content": "Missing title"}, "title"),
        ({"user_id": 1, "title": "Missing content"}, "content"),
    ],
)
async def test_create_post_missing_required_fields(client, payload, expected_field):
    """
    Creating a post without required fields should fail.
    This proves that request body validation works correctly.
    """
    response = await client.post("/api/posts", json=payload)
    assert response.status_code == 422

    errors = response.json()["detail"]
    assert any(expected_field in error["loc"] for error in errors)


async def test_create_post_invalid_user_id_type(client):
    """
    user_id must be a valid integer.
    A string value should be rejected.
    """
    payload = {
        "user_id": "invalid_id",
        "title": "Invalid User ID",
        "content": "This should fail",
    }

    response = await client.post("/api/posts", json=payload)
    assert response.status_code == 422


async def test_update_post_blank_title_should_fail(client):
    """
    Updating a post with a blank title should not be allowed.
    If this test fails, the update endpoint has weaker validation than create endpoint.
    """
    create_payload = {
        "user_id": 1,
        "title": "Original Title",
        "content": "Original content",
    }
    create_resp = await client.post("/api/posts", json=create_payload)
    post_id = create_resp.json()["id"]

    update_payload = {
        "title": "   ",
        "content": "Updated content",
    }

    response = await client.put(f"/api/posts/{post_id}", json=update_payload)
    assert response.status_code == 422


async def test_update_post_content_too_long_should_fail(client):
    """
    Updating a post with content longer than allowed limit should fail.
    This checks whether validation is applied during update also.
    """
    create_payload = {
        "user_id": 1,
        "title": "Original Title",
        "content": "Original content",
    }
    create_resp = await client.post("/api/posts", json=create_payload)
    post_id = create_resp.json()["id"]

    update_payload = {
        "title": "Valid Updated Title",
        "content": "a" * 5001,
    }

    response = await client.put(f"/api/posts/{post_id}", json=update_payload)
    assert response.status_code == 422


async def test_update_post_id_must_be_integer(client):
    """
    Post ID should be an integer when updating.
    """
    payload = {
        "title": "Updated Title",
        "content": "Updated content",
    }

    response = await client.put("/api/posts/abc", json=payload)
    assert response.status_code == 422


async def test_delete_post_id_must_be_integer(client):
    """
    Post ID should be an integer when deleting.
    """
    response = await client.delete("/api/posts/abc")
    assert response.status_code == 422


async def test_delete_post_twice_second_attempt_should_fail(client):
    """
    After deleting a post, deleting the same post again should return 404.
    This proves that deleted records are not still treated as active records.
    """
    create_payload = {
        "user_id": 1,
        "title": "Delete Twice",
        "content": "This post will be deleted twice",
    }

    create_resp = await client.post("/api/posts", json=create_payload)
    post_id = create_resp.json()["id"]

    first_delete = await client.delete(f"/api/posts/{post_id}")
    assert first_delete.status_code == 200

    second_delete = await client.delete(f"/api/posts/{post_id}")
    assert second_delete.status_code == 404
    assert "Post not found" in second_delete.json()["detail"]


async def test_deleted_post_cannot_be_updated(client):
    """
    A deleted post should not be updatable.
    This checks data consistency after delete operations.
    """
    create_payload = {
        "user_id": 1,
        "title": "Deleted Update Test",
        "content": "This post will be deleted first",
    }

    create_resp = await client.post("/api/posts", json=create_payload)
    post_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/posts/{post_id}")
    assert delete_resp.status_code == 200

    update_payload = {
        "title": "Should Not Update",
        "content": "This update should fail",
    }

    update_resp = await client.put(f"/api/posts/{post_id}", json=update_payload)
    assert update_resp.status_code == 404
    assert "Post not found" in update_resp.json()["detail"]


async def test_invalid_seed_request_should_not_change_database(client):
    """
    Invalid seed requests should fail and should not change the current database state.
    This proves that failed operations do not corrupt the test data.
    """
    before_resp = await client.get("/api/metrics/db-size")
    before_counts = before_resp.json()

    invalid_payload = {"num_users": 0}
    response = await client.post("/api/seed", json=invalid_payload)
    assert response.status_code == 422

    after_resp = await client.get("/api/metrics/db-size")
    after_counts = after_resp.json()

    assert after_counts == before_counts