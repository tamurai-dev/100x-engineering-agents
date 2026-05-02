"""
Duet Blueprint 生成 — 自然言語仕様から Task Agent + QA Agent を同時生成する

Duet Factory の中核モジュール。以下の7フェーズで動作する:
  Phase 1: Task Agent Blueprint 生成（既存 blueprint.py を再利用）
  Phase 2: QA Agent Blueprint 生成（qa_strategy.py でテンプレート自動選択）
  Phase 3: SKILL.md 生成
  Phase 4: duet.json + workflow.md 生成
  Phase 5: 登録 + バリデーション（マニフェスト + frontmatter + config 検証）

Usage:
    from duet_factory.duet_blueprint import generate_duet
    result = generate_duet(client, spec, model="claude-haiku-4-5")
"""

from __future__ import annotations

import datetime
import json
import re
import textwrap
from pathlib import Path

from duo_agents.json_utils import extract_json, parse_json_lenient
from duet_factory.qa_strategy import resolve_qa_strategy
from duet_factory.skill_resolver import (
    get_full_skill_catalog,
    resolve_skills,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = REPO_ROOT / "agents" / "agents"
DUETS_DIR = REPO_ROOT / "agents" / "duets"
TEMPLATES_DIR = REPO_ROOT / "agents" / "templates"

MODEL_MAP = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-7",
}

# ── Duet Blueprint 生成プロンプト ─────────────────

DUET_BLUEPRINT_SYSTEM = textwrap.dedent("""\
あなたはデュエット設計の専門家です。
ユーザーの自然言語仕様に基づいて、Task Agent と QA Agent のペアを設計してください。

## デュエットの設計原則

1. Task Agent（Actor）: タスクを実行して成果物を生成する
2. QA Agent（Critic）: 成果物を fresh-context で品質検査する（同意バイアス排除）
3. 両エージェントは独立して動作する（QA はタスク実行の過程を知らない）

## Task Agent の system prompt 設計

1. 「あなたは〇〇の専門家です。」で始める
2. 「## 責務」に具体的なタスクを番号付きで列挙（4-6項目）
3. 「## 出力形式」に具体的なフォーマットを定義
4. 「## 制約事項」にやってはいけないことを列挙
5. 弱点対策を含める:
   - 入力に存在しない情報を推測で補完してはならない
   - 指示された範囲の作業のみを行う
   - 不明点がある場合は AMBIGUITY: / ASSUMPTION: の形式で記録

## agent_type の判定基準

- detection: 入力を分析し問題/パターンを見つけて報告する
- generation_verifiable: コード/データを生成し、実行で正否を検証できる
- generation_subjective: テキスト/コンテンツを生成するが正解が一意でない
- repair_transform: 既存の成果物を変更して改善する
- planning: タスクを分解・計画・構造化する
- research_retrieval: 情報源を探索し質問に事実に基づいて回答する
- classification: 入力をカテゴリに分類し適切な先に振り分ける
- extraction: 非構造データから構造化データを抽出する

## artifact_format の判定基準

- text: テキスト出力（レビュー結果、計画書等）
- code: ソースコード（テスト、スクリプト等）
- structured_data: JSON/CSV（抽出結果、分類結果等）
- document: DOCX/PDF（レポート、契約書等）
- presentation: PPTX（プレゼン資料等）
- html_ui: HTML/CSS/React（ページ、コンポーネント等）
- media_image: 画像（バナー、図解等）
- media_video: 動画（プロモ、説明等）
- environment_state: 画面操作による環境変更

## ツール選択ガイド（Task Agent 用）

- 読み取りのみ: ["bash", "read", "glob", "grep"]
- ファイル生成あり: ["bash", "read", "glob", "grep", "write", "edit"]
- Web 検索が必要: 上記 + ["web_search", "web_fetch"]

以下の JSON のみを返してください。他のテキストは不要です。

{skill_catalog}
""")

