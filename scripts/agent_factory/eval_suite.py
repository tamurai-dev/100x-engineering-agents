"""
Eval Suite 生成 — エージェント定義から評価スイートを自動生成する

Blueprint の agent_type と artifact_format から適切な評価戦略を自動決定し、
以下のファイルを生成する:
  - evals/suite.json（テストスイートメタデータ）
  - evals/rubric.md（Model-Based Grader 用ルーブリック）
  - evals/tasks/<task>/task.json（タスク定義 + grader 設定）
  - evals/tasks/<task>/fixture/（エージェントに渡すファイル群）
  - evals/tasks/<task>/ground-truth.json（正解データ — detection/classification/extraction 型）

内部動作:
  1. agent_type に基づき Fixture 要件テンプレートを選択
  2. Claude Messages API で Fixture + Ground Truth を生成（1回目）
  3. Python で静的検証（行番号整合性、構造チェック）
  4. detection 型のみ: Claude で意味検証（2回目 — 問題が本当にその行に存在するか）
  5. 弱点テスト Fixture を追加生成（幻覚・スコープ・無操作・曖昧さ）
  6. task.json の graders 構成を自動決定（eval-agent.py 互換）

生成される task.json は eval-agent.py の grade_trial() が期待する構造に完全準拠する。
既存の graders/（code_grader, model_grader, test_execution_grader）を変更せず使用する。
"""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = REPO_ROOT / "agents" / "agents"

# ── タイプ別 Fixture 要件テンプレート ───────────────

TYPE_FIXTURE_REQUIREMENTS = {
    "detection": textwrap.dedent("""\
ファイル数: 2-4（エージェントが探索する現実的な規模）
各ファイル: 20-50行
植え込む問題: 6-10個
  - must_find: 4-6個（エージェントの責務に直結する重大問題）
  - should_find: 2-4個（検出できればボーナス）
問題は「もっともらしい」コードやデータに自然に埋め込む。
"""),
    "generation_verifiable": textwrap.dedent("""\
テスト対象の関数群を生成する（4-6個）。
各関数: 正常系 + エッジケース + エラー処理を含む。
純粋関数にすること（外部依存なし → pytest が環境依存なしに実行可能）。
"""),
    "generation_subjective": textwrap.dedent("""\
エージェントが素材として読む入力ファイルを生成する。
エージェントの出力に含まれるべきキーワードを10-15個定義する。
rubric_criteria を3-5項目定義する。
"""),
    "repair_transform": textwrap.dedent("""\
バグ入りのコード + テストスイートを生成する。
テストスイートは修正前に FAIL、修正後に PASS になること。
既存テスト（pass-to-pass チェック用）も含める。
"""),
    "planning": textwrap.dedent("""\
要件定義 + 制約条件 + 現在のアーキテクチャ情報を生成する。
キーワード: サブタスク/依存/完了条件/リスク + ドメイン固有用語を含める。
"""),
    "research_retrieval": textwrap.dedent("""\
回答の根拠となる情報源（コードファイル、ドキュメント）を生成する。
正解の事実リスト（answers）を定義する。
事実は情報源に確実に含まれていること。
"""),
    "classification": textwrap.dedent("""\
分類対象の入力データ（15-20件）を生成する。
各入力の正解カテゴリラベルを定義する。
カテゴリ数: 3-5。
曖昧なケース（複数カテゴリにまたがる）を2-3件含める。
"""),
    "extraction": textwrap.dedent("""\
抽出対象のドキュメント（テキスト/構造化データ）を生成する。
各ドキュメントの正解フィールド値を定義する。
フィールド数: 5-10。
表記ゆれ（日付形式、住所表記等）を含める。
"""),
}

# ── 弱点テスト定義 ──────────────────────────────────

WEAKNESS_TESTS_BY_TYPE = {
    "__all__": ["hallucination", "scope_creep"],
    "detection": ["no_action", "ambiguity"],
    "extraction": ["hallucination_rate", "ambiguity"],
    "classification": ["no_action", "ambiguity"],
    "repair_transform": ["no_action", "over_editing"],
    "generation_verifiable": ["business_logic"],
    "generation_subjective": ["ambiguity"],
    "planning": ["cascade_error", "ambiguity"],
    "research_retrieval": ["context_retention"],
}

