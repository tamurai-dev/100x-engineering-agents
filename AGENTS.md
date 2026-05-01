---
# ============================================================
# AGENTS.md — 全エージェント共通指示書
# Claude Code subagent 書式準拠
# ============================================================

name: 100x-engineering-agents
description: >
  ANTHROPIC_API_KEY ひとつで、AIエージェントの作成・テスト・評価が
  ローカル完結で行えるフレームワーク。
  技術スタック非依存。GitHub リポジトリ不要。
  本ファイルは全エージェントがセッション開始時に必読する指示書である。
owner: YoshibaTakumu
repo: tamurai-dev/100x-engineering-agents
status: active

document:
  type: single-source-of-truth
  read_frequency: session-start
  permission:
    modify: owner-approval-required
  integrity:
    - 曖昧な記述や願望は載せない
    - 記載内容はすべて現時点での決定事項である
    - 未決定事項は明示的に「未決定」と記載する

agent:
  language:
    documentation: ja
    code_comments: en
    identifiers: en
  disallowedActions:
    - main ブランチへの直接プッシュ
    - force push（--force-with-lease は自分のfeatureブランチに限り許可）
    - 推測に基づくコード生成（不明な仕様はIssueで確認）
    - 未使用ライブラリの無断追加
    - テストの改変による通過
    - 自動生成ファイルの手動編集
    - AGENTS.md / README.md の無断変更
  effort: high
---

# 100x Engineering Agents — エージェント指示書

## 1. このドキュメントの役割

本プロジェクトに関わるすべてのAIエージェント（Devin, Claude Code, Cursor等）は、セッション開始時にこのファイルを読むこと。ここに書かれた規約は例外なく遵守する。

**このプロジェクトの目的**: ANTHROPIC_API_KEY ひとつで、エージェントの作成・テスト・品質評価がローカル完結で行えるフレームワークを提供する。技術スタック非依存。GitHub リポジトリ不要。コード検査から業務効率化まで、あらゆる用途のエージェントを生成できる。

## 2. プロジェクト構成

