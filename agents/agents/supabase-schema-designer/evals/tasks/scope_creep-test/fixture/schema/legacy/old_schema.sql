-- ====================================================
-- LEGACY SCHEMA v0.1 (2021年作成, 非推奨)
-- このファイルは歴史的参考のために保持しています
-- 本番環境では使用しないでください
-- ====================================================

-- 古いテナント管理テーブル（現在のtenants相当）
CREATE TABLE IF NOT EXISTS organisations (
  id SERIAL PRIMARY KEY,  -- UUIDではなくSERIAL
  org_name VARCHAR(255),
  org_slug VARCHAR(100),
  subscription_type VARCHAR(50) DEFAULT 'basic',  -- planではなくsubscription_type
  ts_created TIMESTAMP DEFAULT NOW(),  -- created_atではなくts_created
  ts_modified TIMESTAMP DEFAULT NOW()
);

-- 古いユーザーテーブル
CREATE TABLE IF NOT EXISTS app_users (
  id SERIAL PRIMARY KEY,
  org_id INTEGER REFERENCES organisations(id),
  user_email VARCHAR(255) UNIQUE,
  user_name VARCHAR(100),
  user_role VARCHAR(50) DEFAULT 'regular',
  ts_created TIMESTAMP DEFAULT NOW()
);

-- 古いプロジェクトテーブル
CREATE TABLE IF NOT EXISTS org_projects (
  id SERIAL PRIMARY KEY,
  org_id INTEGER REFERENCES organisations(id),
  proj_name VARCHAR(255) NOT NULL,
  proj_desc TEXT,
  proj_status VARCHAR(50) DEFAULT 'open',
  created_by INTEGER REFERENCES app_users(id),
  ts_created TIMESTAMP DEFAULT NOW(),
  ts_modified TIMESTAMP DEFAULT NOW()
);

-- 古いタスクテーブル
CREATE TABLE IF NOT EXISTS proj_tasks (
  id SERIAL PRIMARY KEY,
  project_id INTEGER REFERENCES org_projects(id),
  task_title VARCHAR(500),
  task_desc TEXT,
  task_status VARCHAR(50) DEFAULT 'open',
  assigned_to INTEGER REFERENCES app_users(id),
  ts_created TIMESTAMP DEFAULT NOW(),
  ts_modified TIMESTAMP DEFAULT NOW()
);
-- RLSなし、インデックスなし、トリガーなし
