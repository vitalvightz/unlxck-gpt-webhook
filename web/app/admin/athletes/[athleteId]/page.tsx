"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import {
  AthleteProfileHero,
  AthleteProfileOverviewCard,
} from "@/components/admin-athlete-profile";
import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import {
  generateAdminAthletePlanFromLatestIntake,
  getAdminAthlete,
  getAdminAthleteNutritionCurrent,
  updateAdminAthleteNutritionCurrent,
} from "@/lib/api";
import { useGenerationController } from "@/lib/generation-controller";
import type { AdminAthleteRecord, NutritionWorkspaceState, NutritionWorkspaceUpdateRequest } from "@/lib/types";

function toNutritionUpdateRequest(workspace: NutritionWorkspaceState): NutritionWorkspaceUpdateRequest {
  return {
    nutrition_profile: workspace.nutrition_profile,
    shared_camp_context: workspace.shared_camp_context,
    s_and_c_preferences: workspace.s_and_c_preferences,
    nutrition_readiness: workspace.nutrition_readiness,
    nutrition_monitoring: workspace.nutrition_monitoring,
    nutrition_coach_controls: workspace.nutrition_coach_controls,
  };
}

export default function AdminAthletePage() {
  const { session } = useAppSession();
  const params = useParams();
  const athleteId = typeof params?.athleteId === "string" ? params.athleteId : null;
  const [athlete, setAthlete] = useState<AdminAthleteRecord | null>(null);
  const [nutrition, setNutrition] = useState<NutritionWorkspaceState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isSavingControls, setIsSavingControls] = useState(false);

  const controller = useGenerationController({
    token: session?.access_token ?? null,
    storageKey: athleteId ? `unlxck:pending-generation:admin:${athleteId}` : null,
    createJob: async (clientRequestId) => {
      if (!session?.access_token || !athleteId) {
        throw new Error("Session or athlete context is missing.");
      }
      return generateAdminAthletePlanFromLatestIntake(session.access_token, athleteId, clientRequestId);
    },
    onComplete: ({ planId, status, recovered }) => {
      const search = new URLSearchParams();
      if (status === "review_required") {
        search.set("review_required", "1");
      }
      if (recovered) {
        search.set("recovered", "1");
      }
      window.location.replace(`/plans/${planId}${search.toString() ? `?${search.toString()}` : ""}`);
    },
  });

  useEffect(() => {
    if (!session?.access_token || !athleteId) {
      return;
    }

    Promise.all([
      getAdminAthlete(session.access_token, athleteId),
      getAdminAthleteNutritionCurrent(session.access_token, athleteId),
    ])
      .then(([nextAthlete, nextNutrition]) => {
        setAthlete(nextAthlete);
        setNutrition(nextNutrition);
      })
      .catch((athleteError) => {
        setError(athleteError instanceof Error ? athleteError.message : "Unable to load athlete profile.");
      });
  }, [athleteId, session?.access_token]);

  useEffect(() => {
    if (controller.error) {
      setError(controller.error);
    }
  }, [controller.error]);

  async function handleGenerateNewPlan() {
    if (!athlete?.latest_intake || !athleteId || controller.isGenerating) {
      return;
    }
    setError(null);
    await controller.startGeneration();
  }

  async function handleSaveCoachControls() {
    if (!session?.access_token || !athleteId || !nutrition || isSavingControls) {
      return;
    }
    setError(null);
    setMessage(null);
    setIsSavingControls(true);
    try {
      const updated = await updateAdminAthleteNutritionCurrent(
        session.access_token,
        athleteId,
        toNutritionUpdateRequest(nutrition),
      );
      setNutrition(updated);
      setMessage("Coach controls saved.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to save coach controls.");
    } finally {
      setIsSavingControls(false);
    }
  }

  return (
    <RequireAuth adminOnly>
      {error ? (
        <section className="panel loading-card">
          <p className="kicker">Athlete Profile</p>
          <div className="error-banner">{error}</div>
          <div className="plan-summary-actions">
            <Link href="/admin" className="ghost-button">
              Back to admin
            </Link>
          </div>
        </section>
      ) : !athlete ? (
        <section className="panel loading-card">
          <p className="kicker">Athlete Profile</p>
          <h1>Loading profile</h1>
          <p className="muted">Fetching athlete record now.</p>
        </section>
      ) : (
        <section className="panel athlete-profile-panel">
          <AthleteProfileHero athlete={athlete} />

          <div className="plan-summary-actions">
            <Link href="/admin" className="ghost-button">
              Back to admin
            </Link>
            <button
              type="button"
              className="cta"
              onClick={handleGenerateNewPlan}
              disabled={!athlete.latest_intake || controller.isGenerating}
            >
              {controller.isGenerating ? "Generating..." : "Generate new plan"}
            </button>
          </div>
          {controller.statusMessage ? <p className="muted">{controller.statusMessage}</p> : null}
          {!athlete.latest_intake ? (
            <p className="muted">Generate is available after this athlete has at least one saved intake.</p>
          ) : null}

          <AthleteProfileOverviewCard athlete={athlete} />

          {nutrition ? (
            <div className="split-layout nutrition-admin-split">
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Nutrition summary</p>
                  <h2 className="form-section-title">Current weight and readiness</h2>
                </div>
                <div className="review-detail-list nutrition-review-list">
                  {[
                    ["Foundation", nutrition.derived.foundation_status],
                    ["Days until fight", nutrition.derived.days_until_fight != null ? String(nutrition.derived.days_until_fight) : "Not set"],
                    ["Current phase", nutrition.derived.current_phase_effective || "Not derived yet"],
                    ["Weight cut", `${nutrition.derived.weight_cut_pct.toFixed(1)}%`],
                    ["Fight-week override", nutrition.derived.fight_week_override_band.replaceAll("_", " ")],
                    ["Readiness flags", nutrition.derived.readiness_flags.join(", ") || "baseline"],
                  ].map(([label, value]) => (
                    <div key={label} className="review-detail-row">
                      <p className="review-detail-label">{label}</p>
                      <p className="review-detail-value">{value}</p>
                    </div>
                  ))}
                </div>
              </article>

              <aside className="step-aside athlete-motion-slot athlete-motion-rail">
                <div className="support-panel">
                  <div className="form-section-header">
                    <p className="kicker">Coach controls</p>
                    <h2 className="form-section-title">Admin-only overrides</h2>
                  </div>
                  <div className="nutrition-admin-controls">
                    <label className="checkbox-card">
                      <input
                        type="checkbox"
                        checked={nutrition.nutrition_coach_controls.coach_override_enabled}
                        onChange={(event) =>
                          setNutrition((current) =>
                            current
                              ? {
                                  ...current,
                                  nutrition_coach_controls: {
                                    ...current.nutrition_coach_controls,
                                    coach_override_enabled: event.target.checked,
                                  },
                                }
                              : current,
                          )
                        }
                      />
                      <span className="checkbox-card-copy">
                        <span className="checkbox-card-title">Coach override enabled</span>
                      </span>
                    </label>
                    <label className="checkbox-card">
                      <input
                        type="checkbox"
                        checked={nutrition.nutrition_coach_controls.athlete_override_enabled}
                        onChange={(event) =>
                          setNutrition((current) =>
                            current
                              ? {
                                  ...current,
                                  nutrition_coach_controls: {
                                    ...current.nutrition_coach_controls,
                                    athlete_override_enabled: event.target.checked,
                                  },
                                }
                              : current,
                          )
                        }
                      />
                      <span className="checkbox-card-copy">
                        <span className="checkbox-card-title">Athlete override enabled</span>
                      </span>
                    </label>
                    <label className="checkbox-card">
                      <input
                        type="checkbox"
                        checked={nutrition.nutrition_coach_controls.fight_week_manual_mode}
                        onChange={(event) =>
                          setNutrition((current) =>
                            current
                              ? {
                                  ...current,
                                  nutrition_coach_controls: {
                                    ...current.nutrition_coach_controls,
                                    fight_week_manual_mode: event.target.checked,
                                  },
                                }
                              : current,
                          )
                        }
                      />
                      <span className="checkbox-card-copy">
                        <span className="checkbox-card-title">Fight week manual mode</span>
                      </span>
                    </label>
                    <label className="checkbox-card">
                      <input
                        type="checkbox"
                        checked={nutrition.nutrition_coach_controls.water_cut_locked_to_manual}
                        onChange={(event) =>
                          setNutrition((current) =>
                            current
                              ? {
                                  ...current,
                                  nutrition_coach_controls: {
                                    ...current.nutrition_coach_controls,
                                    water_cut_locked_to_manual: event.target.checked,
                                  },
                                }
                              : current,
                          )
                        }
                      />
                      <span className="checkbox-card-copy">
                        <span className="checkbox-card-title">Water cut locked to manual</span>
                      </span>
                    </label>
                    <div className="field">
                      <label htmlFor="coachCalorieFloor">Minimum calories</label>
                      <input
                        id="coachCalorieFloor"
                        type="number"
                        value={nutrition.nutrition_coach_controls.do_not_reduce_below_calories ?? ""}
                        onChange={(event) =>
                          setNutrition((current) =>
                            current
                              ? {
                                  ...current,
                                  nutrition_coach_controls: {
                                    ...current.nutrition_coach_controls,
                                    do_not_reduce_below_calories: event.target.value ? Number(event.target.value) : null,
                                  },
                                }
                              : current,
                          )
                        }
                      />
                    </div>
                    <div className="field">
                      <label htmlFor="coachProteinFloor">Protein floor (g/kg)</label>
                      <input
                        id="coachProteinFloor"
                        type="number"
                        step="0.1"
                        value={nutrition.nutrition_coach_controls.protein_floor_g_per_kg ?? ""}
                        onChange={(event) =>
                          setNutrition((current) =>
                            current
                              ? {
                                  ...current,
                                  nutrition_coach_controls: {
                                    ...current.nutrition_coach_controls,
                                    protein_floor_g_per_kg: event.target.value ? Number(event.target.value) : null,
                                  },
                                }
                              : current,
                          )
                        }
                      />
                    </div>
                    <div className="plan-summary-actions">
                      <button type="button" className="cta" onClick={handleSaveCoachControls} disabled={isSavingControls}>
                        {isSavingControls ? "Saving..." : "Save coach controls"}
                      </button>
                    </div>
                  </div>
                </div>
              </aside>
            </div>
          ) : null}
          {message ? <div className="success-banner">{message}</div> : null}
        </section>
      )}
    </RequireAuth>
  );
}