```
/
├── AGENTS.md                         # ← 今読んでいるファイル（全エージェント共通指示）
├── CLAUDE.md                         # Claude Code 用エントリポイント（AGENTS.md への参照）
├── README.md                         # ビジョン・クイックスタート・開発規約
├── pyproject.toml                    # Python 依存管理（pip install -e ".[dev]"）
│
├── Makefile                          # 開発タスクランナー（make help で全コマンド表示）
├── agents/                           # 全エージェント資産の格納場所（= .claude/ の実体）
│   ├── agents/                       # Subagent 定義（7体）
│   │   ├── code-reviewer/            #   コードレビュー専門
│   │   │   ├── agent.md              #     Claude Code 用定義
│   │   │   ├── config.json           #     Managed Agents API 用設定
│   │   │   ├── test-prompts.json     #     スモークテストケース
│   │   │   └── evals/                #     品質評価（fixture + grader）
│   │   │       ├── suite.json         #       テストスイートメタデータ
│   │   │       ├── rubric.md          #       ルーブリック（Model-Based 採点用）
│   │   │       └── tasks/             #       タスク別 fixture
│   │   │           └── <task-name>/
│   │   │               ├── task.json      # タスク定義（プロンプト・grader設定）
│   │   │               ├── fixture/       # エージェントに渡すファイル群
│   │   │               └── ground-truth.json  # 正解データ
│   │   ├── security-auditor/         #   セキュリティ監査専門
│   │   ├── test-generator/           #   テスト生成専門
│   │   ├── doc-writer/               #   ドキュメント生成専門
│   │   ├── task-planner/             #   タスク分解・計画専門
│   │   ├── code-review-qa/           #   コードレビュー QA（Actor-Critic Bundle の Critic）
│   │   └── performance-optimizer/    #   パフォーマンス最適化専門
│   ├── bundles/                      # Actor-Critic Bundle 定義
│   │   └── code-review-bundle/       #   コードレビューバンドル（code-reviewer + code-review-qa）
│   │       └── bundle.json           #     バンドル定義（Task/QA Agent 参照、QA ループ設定）
│   ├── schemas/                      # バリデーションスキーマ
│   │   ├── subagent-frontmatter.schema.json   # Claude Code 用
│   │   ├── managed-agent-config.schema.json   # Managed Agents API 用
│   │   └── bundle.schema.json                 # Actor-Critic Bundle 用
│   ├── templates/                    # テンプレート
│   │   ├── subagent.md.tmpl          #   agent.md テンプレート
│   │   ├── config.json.tmpl          #   config.json テンプレート
│   │   ├── test-prompts.json.tmpl    #   テストケーステンプレート
│   │   ├── qa-presentation.md.tmpl   #   QA テンプレート: presentation（ビジュアル品質検査）
│   │   ├── qa-html-ui.md.tmpl        #   QA テンプレート: html_ui（UI 品質検査）
│   │   ├── qa-code.md.tmpl           #   QA テンプレート: code（コード品質検査）
│   │   ├── qa-generic.md.tmpl        #   QA テンプレート: generic（汎用品質検査）
│   │   └── qa-config.json.tmpl       #   QA Agent config.json テンプレート
│   ├── skills/                       # 再利用可能スキル定義
│   ├── commands/                     # カスタムスラッシュコマンド
│   ├── rules/                        # トピック別ルール（パスゲート対応）
│   ├── output-styles/                # 出力スタイル定義
│   ├── agent-memory/                 # エージェント永続メモリ（自動生成）
│   ├── settings.json                 # Claude Code 設定
│   └── evaluations/                  # エージェント品質評価フレームワーク
│
├── scripts/                          # CLIツール一式
│   ├── validate_subagents.py         #   Frontmatter バリデーション（Claude Code 用）
│   ├── validate-config.py            #   config.json バリデーション（Managed Agents API 用）
│   ├── test-agent.py                 #   Managed Agents API スモークテストランナー
│   ├── eval-agent.py                 #   品質評価ランナー（fixture + 3層Grader + Trial）
│   ├── graders/                      #   評価 grader モジュール
│   │   ├── code_grader.py            #     Ground Truth マッチ + Transcript 分析
│   │   ├── model_grader.py           #     Messages API ルーブリック採点
│   │   └── test_execution_grader.py  #     テスト実行結果判定
│   ├── agent-factory.py              #   Agent Factory CLI（自然言語 → エージェント全自動生成）
│   ├── agent_factory/                #   Agent Factory コアモジュール
│   │   ├── blueprint.py              #     Phase 1: Blueprint 生成
│   │   ├── eval_suite.py             #     Phase 2: Eval Suite 生成
│   │   ├── edd_loop.py               #     Phase 4: EDD ループ
│   │   └── utils.py                  #     共通ユーティリティ（JSON パース等）
│   ├── bundle-factory.py              #   Bundle Factory CLI（自然言語 → バンドル自動生成）
│   ├── bundle_factory/                #   Bundle Factory コアモジュール
│   │   ├── qa_strategy.py             #     QA 戦略エンジン（artifact_format → テンプレート自動選択）
│   │   ├── bundle_blueprint.py        #     Bundle Blueprint 生成（Task + QA Agent + bundle.json）
│   │   └── skill_resolver.py          #     Skill Resolver（プリビルト + コミュニティスキル自動選択）
│   ├── collect-evidence.py           #   セッション証跡収集
│   ├── create-subagent.sh            #   新規 Subagent 作成（テンプレートベース）
│   ├── manifest.py                   #   マニフェスト管理（HMAC署名）
│   ├── validate-bundle.py            #   Bundle バリデーション
│   ├── run-bundle.py                 #   Bundle ワークフロー実行エンジン v2
│   ├── run_bundle_helpers.py          #   run-bundle.py テスト用ヘルパー
│   └── setup-hooks.sh                #   初期セットアップ
│
├── evidence/                         # テスト証跡（Managed Agents セッション）
│   ├── sessions/                     #   スモークテスト証跡
│   ├── bundles/                      #   Bundle 実行証跡
│   ├── evals/                        #   品質評価結果
│   ├── SUMMARY.md                    #   証跡サマリー（自動生成）
│   └── .gitattributes                #   linguist-generated 設定
│
├── tests/                            # テスト
│   ├── test_validate_subagents.py    #   バリデーションテストスイート
│   ├── test_validate_bundle.py       #   Bundle バリデーションテストスイート
│   ├── test_qa_strategy.py           #   QA 戦略エンジンテストスイート
│   ├── test_bundle_factory.py        #   Bundle Factory テストスイート
│   ├── test_run_bundle.py            #   Bundle ワークフロー実行エンジンテストスイート
│   ├── test_skill_resolver.py        #   Skill Resolver テストスイート
│   ├── fixtures/                     #   テスト用フィクスチャ（正常系 + 異常系）
│   └── reports/                      #   バリデーションレポート（自動生成）
│
└── .claude -> agents                 # Symlink（Claude Code 互換）
```

