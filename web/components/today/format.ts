import { formatAppDate } from "@/lib/date-format";

/** Athlete-local training day as display text, falling back to "Today". */
export function formatTrainingDay(value: string | null | undefined): string {
  if (!value) {
    return "Today";
  }
  return formatAppDate(value);
}
