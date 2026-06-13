-- Schema-first structured training plan storage on the plans table.
--
-- PR #1738 added the StructuredTrainingPlan schema, validation helpers, and the
-- read/mapping path (api/structured_plan_models.py, api/plan_mappers.py). This
-- migration adds the persistence side so Stage 2 can save a validated structured
-- plan beside the existing raw plan_text without removing any legacy field.
--
-- Both columns are additive and nullable:
--   * structured_plan holds a validated StructuredTrainingPlan as JSONB. It is
--     written only when structured generation produced a schema-valid object;
--     an invalid attempt leaves it NULL so the raw plan_text remains the
--     fallback.
--   * schema_version records the structured schema version of the stored plan.
--
-- Existing rows simply keep NULLs and continue to open via plan_text, so applying
-- this migration cannot break legacy plans or in-flight generation.

alter table public.plans add column if not exists structured_plan jsonb;
alter table public.plans add column if not exists schema_version text;
