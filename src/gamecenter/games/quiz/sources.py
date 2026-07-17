"""Question sources for the Trivia Quiz game.

Questions come from popular open trivia repositories - the `Open Trivia
Database <https://opentdb.com>`_ and `The Trivia API
<https://the-trivia-api.com>`_ - or from user-provided custom sets configured
under ``quiz.custom_sets`` (inline questions and/or a JSON file). Kivy-free;
the HTTP fetch is injected as a plain ``fetch_json`` callable so every parser
is testable offline, and the widget runs :func:`load_questions` off the UI
thread.
"""

from __future__ import annotations

import base64
import binascii
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from gamecenter.config.models import QuizConfig, QuizCustomSet

# Kinds of question set offered to the host.
KIND_OPENTDB = "opentdb"
KIND_TRIVIA_API = "trivia_api"
KIND_CUSTOM = "custom"

_OPENTDB_URL = "https://opentdb.com/api.php"
_TRIVIA_API_URL = "https://the-trivia-api.com/v2/questions"
# Both APIs cap a single request at 50 questions.
_MAX_ONLINE_QUESTIONS = 50
_FETCH_TIMEOUT_SECONDS = 10


class QuizSourceError(Exception):
    """A question set could not be fetched or contained no usable questions."""


@dataclass(frozen=True, slots=True)
class QuizQuestion:
    """One question ready to be asked, with the answer the host reveals."""

    text: str
    answer: str
    category: str | None = None
    difficulty: str | None = None


@dataclass(frozen=True, slots=True)
class QuestionSetInfo:
    """A pickable question set shown on the game's source-selection panel."""

    set_id: str
    name: str
    kind: str


def available_sets(config: QuizConfig) -> list[QuestionSetInfo]:
    """Return the online repositories plus every custom set from the config."""
    sets = [
        QuestionSetInfo(set_id=KIND_OPENTDB, name="Open Trivia Database (online)", kind=KIND_OPENTDB),
        QuestionSetInfo(set_id=KIND_TRIVIA_API, name="The Trivia API (online)", kind=KIND_TRIVIA_API),
    ]
    sets.extend(
        QuestionSetInfo(set_id=f"{KIND_CUSTOM}:{index}", name=custom.name, kind=KIND_CUSTOM)
        for index, custom in enumerate(config.custom_sets)
    )
    return sets


def default_fetch_json(url: str) -> Any:  # noqa: ANN401
    """GET ``url`` and decode the JSON body (the default network fetcher)."""
    request = urllib.request.Request(url, headers={"User-Agent": "gamecenter-quiz"})  # noqa: S310 - https URLs built from module constants
    with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:  # noqa: S310
        return json.load(response)


def load_questions(
    info: QuestionSetInfo,
    config: QuizConfig,
    fetch_json: Callable[[str], Any] = default_fetch_json,
) -> list[QuizQuestion]:
    """Load the questions behind ``info``; raises :class:`QuizSourceError` on failure."""
    if info.kind == KIND_OPENTDB:
        return _load_opentdb(config, fetch_json)
    if info.kind == KIND_TRIVIA_API:
        return _load_trivia_api(config, fetch_json)
    if info.kind == KIND_CUSTOM:
        return _load_custom(_custom_set_for(info, config))
    msg = f"Unknown question set kind: {info.kind!r}"
    raise QuizSourceError(msg)


def _amount(config: QuizConfig) -> int:
    return max(1, min(config.questions_per_game, _MAX_ONLINE_QUESTIONS))