DUET_BLUEPRINT_USER = textwrap.dedent("""\
以下の仕様でデュエット（Task Agent + QA Agent ペア）を設計してください:

{spec}

## 利用可能なスキル一覧

以下のスキルが利用可能です。タスクに適合する場合は `recommended_skills` に含めてください。
プリビルトスキル（pptx/xlsx/docx/pdf）がある場合はそれを優先的に使用してください。
プリビルトにない場合は、必要なパッケージを `required_packages` に指定してください。

{skill_catalog}

以下の JSON 形式で返してください:
```json
{{
  "duet_name": "kebab-case-duet（末尾に -duet を付ける）",
  "task_agent_name": "kebab-case のタスクエージェント名",
  "description": "デュエットの説明（50文字以上）",
  "agent_type": "{valid_types}",
  "artifact_format": "{valid_formats}",
  "task_system_prompt": "Task Agent の system prompt 全文",
  "task_tools": ["bash", "read", ...],
  "task_disallowed_tools": [],
  "skill_topics": ["タスクに必要なスキル・手順のトピック"],
  "recommended_skills": [
    {{“type”: “anthropic”, “skill_id”: “pptx”}}
  ],
  "required_packages": {{
    "npm": ["package-name"],
    "pip": ["package-name"]
  }},
  "test_prompts": [
    {{
      "name": "テスト名",
      "prompt": "テストプロンプト",
      "expected_behaviors": ["期待動作1"],
      "success_criteria": "成功基準"
    }}
  ]
}}
```

注意:
- `recommended_skills` が空の場合は `[]` を返してください
- `required_packages` が不要の場合は `{{}}` を返してください
- プリビルトスキルでカバーできる場合、同等のパッケージは `required_packages` に含めないでください
""")

# ── SKILL.md 生成プロンプト ─────────────────────────

SKILL_SYSTEM = textwrap.dedent("""\
あなたはエージェントのスキル設計専門家です。
Task Agent が高品質な成果物を生成するために必要な手順書（SKILL.md）を作成してください。

## SKILL.md の構造

1. ## 概要 — このスキルで何ができるか
2. ## 前提条件 — 必要なパッケージ・環境
3. ## 実行手順 — 具体的なステップバイステップの手順
4. ## スクリプトテンプレート — 成果物生成用スクリプトの例（該当する場合）
5. ## 品質基準 — 成果物が満たすべき品質基準
6. ## よくある問題と対策 — エラー対応ガイド

SKILL.md の全文のみを返してください。
""")

SKILL_USER = textwrap.dedent("""\
以下のデュエット用の SKILL.md を作成してください:

## デュエット情報
- 名前: {duet_name}
- 説明: {description}
- 成果物フォーマット: {artifact_format}
- タスクタイプ: {agent_type}
- スキルトピック: {skill_topics}

## Task Agent の責務
{task_system_prompt_excerpt}

SKILL.md の全文を返してください。
""")

# ── workflow.md 生成 ────────────────────────────────

WORKFLOW_TEMPLATE = textwrap.dedent("""\
# {duet_name} — ワークフロー手順書

## 概要

{description}

## ワークフローフロー

```
Phase A: Pre-task
  → duet.json 読込
  → SKILL.md を Task Agent コンテキストに注入
  → パッケージ確認（{verify_packages}）

Phase B: Task Execution
  → Task Agent（{task_agent_name}）を起動
  → 実行戦略: {execution_strategy}
  → 成果物を生成

Phase C: QA Loop（最大 {max_iterations} 回）
  → QA Agent（{qa_agent_name}）を fresh-context で起動
  → 成果物のみを渡す（タスク実行過程は渡さない）
  → score >= {pass_threshold} → PASS
  → score < {pass_threshold} → feedback → Task Agent で修正 → 再 QA

Phase D: Result
  → 最高スコア版を最終成果物として出力
  → 証跡を evidence/duets/ に保存
```

## エージェント構成

| 役割 | エージェント名 | モデル |
|------|--------------|-------|
| Task Agent（Actor） | {task_agent_name} | sonnet |
| QA Agent（Critic） | {qa_agent_name} | {qa_model} |

## 実行方法

```bash
make run-duet NAME={duet_name} INPUT="..." MODEL=haiku
```
""")


