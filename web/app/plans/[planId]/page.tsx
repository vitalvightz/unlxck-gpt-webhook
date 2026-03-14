import { PlanDetailScreen } from "@/components/plan-detail-screen";

export default async function PlanDetailPage({ params }: { params: Promise<{ planId: string }> }) {
  const { planId } = await params;
  return <PlanDetailScreen planId={planId} />;
}