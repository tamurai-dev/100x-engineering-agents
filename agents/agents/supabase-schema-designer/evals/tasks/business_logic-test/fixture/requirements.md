# SaaS プロジェクト管理プラットフォーム 要件定義

## 概要
マルチテナント対応の SaaS プロジェクト管理ツール。
各 Organization（テナント）が独立したワークスペースを持つ。

## エンティティ

### organizations
- id, name, plan（'free' | 'pro'）, created_at, updated_at

### users
- id（Supabase auth.users と連携）, email, display_name, created_at

### organization_members
- organization_id, user_id, role（'owner' | 'admin' | 'member'）, joined_at

### projects
- id, organization_id, name, status（'active' | 'archived'）, created_at, updated_at, deleted_at

### subscriptions
- id, organization_id, plan（'free' | 'pro'）, started_at, cancelled_at, current_period_start, current_period_end

### invoices
- id, organization_id, subscription_id, amount（円単位）, period_start, period_end, created_at

### refunds
- id, organization_id, invoice_id, amount（円単位）, reason, created_at

## ビジネスルール

### プラン制限
- free プラン: 同時にアクティブ（status = 'active' かつ deleted_at IS NULL）なプロジェクトは最大 3 件
- pro プラン: 制限なし
- プロジェクト作成時にチェックし、超過する場合は ERROR を返す

### 月途中キャンセル返金
- サブスクリプションのキャンセル（cancelled_at をセット）時に自動計算
- 返金額 = invoice.amount × (残日数 / 請求期間の総日数)
- 残日数 = current_period_end - cancelled_at（日単位、端数切り捨て）
- 請求期間の総日数 = current_period_end - current_period_start（日単位）
- 残日数が 0 以下の場合は返金不要（refunds に挿入しない）
- 返金額は FLOOR で整数円に切り捨て
- 返金額が 0 円の場合も挿入しない

### 論理削除強制
- projects テーブルへの DELETE 文を禁止
- 削除は UPDATE で deleted_at をセットすることで行う

### プロジェクト名重複禁止
- 同一 organization_id 内で、deleted_at IS NULL のプロジェクト間での name 重複を禁止
- ユニーク制約またはトリガーで実装

### オーナー退会禁止
- organization_members からの DELETE 時に、対象ユーザーが role = 'owner' であれば EXCEPTION を発生させる
- オーナーは先に他のメンバーにオーナー権限を移譲してから退会する必要がある
