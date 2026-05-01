"""Model definitions — when a new Claude model is released, update only this file.

The constants in this module are the single source of truth for which Claude
model corresponds to each tier (haiku / sonnet / opus). The Bundle Runner,
Factory and Eval modules all dereference ``MODEL_IDS`` instead of hard-coding
model IDs.
"""

from __future__ import annotations

from enum import Enum
from typing import Final


class ModelTier(str, Enum):
    """Logical tier name decoupled from the concrete API model ID.

    Using a tier name (``haiku`` / ``sonnet`` / ``opus``) rather than an API ID
    in user-facing config (Makefile targets, bundle.json) means that bumping a
    model only requires editing ``MODEL_IDS`` below.
    """

    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"


# When a new Claude model is released, edit only this dict.
# PR-1 keeps opus on 4-6; PR-3 will switch the default to claude-opus-4-7
# along with the API breaking-change handling for that model.
MODEL_IDS: Final[dict[ModelTier, str]] = {
    ModelTier.HAIKU: "claude-haiku-4-5",
    ModelTier.SONNET: "claude-sonnet-4-6",
    ModelTier.OPUS: "claude-opus-4-6",
}

DEFAULT_MODEL: Final[ModelTier] = ModelTier.HAIKU

# Escalation order used when QA scores stay below ``DEFAULT_ESCALATION_THRESHOLD``.
# The runner walks this list left-to-right when deciding to up-tier.
ESCALATION_ORDER: Final[list[ModelTier]] = [
    ModelTier.HAIKU,
    ModelTier.SONNET,
    ModelTier.OPUS,
]


class ModelCapabilities:
    """Capabilities that differ between models.

    PR-1 keeps every tier marked as supporting legacy thinking and sampling
    parameters because the current default opus model (4.6) still accepts
    them. PR-3 will narrow these sets when the default opus moves to 4.7,
    which removes ``temperature`` / ``top_p`` / ``top_k`` and switches to
    adaptive thinking.
    """

    SUPPORTS_LEGACY_THINKING: Final[set[ModelTier]] = {
        ModelTier.HAIKU,
        ModelTier.SONNET,
        ModelTier.OPUS,
    }

    SUPPORTS_SAMPLING_PARAMS: Final[set[ModelTier]] = {
        ModelTier.HAIKU,
        ModelTier.SONNET,
        ModelTier.OPUS,
    }

    @classmethod
    def supports_legacy_thinking(cls, tier: ModelTier) -> bool:
        return tier in cls.SUPPORTS_LEGACY_THINKING

    @classmethod
    def supports_sampling_params(cls, tier: ModelTier) -> bool:
        return tier in cls.SUPPORTS_SAMPLING_PARAMS


def resolve_model_id(tier_or_id: str) -> str:
    """Resolve a tier name (e.g. ``haiku``) to its API model ID.

    Passing a full model ID (e.g. ``claude-haiku-4-5``) is a no-op.
    """
    try:
        tier = ModelTier(tier_or_id)
    except ValueError:
        return tier_or_id
    return MODEL_IDS[tier]
