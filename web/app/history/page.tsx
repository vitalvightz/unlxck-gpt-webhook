"use client";

import { RequireAuth } from "@/components/auth-guard";
import { HistoryScreen } from "@/components/history-screen";

export default function HistoryPage() {
  return (
    <RequireAuth>
      <HistoryScreen />
    </RequireAuth>
  );
}
