"use client";
import { RequireAuth } from "@/components/auth-guard";
import { ProductAnalytics } from "@/components/product-analytics";
export default function ProductAnalyticsPage() {
  return <RequireAuth adminOnly><ProductAnalytics /></RequireAuth>;
}
