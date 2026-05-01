-- Migration 002: Orders RLS
-- Applied: 2024-01-15

ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tenant_isolation_orders"
  ON orders
  FOR ALL
  USING (tenant_id = current_setting('app.current_tenant')::UUID);
