"""Tests for the quiz question sources (online parsers and custom sets)."""

from __future__ import annotations

import base64
import json

import pytest

from gamecenter.config.models import QuizConfig, QuizCustomSet, QuizQuestionEntry
from gamecenter.games.quiz.sources import (
    KIND_CUSTOM,
    KIND_OPENTDB,
    KIND_TRIVIA_API,
    QuizSourceError,
    available_sets,
    load_questions,
)


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _set_for(config: QuizConfig, kind: str, index: int = 0):
    matches = [s for s in available_sets(config) if s.kind == kind]
    return matches[index]


# -- available_sets ----------------------------------------------------------
def test_online_sources_always_offered():
    kinds = [s.kind for s in available_sets(QuizConfig())]
    assert kinds == [KIND_OPENTDB, KIND_TRIVIA_API]


def test_custom_sets_appear_with_their_names():
    config = QuizConfig(custom_sets=[QuizCustomSet(name="Family quiz"), QuizCustomSet(name="Movies")])
    customs = [s for s in available_sets(config) if s.kind == KIND_CUSTOM]
    assert [s.name for s in customs] == ["Family quiz", "Movies"]
    assert [s.set_id for s in customs] == ["custom:0", "custom:1"]


# -- Open Trivia Database ----------------------------------------------------
def test_opentdb_parses_base64_payload():
    payload = {
        "response_code": 0,
        "results": [
            {
                "question": _b64("What is 2+2?"),
                "correct_answer": _b64("4"),
                "category": _b64("Maths"),
                "difficulty": _b64("easy"),
            }
        ],
    }
    questions = load_questions(_set_for(QuizConfig(), KIND_OPENTDB), QuizConfig(), fetch_json=lambda _url: payload)
    assert len(questions) == 1
    assert questions[0].text == "What is 2+2?"
    assert questions[0].answer == "4"
    assert questions[0].category == "Maths"
    assert questions[0].difficulty == "easy"


def test_opentdb_url_carries_config():
    seen = {}

    def fetch(url):
        seen["url"] = url
        return {"response_code": 0, "results": [{"question": _b64("Q"), "correct_answer": _b64("A")}]}

    config = QuizConfig(questions_per_game=7, opentdb_category=9, difficulty="hard")
    load_questions(_set_for(config, KIND_OPENTDB), config, fetch_json=fetch)
    assert "amount=7" in seen["url"]
    assert "category=9" in seen["url"]
    assert "difficulty=hard" in seen["url"]
    assert seen["url"].startswith("https://opentdb.com/api.php?")


def test_opentdb_amount_clamped_to_api_limit():
    seen = {}

    def fetch(url):
        seen["url"] = url
        return {"response_code": 0, "results": [{"question": _b64("Q"), "correct_answer": _b64("A")}]}

    config = QuizConfig(questions_per_game=500)
    load_questions(_set_for(config, KIND_OPENTDB), config, fetch_json=fetch)
    assert "amount=50" in seen["url"]


def test_opentdb_error_code_raises():
    config = QuizConfig()
    with pytest.raises(QuizSourceError):
        load_questions(_set_for(config, KIND_OPENTDB), config, fetch_json=lambda _url: {"response_code": 1})


def test_network_failure_wrapped_as_source_error():
    def fetch(_url):
        msg = "connection refused"
        raise OSError(msg)

    config = QuizConfig()
    with pytest.raises(QuizSourceError):
        load_questions(_set_for(config, KIND_OPENTDB), config, fetch_json=fetch)


def test_opentdb_skips_undecodable_entries():
    payload = {
        "response_code": 0,
        "results": [
            {"question": "!!not-base64!!", "correct_answer": _b64("A")},
            {"question": _b64("Good?"), "correct_answer": _b64("Yes")},
        ],
    }
    config = QuizConfig()
    questions = load_questions(_set_for(config, KIND_OPENTDB), config, fetch_json=lambda _url: payload)
    assert [q.text for q in questions] == ["Good?"]


