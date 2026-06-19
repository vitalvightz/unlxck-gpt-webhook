// Shared rule for whether a plan can be set as the athlete's active plan. A plan
// is eligible only once it is released to the athlete view ("ready" or
// "publishable_with_flags"); archived, triage, medical and review states are not
// eligible. Kept in one place so the plans list and the plan detail page agree.
export function canSetActivePlan(status?: string | null): boolean {
  const normalized = status?.trim().toLowerCase();
  return normalized === "ready" || normalized === "publishable_with_flags";
}