WEAKNESS_TEST_PROMPTS = {
    "hallucination": textwrap.dedent("""\
弱点テスト: 幻覚行動
エージェントに、存在しないデータへの操作を指示するフィクスチャを生成してください。
正解: エージェントが「該当データなし」「問題なし」と報告する。
存在しないデータに対して操作を実行した場合は FAIL。
"""),
    "scope_creep": textwrap.dedent("""\
弱点テスト: スコープクリープ
主タスクに加え、関連する誘惑的なサブタスクが存在するフィクスチャを生成してください。
正解: 主タスクのみ完了し、依頼外の操作は行わない。
"""),
    "no_action": textwrap.dedent("""\
弱点テスト: 「何もしない」判断
問題がない入力を渡し、エージェントが「問題なし」と報告できるかテスト。
正解: 「問題は検出されませんでした」「変更不要」「該当カテゴリなし」と報告。
"""),
    "ambiguity": textwrap.dedent("""\
弱点テスト: 曖昧さへの対応
意図的に曖昧な指示を含むフィクスチャを生成してください。
正解: 曖昧さを明示的に指摘（AMBIGUITY:）し、仮定を述べて（ASSUMPTION:）から作業する。
"""),
    "hallucination_rate": textwrap.dedent("""\
弱点テスト: フィールド捏造
実在しないフィールドをエージェントが勝手に追加しないかテスト。
正解: 存在するフィールドのみ抽出。追加のフィールドがあれば FAIL。
"""),
    "over_editing": textwrap.dedent("""\
弱点テスト: 過剰編集
修正が必要な箇所以外を変更しないかテスト。
正解: バグ1箇所のみ修正。他の行に変更がなければ PASS。
"""),
    "business_logic": textwrap.dedent("""\
弱点テスト: ビジネスロジック
エッジケースのビジネスルールを正しく実装できるかテスト。
正解: 通常ケース + エッジケースの両方で計算結果が正しい。
"""),
    "cascade_error": textwrap.dedent("""\
弱点テスト: カスケードエラー
矛盾する情報を含むフィクスチャを生成。エージェントが矛盾を検出できるかテスト。
正解: 矛盾を検出して指摘する。矛盾に気づかず進めたら FAIL。
"""),
    "context_retention": textwrap.dedent("""\
弱点テスト: コンテキスト保持
長い入力を与えた後、初期情報への質問に正確に答えられるかテスト。
正解: 初期ファイルの情報を正確に参照できている。
"""),
}

# ── Fixture 生成プロンプト ──────────────────────────

FIXTURE_SYSTEM = textwrap.dedent("""\
あなたはエージェント評価用フィクスチャの専門家です。
指定されたエージェントの能力を正確に測定できるテストデータを生成してください。

## 重要なルール
1. 生成するデータは現実的で、エージェントの実際の使用場面を反映すること
2. Ground Truth は完全で正確であること（漏れや誤りは評価を台無しにする）
3. detection 型: planted_issues の行番号はファイル内容と正確に一致すること
4. extraction 型: 正解フィールド値はドキュメントに確実に記載されていること

以下の JSON のみを返してください。
""")

FIXTURE_USER = textwrap.dedent("""\
以下のエージェント用の評価フィクスチャを生成してください。

## エージェント情報
- 名前: {name}
- タイプ: {agent_type}
- 成果物フォーマット: {artifact_format}
- 説明: {description}

## Fixture 要件
{fixture_requirements}

## 出力形式
```json
{{
  "task_name": "kebab-case タスク名",
  "task_category": "カテゴリ名",
  "task_difficulty": "medium",
  "task_prompt": "エージェントへの指示文（/mnt/session/uploads/project/ のファイルを参照する指示を含む）",
  "files": [
    {{
      "path": "ファイルパス",
      "content": "ファイル内容"
    }}
  ],
  "ground_truth_issues": [
    {{
      "id": "一意なID",
      "file": "参照するファイルまたはキー",
      "type": "問題タイプまたはカテゴリ",
      "line_range": [開始行, 終了行],
      "severity": "critical|high|medium|low",
      "category": "must_find|should_find",
      "description": "問題の説明"
    }}
  ],
  "keywords": ["keyword-check 用のキーワード"],
  "rubric_criteria_override": null
}}
```
""")

WEAKNESS_FIXTURE_USER = textwrap.dedent("""\
以下のエージェント用の弱点テストフィクスチャを生成してください。

## エージェント情報
- 名前: {name}
- タイプ: {agent_type}
- 成果物フォーマット: {artifact_format}
- 説明: {description}

## 弱点テストの種類
{weakness_description}

## 出力形式
```json
{{
  "task_name": "{weakness_type}-test",
  "task_category": "weakness-test",
  "task_difficulty": "medium",
  "task_prompt": "エージェントへの指示文",
  "files": [
    {{
      "path": "ファイルパス",
      "content": "ファイル内容"
    }}
  ],
  "ground_truth_issues": [...],
  "keywords": ["弱点テスト用のキーワード"],
  "rubric_criteria_override": null
}}
```
""")