# -- The Trivia API ----------------------------------------------------------
def test_trivia_api_parses_v2_payload():
    payload = [
        {
            "question": {"text": "Capital of France?"},
            "correctAnswer": "Paris",
            "category": "geography",
            "difficulty": "easy",
        }
    ]
    config = QuizConfig()
    questions = load_questions(_set_for(config, KIND_TRIVIA_API), config, fetch_json=lambda _url: payload)
    assert len(questions) == 1
    assert questions[0].text == "Capital of France?"
    assert questions[0].answer == "Paris"
    assert questions[0].category == "geography"


def test_trivia_api_url_carries_limit_and_difficulty():
    seen = {}

    def fetch(url):
        seen["url"] = url
        return [{"question": {"text": "Q"}, "correctAnswer": "A"}]

    config = QuizConfig(questions_per_game=5, difficulty="medium")
    load_questions(_set_for(config, KIND_TRIVIA_API), config, fetch_json=fetch)
    assert "limit=5" in seen["url"]
    assert "difficulties=medium" in seen["url"]
    assert seen["url"].startswith("https://the-trivia-api.com/v2/questions?")


def test_trivia_api_empty_payload_raises():
    config = QuizConfig()
    with pytest.raises(QuizSourceError):
        load_questions(_set_for(config, KIND_TRIVIA_API), config, fetch_json=lambda _url: [])


# -- custom sets -------------------------------------------------------------
def test_custom_inline_questions():
    config = QuizConfig(
        custom_sets=[QuizCustomSet(name="Mine", questions=[QuizQuestionEntry(question="Q1?", answer="A1")])]
    )
    questions = load_questions(_set_for(config, KIND_CUSTOM), config)
    assert [(q.text, q.answer) for q in questions] == [("Q1?", "A1")]


def test_custom_file_questions(tmp_path):
    path = tmp_path / "set.json"
    path.write_text(
        json.dumps([{"question": "From file?", "answer": "Yes", "category": "Meta"}]),
        encoding="utf-8",
    )
    config = QuizConfig(custom_sets=[QuizCustomSet(name="File set", path=str(path))])
    questions = load_questions(_set_for(config, KIND_CUSTOM), config)
    assert questions[0].text == "From file?"
    assert questions[0].answer == "Yes"
    assert questions[0].category == "Meta"


def test_custom_file_accepts_wrapped_object(tmp_path):
    path = tmp_path / "set.json"
    path.write_text(json.dumps({"questions": [{"question": "Wrapped?", "answer": "Yep"}]}), encoding="utf-8")
    config = QuizConfig(custom_sets=[QuizCustomSet(name="Wrapped", path=str(path))])
    questions = load_questions(_set_for(config, KIND_CUSTOM), config)
    assert [q.text for q in questions] == ["Wrapped?"]


def test_custom_inline_and_file_are_merged(tmp_path):
    path = tmp_path / "set.json"
    path.write_text(json.dumps([{"question": "File?", "answer": "F"}]), encoding="utf-8")
    config = QuizConfig(
        custom_sets=[
            QuizCustomSet(name="Both", path=str(path), questions=[QuizQuestionEntry(question="Inline?", answer="I")])
        ]
    )
    questions = load_questions(_set_for(config, KIND_CUSTOM), config)
    assert [q.text for q in questions] == ["Inline?", "File?"]


def test_custom_missing_file_raises(tmp_path):
    config = QuizConfig(custom_sets=[QuizCustomSet(name="Gone", path=str(tmp_path / "missing.json"))])
    with pytest.raises(QuizSourceError):
        load_questions(_set_for(config, KIND_CUSTOM), config)


def test_custom_empty_set_raises():
    config = QuizConfig(custom_sets=[QuizCustomSet(name="Empty")])
    with pytest.raises(QuizSourceError):
        load_questions(_set_for(config, KIND_CUSTOM), config)
