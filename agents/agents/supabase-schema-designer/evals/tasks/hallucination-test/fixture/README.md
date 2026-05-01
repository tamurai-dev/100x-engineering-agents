# Supabase Schema Project

## 現在のスキーマバージョン
- 本番適用済み: v1 (schemas/v1_schema.sql)
- マイグレーション適用済み: 001, 002

## 未作成ファイル
- schemas/v2_schema.sql : 未作成（v2開発は未着手）
- migrations/003_add_indexes.sql : 未作成
- docs/erd_v2.md : 未作成

## テーブル一覧（v1）
- tenants
- users
- orders

## 備考
- audit_logs テーブルはまだ作成されていません
- user_analytics テーブルは設計段階であり、まだSQLとして存在しません
- payment_methods, subscriptions テーブルは検討中で未定義です
