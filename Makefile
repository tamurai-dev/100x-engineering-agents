# ============================================================
# 100x Engineering Agents — 開発タスクランナー
#
# エージェント・人間共通のインターフェース。
# 新規 subagent 作成、バリデーション、テストはすべてここから実行する。
# ============================================================

PYTHON     ?= python3
SHELL      := /bin/bash
AGENTS_DIR := agents/agents
REPORT     := tests/reports/validation-report.json

.PHONY: help validate validate-config test test-bundle test-qa-strategy check-template check-all create-agent create-smart-agent improve-agent setup report clean manifest-verify manifest-show manifest-init test-agent test-all-agents evidence-summary eval-agent eval-all-agents eval-agent-dry validate-bundle run-bundle run-bundle-dry create-bundle create-bundle-dry test-bundle-factory test-run-bundle test-skill-resolver

# ── デフォルト ────────────────────────────────────
help: ## このヘルプを表示
	@echo ""
	@echo "使用可能なコマンド:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36mmake %-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ── バリデーション ───────────────────────────────
validate: ## 全 subagent の frontmatter をバリデーション（Claude Code 用）
	@$(PYTHON) scripts/validate_subagents.py

validate-config: ## 全 config.json をバリデーション（Managed Agents API 用 + 整合性チェック）
	@$(PYTHON) scripts/validate-config.py

check-template: ## テンプレート (subagent.md.tmpl) の整合性チェック
	@$(PYTHON) scripts/validate_subagents.py --check-template

test: ## テストスイート実行（正常系 + 異常系 + 既存エージェント）
	@$(PYTHON) tests/test_validate_subagents.py

report: ## バリデーションレポート生成 (tests/reports/validation-report.json)
	@mkdir -p tests/reports
	@$(PYTHON) scripts/validate_subagents.py --report $(REPORT)
	@echo ""
	@echo "レポート生成: $(REPORT)"

# ── Managed Agents テスト ─────────────────────────
test-agent: ## エージェントを Managed Agents API でテスト (usage: make test-agent NAME=<name> [MODEL=haiku|sonnet|all])
ifndef NAME
	@echo "ERROR: NAME を指定してください"
	@echo "  例: make test-agent NAME=code-reviewer"
	@echo "  例: make test-agent NAME=code-reviewer MODEL=haiku"
	@echo "  例: make test-agent NAME=code-reviewer MODEL=all"
	@exit 1
endif
	@$(PYTHON) scripts/test-agent.py $(NAME) --model $(or $(MODEL),sonnet)

test-agent-dry: ## テスト予行（API を呼ばずに設定確認）(usage: make test-agent-dry NAME=<name>)
ifndef NAME
	@echo "ERROR: NAME を指定してください"
	@exit 1
endif
	@$(PYTHON) scripts/test-agent.py $(NAME) --model $(or $(MODEL),sonnet) --dry-run

test-all-agents: ## 全エージェントを Managed Agents API でテスト
	@$(PYTHON) scripts/test-agent.py --all --model $(or $(MODEL),sonnet)

# ── 品質評価（Eval） ──────────────────────────────
eval-agent: ## エージェント品質評価 (usage: make eval-agent NAME=<name> [MODEL=haiku] [TRIALS=3])
ifndef NAME
	@echo "ERROR: NAME を指定してください"
	@echo "  例: make eval-agent NAME=code-reviewer"
	@echo "  例: make eval-agent NAME=code-reviewer MODEL=haiku TRIALS=3"
	@exit 1
endif
	@$(PYTHON) scripts/eval-agent.py $(NAME) --model $(or $(MODEL),haiku) --trials $(or $(TRIALS),3)

eval-agent-dry: ## 品質評価の予行（API を呼ばずに設定確認）(usage: make eval-agent-dry NAME=<name>)
ifndef NAME
	@echo "ERROR: NAME を指定してください"
	@exit 1
endif
	@$(PYTHON) scripts/eval-agent.py $(NAME) --dry-run

eval-all-agents: ## 全エージェント品質評価
	@$(PYTHON) scripts/eval-agent.py --all --model $(or $(MODEL),haiku) --trials $(or $(TRIALS),3)

# ── マニフェスト ─────────────────────────────────
manifest-verify: ## マニフェスト全エントリの HMAC 署名検証
	@$(PYTHON) scripts/manifest.py verify

manifest-show: ## マニフェスト内容を表示
	@$(PYTHON) scripts/manifest.py show

manifest-init: ## 既存エージェントをマニフェストに一括登録（初回セットアップ用）
	@$(PYTHON) scripts/manifest.py init

# ── 証跡 ─────────────────────────────────────────
evidence-summary: ## evidence/SUMMARY.md を再生成
	@$(PYTHON) scripts/collect-evidence.py summary

# ── 統合チェック ─────────────────────────────────
check-all: validate validate-config test test-bundle test-qa-strategy test-bundle-factory test-run-bundle test-skill-resolver check-template manifest-verify validate-bundle report ## 全チェック実行（CI と同等）
	@echo ""
	@echo "========================================"
	@echo "  check-all: ALL PASSED"
	@echo "========================================"

