# SaaSプロジェクト管理アプリ 要件定義

## 概要
マルチテナント対応のプロジェクト管理SaaSアプリ。
各組織（テナント）が独立してプロジェクト・タスク・メンバーを管理する。

## エンティティ

### Organization（組織/テナント）
- id: UUID（PK）
- name: 組織名（最大100文字）
- slug: URLスラッグ（英数字・ハイフンのみ、3〜50文字、一意）
- plan: サブスクリプションプラン（free/pro/enterprise）
- max_projects: プランごとの最大プロジェクト数（free=3, pro=20, enterprise=無制限）
- max_members: プランごとの最大メンバー数（free=5, pro=50, enterprise=無制限）
- created_at, updated_at

### User（ユーザー）
- id: UUID（PK、Supabase Auth と連携）
- email: メールアドレス（一意）
- display_name: 表示名
- avatar_url: アバターURL（任意）
- created_at, updated_at

### OrganizationMember（組織メンバー）
- organization_id + user_id: 複合PK
- role: owner/admin/member/viewer
- invited_by: 招待したユーザーのID
- joined_at

### Project（プロジェクト）
- id: UUID（PK）
- organization_id: FK → Organization
- name: プロジェクト名（最大200文字）
- description: 説明（任意）
- status: active/archived/deleted
- owner_id: FK → User
- due_date: 期限（任意）
- created_at, updated_at

### Task（タスク）
- id: UUID（PK）
- project_id: FK → Project
- organization_id: FK → Organization（RLS用）
- title: タスクタイトル（最大500文字）
- description: 説明（任意）
- status: todo/in_progress/done/cancelled
- priority: low/medium/high/urgent
- assignee_id: FK → User（任意）
- due_date: 期限（任意）
- sort_order: 並び順（整数）
- created_by: FK → User
- created_at, updated_at

### Comment（コメント）
- id: UUID（PK）
- task_id: FK → Task
- organization_id: FK → Organization（RLS用）
- author_id: FK → User
- body: コメント本文（最大5000文字）
- edited_at: 編集日時（任意）
- created_at

### AuditLog（監査ログ）
- id: UUID（PK）
- organization_id: FK → Organization
- actor_id: FK → User
- action: 操作種別（文字列）
- resource_type: リソース種別（project/task/comment/member）
- resource_id: 操作対象のUUID
- metadata: JSONB（変更前後の値など）
- created_at

## ビジネスルール
1. organizationのslugは小文字英数字とハイフンのみ使用可能
2. ownerロールは organization に必ず1人以上存在する
3. freeプランは project 3件まで、pro は20件まで、enterprise は無制限
4. 削除済みプロジェクト（status=deleted）のタスクは新規作成不可
5. viewer ロールはコメント・タスクの作成不可（読み取り専用）
6. audit_logs は INSERT のみ（UPDATE/DELETE 不可）
