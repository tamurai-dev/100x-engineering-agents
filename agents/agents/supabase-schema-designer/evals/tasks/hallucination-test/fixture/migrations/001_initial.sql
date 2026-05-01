-- Migration 001: Initial setup
-- Applied: 2024-01-10

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable RLS on users
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tenant_isolation_users"
  ON users
  FOR ALL
  USING (tenant_id = current_setting('app.current_tenant')::UUID);