### 設計原則

1. **ローカル完結**: ANTHROPIC_API_KEY と Python 3.10+ があれば、Mac のターミナルだけで全ワークフローが完結する
2. **技術スタック非依存**: 生成するエージェントは Python / TypeScript / Go / その他あらゆる言語・領域に対応。コード以外の業務効率化にも対応
3. **二重管理の許容**: 各エージェントは `agent.md`（Claude Code 用）と `config.json`（Managed Agents API 用）を持つ。公式仕様に合わせるための意図的な二重管理
4. **Symlink 同期**: `.claude/` は `agents/` への symlink。手動で `.claude/` 配下にファイルを作らない
5. **Claude Code 互換**: `agents/agents/*/agent.md`, `agents/skills/`, `agents/rules/` 等は Claude Code が自動認識する
6. **テスト駆動モデル選定**: haiku でタスク成功できるなら haiku を使う。テスト結果に基づく最安モデル選定
7. **Actor-Critic 品質保証**: Task Agent（Actor）が成果物を生成し、QA Agent（Critic）が fresh-context で品質検査する。同意バイアスを構造的に排除し、フィードバックループで品質を収束させる
8. **スキル自動選択**: Bundle 生成時に artifact_format から Anthropic プリビルトスキル（pptx/xlsx/docx/pdf）を自動マッチし、マッチしない場合はコミュニティスキル候補を推薦。必要なパッケージ（npm/pip/apt）も Environment に自動設定する

## 3. ファイル参照ガイド

| 知りたいこと | 参照先 |
|-------------|-------|
| クイックスタート（5分で最初のエージェント） | `README.md` §0 |
| プロジェクトのビジョン・目的 | `README.md` §1 |
| 開発規約（ブランチ・コミット・PR） | `README.md` §2 |
| エージェント禁止行動 | `README.md` §2.7 / 本ファイル frontmatter `disallowedActions` |
| 個別エージェントの役割・能力 | `agents/agents/*/agent.md` |
| Managed Agents API 設定 | `agents/agents/*/config.json` |
| ルール（パスゲート等） | `agents/rules/*.md` |
| プロジェクトの現在地 | `README.md` §3 |
| 全コマンド一覧 | `make help` |

## 4. エージェント行動規範

### 4.1 作業開始時

1. `AGENTS.md`（本ファイル）を読む
2. `README.md` のビジョン（§1）と開発規約（§2）を確認する
3. 担当タスクに関連する `agents/agents/*/agent.md` を確認する
4. 担当タスクに関連する `agents/rules/*.md` を確認する

### 4.2 コード変更時

1. `README.md` §2 の開発規約に従う
2. `feature/*`, `fix/*`, `docs/*`, `refactor/*` ブランチを作成する
3. Conventional Commits 形式（日本語）でコミットする
4. 1 PR = 1 論理的変更。PRタイトル・本文は日本語
5. ドキュメント義務（§2.6）を確認し、必要なドキュメントを更新する

### 4.3 検証フロー（絶対遵守）

**原則: コードで書かれた検証を通過しないものはマージしない。**

#### 新規 Subagent 作成時

2つの方法がある:

```bash
# 方法 A: 自然言語から全自動生成（推奨）
make create-smart-agent SPEC="エージェントの仕様を自然言語で記述"

# 方法 B: テンプレートから手動作成
make create-agent NAME=<agent-name>
```

