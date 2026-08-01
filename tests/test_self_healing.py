"""Deterministic tests for the guarded autonomous repair engine."""

import asyncio
import json
import sys
from pathlib import Path

import pytest
import tests_selecter.self_healing as healing
import tests_selecter.selecter as selector

from tests_generated.generator import _generated_test_validation_error
from tests_selecter.self_healing import (
    RepairResult,
    RepairValidationError,
    attempt_repair,
    build_patched_source,
    normalize_test_id,
    resolve_test_target,
    write_healing_artifacts,
)


def create_test_file(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "tests" / "test_sample.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_normalize_parameterized_test_id():
    test_file, function_name, base_id = normalize_test_id(
        "tests/test_api.py::TestPosts::test_create[payload-title]"
    )

    assert test_file == "tests/test_api.py"
    assert function_name == "test_create"
    assert base_id == "tests/test_api.py::TestPosts::test_create"


def test_patch_preserves_decorators_signature_and_sibling_code():
    original = """@pytest.mark.asyncio
async def test_target(client):
    response = await client.get('/api/old-health')
    assert response.status_code == 201


def test_sibling():
    assert True
"""
    candidate = """async def test_target(client):
    response = await client.get('/api/health')
    assert response.status_code == 200
"""

    patched, diff = build_patched_source(original, candidate, "test_target")

    assert "@pytest.mark.asyncio\nasync def test_target(client):" in patched
    assert "def test_sibling():" in patched
    assert "assert response.status_code == 200" in patched
    assert "-    assert response.status_code == 201" in diff


def test_typed_client_signature_is_preserved_without_blocking_safe_repair():
    original = """async def test_target(client: AsyncClient) -> None:
    response = await client.get('/api/old-health')
    assert response.status_code == 201
"""
    candidate = """async def test_target(client: AsyncClient) -> None:
    response = await client.get('/api/health')
    assert response.status_code == 200
"""

    patched, _ = build_patched_source(original, candidate, "test_target")

    assert "client: AsyncClient" in patched
    assert "-> None" in patched
    assert "assert response.status_code == 200" in patched


@pytest.mark.parametrize(
    "candidate, reason",
    [
        ("def test_other():\n    value = 1\n    assert value == 2\n", "name"),
        ("def test_target():\n    import os\n    value = 1\n    assert value == 2\n", "Forbidden construct"),
        ("def test_target():\n    open('secret.txt')\n    value = 1\n    assert value == 2\n", "Forbidden call"),
        ("def test_target():\n    writer = open\n    value = 1\n    assert value == 2\n", "Forbidden name"),
        ("def test_target():\n    pytest.skip('skip')\n    value = 1\n    assert value == 2\n", "Forbidden call"),
        ("def test_target():\n    value = 1\n", "assertions"),
        ("def test_target():\n    assert True\n", "trivially true"),
        (
            "@pytest.mark.skip\ndef test_target():\n    value = 1\n    assert value == 2\n",
            "decorators",
        ),
        (
            "def test_target() -> [0] * 10**10:\n    value = 1\n    assert value == 2\n",
            "annotations",
        ),
    ],
)
def test_unsafe_or_weakened_candidate_is_rejected(candidate, reason):
    original = "def test_target():\n    value = 1\n    assert value == 2\n"

    with pytest.raises(RepairValidationError, match=reason):
        build_patched_source(original, candidate, "test_target")


def test_repair_is_kept_after_two_successful_validation_runs(tmp_path):
    path = create_test_file(
        tmp_path, "def test_target():\n    actual = 1\n    assert actual == 2\n"
    )
    candidate = "def test_target():\n    actual = 1\n    assert actual == 1\n"

    result = attempt_repair(
        f"{path}::test_target",
        candidate,
        project_root=tmp_path,
        backup_dir=tmp_path / "reports" / "backups",
        validation_runs=2,
        timeout_sec=30,
    )

    assert result.outcome == "healed"
    assert result.safety_validated is True
    assert result.validation_runs == 2
    assert result.kept is True
    assert "assert actual == 1" in path.read_text(encoding="utf-8")
    backup = tmp_path / "reports" / "backups" / "tests" / "test_sample.py.before"
    assert "assert actual == 2" in backup.read_text(encoding="utf-8")


def test_failed_repair_is_rolled_back_exactly(tmp_path):
    original = b"def test_target():\r\n    actual = 1\r\n    assert actual == 2\r\n"
    path = tmp_path / "tests" / "test_sample.py"
    path.parent.mkdir(parents=True)
    path.write_bytes(original)
    candidate = "def test_target():\n    actual = 1\n    assert actual == 3\n"

    result = attempt_repair(
        f"{path}::test_target",
        candidate,
        project_root=tmp_path,
        validation_runs=2,
        timeout_sec=30,
    )

    assert result.outcome == "rolled_back"
    assert result.rolled_back is True
    assert result.rollback_verified is True
    assert result.kept is False
    assert path.read_bytes() == original


def test_target_outside_allowlisted_test_directories_is_rejected(tmp_path):
    path = tmp_path / "main.py"
    path.write_text("def test_target():\n    assert False\n", encoding="utf-8")

    with pytest.raises(RepairValidationError, match="tests/"):
        resolve_test_target(f"{path}::test_target", project_root=tmp_path)


def test_self_healing_safety_file_is_protected_from_repair(tmp_path):
    path = tmp_path / "tests" / "test_self_healing.py"
    path.parent.mkdir(parents=True)
    path.write_text("def test_target():\n    assert False\n", encoding="utf-8")

    with pytest.raises(RepairValidationError, match="protected"):
        resolve_test_target(f"{path}::test_target", project_root=tmp_path)


def test_external_network_client_is_rejected():
    original = """async def test_target(client):
    response = await client.get('/api/health')
    assert response.status_code == 201
"""
    candidate = """async def test_target(client):
    async with AsyncClient() as external:
        response = await external.get('https://example.com')
    assert response.status_code == 200
"""

    with pytest.raises(RepairValidationError, match="Forbidden|network"):
        build_patched_source(original, candidate, "test_target")


def test_generated_test_policy_accepts_relative_fixture_client_usage():
    candidate = """async def test_health(client):
    response = await client.get('/api/health')
    assert response.status_code == 200
"""

    assert _generated_test_validation_error(candidate) is None


def test_generated_test_policy_rejects_unsafe_or_bypass_code():
    candidates = [
        """async def test_health(client):
    import os
    assert True
""",
        """async def test_health(client):
    response = await client.get('https://example.com')
    assert response.status_code == 200
""",
        """async def test_health(client):
    open('secret.txt')
    assert True
""",
        """async def test_health(client):
    response = await client.get('/api/health')
    writer = open
    handle = writer('untracked.py', 'w')
    handle.write('malicious')
    assert response.status_code == 200
""",
        """async def test_health(client):
    return
    assert False
""",
        """async def test_health(client):
    if False:
        assert False
""",
        """async def test_health(client):
    response = await client.get('/api/health')
    assert 1 == 1
""",
        """async def test_health(client):
    response = await client.get('/api/health')
    assert response is response
""",
        """async def test_health(client):
    response = await client.get('/api/health')
    response = 1
    assert response == 1
""",
        """async def test_health(client):
    response = await client.get('/api/health')
    response.status_code = 200
    assert response.status_code == 200
""",
        """async def test_health(client):
    response = await client.get('/api/health')
    assert response.status_code == 500 or True
""",
        """async def test_health(client):
    response = await client.get('/api/health')
    assert [response.status_code == 500]
""",
        """async def test_health(client):
    response = await client.get('/api/health')
    assert response.status_code >= 0
""",
        """async def test_health(client: [0] * 10**10):
    response = await client.get('/api/health')
    assert response.status_code == 200
""",
        """async def test_health(client):
    response = type('Fake', (), {'status_code': 200})()
    assert response.status_code == 200
    response = await client.get('/api/health')
""",
        """async def test_health(client):
    response = (await client.get('/api/health'), type('Fake', (), {'status_code': 200})())[1]
    assert response.status_code == 200
""",
    ]

    for candidate in candidates:
        assert _generated_test_validation_error(candidate) is not None


def test_candidate_must_preserve_call_structure():
    original = "def test_target():\n    actual = 1\n    assert actual == 2\n"
    candidate = """def test_target():
    danger()
    actual = 1
    assert actual == 1
"""

    with pytest.raises(RepairValidationError, match="call structure"):
        build_patched_source(original, candidate, "test_target")


@pytest.mark.parametrize(
    "candidate",
    [
        """def test_target():
    return
    actual = 1
    assert actual == 2
""",
        """def test_target():
    if False:
        actual = 1
        assert actual == 2
""",
    ],
)
def test_candidate_cannot_bypass_assertions_with_control_flow(candidate):
    original = "def test_target():\n    actual = 1\n    assert actual == 2\n"

    with pytest.raises(RepairValidationError, match="function-body structure"):
        build_patched_source(original, candidate, "test_target")


def test_repair_rejects_control_dependent_and_boolean_bypass_assertions():
    controlled_original = """def test_target(response):
    if response.status_code == 200:
        assert response.json()['status'] == 'ok'
"""
    controlled_candidate = """def test_target(response):
    if response.status_code == 500:
        assert response.json()['status'] == 'ok'
"""
    with pytest.raises(RepairValidationError, match="control flow"):
        build_patched_source(
            controlled_original, controlled_candidate, "test_target"
        )

    boolean_original = """def test_target(response):
    assert response.status_code == 200 or False
"""
    boolean_candidate = """def test_target(response):
    assert response.status_code == 200 or True
"""
    with pytest.raises(RepairValidationError, match="control flow|assertion structure"):
        build_patched_source(boolean_original, boolean_candidate, "test_target")

    caught_original = """def test_target():
    try:
        int('1')
    except ValueError:
        return
    assert False
"""
    caught_candidate = """def test_target():
    try:
        int('x')
    except ValueError:
        return
    assert False
"""
    with pytest.raises(RepairValidationError, match="control flow"):
        build_patched_source(caught_original, caught_candidate, "test_target")

    numeric_or_original = """def test_target(response):
    assert response.status_code == 200 or 0
"""
    numeric_or_candidate = """def test_target(response):
    assert response.status_code == 200 or 1
"""
    with pytest.raises(RepairValidationError, match="control flow"):
        build_patched_source(
            numeric_or_original, numeric_or_candidate, "test_target"
        )


def test_repair_may_not_introduce_a_new_server_error_expectation():
    original = """async def test_target(client):
    response = await client.get('/api/health')
    assert response.status_code == 200
"""
    candidate = """async def test_target(client):
    response = await client.get('/api/health')
    assert response.status_code == 500
"""

    with pytest.raises(RepairValidationError, match="new 5xx"):
        build_patched_source(original, candidate, "test_target")


def test_rollback_write_failure_is_reported(tmp_path, monkeypatch):
    original = b"def test_target():\n    actual = 1\n    assert actual == 2\n"
    path = tmp_path / "tests" / "test_sample.py"
    path.parent.mkdir(parents=True)
    path.write_bytes(original)
    real_atomic_write = healing._atomic_write

    def fail_only_during_restore(target, content, mode):
        if content == original:
            raise OSError("forced rollback write failure")
        return real_atomic_write(target, content, mode)

    monkeypatch.setattr(healing, "_atomic_write", fail_only_during_restore)
    result = attempt_repair(
        f"{path}::test_target",
        "def test_target():\n    actual = 1\n    assert actual == 3\n",
        project_root=tmp_path,
        validation_runs=1,
        timeout_sec=30,
    )

    assert result.outcome == "rollback_failed"
    assert result.rolled_back is False
    assert result.rollback_verified is False
    assert "forced rollback write failure" in result.rollback_error


def test_selector_runs_complete_fail_repair_validate_keep_flow(tmp_path, monkeypatch):
    test_file = create_test_file(
        tmp_path, "def test_target():\n    actual = 1\n    assert actual == 2\n"
    )
    test_id = "tests/test_sample.py::test_target"
    diff_path = tmp_path / "change.diff"
    diff_path.write_text(
        "diff --git a/main.py b/main.py\n@@ -1 +1 @@\n-old\n+new\n",
        encoding="utf-8",
    )

    async def deterministic_selection(_diff, _tests):
        return {"high": [test_id], "medium": [], "low": []}

    async def deterministic_repair(_test_id, _message):
        return "def test_target():\n    actual = 1\n    assert actual == 1\n"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(selector, "client", object())
    monkeypatch.setattr(selector, "collect_tests", lambda: [test_id])
    monkeypatch.setattr(selector, "select_tests", deterministic_selection)
    monkeypatch.setattr(selector, "suggest_fix", deterministic_repair)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "selecter.py",
            "--diff",
            str(diff_path),
            "--min-tests",
            "1",
            "--max-tests",
            "1",
            "--heal-validation-runs",
            "2",
            "--batch-timeout",
            "30",
            "--before-csv",
            str(tmp_path / "reports" / "before.csv"),
            "--csv-out",
            str(tmp_path / "reports" / "final.csv"),
            "--timing-out",
            str(tmp_path / "reports" / "timing.json"),
            "--healing-report",
            str(tmp_path / "reports" / "healing.json"),
            "--healing-patch",
            str(tmp_path / "reports" / "healing.patch"),
            "--healing-backup-dir",
            str(tmp_path / "reports" / "backups"),
        ],
    )

    exit_code = asyncio.run(selector.main())
    report = json.loads((tmp_path / "reports" / "healing.json").read_text())

    assert exit_code == 0
    assert "assert actual == 1" in test_file.read_text(encoding="utf-8")
    assert report["healed_count"] == 1
    assert report["final_validation_passed"] is True
    assert (tmp_path / "reports" / "healing.patch").stat().st_size > 0


