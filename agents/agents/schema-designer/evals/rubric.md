# Schema Designer Rubric

## Supabase Best Practices (0.0-1.0)
- All tables use `uuid` primary keys with `gen_random_uuid()` default
- `timestamptz` is used instead of `timestamp`
- RLS is enabled on every table with appropriate policies
- Audit columns (`created_at`, `updated_at`) are present on all tables
- `COMMENT ON` statements provide Japanese descriptions

## Schema Completeness (0.0-1.0)
- All entities from the workflow are represented as tables
- Relationships are correctly modeled with foreign keys
- Enum types are defined for status/category columns
- Indexes are created for frequently queried columns
- Multi-tenant isolation is properly implemented when required

## Production Readiness (0.0-1.0)
- Migration SQL is syntactically valid and executable
- Proper constraint definitions (NOT NULL, UNIQUE, CHECK, FK)
- Soft delete support (`deleted_at`) where appropriate
- Event/audit log tables for workflow state transitions
- Extensibility via `metadata jsonb` columns

## Output Quality (0.0-1.0)
- Mermaid ER diagram is included and accurate
- Design rationale is documented for each major decision
- Unknown requirements are flagged in a "pending confirmation" section
- Table and column names follow snake_case convention
