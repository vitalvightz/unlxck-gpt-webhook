import Link from "next/link";

import { StructuredPlanRenderer } from "@/components/structured-plan-renderer";
import type { StructuredPlan } from "@/lib/types";

const demoMeta = [
  { label: "Athlete", value: "Sample Fighter" },
  { label: "Discipline", value: "MMA / Muay Thai" },
  { label: "Fight date", value: "8 weeks out" },
  { label: "Rounds format", value: "3 x 5" },
  { label: "Training days", value: "Mon, Tue, Thu, Fri, Sat" },
  { label: "Sessions per week", value: "5" },
];

const demoStructuredPlan = {
  schema_version: "1.0",
  plan_metadata: {
    title: "Sample Fighter - 8 Week Fight Camp",
    sport: "MMA / Muay Thai",
    plan_type: "fight_camp",
  },
  athlete_context: {
    sport_profile: "MMA / Muay Thai",
    style_profile: "Pressure striker with clinch emphasis",
  },
  event_context: {
    fight_date: "8 weeks out",
    event_type: "fight_or_match",
  },
  red_flag_rules: [
    {
      rule_id: "demo-stop-report",
      severity: "red",
      display_text: "Stop and report sharp pain, dizziness, or symptoms that worsen during sparring.",
      action: "Pause the session and get coach or clinician review before resuming.",
    },
  ],
  weeks: [
    {
      week_id: "demo-week-4",
      week_index: 4,
      phase_label: "SPP",
      week_goal: "Round-specific pressure and repeat power",
      days: [
        {
          date: "Mon",
          countdown_label: "D-32",
          day_type: "hard_spar",
          today_card: {
            headline: "Primary hard day. Keep the first rounds technical before raising intent.",
            readiness_status: "train_as_planned",
            nutrition_summary: "Fuel early and keep fluids steady before live rounds.",
            mindset_anchor: {
              intent: "Win position before volume.",
              focus_cue: "Exit clean after every exchange.",
              context: "Highest skill-intensity day of the week.",
            },
          },
          sessions: [
            {
              session_id: "demo-session-spar",
              session_type: "sparring",
              title: "Hard sparring + tactical cleanup",
              objective: "Build fight-speed decision making without turning every round into a war.",
              planned_duration: { value: 90, unit: "minutes" },
              primary_stressor: "sparring",
              cns_demand: "high",
              impact_level: "high",
              blocks: [
                {
                  block_id: "demo-block-rounds",
                  block_type: "skill",
                  category: "sparring",
                  display_name: "Live rounds",
                  rounds: 5,
                  duration: { value: 5, unit: "minutes" },
                  rest: { value: 60, unit: "seconds" },
                  intensity: "fight rhythm",
                  impact_level: "high",
                  purpose: "Match the fight format while preserving coach control over intensity.",
                  coaching_cues: ["Win the first grip", "Leave on angles", "Reset before chasing volume"],
                },
              ],
            },
          ],
        },
        {
          date: "Tue",
          countdown_label: "D-31",
          day_type: "strength",
          sessions: [
            {
              session_id: "demo-session-strength",
              session_type: "strength_power",
              title: "Max strength + alactic finisher",
              objective: "Keep force output high while avoiding fatigue that bleeds into skill work.",
              planned_duration: { value: 60, unit: "minutes" },
              primary_stressor: "strength",
              cns_demand: "moderate",
              impact_level: "low",
              blocks: [
                {
                  block_id: "demo-block-trap",
                  block_type: "strength",
                  category: "strength",
                  display_name: "Trap bar deadlift",
                  sets: 4,
                  reps: "3",
                  load: { display: "Heavy, crisp reps" },
                  effort: { method: "RPE", value: 8 },
                  rest: { value: 150, unit: "seconds" },
                  purpose: "Bank force production without grinding.",
                  coaching_cues: ["Fast bar, clean brace", "Stop before form slows"],
                },
                {
                  block_id: "demo-block-sled",
                  block_type: "conditioning",
                  category: "power",
                  display_name: "Sled push sprint",
                  sets: 6,
                  reps: "10 seconds",
                  rest: { value: 70, unit: "seconds" },
                  energy_system: "alactic",
                  intensity: "explosive",
                  impact_level: "low",
                  purpose: "Repeat explosive drive without extra joint impact.",
                },
              ],
            },
          ],
        },
        {
          date: "Wed",
          countdown_label: "D-30",
          day_type: "recovery",
          today_card: {
            headline: "Unload the system. No high-intent contact.",
            readiness_status: "pull_back",
            primary_warning: "If soreness is rising, keep this strictly recovery.",
            mindset_anchor: {
              intent: "Leave fresher than you arrived.",
              focus_cue: "Smooth breath, loose shoulders.",
            },
          },
          sessions: [],
        },
      ],
    },
  ],
  deterministic_support: {
    schema_version: "1.0",
    source: "demo",
    nutrition: {
      by_phase: {
        SPP: {
          meal_structure: "Protein each meal, carbs around hard sessions, lighter evening intake on recovery days.",
          protein_g_per_day: { min: 150, max: 175 },
          carbs_g_per_day: { min: 260, max: 340, note: "Bias higher around sparring and conditioning." },
          hydration_ml_per_day: { min: 3000, max: 3800 },
          fuel_timing: {
            pre: "Carb-led meal 2-3 hours before hard work.",
            post: "Protein plus carbs inside the first recovery window.",
          },
        },
      },
    },
    recovery: {
      by_phase: {
        SPP: {
          sleep_hours_target: [8, 9],
          core_strategies: ["Downshift after hard sparring", "Keep recovery sessions honest"],
          phase_focus: ["Absorb high-intensity work", "Protect Thursday technical quality"],
          fatigue_notes: ["If morning readiness drops twice, trim accessory volume first"],
        },
      },
    },
  },
  progression_notes:
    "Hard days stay hard, recovery days stay clean, and support work never steals quality from sparring.",
} satisfies StructuredPlan;