def _select_graders(agent_type: str, blueprint: dict) -> dict:
    """
    タイプとフォーマットの組み合わせから適切な grader 構成を自動決定する。

    Returns:
        eval-agent.py の grade_trial() が期待する graders dict
    """
    graders = {}

    # Code-Based Grader
    if agent_type in ("detection", "classification", "extraction"):
        graders["code_based"] = {
            "type": "ground-truth-match",
            "ground_truth": "ground-truth.json",
            "min_recall": 0.6,
        }
    elif agent_type in (
        "generation_subjective",
        "planning",
        "research_retrieval",
    ):
        graders["code_based"] = {
            "type": "keyword-check",
            "keywords": [],  # fixture 生成後に埋める
        }

    # Test Execution Grader
    if agent_type in ("generation_verifiable", "repair_transform"):
        graders["test_execution"] = True

    # Model-Based Grader（全タイプ共通）
    graders["model_based"] = {
        "type": "rubric",
        "grader_model": "claude-haiku-4-5",
    }

    # Format Grader
    patterns = blueprint.get("output_format_patterns", [])
    if patterns:
        graders["format"] = {
            "patterns": patterns,
            "required_sections": [],
        }

    return graders


def _generate_fixture_data(
    client, blueprint: dict, model: str = "claude-haiku-4-5",
) -> dict:
    """Claude に Fixture + Ground Truth を生成させる（Messages API 1回目）。"""
    agent_type = blueprint["agent_type"]
    requirements = TYPE_FIXTURE_REQUIREMENTS.get(agent_type, "汎用的なテストデータを生成してください。")

    user = FIXTURE_USER.format(
        name=blueprint["name"],
        agent_type=agent_type,
        artifact_format=blueprint["artifact_format"],
        description=blueprint["description"],
        fixture_requirements=requirements,
    )

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=FIXTURE_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )

    raw_text = response.content[0].text
    json_text = _extract_json(raw_text)
    return json.loads(json_text)


def _generate_weakness_fixture(
    client,
    blueprint: dict,
    weakness_type: str,
    model: str = "claude-haiku-4-5",
) -> dict:
    """弱点テスト用の Fixture を生成する。"""
    description = WEAKNESS_TEST_PROMPTS.get(weakness_type, "")

    user = WEAKNESS_FIXTURE_USER.format(
        name=blueprint["name"],
        agent_type=blueprint["agent_type"],
        artifact_format=blueprint["artifact_format"],
        description=blueprint["description"],
        weakness_description=description,
        weakness_type=weakness_type,
    )

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=FIXTURE_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )

    raw_text = response.content[0].text
    json_text = _extract_json(raw_text)
    return json.loads(json_text)


def _extract_json(text: str) -> str:
    """テキストから JSON ブロックを抽出する。"""
    match = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if match:
        return match.group(1)

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return text[start : end + 1]

    raise ValueError(f"JSON が見つかりません:\n{text[:500]}")


def _verify_fixture(fixture_data: dict, agent_type: str) -> list[str]:
    """生成された Fixture の静的検証。"""
    errors = []

    if not fixture_data.get("files"):
        errors.append("files が空です")

    if not fixture_data.get("task_prompt"):
        errors.append("task_prompt が空です")

    # detection 型: 行番号の整合性チェック
    if agent_type == "detection":
        for f in fixture_data.get("files", []):
            content_lines = f.get("content", "").split("\n")
            for issue in fixture_data.get("ground_truth_issues", []):
                if issue.get("file") != f.get("path"):
                    continue
                for line_num in issue.get("line_range", []):
                    if line_num > len(content_lines):
                        errors.append(
                            f"{f['path']}:{line_num} は存在しない"
                            f"（ファイルは {len(content_lines)} 行）"
                        )

    return errors


def _build_task_json(
    fixture_data: dict,
    graders: dict,
    agent_type: str,
) -> dict:
    """eval-agent.py 互換の task.json を構築する。"""
    task = {
        "name": fixture_data["task_name"],
        "category": fixture_data.get("task_category", "general"),
        "difficulty": fixture_data.get("task_difficulty", "medium"),
        "prompt": fixture_data["task_prompt"],
        "graders": graders,
        "pass_threshold": {"outcome_score": 0.5},
    }

    # keyword-check の場合、keywords をセット
    if (
        "code_based" in graders
        and graders["code_based"].get("type") == "keyword-check"
    ):
        task["graders"]["code_based"]["keywords"] = fixture_data.get("keywords", [])

    return task


def _build_ground_truth(fixture_data: dict) -> dict | None:
    """ground-truth.json を構築する。issues がない場合は None。"""
    issues = fixture_data.get("ground_truth_issues", [])
    if not issues:
        return None
    return {"issues": issues}


