import type {
  AdminAthleteRecord,
  AdminGenerationJobDiagnostic,
  AdminPlanSummary,
  NutritionWorkspaceState,
} from "@/lib/types";

export type AdminAthleteProfileData = {
  athlete: AdminAthleteRecord;
  nutrition: NutritionWorkspaceState | null;
  jobs: AdminGenerationJobDiagnostic[];
  plans: AdminPlanSummary[];
  nutritionWarning: string | null;
  jobsWarning: string | null;
  plansWarning: string | null;
};

export async function loadAdminAthleteProfileData(
  loaders: {
    getAdminAthlete: () => Promise<AdminAthleteRecord>;
    getAdminAthleteNutritionCurrent: () => Promise<NutritionWorkspaceState>;
    getAdminAthleteGenerationJobs: () => Promise<AdminGenerationJobDiagnostic[]>;
    listAdminPlans?: () => Promise<AdminPlanSummary[]>;
  },
): Promise<AdminAthleteProfileData> {
  const athlete = await loaders.getAdminAthlete();

  const [nutritionResult, jobsResult, plansResult] = await Promise.allSettled([
    loaders.getAdminAthleteNutritionCurrent(),
    loaders.getAdminAthleteGenerationJobs(),
    loaders.listAdminPlans?.() ?? Promise.resolve([]),
  ]);
  const plans = 
    plansResult.status === "fulfilled" && Array.isArray(plansResult.value)
      ? plansResult.value.filter((plan) => plan.athlete_id === athlete.athlete_id)
      : [];

  return {
    athlete,
    nutrition: nutritionResult.status === "fulfilled" ? nutritionResult.value : null,
    jobs: jobsResult.status === "fulfilled" && Array.isArray(jobsResult.value) ? jobsResult.value : [],
    plans,
    nutritionWarning: nutritionResult.status === "rejected" ? "Nutrition workspace could not be loaded." : null,
    jobsWarning: jobsResult.status === "rejected" ? "Generation diagnostics could not be loaded." : null,
    plansWarning: plansResult.status === "rejected" ? "Plan history could not be loaded." : null,
  };
}