def _validate_duet_blueprint(data: dict) -> None:
    """Duet Blueprint の必須フィールドを検証する。"""
    required = [
        "duet_name", "task_agent_name", "description",
        "agent_type", "artifact_format",
        "task_system_prompt", "task_tools",
    ]
    missing = [f for f in required if f not in data]
    if missing:
        raise ValueError(f"Duet Blueprint に必須フィールドがありません: {missing}")

    valid_types = [
        "detection", "generation_verifiable", "generation_subjective",
        "repair_transform", "planning", "research_retrieval",
        "classification", "extraction",
    ]
    valid_formats = [
        "text", "code", "structured_data", "document", "presentation",
        "html_ui", "media_image", "media_video", "environment_state",
    ]

    if data["agent_type"] not in valid_types:
        raise ValueError(f"不明な agent_type: {data['agent_type']}")
    if data["artifact_format"] not in valid_formats:
        raise ValueError(f"不明な artifact_format: {data['artifact_format']}")

    # duet_name format check
    if not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]-duet$", data["duet_name"]):
        raise ValueError(
            f"duet_name は末尾 -duet の kebab-case にしてください: {data['duet_name']}"
        )


def generate_duet_blueprint(
    client, spec: str, model: str = "claude-haiku-4-5"
) -> dict:
    """自然言語仕様から Duet Blueprint を生成する。

    LLM にスキルカタログを渡し、適切なプリビルトスキルとパッケージを
    自動選択させる。

    Returns:
        Duet Blueprint dict
    """
    valid_types = (
        "detection | generation_verifiable | generation_subjective | "
        "repair_transform | planning | research_retrieval | "
        "classification | extraction"
    )
    valid_formats = (
        "text | code | structured_data | document | presentation | "
        "html_ui | media_image | media_video | environment_state"
    )

    # Build skill catalog for LLM to reference
    skill_catalog = get_full_skill_catalog()

    system = DUET_BLUEPRINT_SYSTEM.format(skill_catalog=skill_catalog)

    user = DUET_BLUEPRINT_USER.format(
        spec=spec,
        valid_types=valid_types,
        valid_formats=valid_formats,
        skill_catalog=skill_catalog,
    )

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    raw_text = response.content[0].text
    json_text = extract_json(raw_text)
    blueprint = parse_json_lenient(json_text)

    _validate_duet_blueprint(blueprint)

    # Merge LLM recommendations with programmatic skill resolution
    skill_resolution = resolve_skills(
        blueprint["artifact_format"], spec
    )
    llm_skills = blueprint.get("recommended_skills", [])
    llm_packages = blueprint.get("required_packages", {})

    # Prefer pre-built skills from resolver; merge LLM recommendations
    final_skills = list(skill_resolution.skills)
    seen_ids = {s["skill_id"] for s in final_skills}
    for s in llm_skills:
        if s.get("skill_id") and s["skill_id"] not in seen_ids:
            final_skills.append(s)
            seen_ids.add(s["skill_id"])

    # Merge packages: resolver defaults + LLM recommendations
    final_packages = dict(skill_resolution.packages)
    for mgr, pkgs in llm_packages.items():
        if mgr not in final_packages:
            final_packages[mgr] = list(pkgs)
        else:
            existing = set(final_packages[mgr])
            for p in pkgs:
                if p not in existing:
                    final_packages[mgr].append(p)

    # Store resolved skills/packages in blueprint
    blueprint["resolved_skills"] = final_skills
    blueprint["resolved_packages"] = final_packages
    blueprint["skill_resolution_summary"] = skill_resolution.summary

    return blueprint


