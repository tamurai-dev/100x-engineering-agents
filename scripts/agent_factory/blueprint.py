"""
Blueprint 生成 — 自然言語仕様からエージェント定義ファイル群を生成する

Claude Messages API を1回呼び出し、以下を同時に生成する:
  - agent.md（Claude Code subagent 定義）
  - config.json（Managed Agents API 設定）
  - test-prompts.json（スモークテストケース）

内部動作:
  1. 既存エージェント（code-reviewer, doc-writer）を Few-Shot Example として読み込む
  2. ユーザー仕様 + 8タイプ分類基準 + 成果物フォーマット基準を Claude に渡す
  3. Claude が返す Blueprint JSON を agent.md / config.json / test-prompts.json に展開する

8タイプ分類:
  detection | generation_verifiable | generation_subjective | repair_transform
  planning | research_retrieval | classification | extraction

成果物フォーマット:
  text | code | structured_data | document | presentation
  html_ui | media_image | media_video | environment_state

エージェントの弱点への対策:
  生成される system prompt には、エージェントが苦手とする以下の状況への
  明示的な指示が組み込まれる:
  - 幻覚行動の抑制（存在しないデータへの操作を禁止）
  - スコープクリープの防止（依頼範囲外の操作を禁止）
  - 「何もしない」判断の許容（問題なしの場合は問題なしと報告）
  - 曖昧さの明示（不明点は仮定を述べてから進む）
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = REPO_ROOT / "agents" / "agents"

# ── 8タイプ分類 ─────────────────────────────────────

VALID_AGENT_TYPES = [
    "detection",
    "generation_verifiable",
    "generation_subjective",
    "repair_transform",
    "planning",
    "research_retrieval",
    "classification",
    "extraction",
]

# ── 9成果物フォーマット ─────────────────────────────

VALID_ARTIFACT_FORMATS = [
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

# ── タイプ別の弱点対策指示 ──────────────────────────

WEAKNESS_MITIGATIONS = {
    "__all__": [
        "入力に存在しない情報を推測で補完してはならない",
        "指示された範囲の作業のみを行う。関連する改善提案がある場合は本作業とは別のセクションで報告する",
        "不明点がある場合は AMBIGUITY: [曖昧な点] / ASSUMPTION: [仮定] の形式で記録してから作業を進める",
    ],
    "detection": [
        "問題が見つからない場合は「問題は検出されませんでした」と明示的に報告する",
        "確信度が低い指摘は報告しない。誤検出は見逃しより有害である",
    ],
    "extraction": [
        "ドキュメントに記載されていないフィールドは空欄にする。推測で埋めない",
        "読み取れない文字は「[判読不能]」と記載する",
        "大量のデータを処理する場合も各行の構造を一定に保つ。欠落フィールドは空文字にする",
    ],
    "classification": [
        "既知のどのカテゴリにも当てはまらない場合は「該当なし」または「その他」と分類する",
        "無理にカテゴリを当てはめない",
    ],
    "repair_transform": [
        "指摘された問題のみ修正し、それ以外のコードは変更しない",
        "修正が不要な場合は「変更不要」と報告する",
    ],
    "generation_verifiable": [
        "エッジケースとエラーハンドリングを必ず考慮する",
        "ビジネスルールが曖昧な場合は仮定を明示してから実装する",
    ],
    "generation_subjective": [
        "出力形式のセクションで定義した構造を厳守する",
    ],
    "planning": [
        "矛盾する要件がある場合は矛盾を明示的に指摘する",
        "不確実性が高い部分は先にスパイク（調査タスク）を設ける",
    ],
    "research_retrieval": [
        "情報源に記載されていない事実を追加しない",
        "回答の根拠となる情報源を明示する",
    ],
}

# ── Blueprint 生成プロンプト ────────────────────────

BLUEPRINT_SYSTEM = textwrap.dedent("""\
あなたはエージェント設計の専門家です。
ユーザーの自然言語仕様に基づいて、高品質なエージェント定義を生成してください。

## 成功例1（検出型 — code-reviewer）

```json
{few_shot_detection}
```

## 成功例2（生成型-主観 — doc-writer）

```json
{few_shot_subjective}
```

## 必ず含めるべき system prompt の構造

