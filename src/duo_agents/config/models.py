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
# Switching opus to 4.7 is an API breaking change — see ``ModelCapabilities``
# for the matching SUPPORTS_* set updates.
MODEL_IDS: Final[dict[ModelTier, str]] = {
    ModelTier.HAIKU: "claude-haiku-4-5",
    ModelTier.SONNET: "claude-sonnet-4-6",
    ModelTier.OPUS: "claude-opus-4-7",
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

    Claude Opus 4.7 (the current default) drops the legacy ``thinking``
    config block and the ``temperature`` / ``top_p`` / ``top_k`` sampling
    parameters in favour of adaptive thinking. Haiku 4.5 and Sonnet 4.6
    still accept the legacy fields, so they remain in the support sets.
    """

    SUPPORTS_LEGACY_THINKING: Final[set[ModelTier]] = {
        ModelTier.HAIKU,
        ModelTier.SONNET,
    }

    SUPPORTS_SAMPLING_PARAMS: Final[set[ModelTier]] = {
        ModelTier.HAIKU,
        ModelTier.SONNET,
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
