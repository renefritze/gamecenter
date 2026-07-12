"""Small dotenv loader for local runtime credentials."""

from __future__ import annotations

import os
import re
from pathlib import Path

_COMMENT_RE = re.compile(r"\s+#.*$")
_EXPORT_PREFIX = "export "
_MIN_QUOTED_LENGTH = 2
_TRUE_VALUES = {"1", "true", "yes", "on"}


def _parse_dotenv_value(raw: str) -> str:
    """Parse one dotenv value using the common subset this app needs."""
    value = raw.strip()
    if len(value) >= _MIN_QUOTED_LENGTH and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
        if raw.strip().startswith('"'):
            value = bytes(value, "utf-8").decode("unicode_escape")
        return value
    return _COMMENT_RE.sub("", value).strip()


def load_dotenv(path: Path | str = ".env") -> int:
    """Load missing environment variables from ``path`` if it exists.

    Existing process environment variables are left untouched. Returns the
    number of variables loaded, which is useful in tests and harmless for app
    startup.
    """
    dotenv_path = Path(path)
    if not dotenv_path.is_file():
        return 0

    loaded = 0
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(_EXPORT_PREFIX):
            line = line[len(_EXPORT_PREFIX) :].lstrip()
        key, separator, raw_value = line.partition("=")
        key = key.strip()
        if not separator or not key or key in os.environ:
            continue
        os.environ[key] = _parse_dotenv_value(raw_value)
        loaded += 1
    return loaded


def env_flag(name: str) -> bool:
    """Return whether an environment flag is explicitly enabled."""
    return os.environ.get(name, "").strip().lower() in _TRUE_VALUES
