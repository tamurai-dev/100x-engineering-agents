"""
Agent Factory コアモジュール

agent-factory.py CLI が使用する内部モジュール群。
eval-agent.py に対する graders/ と同じ関係。

モジュール:
    blueprint   — Phase 1: 自然言語仕様 → エージェント定義ファイル群
    eval_suite  — Phase 2: エージェント定義 → 評価スイート（fixture + grader 設定）
    edd_loop    — Phase 4: eval 実行 → スコア分析 → system prompt 自動改善
"""