def expand_task_agent(blueprint: dict) -> tuple[str, dict, list]:
    """Duet Blueprint から Task Agent のファイル群を生成する。

    Returns:
        (agent_md_text, config_dict, test_prompts_list)
    """
    name = blueprint["task_agent_name"]
    description = blueprint["description"]
    system_prompt = blueprint["task_system_prompt"]
    tools = blueprint["task_tools"]
    disallowed = blueprint.get("task_disallowed_tools", [])

    # === agent.md ===
    if disallowed:
        tools_section = "disallowedTools:\n" + "\n".join(
            f"  - {_to_pascal(t)}" for t in disallowed
        )
    else:
        tools_section = "tools:\n" + "\n".join(
            f"  - {_to_pascal(t)}" for t in tools
        )

    agent_md = textwrap.dedent(f"""\
---
name: {name}
description: >
  {description}
model: sonnet
{tools_section}
effort: high
---

{system_prompt}
""")

    # === config.json ===
    tool_configs = [{"name": t, "enabled": True} for t in tools]
    config = {
        "name": name,
        "description": description,
        "model": "claude-sonnet-4-6",
        "system": system_prompt,
        "tools": [
            {
                "type": "agent_toolset_20260401",
                "default_config": {"enabled": False},
                "configs": tool_configs,
            }
        ],
    }

    # === test-prompts.json ===
    test_prompts = blueprint.get("test_prompts", [])

    return agent_md, config, test_prompts


def expand_qa_agent(blueprint: dict) -> tuple[str, dict]:
    """Duet Blueprint から QA Agent のファイル群を生成する。

    qa_strategy.py の QA テンプレートを使い、プレースホルダーを置換する。

    Returns:
        (agent_md_text, config_dict)
    """
    strategy = resolve_qa_strategy(blueprint["artifact_format"])
    duet_name = blueprint["duet_name"].removesuffix("-duet")
    qa_name = f"{duet_name}-qa"
    description = blueprint["description"]

    # agent.md: テンプレートを読み込みプレースホルダー置換
    agent_template_path = strategy.agent_template_path
    agent_md = agent_template_path.read_text(encoding="utf-8")
    agent_md = agent_md.replace("<duet-name>", duet_name)
    agent_md = agent_md.replace("<duet-description>", description)

    # config.json: テンプレートを読み込みプレースホルダー置換
    config_template_path = strategy.config_template_path
    config_text = config_template_path.read_text(encoding="utf-8")
    # JSON-escape description to prevent JSONDecodeError from special chars
    safe_description = json.dumps(description)[1:-1]
    config_text = config_text.replace("<duet-name>", duet_name)
    config_text = config_text.replace("<duet-description>", safe_description)
    config_text = config_text.replace(
        "<model>",
        MODEL_MAP.get(strategy.recommended_model, strategy.recommended_model),
    )
    config = json.loads(config_text)

    return agent_md, config


def generate_skill(
    client, blueprint: dict, model: str = "claude-haiku-4-5"
) -> str:
    """SKILL.md を自動生成する。

    Returns:
        SKILL.md テキスト
    """
    skill_topics = ", ".join(blueprint.get("skill_topics", ["一般"]))
    prompt_excerpt = blueprint["task_system_prompt"][:500]

    # Escape braces in LLM-generated content to prevent str.format() crashes
    safe_excerpt = prompt_excerpt.replace("{", "{{").replace("}", "}}")
    safe_description = blueprint["description"].replace("{", "{{").replace("}", "}}")

    user = SKILL_USER.format(
        duet_name=blueprint["duet_name"],
        description=safe_description,
        artifact_format=blueprint["artifact_format"],
        agent_type=blueprint["agent_type"],
        skill_topics=skill_topics,
        task_system_prompt_excerpt=safe_excerpt,
    )

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SKILL_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )

    return response.content[0].text


