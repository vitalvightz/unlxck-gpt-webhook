import { formatAppDate, formatAppDateTime } from "@/lib/date-format";
import { getOptionLabels, TECHNICAL_STYLE_OPTIONS } from "@/lib/intake-options";
import { formatPlanLabel } from "@/lib/plan-labels";

type PlanDisplayFields = {
  fight_date?: string | null;
  plan_name?: string | null;
  status?: string | null;
  technical_style?: string[] | null;
};

function getCustomPlanName(plan: Pick<PlanDisplayFields, "fight_date" | "plan_name">): string | null {
  const customName = plan.plan_name?.trim();
  return customName && customName !== plan.fight_date ? customName : null;
}

export function formatPlanTimestamp(value?: string | null): string {
  if (!value) {
    return "Not available";
  }
  return formatAppDateTime(value);
}

export function formatPlanFightDate(value?: string | null): string {
  if (!value) {
    return "Not provided";
  }
  return formatAppDate(value);
}

export function getPlanDisplayName(plan: Pick<PlanDisplayFields, "fight_date" | "plan_name">): string {
  const customName = getCustomPlanName(plan);
  if (customName) {
    return customName;
  }

  if (plan.fight_date) {
    return formatPlanFightDate(plan.fight_date);
  }

  return "Open saved plan";
}

export function getFeaturedPlanTitle(plan: Pick<PlanDisplayFields, "fight_date" | "plan_name">): string {
  const customName = getCustomPlanName(plan);
  if (!customName) {
    return "Fight camp plan";
  }

  return customName;
}

export function getPlanStyleSummary(plan: Pick<PlanDisplayFields, "technical_style">): string {
  return getOptionLabels(TECHNICAL_STYLE_OPTIONS, plan.technical_style ?? []).join(", ") || "Unspecified style";
}

export function formatPlanStatus(value?: string | null): string {
  const normalized = value?.trim();
  if (!normalized) {
    return "Pending";
  }

  return formatPlanLabel(normalized);
}