const demoCoachNotes = [
  "Hard days are spaced so the nervous system has 48h to recover before another high-intent session.",
  "Strength sits the day after hard sparring on purpose - it preserves the skill quality of the next sparring day.",
  "Conditioning is round-specific (3 x 5 here), so the energy systems trained match what the fight will demand.",
];

export default function DemoPlanPage() {
  return (
    <>
      <section className="hero-panel welcome-panel">
        <div className="hero-panel-copy welcome-copy">
          <p className="eyebrow">Demo plan</p>
          <h1 className="hero-title">This is what a generated camp looks like.</h1>
          <p className="overview-command-summary">
            A static sample from the same structured renderer used for athlete plans. No data is generated and nothing is saved.
          </p>
          <p className="muted welcome-context">
            When you build your own, the planner uses your fight date, training days, restrictions, and goals to shape every week.
          </p>
          <div className="hero-actions welcome-actions">
            <Link href="/onboarding" className="cta">
              Start Advanced Intake
            </Link>
            <Link href="/quick-build" className="secondary-button">
              Use Quick Build
            </Link>
            <Link href="/" className="ghost-button">
              Back to dashboard
            </Link>
          </div>
        </div>
      </section>

      <section className="support-panel">
        <div className="form-section-header">
          <p className="kicker">Camp context</p>
          <h2 className="form-section-title">Sample athlete setup</h2>
        </div>
        <div className="overview-detail-grid">
          <div className="overview-detail-column">
            <div className="review-detail-list overview-detail-list">
              {demoMeta.map((item) => (
                <div key={item.label} className="review-detail-row">
                  <div className="overview-detail-heading">
                    <p className="review-detail-label">{item.label}</p>
                  </div>
                  <p className="review-detail-value">{item.value}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="demo-structured-plan-section">
        <div className="form-section-header">
          <p className="kicker">Athlete view</p>
          <h2 className="form-section-title">Structured card renderer</h2>
          <p className="muted">Weeks open cleanly, session cards stay scannable, and detail blocks expand only when needed.</p>
        </div>
        <StructuredPlanRenderer plan={demoStructuredPlan} />
      </section>

      <section className="support-panel">
        <div className="form-section-header">
          <p className="kicker">Why this layout</p>
          <h2 className="form-section-title">Planner reasoning</h2>
        </div>
        <ul className="demo-coach-notes">
          {demoCoachNotes.map((note) => (
            <li key={note} className="muted">
              {note}
            </li>
          ))}
        </ul>
        <div className="hero-actions welcome-actions">
          <Link href="/onboarding" className="cta">
            Start Advanced Intake
          </Link>
          <Link href="/quick-build" className="secondary-button">
            Use Quick Build
          </Link>
        </div>
      </section>
    </>
  );
}
