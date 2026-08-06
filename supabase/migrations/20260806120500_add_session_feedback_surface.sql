-- Post-session feedback: a fourth beta_feedback surface.
--
-- The prompt shown after a completed session asks three quick structured
-- questions (difficulty, instructions, plan accuracy) plus an optional comment
-- and screenshot. That does not fit the yes/no `response` shape the plan and
-- Today surfaces use, so the structured answers get their own jsonb column and
-- the reviewed session becomes a first-class column instead of only being
-- encoded inside `context_key`.
--
-- All existing rows stay valid: `structured_response` defaults to '{}' and
-- `session_id` stays null on every non-session surface.

alter table public.beta_feedback
  add column if not exists structured_response jsonb not null default '{}'::jsonb;

alter table public.beta_feedback
  add column if not exists session_id text;

comment on column public.beta_feedback.structured_response is
  'Session-surface only: the quick structured answers collected after a completed session.';
comment on column public.beta_feedback.session_id is
  'Session-surface only: the plan session the feedback reviews (session_completions.session_id).';

-- The surface and category domains are column-level checks, so Postgres named
-- them <table>_<column>_check. Replace both to admit the session surface.
alter table public.beta_feedback
  drop constraint if exists beta_feedback_surface_check;
alter table public.beta_feedback
  add constraint beta_feedback_surface_check
  check (surface in ('plan', 'daily_recommendation', 'session', 'global'));

alter table public.beta_feedback
  drop constraint if exists beta_feedback_category_check;
alter table public.beta_feedback
  add constraint beta_feedback_category_check
  check (category in (
    'plan_usefulness',
    'recommendation_fit',
    'recommendation_safety',
    'session_review',
    'bug_report',
    'feature_request',
    'safety_issue',
    'general_feedback'
  ));

alter table public.beta_feedback
  drop constraint if exists beta_feedback_surface_category_check;
alter table public.beta_feedback
  add constraint beta_feedback_surface_category_check check (
    (surface = 'plan' and category = 'plan_usefulness')
    or (surface = 'daily_recommendation' and category in ('recommendation_fit', 'recommendation_safety'))
    or (surface = 'session' and category = 'session_review')
    or (surface = 'global' and category in ('bug_report', 'feature_request', 'safety_issue', 'general_feedback'))
  );

-- Session feedback carries no yes/no verdict and no free-text reason code: the
-- structured answers are the verdict.
alter table public.beta_feedback
  drop constraint if exists beta_feedback_response_shape_check;
alter table public.beta_feedback
  add constraint beta_feedback_response_shape_check check (
    (surface in ('global', 'session') and response is null)
    or (surface = 'plan' and response in ('yes', 'no'))
    or (surface = 'daily_recommendation' and response in ('yes', 'no', 'unsafe'))
  );

alter table public.beta_feedback
  drop constraint if exists beta_feedback_reason_check;
alter table public.beta_feedback
  add constraint beta_feedback_reason_check check (
    (surface in ('global', 'session') and reason is null)
    or (response in ('yes', 'unsafe') and reason is null)
    or (surface = 'plan' and response = 'no' and (
      reason is null or reason in (
        'too_hard', 'too_easy', 'schedule_mismatch', 'injury_restrictions_wrong',
        'exercises_unsuitable', 'instructions_unclear', 'other'
      )
    ))
    or (surface = 'daily_recommendation' and response = 'no' and (
      reason is null or reason in (
        'too_demanding', 'too_cautious', 'pain_or_injury_ignored',
        'training_mismatch', 'repetitive', 'unclear'
      )
    ))
  );

-- Only the session surface stores structured answers, and every answer it does
-- store has to be one of the offered choices. Keys may be absent: each question
-- is optional as long as the submission carries something (enforced by the API).
alter table public.beta_feedback
  drop constraint if exists beta_feedback_structured_response_check;
alter table public.beta_feedback
  add constraint beta_feedback_structured_response_check check (
    case
      when surface = 'session' then
        jsonb_typeof(structured_response) = 'object'
        and coalesce(structured_response ->> 'difficulty', 'appropriate')
          in ('too_easy', 'appropriate', 'too_hard')
        and coalesce(structured_response ->> 'instructions', 'clear')
          in ('clear', 'unclear')
        and coalesce(structured_response ->> 'plan_accuracy', 'felt_right')
          in ('felt_right', 'something_wrong')
      else structured_response = '{}'::jsonb
    end
  );

-- The 120-character ceiling is what keeps the derived context key inside its
-- own 180-character check: "session:{plan_id}:{session_id}:{training_day}" is
-- 56 characters of frame around a UUID plan id and an ISO date.
alter table public.beta_feedback
  drop constraint if exists beta_feedback_session_id_check;
alter table public.beta_feedback
  add constraint beta_feedback_session_id_check check (
    (surface = 'session' and session_id is not null and char_length(session_id) between 1 and 120)
    or (surface <> 'session' and session_id is null)
  );
