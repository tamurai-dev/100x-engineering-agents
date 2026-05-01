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

.PHONY: help validate test check-template check-all create-agent setup report clean

# ── デフォルト ────────────────────────────────────
help: ## このヘルプを表示
	@echo ""
	@echo "使用可能なコマンド:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36mmake %-18s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ── バリデーション ───────────────────────────────
validate: ## 全 subagent の frontmatter をバリデーション
	@$(PYTHON) scripts/validate_subagents.py

check-template: ## テンプレート (subagent.md.tmpl) の整合性チェック
	@$(PYTHON) scripts/validate_subagents.py --check-template

test: ## テストスイート実行（正常系 + 異常系 + 既存エージェント）
	@$(PYTHON) tests/test_validate_subagents.py

report: ## バリデーションレポート生成 (tests/reports/validation-report.json)
	@mkdir -p tests/reports
	@$(PYTHON) scripts/validate_subagents.py --report $(REPORT)
	@echo ""
	@echo "レポート生成: $(REPORT)"

# ── 統合チェック ─────────────────────────────────
check-all: validate test check-template report ## 全チェック実行（CI と同等）
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

# ── セットアップ ─────────────────────────────────
setup: ## 開発環境セットアップ（依存パッケージ + pre-commit hook）
	@bash scripts/setup-hooks.sh

# ── クリーンアップ ───────────────────────────────
clean: ## 生成ファイル削除
	@rm -rf tests/reports/ scripts/__pycache__/ tests/__pycache__/
	@echo "クリーンアップ完了"