方法 A（Agent Factory）は以下を全自動で行う:
1. `agents/agents/<name>/agent.md` — Claude Code 用定義
2. `agents/agents/<name>/config.json` — Managed Agents API 用設定
3. `agents/agents/<name>/test-prompts.json` — テストケース
4. `agents/agents/<name>/evals/` — 品質評価スイート（fixture + ground-truth + rubric）
5. `.manifest.json` へのマニフェスト登録（HMAC-SHA256 署名付き）
6. バリデーション + 品質評価 + 自動改善（EDD ループ）

方法 B は 1〜3 のテンプレートのみ生成。4 以降は手動で作成・編集する。

#### コード変更後の検証

```bash
# 全チェック実行（CI と同等の内容をローカルで実行）
make check-all
```

`make check-all` は以下を順番に実行する:

| ステップ | コマンド | 内容 |
|---------|---------|------|
| 1 | `make validate` | 全 agent.md の frontmatter バリデーション（Claude Code 用） |
| 2 | `make validate-config` | 全 config.json バリデーション + agent.md との整合性チェック |
| 3 | `make test` | テストスイート（正常系 + 異常系 + 既存エージェント） |
| 4 | `make test-bundle` | Bundle バリデーションテストスイート（正常系 + 異常系 + 整合性） |
| 5 | `make test-qa-strategy` | QA 戦略エンジンテストスイート（テンプレート選択 + 完全性 + 整合性） |
| 6 | `make test-bundle-factory` | Bundle Factory テストスイート（Blueprint 生成 + テンプレート展開） |
| 7 | `make test-run-bundle` | Bundle ワークフロー実行エンジンテストスイート（QA パース + SKILL 注入 + フィードバック蓄積） |
| 8 | `make test-skill-resolver` | Skill Resolver テストスイート（プリビルト + コミュニティ + パッケージ解決） |
| 9 | `make check-template` | テンプレート整合性チェック |
| 10 | `make manifest-verify` | マニフェスト + HMAC 署名検証 |
| 11 | `make validate-bundle` | Actor-Critic Bundle バリデーション |
| 12 | `make report` | バリデーションレポート (JSON) 生成 |

#### Managed Agents API テスト

```bash
# 個別エージェントをテスト（ANTHROPIC_API_KEY 必須）
make test-agent NAME=code-reviewer MODEL=haiku

# テスト駆動モデル選定（haiku → sonnet の2段テスト）
make test-agent NAME=code-reviewer MODEL=all

# 全エージェントをテスト
make test-all-agents MODEL=all

# ドライラン（API を呼ばずに設定確認）
make test-agent-dry NAME=code-reviewer
```

テスト結果は `evidence/sessions/` に自動保存される。`agent.md` の `model` フィールドはテスト結果に基づいて最安モデルを選定する。

#### 品質評価（Eval-Driven Development）

スモークテスト（`make test-agent`）はキーワードマッチによる動作確認。品質評価（`make eval-agent`）は多角的な品質スコアリング。

```bash
# 個別エージェントの品質評価（ANTHROPIC_API_KEY 必須）
make eval-agent NAME=code-reviewer MODEL=haiku TRIALS=3

# 全エージェントの品質評価
make eval-all-agents MODEL=haiku TRIALS=3

# ドライラン（設定確認のみ）
make eval-agent-dry NAME=code-reviewer
```

**評価の構造:**

| 評価軸 | 重み | 内容 |
|--------|------|------|
| Outcome | 50% | 正解データとの照合（Precision/Recall/F1）、テスト実行結果 |
| Efficiency | 20% | ターン数、ツール呼び出し数、トークン使用量 |
| Output Quality | 30% | フォーマット準拠、ルーブリック採点（Model-Based） |

**Grader の3層構造:**

| 種類 | 用途 | コスト |
|------|------|--------|
| Code-Based | Ground Truth マッチ、Transcript 分析、フォーマット検証 | 無料 |
| Model-Based | ルーブリック採点（Messages API 1回呼び出し） | 低 |
| Test Execution | テスト生成エージェント用（pytest 実行結果） | 無料 |