# ── subagent 作成 ────────────────────────────────
create-agent: ## 新規 subagent 作成 (usage: make create-agent NAME=<agent-name>)
ifndef NAME
	@echo "ERROR: NAME を指定してください"
	@echo "  例: make create-agent NAME=my-new-agent"
	@exit 1
endif
	@bash scripts/create-subagent.sh $(NAME)

# ── Agent Factory（AI 自動生成） ─────────────────
create-smart-agent: ## 自然言語からエージェント自動生成 + EDD (usage: make create-smart-agent SPEC="..." [MODEL=haiku] [SKIP_EDD=1])
ifndef SPEC
	@echo "ERROR: SPEC を指定してください"
	@echo '  例: make create-smart-agent SPEC="請求書からスプレッドシートに正しい情報を転記するエージェント"'
	@echo '  例: make create-smart-agent SPEC="..." MODEL=haiku SKIP_EDD=1'
	@exit 1
endif
	@$(PYTHON) scripts/agent-factory.py --spec "$(SPEC)" --model $(or $(MODEL),haiku) $(if $(SKIP_EDD),--skip-edd,)

improve-agent: ## 既存エージェントの EDD ループ実行 (usage: make improve-agent NAME=<name> [MODEL=haiku])
ifndef NAME
	@echo "ERROR: NAME を指定してください"
	@echo "  例: make improve-agent NAME=code-reviewer"
	@exit 1
endif
	@$(PYTHON) scripts/agent-factory.py --improve $(NAME) --model $(or $(MODEL),haiku)

# ── Bundle Factory（バンドル自動生成）─────────────
create-bundle: ## 自然言語からバンドル自動生成 (usage: make create-bundle SPEC="..." [MODEL=haiku] [FORMAT=presentation])
ifndef SPEC
	@echo "ERROR: SPEC を指定してください"
	@echo '  例: make create-bundle SPEC="pptxgenjsでプレゼンスライドを生成"'
	@echo '  例: make create-bundle SPEC="..." MODEL=haiku FORMAT=presentation'
	@exit 1
endif
	@$(PYTHON) scripts/bundle-factory.py --spec "$(SPEC)" --model $(or $(MODEL),haiku) $(if $(FORMAT),--format $(FORMAT),)

create-bundle-dry: ## バンドル生成のドライラン (usage: make create-bundle-dry SPEC="..." [FORMAT=presentation])
ifndef SPEC
	@echo "ERROR: SPEC を指定してください"
	@exit 1
endif
	@$(PYTHON) scripts/bundle-factory.py --spec "$(SPEC)" --dry-run $(if $(FORMAT),--format $(FORMAT),)

# ── Bundle ────────────────────────────────────────
test-bundle: ## Bundle バリデーションテストスイート（正常系 + 異常系 + 整合性）
	@$(PYTHON) tests/test_validate_bundle.py

test-qa-strategy: ## QA 戦略エンジンテストスイート（テンプレート選択 + 完全性 + 整合性）
	@$(PYTHON) tests/test_qa_strategy.py

test-bundle-factory: ## Bundle Factory テストスイート（Blueprint 生成 + テンプレート展開 + バリデーション）
	@$(PYTHON) tests/test_bundle_factory.py

test-run-bundle: ## Bundle ワークフロー実行エンジン テストスイート（QA パース + SKILL 注入 + フィードバック蓄積）
	@$(PYTHON) tests/test_run_bundle.py

test-skill-resolver: ## Skill Resolver テストスイート（プリビルト + コミュニティ + パッケージ解決）
	@$(PYTHON) tests/test_skill_resolver.py

validate-bundle: ## 全バンドルの bundle.json をバリデーション
	@$(PYTHON) scripts/validate-bundle.py

run-bundle: ## バンドルワークフロー実行 (usage: make run-bundle NAME=<bundle-name> INPUT="..." [MODEL=haiku] [VERBOSE=1])
ifndef NAME
	@echo "ERROR: NAME を指定してください"
	@echo '  例: make run-bundle NAME=code-review-bundle INPUT="レビュー対象コード"'
	@exit 1
endif
ifndef INPUT
	@echo "ERROR: INPUT を指定してください"
	@echo '  例: make run-bundle NAME=code-review-bundle INPUT="レビュー対象コード"'
	@exit 1
endif
	@$(PYTHON) scripts/run-bundle.py $(NAME) --input "$(INPUT)" --model $(or $(MODEL),haiku) $(if $(VERBOSE),--verbose,)

run-bundle-dry: ## バンドルワークフローのドライラン (usage: make run-bundle-dry NAME=<bundle-name>)
ifndef NAME
	@echo "ERROR: NAME を指定してください"
	@exit 1
endif
	@$(PYTHON) scripts/run-bundle.py $(NAME) --dry-run

# ── セットアップ ─────────────────────────────────
setup: ## 開発環境セットアップ（依存パッケージ + pre-commit hook）
	@bash scripts/setup-hooks.sh

# ── クリーンアップ ───────────────────────────────
clean: ## 生成ファイル削除
	@rm -rf tests/reports/ scripts/__pycache__/ tests/__pycache__/
	@echo "クリーンアップ完了"
