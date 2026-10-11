"use client";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { CustomPlanBuilder } from "@/components/custom-plan-builder";
function Editor() {
  const { session } = useAppSession();
  const planId = useSearchParams().get("plan") ?? undefined;
  return (
    <RequireAuth>
      {session?.access_token ? (
        <CustomPlanBuilder
          key={`${session.user_id}:${planId ?? "new"}`}
          accessToken={session.access_token}
          planId={planId}
        />
      ) : null}
    </RequireAuth>
  );
}
export default function CustomPlansPage() {
  return (
    <Suspense fallback={<p role="status">Loading plan…</p>}>
      <Editor />
    </Suspense>
  );
}