def generate_duet_json(blueprint: dict) -> dict:
    """duet.json を生成する。"""
    strategy = resolve_qa_strategy(blueprint["artifact_format"])
    duet_name = blueprint["duet_name"]
    task_name = blueprint["task_agent_name"]
    qa_name = duet_name.removesuffix("-duet") + "-qa"
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    resolved_skills = blueprint.get("resolved_skills", [])
    resolved_packages = blueprint.get("resolved_packages", {})
    # Filter out empty package lists
    resolved_packages = {k: v for k, v in resolved_packages.items() if v}

    duet_json: dict = {
        "name": duet_name,
        "version": "1.0.0",
        "description": blueprint["description"],
        "artifact_format": blueprint["artifact_format"],
        "tags": [],
        "metadata": {
            "author": "duet-factory",
            "created_at": now,
        },
        "task_agent": {
            "name": task_name,
            "ref": f"agents/agents/{task_name}",
        },
        "qa_agent": {
            "name": qa_name,
            "ref": f"agents/agents/{qa_name}",
        },
        "skill": f"agents/duets/{duet_name}/skill.md",
        "workflow": {
            "pre_task": {
                "read_skills": True,
            },
            "execution": {
                "strategy": strategy.execution_strategy,
            },
            "qa": {
                "max_iterations": 3,
                "pass_threshold": 0.80,
                "convergence_delta": 0.02,
                "keep_best": True,
                "escalation_threshold": 0.40,
                "model_escalation": ["haiku", "sonnet"],
            },
        },
    }

    # Add skills if resolved
    if resolved_skills:
        duet_json["skills"] = resolved_skills

    # Add environment if packages are needed
    if resolved_packages:
        duet_json["environment"] = {
            "packages": resolved_packages,
            "networking": {"type": "unrestricted"},
        }

    return duet_json


def generate_workflow_md(blueprint: dict, duet_json: dict) -> str:
    """workflow.md を生成する。"""
    strategy = resolve_qa_strategy(blueprint["artifact_format"])
    qa_name = blueprint["duet_name"].removesuffix("-duet") + "-qa"
    workflow = duet_json["workflow"]
    pre_task = workflow.get("pre_task", {})
    packages = pre_task.get("verify_packages", [])

    return WORKFLOW_TEMPLATE.format(
        duet_name=blueprint["duet_name"],
        description=blueprint["description"],
        verify_packages=", ".join(packages) if packages else "なし",
        task_agent_name=blueprint["task_agent_name"],
        qa_agent_name=qa_name,
        execution_strategy=workflow.get("execution", {}).get("strategy", "direct"),
        max_iterations=workflow["qa"]["max_iterations"],
        pass_threshold=workflow["qa"]["pass_threshold"],
        qa_model=strategy.recommended_model,
    )


def save_duet(
    blueprint: dict,
    task_agent_md: str,
    task_config: dict,
    task_test_prompts: list,
    qa_agent_md: str,
    qa_config: dict,
    duet_json: dict,
    workflow_md: str,
    skill_md: str,
) -> dict[str, Path]:
    """生成された全ファイルをディスクに書き出す。

    Returns:
        作成したディレクトリ・ファイルのパス辞書
    """
    task_name = blueprint["task_agent_name"]
    qa_name = blueprint["duet_name"].removesuffix("-duet") + "-qa"
    duet_name = blueprint["duet_name"]

    paths: dict[str, Path] = {}

    # Task Agent → agents/agents/<task-name>/
    task_dir = AGENTS_DIR / task_name
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "agent.md").write_text(task_agent_md, encoding="utf-8")
    _write_json(task_dir / "config.json", task_config)
    _write_json(task_dir / "test-prompts.json", task_test_prompts)
    paths["task_agent_dir"] = task_dir

    # QA Agent → agents/agents/<qa-name>/
    qa_dir = AGENTS_DIR / qa_name
    qa_dir.mkdir(parents=True, exist_ok=True)
    (qa_dir / "agent.md").write_text(qa_agent_md, encoding="utf-8")
    _write_json(qa_dir / "config.json", qa_config)
    _write_json(qa_dir / "test-prompts.json", [])
    paths["qa_agent_dir"] = qa_dir

    # Duet → agents/duets/<duet-name>/
    duet_dir = DUETS_DIR / duet_name
    duet_dir.mkdir(parents=True, exist_ok=True)
    _write_json(duet_dir / "duet.json", duet_json)
    (duet_dir / "workflow.md").write_text(workflow_md, encoding="utf-8")
    (duet_dir / "skill.md").write_text(skill_md, encoding="utf-8")
    paths["duet_dir"] = duet_dir

    return paths


def _write_json(path: Path, data) -> None:
    """JSON ファイルを書き出す。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _to_pascal(s: str) -> str:
    """snake_case → PascalCase 変換。"""
    return "".join(word.capitalize() for word in s.split("_"))
