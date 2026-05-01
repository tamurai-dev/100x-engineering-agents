"""Default thresholds for QA loops, EDD loops and model escalation.

These values are *defaults* — individual bundle.json / duet.json files can
override them. Centralizing here lets us tune quality vs. cost trade-offs in
one place.
"""

from __future__ import annotations

from typing import Final

# ── QA loop (per-execution) ──────────────────────────────────────────────────
# Used by the Bundle Runner when invoking the QA Agent on each Task Agent
# artifact. The runner retries the Task Agent up to ``DEFAULT_QA_MAX_ITERATIONS``
# times until the QA score reaches ``DEFAULT_QA_PASS_THRESHOLD``.
DEFAULT_QA_PASS_THRESHOLD: Final[float] = 0.80
DEFAULT_QA_MAX_ITERATIONS: Final[int] = 3
DEFAULT_QA_CONVERGENCE_DELTA: Final[float] = 0.02

# ── Model escalation (per-execution) ─────────────────────────────────────────
# When QA score is at or below ``DEFAULT_ESCALATION_THRESHOLD`` AND the score
# improvement is smaller than ``DEFAULT_ESCALATION_IMPROVEMENT_DELTA`` between
# iterations, the runner escalates haiku → sonnet → opus.
DEFAULT_ESCALATION_THRESHOLD: Final[float] = 0.40
DEFAULT_ESCALATION_IMPROVEMENT_DELTA: Final[float] = 0.05

# ── EDD loop (development-time) ──────────────────────────────────────────────
# Eval-Driven Development runs the full eval suite, analyses scores, and
# improves the Task Agent prompt. Stops when the overall score reaches
# ``DEFAULT_EDD_TARGET_OVERALL`` or after ``DEFAULT_EDD_MAX_ITERATIONS`` rounds
# or when the round-over-round delta falls below
# ``DEFAULT_EDD_CONVERGENCE_DELTA``.
DEFAULT_EDD_TARGET_OVERALL: Final[float] = 0.65
DEFAULT_EDD_MAX_ITERATIONS: Final[int] = 3
DEFAULT_EDD_CONVERGENCE_DELTA: Final[float] = 0.02