**信頼性指標:**

| 指標 | 意味 |
|------|------|
| pass@k | k回中1回でも成功 → エージェントの「能力」 |
| pass^k | k回全て成功 → エージェントの「信頼性」 |

評価結果は `evidence/evals/` に自動保存される。

#### 強制メカニズム（多層防御）

```
Layer 5 [最強] ── Branch Protection (required status checks)
                   → CI 未通過 = マージ不可能
Layer 4 ────────── GitHub Actions CI
                   → push/PR 時に自動実行
Layer 3 ────────── pre-commit hook（4段構成）
                   → Hook 1: agent.md frontmatter バリデーション
                   → Hook 2: config.json バリデーション + 整合性チェック
                   → Hook 3: マニフェスト + HMAC 署名検証
                   → Hook 4: Actor-Critic Bundle バリデーション
Layer 2 ────────── マニフェスト登録制 + HMAC-SHA256 署名
                   → create-subagent.sh 以外からの作成を検出
Layer 1 [最弱] ── 本ドキュメント（AGENTS.md）
                   → エージェントへのコンテキスト提供
```

上位層が下位層のバイパスをカバーする設計。

### 4.4 Managed Agents テスト証跡

テスト結果は `evidence/sessions/` に JSON 形式で自動保存される。
Anthropic のインフラ側で全セッションイベントが自動記録されるため、自己申告ではなく第三者証跡として機能する。

#### 証跡の管理コマンド

| コマンド | 用途 |
|---------|------|
| `make evidence-summary` | `evidence/SUMMARY.md` を再生成 |

#### テスト駆動モデル選定

`model` フィールドの値はテスト結果に基づくデータ駆動。手動で「sonnet にしておけば安全」ではなく「haiku で動くことを証明済み」の根拠を持つ。

1. haiku でテスト実行 → 成功すれば `model: haiku`
2. haiku で失敗 → sonnet でテスト → 成功すれば `model: sonnet`
3. 両方失敗 → プロンプトまたはタスク定義の改善が必要

### 4.5 Agent Factory — 自然言語からエージェント全自動生成

Agent Factory は自然言語の仕様から高品質なエージェントを完全自動生成する4フェーズパイプライン。GitHub リポジトリを持っていなくても、自然言語で仕様を書くだけでエージェントが作れる。

#### ユースケース例

```bash
# 業務効率化
make create-smart-agent SPEC="毎週の営業レポートを自動集計し、前週比を含むサマリーを生成するエージェント"

# コード検査
make create-smart-agent SPEC="Pythonコードのパフォーマンスボトルネックを検出し改善案を提示するエージェント"

# データ処理
make create-smart-agent SPEC="CSVファイルのデータクレンジングと統計サマリー生成を行うエージェント"

# ドキュメント生成
make create-smart-agent SPEC="技術仕様書から運用マニュアルを自動生成するエージェント"
```

#### 4フェーズパイプライン

```
Phase 1: Blueprint 生成
  自然言語仕様 → Claude Messages API → agent.md + config.json + test-prompts.json
  - 8タイプ自動分類: detection | generation_verifiable | generation_subjective | repair_transform
                      planning | research_retrieval | classification | extraction
  - 9成果物フォーマット自動判定: text | code | structured_data | document | presentation
                                  html_ui | media_image | media_video | environment_state
  - 弱点対策を system prompt に自動注入（Layer 1）

Phase 2: Eval Suite 生成
  Blueprint → Claude Messages API → fixture/ + ground-truth.json + task.json + rubric.md
  - タイプ別 Grader 自動選択（3層: Code-Based / Model-Based / Test Execution）
  - 弱点テスト Fixture 自動追加（Layer 2）
  - eval-agent.py 完全互換の task.json 生成

Phase 3: 登録 + バリデーション
  マニフェスト登録 + validate_subagents.py + validate-config.py + eval --dry-run

Phase 4: EDD ループ（評価駆動開発）
  eval 実行（trials=1）→ スコア分析 → 改善対象自動特定 → system prompt 改善 → 再 eval
  - 停止条件: overall >= 0.65 or 3回完了 or 収束（Δ < 0.02）
  - 弱点テスト特化改善（Layer 3）
  - 最終 eval は trials=3 で信頼性確認
```

