"""Pydantic v2 models for the three project schemas.

Replaces the JSON Schema files under ``agents/schemas/``:

* ``subagent-frontmatter.schema.json`` → :class:`SubagentFrontmatter`
* ``managed-agent-config.schema.json`` → :class:`ManagedAgentConfig`
* ``duet.schema.json``               → :class:`Duet`

Design notes:

* Models use ``model_config = ConfigDict(extra="forbid")`` to mirror the
  JSON Schema ``additionalProperties: false`` constraint.
* Cross-field invariants (e.g. ``tools`` XOR ``disallowedTools``) live in
  :class:`SubagentFrontmatter`'s ``model_validator``.
* The complex tool / mcp / skill arrays in :class:`ManagedAgentConfig` are
  modelled as ``list[dict]`` rather than discriminated unions, because the
  Anthropic Managed Agents API surface is large and changes often. The
  framework only validates the *invariants we care about* (required fields,
  count limits, basic types). Full structural validation is the API's job.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from duo_agents.config.artifacts import VALID_ARTIFACT_FORMATS


# ── 1. SubagentFrontmatter ────────────────────────────────────────────────────


_NAME_PATTERN = r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$"


SubagentName = Annotated[
    str,
    StringConstraints(pattern=_NAME_PATTERN, max_length=64),
]


class SubagentFrontmatter(BaseModel):
    """Claude Code v2.1+ subagent YAML frontmatter (16 fields)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: SubagentName = Field(description="lowercase + hyphen, max 64 chars.")
    description: Annotated[str, StringConstraints(min_length=10)] = Field(
        description="Third-person agent description, min 10 chars."
    )
    model: str | None = Field(
        default=None,
        description="Tier alias (haiku/sonnet/opus/inherit) or full claude-* ID.",
    )
    tools: list[str] | None = Field(default=None)
    disallowedTools: list[str] | None = Field(default=None)
    permissionMode: (
        Literal["default", "acceptEdits", "auto", "dontAsk", "bypassPermissions", "plan"]
        | None
    ) = Field(default=None)
    maxTurns: Annotated[int, Field(ge=1)] | None = Field(default=None)
    skills: list[str] | None = Field(default=None)
    mcpServers: list[str | dict[str, Any]] | None = Field(default=None)
    hooks: dict[str, Any] | None = Field(default=None)
    memory: Literal["user", "project", "local"] | None = Field(default=None)
    background: bool | None = Field(default=None)
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = Field(default=None)
    isolation: Literal["worktree"] | None = Field(default=None)
    initialPrompt: str | None = Field(default=None)
    color: (
        Literal["red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"]
        | None
    ) = Field(default=None)

    @model_validator(mode="after")
    def _validate_model_field(self) -> SubagentFrontmatter:
        if self.model is None:
            return self
        if self.model in {"haiku", "sonnet", "opus", "inherit"}:
            return self
        if self.model.startswith("claude-"):
            return self
        raise ValueError(
            f"model must be one of haiku/sonnet/opus/inherit or start with 'claude-', got: {self.model!r}"
        )

    @model_validator(mode="after")
    def _tools_disallowed_tools_exclusive(self) -> SubagentFrontmatter:
        if self.tools is not None and self.disallowedTools is not None:
            raise ValueError(
                "'tools' と 'disallowedTools' は排他です。どちらか一方のみ指定してください"
            )
        return self


# ── 2. ManagedAgentConfig ─────────────────────────────────────────────────────


_KNOWN_MODEL_IDS: frozenset[str] = frozenset(
    {
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
        "claude-haiku-4-5-20251001",
        "claude-opus-4-5",
        "claude-opus-4-5-20251101",
        "claude-sonnet-4-5",
        "claude-sonnet-4-5-20250929",
    }
)


class ModelConfig(BaseModel):
    """Object form of ``model`` field (with optional speed setting)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    speed: Literal["standard", "fast"] | None = None


class ManagedAgentConfig(BaseModel):
    """Anthropic Managed Agents API ``agents.create`` parameters.

    The framework validates the high-level invariants only: required fields,
    string length caps, and array length caps. Inner shapes for
    ``tools`` / ``mcp_servers`` / ``skills`` are validated lightly so the model
    keeps working as Anthropic ships new tool kinds.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    description: Annotated[str, StringConstraints(max_length=2048)] | None = None
    model: str | ModelConfig
    system: Annotated[str, StringConstraints(max_length=100_000)]
    tools: Annotated[list[dict[str, Any]], Field(max_length=128)] | None = None
    mcp_servers: Annotated[list[dict[str, Any]], Field(max_length=20)] | None = None
    skills: Annotated[list[dict[str, Any]], Field(max_length=20)] | None = None
    metadata: dict[str, str] | None = None

    @model_validator(mode="after")
    def _validate_model_id(self) -> ManagedAgentConfig:
        model_id = self.model.id if isinstance(self.model, ModelConfig) else self.model
        if model_id not in _KNOWN_MODEL_IDS:
            raise ValueError(
                f"unknown model id: {model_id!r}. "
                f"Add it to ManagedAgentConfig._KNOWN_MODEL_IDS once Anthropic ships it."
            )
        return self

    @model_validator(mode="after")
    def _validate_metadata_caps(self) -> ManagedAgentConfig:
        if self.metadata is None:
            return self
        if len(self.metadata) > 16:
            raise ValueError("metadata supports at most 16 key/value pairs")
        for key, value in self.metadata.items():
            if not (1 <= len(key) <= 64):
                raise ValueError(f"metadata key length must be 1..64: {key!r}")
            if len(value) > 512:
                raise ValueError(f"metadata value length must be <= 512: {key!r}")
        return self


