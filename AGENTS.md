---
# ============================================================
# AGENTS.md — 全エージェント共通指示書
# Claude Code subagent 書式準拠
# ============================================================

name: 100x-engineering-agents
description: >
  AIエージェントが正しく動くために必要な「構造化されたコンテキスト」を
  設計・管理・運用するためのフレームワーク。
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
│   ├── agents/                       # Subagent 定義（Claude Code 読み取り対象）
│   │   ├── code-reviewer.md          #   コードレビュー専門
│   │   ├── security-auditor.md       #   セキュリティ監査専門
│   │   ├── test-generator.md         #   テスト生成専門
│   │   ├── doc-writer.md             #   ドキュメント生成専門
│   │   └── task-planner.md           #   タスク分解・計画専門
│   ├── schemas/                      # バリデーションスキーマ
│   │   └── subagent-frontmatter.schema.json
│   ├── templates/                    # Subagent テンプレート
│   │   └── subagent.md.tmpl          #   新規作成時のベース
│   ├── skills/                       # 再利用可能スキル定義
│   ├── commands/                     # カスタムスラッシュコマンド
│   ├── rules/                        # トピック別ルール（パスゲート対応）
│   ├── output-styles/                # 出力スタイル定義
│   ├── agent-memory/                 # エージェント永続メモリ（自動生成）
│   ├── settings.json                 # Claude Code 設定
│   └── evaluations/                  # エージェント品質評価フレームワーク
│
├── scripts/                          # 開発スクリプト
│   ├── validate_subagents.py         #   Frontmatter バリデーション
│   ├── create-subagent.sh            #   新規 Subagent 作成
│   └── setup-hooks.sh                #   pre-commit セットアップ
│
├── tests/                            # テスト
│   ├── test_validate_subagents.py    #   バリデーションテストスイート
│   ├── fixtures/                     #   テスト用フィクスチャ（正常系 + 異常系）
│   └── reports/                      #   バリデーションレポート（自動生成）
│
└── .claude -> agents                 # Symlink（Claude Code 互換）
```

### 設計原則

1. **Single Source of Truth**: エージェント定義はすべて `agents/` に格納する
2. **Symlink 同期**: `.claude/` は `agents/` への symlink。手動で `.claude/` 配下にファイルを作らない
3. **Claude Code 互換**: `agents/agents/*.md`, `agents/skills/`, `agents/rules/` 等は Claude Code が自動認識する
4. **フレームワーク資産**: `agents/templates/`, `agents/evaluations/` は本プロジェクト固有のフレームワーク資産

## 3. ファイル参照ガイド

| 知りたいこと | 参照先 |
|-------------|-------|
| プロジェクトのビジョン・目的 | `README.md` §1 |
| 開発規約（ブランチ・コミット・PR） | `README.md` §2 |
| エージェント禁止行動 | `README.md` §2.7 / 本ファイル frontmatter `disallowedActions` |
| 個別エージェントの役割・能力 | `agents/agents/*.md` |
| ルール（パスゲート等） | `agents/rules/*.md` |
| プロジェクトの現在地 | `README.md` §3 |

## 4. エージェント行動規範

### 4.1 作業開始時

1. `AGENTS.md`（本ファイル）を読む
2. `README.md` のビジョン（§1）と開発規約（§2）を確認する
3. 担当タスクに関連する `agents/agents/*.md` を確認する
4. 担当タスクに関連する `agents/rules/*.md` を確認する

### 4.2 コード変更時

1. `README.md` §2 の開発規約に従う
2. `feature/*`, `fix/*`, `docs/*`, `refactor/*` ブランチを作成する
3. Conventional Commits 形式（日本語）でコミットする
4. 1 PR = 1 論理的変更。PRタイトル・本文は日本語
5. ドキュメント義務（§2.6）を確認し、必要なドキュメントを更新する

### 4.3 検証フロー（絶対遵守）

**原則: コードで書かれた検証を通過しないものはマージしない。**

文書ルールは読み飛ばされる可能性がある。以下の検証メカニズムはコードレベルで強制されるため、バイパスできない。

#### 新規 Subagent 作成時

```bash
# 必ずこのコマンドで作成する（手動コピー禁止）
make create-agent NAME=<agent-name>
```

スクリプトが自動的に以下を実行する:
1. テンプレート (`agents/templates/subagent.md.tmpl`) からコピー
2. `name` フィールドをエージェント名に置換
3. 即時バリデーション実行

#### コード変更後の検証

```bash
# 全チェック実行（CI と同等の内容をローカルで実行）
make check-all
```

`make check-all` は以下を順番に実行する:

| ステップ | コマンド | 内容 |
|---------|---------|------|
| 1 | `make validate` | 全 subagent の frontmatter バリデーション |
| 2 | `make test` | テストスイート（正常系 + 異常系 + 既存エージェント） |
| 3 | `make check-template` | テンプレート整合性チェック |
| 4 | `make report` | バリデーションレポート (JSON) 生成 |

#### 強制メカニズム（多層防御）

```
Layer 4 [最強] ── Branch Protection (required status checks)
                   → CI 未通過 = マージ不可能
Layer 3 ────────── GitHub Actions CI
                   → push/PR 時に 3OS × 2Python で自動実行
Layer 2 ────────── pre-commit hook
                   → コミット時にバリデーション自動実行
Layer 1 [最弱] ── 本ドキュメント（AGENTS.md）
                   → エージェントへのコンテキスト提供
```

上位層が下位層のバイパスをカバーする設計。

#### バリデーションレポート

`make report` を実行すると `tests/reports/validation-report.json` が生成される。
このレポートは「検証を実際に実行した証拠」として機能する。

```json
{
  "timestamp": "2026-04-30T23:00:00+00:00",
  "python_version": "3.12.8",
  "platform": "Linux",
  "summary": { "total": 5, "passed": 5, "failed": 0 },
  "results": [...]
}
```

### 4.4 禁止事項（再掲・厳守）

- `main` への直接プッシュ
- 推測に基づくコード生成
- テストの改変による通過
- `AGENTS.md` / `README.md` の無断変更
- `.claude/` 配下への直接ファイル作成（`agents/` に作成すること）
- **`make check-all` を実行せずにPRを作成すること**
- **`agents/agents/` 配下のファイルを `make create-agent` を使わずに手動作成すること**
- **バリデーション失敗を無視してコミットすること**
