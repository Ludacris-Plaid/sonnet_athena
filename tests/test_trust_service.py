"""
Unit tests for the trust ladder scoring logic (pure function, no DB needed
for the level-derivation part).
"""
from app.services.trust_service import _level_for_score
from app.models.trust import AutomationLevel


def test_starts_draft_only():
    assert _level_for_score(0) == AutomationLevel.DRAFT_ONLY


def test_reaches_limited_autonomy():
    assert _level_for_score(45) == AutomationLevel.LIMITED_AUTONOMY


def test_reaches_full_autonomy():
    assert _level_for_score(80) == AutomationLevel.FULL_AUTONOMY
