"use client";

import { RequireAuth } from "@/components/auth-guard";
import { TodayScreen } from "@/components/today-screen";

export default function DashboardPage() {
  return (
    <RequireAuth>
      <TodayScreen />
    </RequireAuth>
  );
}
