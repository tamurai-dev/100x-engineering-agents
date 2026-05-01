# SaaSプロジェクト管理ツール 要件定義

## 概要
マルチテナント型のSaaSプロジェクト管理ツール。
複数の企業（テナント）が独立したワークスペースを持ち、
プロジェクト・タスク・メンバー管理を行う。

## エンティティ定義

### テナント (tenants)
- id: UUID (PK)
- name: テナント名（企業名）, NOT NULL
- slug: URLスラッグ, UNIQUE, NOT NULL
- plan: サブスクリプションプラン ('free' | 'pro' | 'enterprise'), DEFAULT 'free'
- created_at: TIMESTAMPTZ
- updated_at: TIMESTAMPTZ

### ユーザー (users)
※ Supabase Auth の auth.users を参照する
- id: UUID (PK, auth.users.id と同期)
- email: メールアドレス, UNIQUE, NOT NULL
- display_name: 表示名
- avatar_url: アバター画像URL
- created_at: TIMESTAMPTZ
- updated_at: TIMESTAMPTZ

### テナントメンバー (tenant_members)
- id: UUID (PK)
- tenant_id: FK -> tenants.id
- user_id: FK -> users.id
- role: メンバーロール ('owner' | 'admin' | 'member' | 'viewer')
- joined_at: TIMESTAMPTZ
- UNIQUE(tenant_id, user_id)

### プロジェクト (projects)
- id: UUID (PK)
- tenant_id: FK -> tenants.id  ← マルチテナントキー
- name: プロジェクト名, NOT NULL
- description: 説明文
- status: ('active' | 'archived' | 'completed'), DEFAULT 'active'
- owner_id: FK -> users.id (プロジェクトオーナー)
- start_date: DATE
- due_date: DATE
- created_at: TIMESTAMPTZ
- updated_at: TIMESTAMPTZ

### タスク (tasks)
- id: UUID (PK)
- project_id: FK -> projects.id
- tenant_id: FK -> tenants.id  ← RLS用に冗長保持
- title: タイトル, NOT NULL
- description: 説明
- status: ('todo' | 'in_progress' | 'done' | 'cancelled'), DEFAULT 'todo'
- priority: ('low' | 'medium' | 'high' | 'urgent'), DEFAULT 'medium'
- assignee_id: FK -> users.id (担当者, NULL許容)
- reporter_id: FK -> users.id (起票者)
- due_date: DATE
- estimated_hours: NUMERIC(5,2)
- created_at: TIMESTAMPTZ
- updated_at: TIMESTAMPTZ

### タスクコメント (task_comments)
- id: UUID (PK)
- task_id: FK -> tasks.id
- tenant_id: FK -> tenants.id  ← RLS用
- author_id: FK -> users.id
- body: コメント本文, NOT NULL
- created_at: TIMESTAMPTZ
- updated_at: TIMESTAMPTZ

## RLS要件
- 各テーブルはテナント分離を厳密に実施
- テナントメンバーのみ自テナントのデータを参照可能
- owner/admin はプロジェクト作成・削除が可能
- member はタスクの作成・更新が可能
- viewer は読み取りのみ

## インデックス要件
- tenant_id を含むカラムには複合インデックスを貼る
- タスクの status, priority は検索頻度が高い
- created_at による時系列ソートを最適化

## トリガー要件
- 全テーブルに updated_at 自動更新トリガー
- task_comments 挿入時に親 task の updated_at を更新
- Supabase Auth のユーザー作成時に public.users へ自動同期

<!-- TODO: v2機能として通知テーブル(notifications)の追加を検討中 -->
<!-- 古いコメント: billing_plansテーブルは廃止済み(2023年) -->