#### 3層弱点克服

| 層 | タイミング | 内容 |
|----|-----------|------|
| Layer 1 | Phase 1（Blueprint 生成） | system prompt に弱点対策指示を自動注入 |
| Layer 2 | Phase 2（Eval Suite 生成） | 弱点テスト Fixture を自動追加 |
| Layer 3 | Phase 4（EDD ループ） | 弱点テストで低スコアなら特化改善を実行 |

#### コマンド一覧

```bash
# 全自動生成（Phase 1-4）
make create-smart-agent SPEC="請求書からスプレッドシートに正しい情報を転記するエージェント"

# EDD スキップ（Phase 1-3 のみ）
make create-smart-agent SPEC="..." SKIP_EDD=1

# 既存エージェントの改善（Phase 4 のみ）
make improve-agent NAME=code-reviewer

# ドライラン（API 呼び出しなし）
python scripts/agent-factory.py --spec "..." --dry-run
```

### 4.6 Bundle Factory — 自然言語からバンドル自動生成

Bundle Factory は自然言語の仕様から Task Agent + QA Agent のバンドルを完全自動生成する。Agent Factory がシングルエージェントを生成するのに対し、Bundle Factory は Actor-Critic ペアをセットで生成する。

#### ユースケース例

```bash
# スライド生成バンドル（Task: pptxgenjs スクリプト生成 + QA: ビジュアル品質検査）
make create-bundle SPEC="pptxgenjsでプレゼンスライドを生成"

# HTML モックアップ（Task: HTML 生成 + QA: Playwright screenshot 検査）
make create-bundle SPEC="ランディングページのHTMLモックアップ作成" FORMAT=html_ui

# コード生成（Task: コード生成 + QA: lint + テスト実行検査）
make create-bundle SPEC="Pythonでデータ分析スクリプトを生成" MODEL=sonnet
```

#### 5フェーズパイプライン

```
Phase 1: Bundle Blueprint 生成
  自然言語仕様 → Claude Messages API → Task Agent 設計 + QA Agent 設計
  - agent_type（8タイプ）+ artifact_format（9フォーマット）を自動判定
  - Task Agent の system prompt + ツール選択を自動生成

Phase 2: QA Agent テンプレート展開
  artifact_format → qa_strategy.py → QA テンプレート自動選択
  - presentation → qa-presentation.md.tmpl（ビジュアル品質検査）
  - html_ui → qa-html-ui.md.tmpl（UI 品質検査）
  - code → qa-code.md.tmpl（コード品質検査）
  - その他 → qa-generic.md.tmpl（汎用品質検査）

Phase 3: SKILL.md 生成
  Claude Messages API → タスク固有の手順書（前提条件・実行手順・品質基準）

Phase 4: bundle.json + workflow.md 生成
  ローカル生成 → バンドル定義 + ワークフロー手順書

Phase 5: 登録 + バリデーション
  マニフェスト登録（Task + QA 両方）+ frontmatter + config + bundle 検証
```

#### コマンド一覧

```bash
# バンドル全自動生成
make create-bundle SPEC="pptxgenjsでスライド生成"

# artifact_format を明示指定（LLM 推論をスキップ）
make create-bundle SPEC="..." FORMAT=presentation

# ドライラン（API 呼び出しなし）
make create-bundle-dry SPEC="..." FORMAT=presentation
```

### 4.7 禁止事項（再掲・厳守）

- `main` への直接プッシュ
- 推測に基づくコード生成
- テストの改変による通過
- `AGENTS.md` / `README.md` の無断変更
- `.claude/` 配下への直接ファイル作成（`agents/` に作成すること）
- **`make check-all` を実行せずにPRを作成すること**
- **`agents/agents/` 配下のファイルを `make create-agent` または `make create-smart-agent` を使わずに手動作成すること**
- **バリデーション失敗を無視してコミットすること**
- **`.manifest.json` を手動で編集すること**
- **`.manifest-key` をコミットすること**
- **`evidence/sessions/` のファイルを手動で作成・編集すること**
