"""
Custom exception hierarchy.

Rationale: a bare `except Exception` at the CLI boundary can't tell a
"you forgot to set an API key" problem apart from "the LLM provider is
down" apart from "the model returned garbage we can't parse." Distinct
exception types let the CLI give the user an actionable message instead
of a raw traceback, and let callers (e.g. a future web handler) decide
per-failure-mode whether to retry, alert, or surface to the user.
"""


class LessonAgentError(Exception):
    """Base class for all errors raised by this package."""


class ConfigurationError(LessonAgentError):
    """Raised when required configuration (e.g. API key) is missing or invalid."""


class LLMProviderError(LessonAgentError):
    """Raised when an LLM provider call fails after its retry budget is exhausted."""


class JudgeOutputParseError(LessonAgentError):
    """Raised when the evaluator's response can't be parsed into valid, schema-conformant verdicts."""
