"use client";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { CustomPlanBuilder } from "@/components/custom-plan-builder";

export default function CustomPlansPage() {
  const { session } = useAppSession();
  return <RequireAuth>{session?.access_token ? <CustomPlanBuilder key={session.user_id} accessToken={session.access_token} /> : null}</RequireAuth>;
}
