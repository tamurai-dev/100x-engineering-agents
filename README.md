---
# ============================================================
# Project Frontmatter — Claude Code subagent 書式に準拠
# https://docs.anthropic.com/en/docs/claude-code/sub-agents
# ============================================================

# --- Identity（プロジェクト識別） ---
name: 100x-engineering-agents
description: >
  ANTHROPIC_API_KEY ひとつで、AIエージェントの作成・テスト・評価が
  ローカル完結で行えるフレームワーク。
  技術スタック非依存。GitHub リポジトリ不要。
  コード検査から業務効率化まで、あらゆる用途のエージェントを生成できる。
owner: YoshibaTakumu
repo: tamurai-dev/100x-engineering-agents

# --- Status（プロジェクト状態） ---
status: active
tech_stack: Python 3.10+（技術スタック非依存 — 生成するエージェントは任意の言語・領域に対応）
ci_cd: GitHub Actions（make check-all 自動実行）

# --- Document Governance（文書統制） ---
document:
  type: single-source-of-truth
  read_frequency: session-start
  audience:
    - end-user                      # エージェントを作りたい人（非開発者含む）
    - ai-agent                      # Devin, Claude Code, Cursor, etc.
    - human-developer               # フレームワーク開発者
  permission:
    modify: owner-approval-required
    reason: 規約変更は全エージェント・開発者に影響するため
  integrity:
    - 曖昧な記述や願望は載せない
    - 記載内容はすべて現時点での決定事項である
    - 未決定事項は明示的に「未決定」と記載する
    - 存在しない機能を「対応済み」と書かない

# --- Agent Behavior（エージェント行動制御） ---
agent:
  entry_point: AGENTS.md
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

# --- Directory Layout ---
layout:
  agents_dir: agents/
  claude_symlink: .claude -> agents
---

# 100x Engineering Agents

**ANTHROPIC_API_KEY ひとつで、AIエージェントの作成・テスト・品質評価がローカル完結で行えるフレームワーク。**

GitHub リポジトリを持っていなくても、自分の業務効率化のためのエージェントが作れる。コードレビューからデータ集計まで、技術スタックを問わずあらゆる用途に対応。

### 特徴

- 🏭 **Agent Factory** — 自然言語1行からエージェントを全自動生成
- 🎯 **Actor-Critic Bundle** — Task Agent（実行）と QA Agent（検査）のペアで、成果物の品質を自律的に保証
- 📊 **Eval-Driven Development** — テストスコアに基づく自動品質改善ループ

---

## 0. クイックスタート（5分で最初のエージェント）

### 前提条件

