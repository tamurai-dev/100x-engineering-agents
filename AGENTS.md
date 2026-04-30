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
├── agents/                           # 全エージェント資産の格納場所（= .claude/ の実体）
│   ├── agents/                       # Subagent 定義（Claude Code 読み取り対象）
│   │   ├── code-reviewer.md          #   コードレビュー専門
│   │   ├── security-auditor.md       #   セキュリティ監査専門
│   │   ├── test-generator.md         #   テスト生成専門
│   │   ├── doc-writer.md             #   ドキュメント生成専門
│   │   └── task-planner.md           #   タスク分解・計画専門
│   ├── skills/                       # 再利用可能スキル定義
│   ├── commands/                     # カスタムスラッシュコマンド
│   ├── rules/                        # トピック別ルール（パスゲート対応）
│   ├── output-styles/                # 出力スタイル定義
│   ├── agent-memory/                 # エージェント永続メモリ（自動生成）
│   ├── settings.json                 # Claude Code 設定
│   ├── templates/                    # 他プロジェクト向けエージェントテンプレート
│   └── evaluations/                  # エージェント品質評価フレームワーク
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

### 4.3 禁止事項（再掲・厳守）

- `main` への直接プッシュ
- 推測に基づくコード生成
- テストの改変による通過
- `AGENTS.md` / `README.md` の無断変更
- `.claude/` 配下への直接ファイル作成（`agents/` に作成すること）
