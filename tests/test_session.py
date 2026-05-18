"""Unit tests for Session Manager."""
import pytest
from app.session.manager import SessionManager


def test_create_session():
    mgr = SessionManager()
    session = mgr.get_or_create()
    assert session["session_id"].startswith("sess_")
    assert session["messages"] == []


def test_reuse_session():
    mgr = SessionManager()
    s1 = mgr.get_or_create()
    s2 = mgr.get_or_create(s1["session_id"])
    assert s1["session_id"] == s2["session_id"]


def test_append_message():
    mgr = SessionManager()
    session = mgr.get_or_create()
    sid = session["session_id"]
    mgr.append_message(sid, "user", "hello")
    mgr.append_message(sid, "assistant", "hi there")

    history = mgr.get_history(sid)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["content"] == "hi there"


def test_nonexistent_session():
    mgr = SessionManager()
    assert mgr.get_history("nonexistent") == []
