from typing import Literal

from pydantic import BaseModel


# Constrained string unions ensure only supported platform types are accepted.
# Adding a new platform means extending these literals and the adapters that handle them.
TriggerType = Literal["telegram", "webhook", "cron"]
ReplyType = Literal["telegram", "webhook"]


class Trigger(BaseModel):
    """How an agent gets activated.

    Different trigger types carry different metadata (command, path, schedule).
    Pydantic validates that `type` is one of the allowed literals at construction time.
    """

    type: TriggerType
    # Optional fields are per-type; we intentionally don't model them as a
    # discriminated union here to keep the schema flat and YAML-friendly.
    command: str | None = None
    path: str | None = None
    schedule: str | None = None


class Reply(BaseModel):
    """How an agent sends its response.

    Kept deliberately thin — routing logic lives in adapters, not here.
    """

    type: ReplyType


class AgentDefinition(BaseModel):
    """Complete definition of an agent — the single source of truth.

    All other layers (wiring, casting, adapters) derive their config from this
    model. Pydantic enforces that every required field is present, so a partial
    definition fails fast at load time rather than silently at runtime.
    """

    name: str
    role: str
    brain: str          # LLM identifier in provider/model format, e.g. "gemini/gemini-flash-latest"
    prompt: str
    tools: list[str]    # Dot-namespaced tool references, e.g. "github.list_issues"
    artifacts: list[str]
    trigger: Trigger
    reply: Reply