def test_selector_fails_and_restores_transaction_after_rollback_error(
    tmp_path, monkeypatch
):
    original = "def test_target():\n    actual = 1\n    assert actual == 2\n"
    test_file = create_test_file(tmp_path, original)
    test_id = "tests/test_sample.py::test_target"
    diff_path = tmp_path / "change.diff"
    diff_path.write_text(
        "diff --git a/main.py b/main.py\n@@ -1 +1 @@\n-old\n+new\n",
        encoding="utf-8",
    )

    async def deterministic_selection(_diff, _tests):
        return {"high": [test_id], "medium": [], "low": []}

    async def deterministic_repair(_test_id, _message):
        return "def test_target():\n    actual = 1\n    assert actual == 1\n"

    def simulated_rollback_failure(_test_id, _candidate, **_kwargs):
        test_file.write_text(
            "def test_target():\n    actual = 1\n    assert actual == 1\n",
            encoding="utf-8",
        )
        return RepairResult(
            test_id=test_id,
            base_test_id=test_id,
            test_file="tests/test_sample.py",
            function_name="test_target",
            outcome="rollback_failed",
            safety_validated=True,
            applied=True,
            rollback_error="simulated first rollback failure",
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(selector, "client", object())
    monkeypatch.setattr(selector, "collect_tests", lambda: [test_id])
    monkeypatch.setattr(selector, "select_tests", deterministic_selection)
    monkeypatch.setattr(selector, "suggest_fix", deterministic_repair)
    monkeypatch.setattr(selector, "attempt_repair", simulated_rollback_failure)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "selecter.py",
            "--diff",
            str(diff_path),
            "--min-tests",
            "1",
            "--max-tests",
            "1",
            "--batch-timeout",
            "30",
            "--before-csv",
            str(tmp_path / "reports" / "before.csv"),
            "--csv-out",
            str(tmp_path / "reports" / "final.csv"),
            "--timing-out",
            str(tmp_path / "reports" / "timing.json"),
            "--healing-report",
            str(tmp_path / "reports" / "healing.json"),
            "--healing-patch",
            str(tmp_path / "reports" / "healing.patch"),
            "--healing-backup-dir",
            str(tmp_path / "reports" / "backups"),
        ],
    )

    exit_code = asyncio.run(selector.main())
    report = json.loads((tmp_path / "reports" / "healing.json").read_text())

    assert exit_code == 1
    assert test_file.read_text(encoding="utf-8") == original
    assert report["rollback_failed_count"] == 1
    assert report["attempts"][0]["rollback_verified"] is True
    assert report["final_validation_passed"] is False


def test_healing_report_and_patch_are_always_written(tmp_path):
    result = RepairResult(
        test_id="tests/test_api.py::test_target",
        base_test_id="tests/test_api.py::test_target",
        test_file="tests/test_api.py",
        function_name="test_target",
        outcome="healed",
        safety_validated=True,
        applied=True,
        kept=True,
        patch="--- a/tests/test_api.py\n+++ b/tests/test_api.py\n",
    )
    report = tmp_path / "self_healing_report.json"
    patch = tmp_path / "self_healing.patch"

    write_healing_artifacts(
        report,
        patch,
        [result],
        model="test-model",
        initial_failed_count=1,
        final_failed_count=0,
        final_validation_passed=True,
    )

    assert '"healed_count": 1' in report.read_text(encoding="utf-8")
    assert "+++ b/tests/test_api.py" in patch.read_text(encoding="utf-8")
