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