1. 「あなたは〇〇の専門家です。」で始める
2. 「## 責務」に具体的なタスクを番号付きで列挙（4-6項目）
3. 「## 出力形式」に具体的なフォーマットを定義（コードブロック例を含む）
4. 「## 制約事項」にやってはいけないことを列挙
5. 制約事項には以下の弱点対策を必ず含める:
   {weakness_instructions}

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

## ツール選択ガイド

- 読み取りのみ: ["bash", "read", "glob", "grep"]
- ファイル生成あり: 上記 + ["write", "edit"]
- Web 検索が必要: 上記 + ["web_search", "web_fetch"]

以下の JSON のみを返してください。他のテキストは不要です。
""")

BLUEPRINT_USER = textwrap.dedent("""\
以下の仕様でエージェントを生成してください:

{spec}

以下の JSON 形式で返してください:
```json
{{
  "name": "kebab-case のエージェント名",
  "description": "エージェントの役割と起動条件（50文字以上）",
  "system_prompt": "## 責務\\n...\\n## 出力形式\\n...\\n## 制約事項\\n... の全文",
  "agent_type": "{valid_types}",
  "artifact_format": "{valid_formats}",
  "tools": ["bash", "read", ...],
  "disallowed_tools": [],
  "output_format_patterns": ["正規表現パターン"],
  "rubric_criteria": [
    {{"name": "基準名", "points": ["判定ポイント1", "判定ポイント2"]}}
  ],
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
""")


def _load_few_shot_examples() -> tuple[str, str]:
    """既存エージェントの config.json を Few-Shot Example として読み込む。"""
    detection_config = AGENTS_DIR / "code-reviewer" / "config.json"
    subjective_config = AGENTS_DIR / "doc-writer" / "config.json"

    examples = []
    for path in [detection_config, subjective_config]:
        if path.exists():
            with open(path, encoding="utf-8") as f:
                config = json.load(f)
            examples.append(json.dumps(config, ensure_ascii=False, indent=2))
        else:
            examples.append("{}")

    return examples[0], examples[1]


def _build_weakness_instructions(agent_type: str | None = None) -> str:
    """タイプ別の弱点対策指示を構築する。"""
    lines = []
    for instruction in WEAKNESS_MITIGATIONS["__all__"]:
        lines.append(f"   - {instruction}")
    if agent_type and agent_type in WEAKNESS_MITIGATIONS:
        for instruction in WEAKNESS_MITIGATIONS[agent_type]:
            lines.append(f"   - {instruction}")
    return "\n".join(lines)


def generate_blueprint(client, spec: str, model: str = "claude-haiku-4-5") -> dict:
    """
    自然言語仕様から Blueprint JSON を生成する。

    Args:
        client: Anthropic client
        spec: ユーザーの自然言語仕様
        model: 使用モデル

    Returns:
        Blueprint dict（name, system_prompt, agent_type, artifact_format 等）
    """
    few_shot_detection, few_shot_subjective = _load_few_shot_examples()

    system = BLUEPRINT_SYSTEM.format(
        few_shot_detection=few_shot_detection,
        few_shot_subjective=few_shot_subjective,
        weakness_instructions=_build_weakness_instructions(),
    )

    user = BLUEPRINT_USER.format(
        spec=spec,
        valid_types=" | ".join(VALID_AGENT_TYPES),
        valid_formats=" | ".join(VALID_ARTIFACT_FORMATS),
    )

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    raw_text = response.content[0].text

    # JSON ブロックを抽出（```json ... ``` またはベアJSON）
    json_text = _extract_json(raw_text)
    blueprint = json.loads(json_text)

    # バリデーション
    _validate_blueprint(blueprint)

    # 弱点対策をタイプに応じて system_prompt に注入
    blueprint["system_prompt"] = _inject_weakness_mitigations(
        blueprint["system_prompt"],
        blueprint["agent_type"],
    )

    return blueprint


def _extract_json(text: str) -> str:
    """テキストから JSON ブロックを抽出する。"""
    # ```json ... ``` パターン
    import re

    match = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if match:
        return match.group(1)

    # ベア JSON（最初の { から最後の } まで）
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return text[start : end + 1]

    raise ValueError(f"JSON が見つかりません:\n{text[:500]}")


def _validate_blueprint(blueprint: dict) -> None:
    """Blueprint の必須フィールドを検証する。"""
    required_fields = [
        "name",
        "description",
        "system_prompt",
        "agent_type",
        "artifact_format",
        "tools",
        "rubric_criteria",
        "test_prompts",
    ]
    missing = [f for f in required_fields if f not in blueprint]
    if missing:
        raise ValueError(f"Blueprint に必須フィールドがありません: {missing}")

    if blueprint["agent_type"] not in VALID_AGENT_TYPES:
        raise ValueError(
            f"不明な agent_type: {blueprint['agent_type']}。"
            f"有効な値: {VALID_AGENT_TYPES}"
        )

    if blueprint["artifact_format"] not in VALID_ARTIFACT_FORMATS:
        raise ValueError(
            f"不明な artifact_format: {blueprint['artifact_format']}。"
            f"有効な値: {VALID_ARTIFACT_FORMATS}"
        )

    # name フォーマット: kebab-case
    import re

    if not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$", blueprint["name"]):
        raise ValueError(
            f"name は kebab-case にしてください: {blueprint['name']}"
        )


def _inject_weakness_mitigations(system_prompt: str, agent_type: str) -> str:
    """system prompt に弱点対策を注入する（まだ含まれていない場合のみ）。"""
    mitigations = list(WEAKNESS_MITIGATIONS.get("__all__", []))
    mitigations += WEAKNESS_MITIGATIONS.get(agent_type, [])

    # 既に含まれている指示はスキップ
    new_items = []
    for m in mitigations:
        # 指示の先頭15文字で存在チェック（表記ゆれ許容）
        if m[:15] not in system_prompt:
            new_items.append(f"- {m}")

    if not new_items:
        return system_prompt

    # ## 制約事項 セクションが既にあれば、そのセクション内末尾に挿入
    constraint_header = "## 制約事項"
    if constraint_header in system_prompt:
        import re as _re
        header_pos = system_prompt.index(constraint_header)
        next_header = _re.search(r"\n## ", system_prompt[header_pos + len(constraint_header):])
        if next_header:
            insert_pos = header_pos + len(constraint_header) + next_header.start()
            return system_prompt[:insert_pos].rstrip() + "\n" + "\n".join(new_items) + "\n" + system_prompt[insert_pos:]
        return system_prompt.rstrip() + "\n" + "\n".join(new_items)

    # なければセクションごと追加
    return (
        system_prompt.rstrip()
        + f"\n\n{constraint_header}\n\n"
        + "\n".join(new_items)
    )


def expand_blueprint(blueprint: dict) -> tuple[str, dict, list]:
    """
    Blueprint JSON → agent.md + config.json + test-prompts.json に展開する。

    Args:
        blueprint: generate_blueprint() の戻り値

    Returns:
        (agent_md_text, config_dict, test_prompts_list)
    """
    name = blueprint["name"]
    description = blueprint["description"]
    system_prompt = blueprint["system_prompt"]
    tools = blueprint["tools"]
    disallowed = blueprint.get("disallowed_tools", [])

    # === agent.md ===
    def _to_pascal(s: str) -> str:
        return "".join(word.capitalize() for word in s.split("_"))

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


def save_blueprint(
    blueprint: dict,
    agent_md: str,
    config: dict,
    test_prompts: list,
    base_dir: Path | None = None,
) -> Path:
    """
    生成されたファイルをディスクに書き出す。

    Args:
        blueprint: Blueprint dict
        agent_md: agent.md テキスト
        config: config.json dict
        test_prompts: test-prompts.json list
        base_dir: エージェント格納先ディレクトリ（デフォルト: agents/agents/）

    Returns:
        エージェントディレクトリのパス
    """
    target_dir = base_dir if base_dir is not None else AGENTS_DIR
    agent_dir = target_dir / blueprint["name"]
    agent_dir.mkdir(parents=True, exist_ok=True)

    # agent.md
    (agent_dir / "agent.md").write_text(agent_md, encoding="utf-8")

    # config.json
    with open(agent_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # test-prompts.json
    with open(agent_dir / "test-prompts.json", "w", encoding="utf-8") as f:
        json.dump(test_prompts, f, ensure_ascii=False, indent=2)
        f.write("\n")

    return agent_dir
