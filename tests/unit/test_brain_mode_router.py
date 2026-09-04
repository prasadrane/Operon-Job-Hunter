"""Tests for brain mode router — classifies queries into avatar/tailoring/qa modes."""
import pytest
from src.brain.mode_router import BrainMode, route_mode


class TestExplicitModeOverride:
    """Explicit mode param bypasses keyword classification."""

    def test_explicit_avatar(self):
        assert route_mode("what is python", mode="avatar") == BrainMode.AVATAR

    def test_explicit_tailoring(self):
        assert route_mode("tell me about yourself", mode="tailoring") == BrainMode.TAILORING

    def test_explicit_qa(self):
        assert route_mode("your experience with leadership", mode="qa") == BrainMode.QA


class TestAvatarKeywordDetection:
    """Avatar mode triggers on self-referential / experience queries."""

    def test_tell_me_about_your(self):
        assert route_mode("tell me about your background") == BrainMode.AVATAR

    def test_your_experience(self):
        assert route_mode("what is your experience with Python?") == BrainMode.AVATAR

    def test_about_you(self):
        assert route_mode("tell me about you") == BrainMode.AVATAR

    def test_your_skills(self):
        assert route_mode("what are your skills?") == BrainMode.AVATAR


class TestTailoringKeywordDetection:
    """Tailoring mode triggers on resume/job customization queries."""

    def test_tailor_keyword(self):
        assert route_mode("tailor my resume for this role") == BrainMode.TAILORING

    def test_customize_keyword(self):
        assert route_mode("customize my cover letter") == BrainMode.TAILORING

    def test_job_desc_present(self):
        assert route_mode("help me apply", job_desc="Senior Python Developer at Google") == BrainMode.TAILORING

    def test_optimize_resume(self):
        assert route_mode("optimize my resume") == BrainMode.TAILORING


class TestQAKeywordDetection:
    """QA mode triggers on general knowledge questions."""

    def test_what_question(self):
        assert route_mode("what is machine learning?") == BrainMode.QA

    def test_which_question(self):
        assert route_mode("which framework is better?") == BrainMode.QA

    def test_how_many_question(self):
        assert route_mode("how many types of design patterns are there?") == BrainMode.QA


class TestDefaultFallback:
    """Ambiguous queries fall back to QA mode."""

    def test_generic_query(self):
        assert route_mode("hello") == BrainMode.QA

    def test_empty_like_query(self):
        assert route_mode("hi there") == BrainMode.QA
