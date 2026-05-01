---
# ============================================================
# AGENTS.md — 全エージェント共通指示書
# Claude Code subagent 書式準拠
# ============================================================

name: 100x-engineering-agents
description: >
  AIエージェントが正しく動くために必要な「構造化されたコンテキスト」を
  設計・管理・運用するためのフレームワーク。
  Claude Managed Agents API での検証に対応。
  本ファイルは全エージェントがセッション開始時に必読する指示書である。
owner: YoshibaTakumu
repo: tamurai-dev/100x-engineering-agents
status: inception

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

## 2. プロジェクト構成

```
/
├── AGENTS.md                         # ← 今読んでいるファイル（全エージェント共通指示）
├── CLAUDE.md                         # Claude Code 用エントリポイント（AGENTS.md への参照）
├── README.md                         # プロジェクトビジョン・開発規約
│
├── Makefile                          # 開発タスクランナー（make check-all, make create-agent 等）
├── agents/                           # 全エージェント資産の格納場所（= .claude/ の実体）
│   ├── agents/                       # Subagent 定義
│   │   ├── code-reviewer/            #   コードレビュー専門
│   │   │   ├── agent.md              #     Claude Code 用定義
│   │   │   ├── config.json           #     Managed Agents API 用設定
│   │   │   └── test-prompts.json     #     テストケース
│   │   ├── security-auditor/         #   セキュリティ監査専門
│   │   ├── test-generator/           #   テスト生成専門
│   │   ├── doc-writer/               #   ドキュメント生成専門
│   │   └── task-planner/             #   タスク分解・計画専門
│   ├── schemas/                      # バリデーションスキーマ
│   │   ├── subagent-frontmatter.schema.json   # Claude Code 用
│   │   └── managed-agent-config.schema.json   # Managed Agents API 用
│   ├── templates/                    # テンプレート
│   │   ├── subagent.md.tmpl          #   agent.md テンプレート
│   │   ├── config.json.tmpl          #   config.json テンプレート
│   │   └── test-prompts.json.tmpl    #   テストケーステンプレート
│   ├── skills/                       # 再利用可能スキル定義
│   ├── commands/                     # カスタムスラッシュコマンド
│   ├── rules/                        # トピック別ルール（パスゲート対応）
│   ├── output-styles/                # 出力スタイル定義
│   ├── agent-memory/                 # エージェント永続メモリ（自動生成）
│   ├── settings.json                 # Claude Code 設定
│   └── evaluations/                  # エージェント品質評価フレームワーク
│
├── scripts/                          # 開発スクリプト
│   ├── validate_subagents.py         #   Frontmatter バリデーション（Claude Code 用）
│   ├── validate-config.py            #   config.json バリデーション（Managed Agents API 用）
│   ├── test-agent.py                 #   Managed Agents API テストランナー
│   ├── collect-evidence.py           #   セッション証跡収集
│   ├── create-subagent.sh            #   新規 Subagent 作成
│   ├── manifest.py                   #   マニフェスト管理（HMAC署名）
│   └── setup-hooks.sh                #   pre-commit セットアップ
│
├── evidence/                         # テスト証跡（Managed Agents セッション）
│   ├── sessions/                     #   セッションイベント保存先
│   ├── SUMMARY.md                    #   証跡サマリー（自動生成）
│   └── .gitattributes                #   linguist-generated 設定
│
├── tests/                            # テスト
│   ├── test_validate_subagents.py    #   バリデーションテストスイート
│   ├── fixtures/                     #   テスト用フィクスチャ（正常系 + 異常系）
│   └── reports/                      #   バリデーションレポート（自動生成）
│
└── .claude -> agents                 # Symlink（Claude Code 互換）
```

### 設計原則

1. **二重管理の許容**: 各エージェントは `agent.md`（Claude Code 用）と `config.json`（Managed Agents API 用）を持つ。公式仕様に合わせるための意図的な二重管理
2. **Symlink 同期**: `.claude/` は `agents/` への symlink。手動で `.claude/` 配下にファイルを作らない
3. **Claude Code 互換**: `agents/agents/*/agent.md`, `agents/skills/`, `agents/rules/` 等は Claude Code が自動認識する
4. **テスト駆動モデル選定**: haiku でタスク成功できるなら haiku を使う。テスト結果に基づく最安モデル選定

## 3. ファイル参照ガイド

| 知りたいこと | 参照先 |
|-------------|-------|
| プロジェクトのビジョン・目的 | `README.md` §1 |
| 開発規約（ブランチ・コミット・PR） | `README.md` §2 |
| エージェント禁止行動 | `README.md` §2.7 / 本ファイル frontmatter `disallowedActions` |
| 個別エージェントの役割・能力 | `agents/agents/*/agent.md` |
| Managed Agents API 設定 | `agents/agents/*/config.json` |
| ルール（パスゲート等） | `agents/rules/*.md` |
| プロジェクトの現在地 | `README.md` §3 |

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

```bash
# 必ずこのコマンドで作成する（手動コピー禁止）
make create-agent NAME=<agent-name>
```

スクリプトが自動的に以下を生成する:
1. `agents/agents/<name>/agent.md` — Claude Code 用定義
2. `agents/agents/<name>/config.json` — Managed Agents API 用設定
3. `agents/agents/<name>/test-prompts.json` — テストケース
4. `.manifest.json` へのマニフェスト登録（HMAC-SHA256 署名付き）

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
| 4 | `make check-template` | テンプレート整合性チェック |
| 5 | `make manifest-verify` | マニフェスト + HMAC 署名検証 |
| 6 | `make report` | バリデーションレポート (JSON) 生成 |

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

#### 強制メカニズム（多層防御）

```
Layer 5 [最強] ── Branch Protection (required status checks)
                   → CI 未通過 = マージ不可能
Layer 4 ────────── GitHub Actions CI
                   → push/PR 時に自動実行
Layer 3 ────────── pre-commit hook（3段構成）
                   → Hook 1: agent.md frontmatter バリデーション
                   → Hook 2: config.json バリデーション + 整合性チェック
                   → Hook 3: マニフェスト + HMAC 署名検証
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

### 4.5 禁止事項（再掲・厳守）

- `main` への直接プッシュ
- 推測に基づくコード生成
- テストの改変による通過
- `AGENTS.md` / `README.md` の無断変更
- `.claude/` 配下への直接ファイル作成（`agents/` に作成すること）
- **`make check-all` を実行せずにPRを作成すること**
- **`agents/agents/` 配下のファイルを `make create-agent` を使わずに手動作成すること**
- **バリデーション失敗を無視してコミットすること**
- **`.manifest.json` を手動で編集すること**
- **`.manifest-key` をコミットすること**
- **`evidence/sessions/` のファイルを手動で作成・編集すること**