# ── 3. Duet ─────────────────────────────────────────────────────────────────


_DUET_NAME_PATTERN = r"^[a-z0-9][a-z0-9-]*[a-z0-9]-duet$"
_AGENT_REF_PATTERN = r"^agents/agents/[a-z0-9][a-z0-9-]*[a-z0-9]$"
_SEMVER_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+$"
_TAG_PATTERN = r"^[a-z0-9][a-z0-9-]*[a-z0-9]$"


class AgentRef(BaseModel):
    """Reference to a subagent under ``agents/agents/<name>/``."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(pattern=_NAME_PATTERN, min_length=1)]
    ref: Annotated[str, StringConstraints(pattern=_AGENT_REF_PATTERN)]


class SkillEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["anthropic", "custom"]
    skill_id: Annotated[str, StringConstraints(min_length=1)]
    version: str | None = None


class PackageList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    apt: list[str] | None = None
    cargo: list[str] | None = None
    gem: list[str] | None = None
    go: list[str] | None = None
    npm: list[str] | None = None
    pip: list[str] | None = None


class DuetMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class DuetNetworking(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["unrestricted", "restricted"] = "unrestricted"


class DuetEnvironment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packages: PackageList | None = None
    networking: DuetNetworking | None = None


class DuetPreTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    read_skills: bool = True
    verify_packages: list[str] | None = None


class DuetExecution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Literal["script_generation", "direct", "hybrid"] = "direct"


class DuetQA(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_iterations: Annotated[int, Field(ge=1, le=10)] = 3
    pass_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.80
    convergence_delta: Annotated[float, Field(ge=0.0, le=0.5)] = 0.02
    keep_best: bool = True
    escalation_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.40
    model_escalation: list[Literal["haiku", "sonnet", "opus"]] = Field(
        default_factory=lambda: ["haiku", "sonnet"]
    )

    @model_validator(mode="after")
    def _model_escalation_unique(self) -> DuetQA:
        if not (1 <= len(self.model_escalation) <= 3):
            raise ValueError("model_escalation must have 1..3 entries")
        if len(set(self.model_escalation)) != len(self.model_escalation):
            raise ValueError("model_escalation entries must be unique")
        return self


class DuetWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pre_task: DuetPreTask | None = None
    execution: DuetExecution | None = None
    qa: DuetQA


class DuetMultiagent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    orchestrator_model: Literal["haiku", "sonnet", "opus"] = "haiku"


class Duet(BaseModel):
    """Actor-Critic Duet definition (``duet.json``)."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str,
        StringConstraints(pattern=_DUET_NAME_PATTERN, min_length=3, max_length=128),
    ]
    version: Annotated[str, StringConstraints(pattern=_SEMVER_PATTERN)]
    description: Annotated[str, StringConstraints(min_length=10, max_length=2048)]
    artifact_format: str
    tags: list[Annotated[str, StringConstraints(pattern=_TAG_PATTERN)]] | None = Field(
        default=None,
        max_length=20,
    )
    metadata: DuetMetadata | None = None
    task_agent: AgentRef
    qa_agent: AgentRef
    skill: str | None = None
    skills: Annotated[list[SkillEntry], Field(max_length=20)] | None = None
    environment: DuetEnvironment | None = None
    workflow: DuetWorkflow
    multiagent: DuetMultiagent | None = None

    @model_validator(mode="after")
    def _validate_artifact_format(self) -> Duet:
        if self.artifact_format not in VALID_ARTIFACT_FORMATS:
            raise ValueError(
                f"artifact_format must be one of {sorted(VALID_ARTIFACT_FORMATS)}, "
                f"got: {self.artifact_format!r}"
            )
        return self

    @model_validator(mode="after")
    def _validate_tags_unique(self) -> Duet:
        if self.tags is not None and len(set(self.tags)) != len(self.tags):
            raise ValueError("tags must be unique")
        return self


# ── Public format helper ──────────────────────────────────────────────────────


def format_validation_error(exc: Exception) -> list[str]:
    """Render a pydantic ``ValidationError`` as the error-message list format
    used by the legacy validators (one entry per error, prefixed with the
    JSON path when available).
    """
    from pydantic import ValidationError

    if not isinstance(exc, ValidationError):
        return [f"  {exc}"]

    out: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", ())) or "(root)"
        msg = err.get("msg", "")
        out.append(f"  [{loc}] {msg}")
    return out


__all__ = [
    "AgentRef",
    "Duet",
    "DuetEnvironment",
    "DuetExecution",
    "DuetMetadata",
    "DuetMultiagent",
    "DuetNetworking",
    "DuetPreTask",
    "DuetQA",
    "DuetWorkflow",
    "ManagedAgentConfig",
    "ModelConfig",
    "PackageList",
    "SkillEntry",
    "SubagentFrontmatter",
    "format_validation_error",
]