- Python 3.10 以上
- [Anthropic API キー](https://console.anthropic.com/)

### セットアップ

```bash
# 1. クローン
git clone https://github.com/tamurai-dev/100x-engineering-agents.git
cd 100x-engineering-agents

# 2. 依存パッケージをインストール
pip install -e ".[dev]"

# 3. 初期セットアップ（HMAC鍵生成 + マニフェスト初期化 + pre-commit hook）
make setup

# 4. API キーをセット
export ANTHROPIC_API_KEY="sk-ant-..."
```

### エージェントを作る

#### 方法 A: 自然言語から全自動生成（Agent Factory）

GitHubリポジトリを持っていなくても、自然言語で仕様を書くだけでエージェントが作れる。

```bash
# 業務効率化エージェントの例
make create-smart-agent SPEC="毎週の営業レポートを自動集計し、前週比を含むサマリーを生成するエージェント"

# コード検査エージェントの例
make create-smart-agent SPEC="Pythonコードのパフォーマンスボトルネックを検出し改善案を提示するエージェント"

# EDD（評価駆動開発）をスキップして高速に作成
make create-smart-agent SPEC="..." SKIP_EDD=1
```

Agent Factory は以下を全自動で行う:

1. **Blueprint 生成** — 自然言語仕様から agent.md + config.json + test-prompts.json を生成
2. **Eval Suite 生成** — 品質評価用の fixture + ground-truth + rubric を生成
3. **登録 + バリデーション** — マニフェスト登録 + 整合性検証
4. **EDD ループ** — 評価 → 改善 → 再評価を自動で繰り返し品質を向上

#### 方法 B: テンプレートから手動作成

構造を細かく制御したい場合はテンプレートベースで作成し、中身を手動で編集する。

```bash
# テンプレートから作成
make create-agent NAME=my-agent

# 生成されたファイルを編集
#   agents/agents/my-agent/agent.md          ← エージェントの役割・能力を定義
#   agents/agents/my-agent/config.json       ← API実行パラメータを定義
#   agents/agents/my-agent/test-prompts.json ← テストケースを定義
```

### テスト・評価

```bash
# 設定の確認（API 不要）
make test-agent-dry NAME=my-agent

# スモークテスト（API キー必須）
make test-agent NAME=my-agent MODEL=haiku

# 品質評価（API キー必須、3回試行でスコア算出）
make eval-agent NAME=my-agent MODEL=haiku TRIALS=3

# 全エージェント一括テスト
make test-all-agents MODEL=haiku

# 全コマンドの一覧を表示
make help
```

### Actor-Critic Bundle（バンドル）

シングルエージェントでは品質のばらつきが避けられない。Actor-Critic Bundle は **Task Agent（実行者 = Actor）** と **QA Agent（批評者 = Critic）** を1つのバンドルとしてペアにし、成果物の品質を自律的に保証する仕組み。

```
Task Agent（Actor）          QA Agent（Critic）
  タスク実行 ──→ 成果物 ──→ fresh-context で品質検査
       ↑                         │
       └── フィードバック ←──────┘
           （不合格なら修正→再検査、最大3回）
```

**なぜ Actor-Critic か:**
- QA Agent は **fresh-context**（タスク実行の過程を知らない状態）で検査する。これにより「自分が作ったものだから正しいはず」という同意バイアスを構造的に排除する
- 各ラウンドの成果物を保存し、最高スコア版を最終成果物として採用する

**QA 戦略の自動選択:**

バンドルの `artifact_format` に応じて、最適な QA テンプレートが自動選択される:

| artifact_format | QA テンプレート | QA パイプライン |
|----------------|---------------|---------------|
| `presentation` | qa-presentation.md.tmpl | PPTX → PDF → PNG → Vision API |
| `html_ui` | qa-html-ui.md.tmpl | Playwright screenshot → Vision API |
| `code` | qa-code.md.tmpl | lint + test execution + 静的解析 |
| その他 | qa-generic.md.tmpl | 汎用テキスト分析 |

```bash
# バンドルの検証（API 不要）
make run-bundle-dry NAME=code-review-bundle

# バンドルのワークフロー実行（ANTHROPIC_API_KEY 必須）
make run-bundle NAME=code-review-bundle INPUT="レビュー対象コード" MODEL=haiku

# バンドルバリデーション
make validate-bundle
```

---

## 1. ビジョン

### 1.1 なぜこのプロジェクトが存在するか

AIエージェントの導入が進んでいるが、多くの現場で「手戻りが増えた」「品質が下がった」「結局人間がやり直した」という失敗が起きている。

原因は明確で、**エージェントに渡すコンテキスト（仕様・規約・判断基準）が曖昧だから**だ。エージェントは曖昧な指示を受けると、もっともらしいが間違った出力を生成する。

100x Engineering Agents は、この問題を根本から解決する。**エージェントが正しく動くために必要な「構造化されたコンテキスト」を設計・管理・運用するためのフレームワーク**を提供する。

### 1.2 目指す状態

- **誰でもエージェントが作れる** — ANTHROPIC_API_KEY と自然言語の仕様だけで、プログラミング経験がなくてもエージェントを作成・テスト・改善できる
- **技術スタック非依存** — Python、TypeScript、Go、その他あらゆる言語やフレームワークのプロジェクトに対応。コード以外の業務効率化にも対応
- **GitHub リポジトリ不要** — コードベースを持たない人でも、業務プロセスの自動化エージェントを作成できる
- **品質が計測可能** — 「動いた気がする」ではなく、Precision/Recall/F1 スコアでエージェントの品質を定量評価できる
- **Actor-Critic で品質保証** — Task Agent（実行者）と QA Agent（批評者）のペアが互いの成果物を検証し合うことで、同意バイアスなき高品質を実現
- **ローカル完結** — 外部サービス（Devin, Cursor 等）に依存せず、Mac のターミナルだけで全ワークフローが完結する

### 1.3 スコープ

**やること:**

- ANTHROPIC_API_KEY だけで動く、エージェント作成・テスト・評価の CLI ツール一式
- 自然言語からのエージェント全自動生成（Agent Factory）
- **Actor-Critic Bundle** — Task Agent + QA Agent のペアによる自律的品質保証ワークフロー
- 3層 Grader による品質評価フレームワーク（Code-Based / Model-Based / Test Execution）
- 評価駆動開発（EDD）による自動品質改善ループ
- エージェント向けコンテキスト設計のテンプレートとベストプラクティス
- 実プロジェクトへの適用事例の蓄積

**やらないこと:**

- LLMの基盤モデル開発やファインチューニング
- 特定のAIエージェント製品（Devin, Cursor等）の代替となるツール開発
- エージェントなしで成立する一般的なソフトウェア開発フレームワーク

---

## 2. 開発規約

以下の規約は、本リポジトリで作業するすべてのエージェントと人間に適用される。例外は許可しない。

### 2.1 言語

- ドキュメント（README、Issue、PR本文、コミットメッセージ）: **日本語**
- コード内のコメント: **英語**（変数名・関数名も英語）
- コード内の識別子: **英語**（snake_case or camelCase、言語の慣例に従う）

### 2.2 ブランチ運用

| ブランチ | 用途 | マージ条件 |
|---------|------|-----------|
| `main` | 安定版。常にデプロイ可能な状態を維持 | PRレビュー承認 + CI通過 |
| `feature/*` | 新機能開発 | `main` から分岐、`main` へマージ |
| `fix/*` | バグ修正 | `main` から分岐、`main` へマージ |
| `docs/*` | ドキュメント変更 | `main` から分岐、`main` へマージ |
| `refactor/*` | リファクタリング | `main` から分岐、`main` へマージ |

**禁止事項:**
- `main` への直接プッシュ
- Force push（`--force`）の使用（`--force-with-lease` は自分のfeatureブランチに限り許可）
- マージコミットの手動作成（GitHub UI の Merge ボタンを使用すること）

### 2.3 コミットメッセージ

[Conventional Commits](https://www.conventionalcommits.org/ja/) に準拠する。

```
<type>: <日本語の簡潔な説明>

[任意] 本文（変更の理由と背景を記述）
```

**type 一覧:**

| type | 用途 |
|------|------|
| `feat` | 新機能 |
| `fix` | バグ修正 |
| `docs` | ドキュメントのみの変更 |
| `refactor` | 機能変更を伴わないコード改善 |
| `test` | テストの追加・修正 |
| `chore` | ビルド・CI設定など |
| `perf` | パフォーマンス改善 |

**例:**
```
feat: エージェント実行ログの構造化出力を追加

従来の自由文ログでは、エージェントの実行結果を機械的に
解析できなかった。JSON Lines形式で出力することで、
品質メトリクスの自動計測を可能にする。
```

### 2.4 Pull Request

- タイトル: `<type>: <日本語の説明>`（コミットメッセージと同じフォーマット）
- 本文: 以下の項目を必ず含める
  - **変更の概要**: 何を変えたか
  - **変更の理由**: なぜ変えたか
  - **影響範囲**: どこに影響するか
  - **テスト結果**: 何で確認したか（該当する場合）
- 1つのPRは**1つの論理的変更**に限定する。複数の変更を混ぜない
- PRの本文は**日本語**で記述する

### 2.5 コード品質

#### 必須ルール

1. **既存コードの慣例に従う** — 新しいパターンを導入する前に、既存コードがどう書かれているか確認する
2. **未使用のコードを残さない** — コメントアウトしたコード、到達不能なコード、使われていないimportは削除する
3. **シークレットをハードコードしない** — API キー、パスワード、トークンは環境変数またはシークレット管理ツール経由で参照する
4. **エラーを握り潰さない** — 空のcatch句、意味のないログ出力だけのエラーハンドリングは禁止
5. **型を曖昧にしない** — `any`（TypeScript）、`object`（Python）など曖昧な型は使用禁止。`getattr`/`setattr` の安易な使用も禁止
6. **テストなしでロジックを追加しない** — ビジネスロジックの変更にはテストの追加・更新を伴うこと

#### コメント規約

- デフォルトはコメントなし。良い命名でコードの意図を表現する
- コメントが必要な場合: **なぜ（Why）** を書く。**何を（What）** は書かない（コードを読めばわかる）
- 差分を説明するコメントは禁止（「以前は〜だったが」「この修正で〜を対応」等）。その情報はPR本文に書く
- TODO コメントを残す場合は、必ずIssue番号を付ける: `// TODO(#123): 説明`

### 2.6 ドキュメント義務

以下の変更を行った場合、対応するドキュメント更新が必須:

| 変更内容 | 更新必須ドキュメント |
|---------|-------------------|
| 新しいディレクトリ・モジュールの追加 | README.md のプロジェクト構成 |
| 新しい規約の追加・変更 | README.md の開発規約セクション |
| 外部API・サービスの追加 | 該当ドキュメント（追加時に作成） |
| 環境変数の追加 | `.env.example` への追記 |

ドキュメントが更新されていないPRはマージしない。

### 2.7 エージェント固有のルール

AIエージェントが本リポジトリで作業する際の追加ルール:

1. **推測でコードを書かない** — 不明な仕様がある場合、コードを書く前にIssueでオーナーに確認する
2. **存在しないライブラリを使わない** — `pyproject.toml` 等の依存定義ファイルを確認し、プロジェクトが使用していないライブラリを勝手に追加しない。追加が必要な場合はPR本文でその理由を明記する
3. **自動生成ファイルを手動編集しない** — ロックファイル、マイグレーションファイル等は専用ツール経由で更新する
4. **テストを改変して通さない** — テストが失敗する場合、テストではなく実装を修正する。テスト自体に問題がある場合はIssueで報告する
5. **1回のPRで触れるファイル数を最小限にする** — 変更が広範囲に及ぶ場合は、複数のPRに分割する
6. **AGENTS.md / README.md を変更する場合は必ずオーナーの承認を得る** — 規約の変更は全体に影響するため、エージェントが独断で変更してはならない
7. **`.claude/` 配下に直接ファイルを作成しない** — `agents/` に作成すること（`.claude/` は symlink）

---

## 3. プロジェクトの現在地

| 項目 | ステータス |
|------|-----------|
| リポジトリ作成 | 完了 |
| ビジョン定義 | 完了（本README §1） |
| 開発規約策定 | 完了（本README §2） |
| エージェント指示書 | 完了（AGENTS.md） |
| agents/ ディレクトリ構成 | 完了 |
| Subagent 定義（7体） | 完了（code-reviewer, security-auditor, test-generator, doc-writer, task-planner, performance-optimizer, code-review-qa） |
| .claude/ symlink 設定 | 完了 |
| pyproject.toml（依存管理） | 完了 |
| Agent Factory（全自動生成） | 完了（`make create-smart-agent`） |
| 品質評価フレームワーク | 完了（3層 Grader + EDD ループ） |
| CI/CD パイプライン | 完了（GitHub Actions） |
| Actor-Critic Bundle | 完了（Vertical Slice — code-review-bundle） |
| Bundle バリデーション | 完了（スキーマ + 整合性チェック + pre-commit + テストスイート17件） |
| QA テンプレート + 戦略エンジン | 完了（presentation / html_ui / code / generic + 自動選択） |
| Getting Started ドキュメント | 完了（本README §0） |
| エンタープライズ要件定義 | **未着手**（コア機能安定後に着手） |
| 実プロジェクト適用事例 | **未着手** |

---

## 4. 次のステップ

1. **Bundle Factory CLI** — `make create-bundle SPEC="..."` でバンドル全自動生成
2. 実プロジェクト（NiaG-Web 等）でのエージェント適用・検証
3. eval fixture を実プロジェクトのコードに置き換え、品質スコアの信頼性を向上
4. agents/rules/ にエンタープライズガードレールを定義
5. agents/skills/ に再利用可能スキルを追加
6. 他プロジェクト向けテンプレートの整備（agents/templates/）
7. ドキュメント: ユースケース別ガイド（業務効率化、コード検査、データ処理等）

---

## ライセンス

MIT License