def _load_opentdb(config: QuizConfig, fetch_json: Callable[[str], Any]) -> list[QuizQuestion]:
    # base64 encoding sidesteps OpenTDB's HTML-entity escaping of plain text.
    params: dict[str, Any] = {"amount": _amount(config), "encode": "base64"}
    if config.opentdb_category is not None:
        params["category"] = config.opentdb_category
    if config.difficulty:
        params["difficulty"] = config.difficulty
    payload = _fetch(f"{_OPENTDB_URL}?{urllib.parse.urlencode(params)}", fetch_json, "Open Trivia Database")
    if not isinstance(payload, dict) or payload.get("response_code") != 0:
        msg = "Open Trivia Database returned no questions; try another category or difficulty."
        raise QuizSourceError(msg)
    questions = []
    results = payload.get("results")
    for item in results if isinstance(results, list) else []:
        if not isinstance(item, dict):
            continue
        text = _decode_b64(item.get("question"))
        answer = _decode_b64(item.get("correct_answer"))
        if text and answer:
            questions.append(
                QuizQuestion(
                    text=text,
                    answer=answer,
                    category=_decode_b64(item.get("category")) or None,
                    difficulty=_decode_b64(item.get("difficulty")) or None,
                )
            )
    return _require_questions(questions, "Open Trivia Database")


def _load_trivia_api(config: QuizConfig, fetch_json: Callable[[str], Any]) -> list[QuizQuestion]:
    params: dict[str, Any] = {"limit": _amount(config)}
    if config.difficulty:
        params["difficulties"] = config.difficulty
    payload = _fetch(f"{_TRIVIA_API_URL}?{urllib.parse.urlencode(params)}", fetch_json, "The Trivia API")
    questions = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        question = item.get("question")
        text = question.get("text") if isinstance(question, dict) else question
        answer = item.get("correctAnswer")
        if isinstance(text, str) and text.strip() and isinstance(answer, str) and answer.strip():
            category = item.get("category")
            difficulty = item.get("difficulty")
            questions.append(
                QuizQuestion(
                    text=text.strip(),
                    answer=answer.strip(),
                    category=category if isinstance(category, str) and category else None,
                    difficulty=difficulty if isinstance(difficulty, str) and difficulty else None,
                )
            )
    return _require_questions(questions, "The Trivia API")


def _custom_set_for(info: QuestionSetInfo, config: QuizConfig) -> QuizCustomSet:
    try:
        index = int(info.set_id.split(":", 1)[1])
        return config.custom_sets[index]
    except (IndexError, ValueError) as exc:
        msg = f"Custom set {info.set_id!r} is no longer configured."
        raise QuizSourceError(msg) from exc


def _load_custom(custom: QuizCustomSet) -> list[QuizQuestion]:
    questions = [QuizQuestion(text=entry.question, answer=entry.answer) for entry in custom.questions]
    if custom.path:
        questions.extend(_load_custom_file(custom))
    if not questions:
        msg = f"Custom set '{custom.name}' has no questions; add inline questions or a valid file path."
        raise QuizSourceError(msg)
    return questions


def _load_custom_file(custom: QuizCustomSet) -> list[QuizQuestion]:
    path = Path(custom.path or "").expanduser()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        msg = f"Could not read custom set '{custom.name}' from {path}: {exc}"
        raise QuizSourceError(msg) from exc
    items = raw.get("questions") if isinstance(raw, dict) else raw
    questions = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        if text and answer:
            category = item.get("category")
            questions.append(
                QuizQuestion(
                    text=text,
                    answer=answer,
                    category=category if isinstance(category, str) and category else None,
                )
            )
    return questions


def _fetch(url: str, fetch_json: Callable[[str], Any], source_name: str) -> Any:  # noqa: ANN401
    try:
        return fetch_json(url)
    except QuizSourceError:
        raise
    except Exception as exc:
        msg = f"Could not reach {source_name}; check the network and try again."
        raise QuizSourceError(msg) from exc


def _require_questions(questions: list[QuizQuestion], source_name: str) -> list[QuizQuestion]:
    if not questions:
        msg = f"{source_name} returned no usable questions."
        raise QuizSourceError(msg)
    return questions


def _decode_b64(value: Any) -> str:  # noqa: ANN401
    if not isinstance(value, str) or not value:
        return ""
    try:
        return base64.b64decode(value).decode("utf-8").strip()
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return ""
