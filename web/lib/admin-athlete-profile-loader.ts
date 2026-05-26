import type { AdminAthleteRecord, AdminGenerationJobDiagnostic, NutritionWorkspaceState } from "@/lib/types";

export type AdminAthleteProfileData = {
  athlete: AdminAthleteRecord;
  nutrition: NutritionWorkspaceState | null;
  jobs: AdminGenerationJobDiagnostic[];
  nutritionWarning: string | null;
  jobsWarning: string | null;
};

export async function loadAdminAthleteProfileData(
  loaders: {
    getAdminAthlete: () => Promise<AdminAthleteRecord>;
    getAdminAthleteNutritionCurrent: () => Promise<NutritionWorkspaceState>;
    getAdminAthleteGenerationJobs: () => Promise<AdminGenerationJobDiagnostic[]>;
  },
): Promise<AdminAthleteProfileData> {
  const athlete = await loaders.getAdminAthlete();

  const [nutritionResult, jobsResult] = await Promise.allSettled([
    loaders.getAdminAthleteNutritionCurrent(),
    loaders.getAdminAthleteGenerationJobs(),
  ]);

  return {
    athlete,
    nutrition: nutritionResult.status === "fulfilled" ? nutritionResult.value : null,
    jobs: jobsResult.status === "fulfilled" ? jobsResult.value : [],
    nutritionWarning: nutritionResult.status === "rejected" ? "Nutrition workspace could not be loaded." : null,
    jobsWarning: jobsResult.status === "rejected" ? "Generation diagnostics could not be loaded." : null,
  };
}
