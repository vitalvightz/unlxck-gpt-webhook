import { ApiError } from "@/lib/api";

// One vocabulary for "the generation went wrong", shared by the full-screen
// /generate failure card and the global ribbon so the two can never disagree
// about what happened or about which buttons make sense.
//
// - job_failed:     the server job reached `failed`. Retry re-runs that job.
// - stalled:        the job stopped reporting progress for long enough that we
//                   stopped watching it. The server may still be chewing on it.
// - start_failed:   the job was never created (network/gateway). Retry starts a
//                   fresh build; there is nothing on the server to re-run.
// - invalid_intake: the request itself is rejected. Retrying the identical
//                   payload cannot succeed — the intake has to change first.
// - limit_reached:  a cap or an in-flight build blocks a new attempt right now.
// - unavailable:    the job is in a state this screen cannot act on (e.g. it
//                   already produced a plan, or it is no longer retryable).
export type GenerationFailureKind =
  | "job_failed"
  | "stalled"
  | "start_failed"
  | "invalid_intake"
  | "limit_reached"
  | "unavailable";

export type GenerationFailureAction = "retry" | "refine_intake" | "plan_history" | "workspace";

export type GenerationFailureCopy = {
  headline: string;
  detail: string;
  primary: GenerationFailureAction;
  secondary: GenerationFailureAction[];
};

// Thrown by the controller when a watched job stops producing progress. Kept
// here so the classifier and the thrower cannot drift apart.
export const STALLED_GENERATION_ERROR = "Build stalled — retry";

const INTAKE_ERROR_SNIPPETS = [
  "invalid Weekly Training Frequency",
  "cannot exceed selected Training Availability days",
  "You selected fewer available training days",
  "fight_date",
  "technical_style",
];

const LIMIT_ERROR_SNIPPETS = [
  "daily plan generation limit",
  "daily generation limit",
  "Too many plan generation requests",
  "already queued or running for this account",
];

const UNAVAILABLE_ERROR_SNIPPETS = [
  "already produced a saved plan",
  "only failed generation jobs can be retried",
  "only queued or running generation jobs can be cancelled",
  "generation job not found",
];

function includesAny(message: string, snippets: string[]): boolean {
  const lowered = message.toLowerCase();
  return snippets.some((snippet) => lowered.includes(snippet.toLowerCase()));
}

export function classifyGenerationFailure(
  error: unknown,
  options: { hasFailedJobId?: boolean } = {},
): GenerationFailureKind {
  const message = error instanceof Error ? error.message : String(error ?? "");

  if (message.includes(STALLED_GENERATION_ERROR)) {
    return "stalled";
  }
  if (includesAny(message, LIMIT_ERROR_SNIPPETS)) {
    return "limit_reached";
  }
  if (includesAny(message, INTAKE_ERROR_SNIPPETS)) {
    return "invalid_intake";
  }
  if (includesAny(message, UNAVAILABLE_ERROR_SNIPPETS)) {
    return "unavailable";
  }
  if (error instanceof ApiError) {
    if (error.status === 429) {
      return "limit_reached";
    }
    if (error.status === 400 || error.status === 422) {
      return "invalid_intake";
    }
    if (error.status === 404 || error.status === 409) {
      return "unavailable";
    }
  }
  // A job id only exists once the backend accepted the request, so its presence
  // is what separates "the build died" from "the build never started".
  return options.hasFailedJobId ? "job_failed" : "start_failed";
}

const RETRYABLE_FAILURE_KINDS: ReadonlySet<GenerationFailureKind> = new Set<GenerationFailureKind>([
  "job_failed",
  "stalled",
  "start_failed",
]);

export function isRetryableGenerationFailure(kind: GenerationFailureKind | null): boolean {
  return kind !== null && RETRYABLE_FAILURE_KINDS.has(kind);
}

// Stored job errors are engineering text ("Stage 2 first_pass prompt too large:
// 214880 chars"). Athletes see these verbatim today; map the known ones and
// fall back to a plain sentence rather than leaking internals.
export function humanizeGenerationError(rawError: string | null | undefined): string {
  const message = String(rawError || "").trim();
  if (!message) {
    return "The build stopped before a plan was saved.";
  }
  if (message.includes("Cancelled by")) {
    return "This build was cancelled before it finished.";
  }
  if (message.includes("Stage 2 first_pass prompt too large")) {
    return "Your camp was too large to finalize in one pass. A retry usually clears it.";
  }
  if (message.includes("Stage 1 planner timed out") || message.includes("timed out")) {
    return "The planner took too long and stopped. Nothing was saved, so a retry starts clean.";
  }
  if (message.toLowerCase().includes("quota")) {
    return "Plan generation is temporarily unavailable on our side. Try again shortly.";
  }
  if (includesAny(message, INTAKE_ERROR_SNIPPETS) || includesAny(message, LIMIT_ERROR_SNIPPETS)) {
    // Already written for athletes by the API — pass it through unchanged.
    return message;
  }
  return "The build stopped before a plan was saved.";
}

export function describeGenerationFailure(
  kind: GenerationFailureKind | null,
  rawError?: string | null,
): GenerationFailureCopy {
  const detail = humanizeGenerationError(rawError);

  switch (kind) {
    case "stalled":
      return {
        headline: "The build stopped responding.",
        detail:
          "No progress came back for several minutes, so we stopped watching it. Nothing was saved — a retry starts clean.",
        primary: "retry",
        secondary: ["workspace"],
      };
    case "start_failed":
      return {
        headline: "We could not start the build.",
        detail:
          "The request never reached the planner, so no plan was started and nothing was charged against your daily builds.",
        primary: "retry",
        secondary: ["workspace"],
      };
    case "invalid_intake":
      return {
        headline: "Your intake needs a change before this can build.",
        detail: rawError ? String(rawError) : "Some of your answers conflict, so the planner rejected the request.",
        primary: "refine_intake",
        secondary: ["workspace"],
      };
    case "limit_reached":
      return {
        headline: "This build cannot start right now.",
        detail: rawError ? String(rawError) : "Another build is in flight or you have hit today's build limit.",
        primary: "workspace",
        secondary: ["plan_history"],
      };
    case "unavailable":
      return {
        headline: "This build can no longer be retried from here.",
        detail: detail,
        primary: "plan_history",
        secondary: ["workspace"],
      };
    case "job_failed":
    default:
      return {
        headline: "Your plan build stopped before it finished.",
        detail,
        primary: "retry",
        secondary: ["workspace", "plan_history"],
      };
  }
}

export const GENERATION_FAILURE_ACTION_LABELS: Record<GenerationFailureAction, string> = {
  retry: "Try again",
  refine_intake: "Fix my intake",
  plan_history: "Open plan history",
  workspace: "Return to workspace",
};
