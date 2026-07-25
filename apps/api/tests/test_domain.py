import pytest

from review_hub.domain import (
    DomainError,
    make_fingerprint,
    normalize_file_path,
    redact_code,
    rediscovery_action,
    stored_code_excerpt,
)


def test_fingerprint_matches_legacy_normalization():
    first = {
        "rule_id": "R1",
        "file_path": "src\\example.py",
        "symbol": "run",
        "code_context": "\r\nvalue = 1  \r\nreturn value\r\n",
    }
    second = {
        "rule_id": "R1",
        "file_path": "src/example.py",
        "symbol": "run",
        "code_context": "value = 1\nreturn value",
    }
    assert make_fingerprint("repo", first) == make_fingerprint("repo", second)


def test_fingerprint_changes_with_context():
    base = {
        "rule_id": "R1",
        "file_path": "src/example.py",
        "symbol": "run",
        "code_context": "value = 1",
    }
    assert make_fingerprint("repo", base) != make_fingerprint(
        "repo", {**base, "code_context": "value = 2"}
    )


def test_path_cannot_escape_repository():
    with pytest.raises(DomainError):
        normalize_file_path("../secret")


def test_fixed_reopens_and_hold_does_not_increment():
    fixed = rediscovery_action("修正済み")
    assert fixed["status"] == "確認中"
    assert fixed["increment_recurrence"] is True
    hold = rediscovery_action("保留")
    assert hold["increment_detection"] is False


def test_redacts_credentials_and_private_keys():
    value = """password = supersecret
-----BEGIN PRIVATE KEY-----
abc
-----END PRIVATE KEY-----"""
    redacted = redact_code(value)
    assert "supersecret" not in redacted
    assert "\nabc\n" not in redacted
    assert "[REDACTED]" in redacted


def test_stored_excerpt_is_redacted_then_bounded():
    value = "password = supersecret\n" + "\n".join(f"line-{i}" for i in range(60))
    excerpt = stored_code_excerpt(value, max_lines=50, max_bytes=120)
    assert "supersecret" not in excerpt
    assert len(excerpt.splitlines()) <= 50
    assert len(excerpt.encode("utf-8")) <= 120
