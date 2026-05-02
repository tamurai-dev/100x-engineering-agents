"""
QA 戦略エンジン — artifact_format に基づく QA テンプレート自動選択

duet.json の artifact_format フィールドから、最適な QA テンプレートと
QA パイプライン設定を自動選択する。

Usage:
    from scripts.duet_factory.qa_strategy import resolve_qa_strategy

    strategy = resolve_qa_strategy("presentation")
    print(strategy.agent_template)    # "qa-agent/presentation.md.tmpl"
    print(strategy.config_template)   # "qa-agent/config.json.tmpl"
    print(strategy.pipeline)          # ["convert_pdf", "render_png", "vision_qa"]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = REPO_ROOT / "agents" / "templates"

# All artifact_format values defined in duet.schema.json
VALID_ARTIFACT_FORMATS = frozenset(
    [
        "text",
        "code",
        "structured_data",
        "document",
        "presentation",
        "html_ui",
        "media_image",
        "media_video",
        "environment_state",
    ]
)


@dataclass(frozen=True)
class QAStrategy:
    """artifact_format に対応する QA 戦略定義。"""

    artifact_format: str
    agent_template: str
    config_template: str
    pipeline: list[str] = field(default_factory=list)
    execution_strategy: str = "direct"
    recommended_model: str = "haiku"
    description: str = ""

    @property
    def agent_template_path(self) -> Path:
        return TEMPLATES_DIR / self.agent_template

    @property
    def config_template_path(self) -> Path:
        return TEMPLATES_DIR / self.config_template

    def validate_templates_exist(self) -> list[str]:
        """Register missing template files as errors."""
        errors: list[str] = []
        if not self.agent_template_path.exists():
            errors.append(
                f"QA agent template not found: {self.agent_template_path}"
            )
        if not self.config_template_path.exists():
            errors.append(
                f"QA config template not found: {self.config_template_path}"
            )
        return errors


# ── QA Strategy Map ──────────────────────────────────────────
# artifact_format → QAStrategy
#
# Phase 3: presentation / html_ui / code に専用テンプレート
# Others:  generic テンプレートでカバー
# ─────────────────────────────────────────────────────────────

_STRATEGY_MAP: dict[str, QAStrategy] = {
    "presentation": QAStrategy(
        artifact_format="presentation",
        agent_template="qa-agent/presentation.md.tmpl",
        config_template="qa-agent/config.json.tmpl",
        pipeline=["convert_pdf", "render_png", "vision_qa"],
        execution_strategy="script_generation",
        recommended_model="sonnet",
        description="PPTX -> PDF -> PNG -> Vision API でビジュアル品質検査",
    ),
    "html_ui": QAStrategy(
        artifact_format="html_ui",
        agent_template="qa-agent/html-ui.md.tmpl",
        config_template="qa-agent/config.json.tmpl",
        pipeline=["playwright_screenshot", "vision_qa"],
        execution_strategy="script_generation",
        recommended_model="sonnet",
        description="Playwright screenshot -> Vision API でUI品質検査",
    ),
    "code": QAStrategy(
        artifact_format="code",
        agent_template="qa-agent/code.md.tmpl",
        config_template="qa-agent/config.json.tmpl",
        pipeline=["lint", "test_execution", "static_analysis"],
        execution_strategy="direct",
        recommended_model="haiku",
        description="lint + test execution + 静的解析でコード品質検査",
    ),
}

# generic fallback defaults (text, structured_data, document, media_*, environment_state)
_GENERIC_DEFAULTS = {
    "agent_template": "qa-agent/generic.md.tmpl",
    "config_template": "qa-agent/config.json.tmpl",
    "pipeline": ["text_analysis"],
    "execution_strategy": "direct",
    "recommended_model": "haiku",
    "description": "汎用テキスト分析による品質検査",
}


def _make_generic_strategy(artifact_format: str) -> QAStrategy:
    """元の artifact_format を保持した generic 戦略を生成する。"""
    return QAStrategy(artifact_format=artifact_format, **_GENERIC_DEFAULTS)


def resolve_qa_strategy(artifact_format: str) -> QAStrategy:
    """artifact_format から最適な QA 戦略を解決する。

    Args:
        artifact_format: duet.json の artifact_format 値。

    Returns:
        QAStrategy: 選択された QA 戦略。

    Raises:
        ValueError: artifact_format が duet.schema.json の enum に含まれない場合。
    """
    if artifact_format not in VALID_ARTIFACT_FORMATS:
        raise ValueError(
            f"Unknown artifact_format: {artifact_format!r}. "
            f"Valid formats: {sorted(VALID_ARTIFACT_FORMATS)}"
        )
    if artifact_format in _STRATEGY_MAP:
        return _STRATEGY_MAP[artifact_format]
    return _make_generic_strategy(artifact_format)


def list_strategies() -> dict[str, QAStrategy]:
    """登録済みの全 QA 戦略を返す（テスト・デバッグ用）。"""
    result: dict[str, QAStrategy] = {}
    for fmt in sorted(VALID_ARTIFACT_FORMATS):
        result[fmt] = resolve_qa_strategy(fmt)
    return result


def get_strategy_summary() -> str:
    """人間可読な QA 戦略サマリーを返す。"""
    lines = ["artifact_format -> QA Strategy:"]
    for fmt, strategy in list_strategies().items():
        tmpl = strategy.agent_template
        desc = strategy.description
        lines.append(f"  {fmt:20s} -> {tmpl:30s} ({desc})")
    return "\n".join(lines)
