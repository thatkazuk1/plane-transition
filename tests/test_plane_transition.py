import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from plane_transition import is_backward


def test_forward_transition_allowed():
    assert is_backward("unstarted", "started") is False
    assert is_backward("started", "completed") is False
    assert is_backward("backlog", "completed") is False


def test_same_group_not_backward():
    assert is_backward("completed", "completed") is False


def test_backward_transition_blocked():
    assert is_backward("completed", "started") is True
    assert is_backward("cancelled", "unstarted") is True
    assert is_backward("started", "backlog") is True


def test_unknown_group_never_blocks():
    assert is_backward(None, "started") is False
    assert is_backward("started", None) is False
    assert is_backward("some-custom-group", "started") is False


def test_access_headers_need_both_values():
    from plane_transition import access_headers

    assert access_headers("", "") == {}
    assert access_headers("id", "") == {}
    assert access_headers("", "secret") == {}
    assert access_headers(" id ", " secret ") == {
        "CF-Access-Client-Id": "id",
        "CF-Access-Client-Secret": "secret",
    }


def test_install_access_headers_adds_to_sdk_requests():
    from plane.api.base_resource import BaseResource
    from plane.config import Configuration

    from plane_transition import install_access_headers

    original = BaseResource._headers
    try:
        install_access_headers({"CF-Access-Client-Id": "id", "CF-Access-Client-Secret": "secret"})
        resource = BaseResource(Configuration(base_path="https://example.test", api_key="k"), "/api/v1")
        headers = resource._headers()
        assert headers["CF-Access-Client-Id"] == "id"
        assert headers["CF-Access-Client-Secret"] == "secret"
        assert headers["X-Api-Key"] == "k"
    finally:
        BaseResource._headers = original


def test_install_access_headers_noop_when_empty():
    from plane.api.base_resource import BaseResource

    from plane_transition import install_access_headers

    original = BaseResource._headers
    install_access_headers({})
    assert BaseResource._headers is original