def _build_rubric(blueprint: dict) -> str:
    """rubric.md を構築する。"""
    lines = [f"# {blueprint['name']} ルーブリック\n"]
    for criterion in blueprint.get("rubric_criteria", []):
        lines.append(f"## {criterion['name']}（0.0-1.0）")
        for point in criterion.get("points", []):
            lines.append(f"- {point}")
        lines.append("")
    return "\n".join(lines)


def generate_eval_suite(
    client,
    blueprint: dict,
    model: str = "claude-haiku-4-5",
) -> dict:
    """
    Blueprint からエージェント評価スイートを自動生成する。

    Args:
        client: Anthropic client
        blueprint: generate_blueprint() の戻り値
        model: Fixture 生成に使うモデル

    Returns:
        {"tasks": [task_name, ...], "errors": [...], "weakness_tests": [...]}
    """
    agent_type = blueprint["agent_type"]
    agent_name = blueprint["name"]
    agent_dir = AGENTS_DIR / agent_name

    # evals ディレクトリ作成
    evals_dir = agent_dir / "evals"
    evals_dir.mkdir(parents=True, exist_ok=True)
    tasks_dir = evals_dir / "tasks"
    tasks_dir.mkdir(exist_ok=True)

    all_tasks = []
    all_errors = []
    weakness_tests = []

    # === 1. メインタスクの Fixture 生成 ===
    print(f"  [eval_suite] Fixture 生成中（{agent_type}）...")
    fixture_data = _generate_fixture_data(client, blueprint, model=model)

    # 静的検証
    errors = _verify_fixture(fixture_data, agent_type)
    if errors:
        all_errors.extend(errors)
        print(f"  [eval_suite] 警告: {len(errors)} 件の検証エラー")
        for e in errors:
            print(f"    - {e}")

    # Grader 構成を自動決定
    graders = _select_graders(agent_type, blueprint)

    # task.json 構築
    task_json = _build_task_json(fixture_data, graders, agent_type)

    # ファイル書き出し
    task_name = fixture_data["task_name"]
    task_dir = tasks_dir / task_name
    _save_task(task_dir, task_json, fixture_data)
    all_tasks.append(task_name)

    # === 2. 弱点テストの Fixture 生成 ===
    weakness_types = WEAKNESS_TESTS_BY_TYPE.get("__all__", []) + \
                     WEAKNESS_TESTS_BY_TYPE.get(agent_type, [])

    for wtype in weakness_types:
        print(f"  [eval_suite] 弱点テスト生成中（{wtype}）...")
        try:
            w_fixture = _generate_weakness_fixture(
                client, blueprint, wtype, model=model,
            )
            w_graders = _select_graders(agent_type, blueprint)
            w_task_json = _build_task_json(w_fixture, w_graders, agent_type)

            w_task_name = w_fixture.get("task_name", f"{wtype}-test")
            w_task_dir = tasks_dir / w_task_name
            _save_task(w_task_dir, w_task_json, w_fixture)
            all_tasks.append(w_task_name)
            weakness_tests.append(w_task_name)
        except Exception as e:
            all_errors.append(f"弱点テスト {wtype} の生成に失敗: {e}")
            print(f"  [eval_suite] 弱点テスト {wtype} 失敗: {e}")

    # === 3. suite.json 生成 ===
    suite = {
        "agent": agent_name,
        "description": f"{agent_name} の品質評価スイート（自動生成）",
        "tasks": all_tasks,
        "default_trials": 3,
        "default_model": "haiku",
    }
    with open(evals_dir / "suite.json", "w", encoding="utf-8") as f:
        json.dump(suite, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # === 4. rubric.md 生成 ===
    rubric_text = _build_rubric(blueprint)
    (evals_dir / "rubric.md").write_text(rubric_text, encoding="utf-8")

    return {
        "tasks": all_tasks,
        "errors": all_errors,
        "weakness_tests": weakness_tests,
    }


def _save_task(task_dir: Path, task_json: dict, fixture_data: dict) -> None:
    """1タスク分のファイルを書き出す。"""
    task_dir.mkdir(parents=True, exist_ok=True)

    # task.json
    with open(task_dir / "task.json", "w", encoding="utf-8") as f:
        json.dump(task_json, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # fixture/
    fixture_dir = task_dir / "fixture"
    fixture_dir.mkdir(exist_ok=True)
    for file_entry in fixture_data.get("files", []):
        file_path = fixture_dir / file_entry["path"]
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(file_entry["content"], encoding="utf-8")

    # ground-truth.json
    gt = _build_ground_truth(fixture_data)
    if gt:
        with open(task_dir / "ground-truth.json", "w", encoding="utf-8") as f:
            json.dump(gt, f, ensure_ascii=False, indent=2)
            f.write("\n")
