import type { PlanRequest } from "./types";

export type LoadingTipCategory =
  | "training"
  | "recovery"
  | "sleep"
  | "hydration"
  | "nutrition"
  | "weight_management"
  | "supplements"
  | "fight_week"
  | "injury_safety"
  | "combat_performance";

export type LoadingTip = {
  id: string;
  category: LoadingTipCategory;
  text: string;
};

// Plain, general guidance only: no diagnosis, no treatment claims, and nothing
// that encourages a rapid or dehydration-led weight cut.
export const LOADING_TIPS: readonly LoadingTip[] = [
  { id: "training-quality", category: "training", text: "Quality beats volume. Finish hard sessions with crisp technique rather than grinding out sloppy extra rounds." },
  { id: "training-separate-hard-days", category: "training", text: "Keep your hardest sparring and heaviest lifting on separate days when you can, so both get your best effort." },
  { id: "training-warm-up", category: "training", text: "Warm up properly before every session: raise your heart rate, mobilise hips and shoulders, then build intensity gradually." },
  { id: "training-log", category: "training", text: "Log how each session felt. Patterns in energy and soreness help you and your coach adjust training early." },

  { id: "recovery-easy-days", category: "recovery", text: "Easy days should feel easy. Light movement and mobility help you absorb hard training instead of adding fatigue." },
  { id: "recovery-rest-days", category: "recovery", text: "Plan your rest days like training days. Recovery is when your body adapts to the work you have done." },
  { id: "recovery-cooldown", category: "recovery", text: "A short cooldown of easy movement and slow breathing after hard rounds can help you settle before the next session." },
  { id: "recovery-soreness", category: "recovery", text: "If soreness keeps building across the week, flag it to your coach rather than pushing through every session." },

  { id: "sleep-consistent", category: "sleep", text: "Aim for a consistent sleep and wake time. Regular sleep supports reaction time, mood and training quality." },
  { id: "sleep-wind-down", category: "sleep", text: "Dim screens and bright lights in the hour before bed to make falling asleep easier after evening training." },
  { id: "sleep-nap", category: "sleep", text: "A short daytime nap can top up energy on double-session days. Keep it brief so night sleep stays solid." },
  { id: "sleep-room", category: "sleep", text: "Keep your bedroom cool, dark and quiet. Small changes to your sleep space can make a real difference." },

  { id: "hydration-steady", category: "hydration", text: "Sip water steadily through the day instead of drinking large amounts at once just before training." },
  { id: "hydration-colour", category: "hydration", text: "Pale-yellow urine is a simple everyday sign you are drinking enough. Darker urine is a cue to drink more." },
  { id: "hydration-salts", category: "hydration", text: "On long or hot sessions, replacing salts as well as fluid can help you stay sharp in later rounds." },
  { id: "hydration-sweat-check", category: "hydration", text: "Weigh yourself before and after hard sessions to learn roughly how much fluid you lose when you train." },

  { id: "nutrition-plate", category: "nutrition", text: "Build each meal around a protein source, colourful vegetables and a carbohydrate portion that fits your training load." },
  { id: "nutrition-pre-session", category: "nutrition", text: "Eat a familiar meal or snack a few hours before training so you have fuel without feeling heavy." },
  { id: "nutrition-refuel", category: "nutrition", text: "After hard sessions, a meal with protein and carbohydrates helps you refuel for the next day of camp." },
  { id: "nutrition-familiar", category: "nutrition", text: "Stick with foods you know agree with you during camp. Big diet changes close to a fight add risk." },

  { id: "weight-gradual", category: "weight_management", text: "Gradual weight change through camp is easier on performance than relying on a large cut in the final days." },
  { id: "weight-trend", category: "weight_management", text: "Weigh in at the same time each morning. Trends over a week matter more than any single reading." },
  { id: "weight-plan-early", category: "weight_management", text: "Agree your weight plan with a coach or qualified professional early, so fight week brings no surprises." },
  { id: "weight-no-crash", category: "weight_management", text: "Avoid crash diets and extreme dehydration. Strength, focus and safety all suffer when a cut is rushed." },

  { id: "supplements-basics-first", category: "supplements", text: "Supplements only fill gaps. Consistent meals, sleep and hydration do far more for your performance." },
  { id: "supplements-tested", category: "supplements", text: "If you compete under anti-doping rules, choose batch-tested supplements and check every product before using it." },
  { id: "supplements-nothing-new", category: "supplements", text: "Try any new supplement during normal training, never for the first time in fight week or on fight night." },
  { id: "supplements-check-first", category: "supplements", text: "Check with a doctor or pharmacist before starting supplements, especially if you take any regular medication." },

  { id: "fight-week-sharp", category: "fight_week", text: "Fight week is for staying sharp, not getting fitter. Shorter, crisper sessions keep you fresh for the fight." },
  { id: "fight-week-rehearse", category: "fight_week", text: "Rehearse your fight-day routine, from meals to warm-up timing, so nothing on the night feels new." },
  { id: "fight-week-taper-intensity", category: "fight_week", text: "As training volume drops in the taper, keep some speed and intensity so you stay sharp and confident." },
  { id: "fight-week-logistics", category: "fight_week", text: "Sort travel, meals and weigh-in logistics early in fight week so you can focus on rest and preparation." },
  { id: "fight-week-restless", category: "fight_week", text: "Feeling restless during a taper is normal. Trust the work you have already banked in camp." },

  { id: "injury-stop-signal", category: "injury_safety", text: "Pain that is sharp, worsening or changes how you move is a signal to stop and get it checked." },
  { id: "injury-work-around", category: "injury_safety", text: "Work around an injury, not through it. Train what you safely can while the affected area is protected." },
  { id: "injury-professional-first", category: "injury_safety", text: "Follow guidance from your doctor or physio first. Your training plan should fit around their advice." },
  { id: "injury-gradual-return", category: "injury_safety", text: "Ease back into contact gradually after an injury, and stop the session if symptoms return." },
  { id: "injury-report-early", category: "injury_safety", text: "Tell your coach about new pain, dizziness or unusual headaches straight away. Early reporting keeps small issues small." },

  { id: "combat-breathing", category: "combat_performance", text: "Breathing control under pressure starts in training. Practise relaxed exhales during hard rounds and between exchanges." },
  { id: "combat-basics", category: "combat_performance", text: "Footwork and defence win rounds too. Sharp, repeatable basics often decide close fights." },
  { id: "combat-format", category: "combat_performance", text: "Match your conditioning to your fight format. Train the round lengths and rest periods you will actually face." },
  { id: "combat-shadowboxing", category: "combat_performance", text: "Shadowbox with a clear goal for each round. It builds sharper habits than simply moving through combinations." },
  { id: "combat-visualise", category: "combat_performance", text: "Mental rehearsal helps. Picture your game plan, key adjustments and how you will respond under pressure." },
];

export type LoadingTipContext = "injury" | "weight" | "fight_week";

const CONTEXT_CATEGORIES: Record<LoadingTipContext, LoadingTipCategory[]> = {
  injury: ["injury_safety", "recovery", "sleep"],
  weight: ["weight_management", "nutrition", "hydration"],
  fight_week: ["fight_week", "recovery", "hydration"],
};

const GENERAL_CATEGORIES: LoadingTipCategory[] = [
  "combat_performance",
  "training",
  "recovery",
  "sleep",
  "hydration",
  "nutrition",
  "supplements",
];

const FIGHT_WEEK_WINDOW_DAYS = 14;
const DAY_MS = 86_400_000;
const NO_INJURY_TEXT = /^(none|no|nil|n\/?a|nothing|-+)\.?$/i;

function hasActiveInjury(intake: PlanRequest): boolean {
  const injuries = typeof intake.injuries === "string" ? intake.injuries.trim() : "";
  if (injuries && !NO_INJURY_TEXT.test(injuries)) return true;
  const guided = [...(intake.guided_injuries ?? []), intake.guided_injury ?? null];
  return guided.some((injury) => Boolean(injury?.area?.trim() || injury?.injury_type?.trim()));
}

function hasWeightGoal(intake: PlanRequest): boolean {
  if (intake.primary_goal === "weight_cut" || (intake.key_goals ?? []).includes("weight_cut")) return true;
  const camp = intake.shared_camp_context;
  const current = camp?.current_weight_kg;
  const target = camp?.target_weight_kg;
  return typeof current === "number" && typeof target === "number" && target > 0 && current > target;
}

function isFightClose(intake: PlanRequest, nowMs: number): boolean {
  if (intake.no_scheduled_fight || !intake.fight_date) return false;
  const fightMs = Date.parse(`${intake.fight_date.slice(0, 10)}T00:00:00Z`);
  if (!Number.isFinite(fightMs)) return false;
  const today = new Date(nowMs);
  const todayMs = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
  const days = Math.round((fightMs - todayMs) / DAY_MS);
  return days >= 0 && days <= FIGHT_WEEK_WINDOW_DAYS;
}

export function resolveLoadingTipContexts(
  intake: PlanRequest | null | undefined,
  nowMs: number = Date.now(),
): LoadingTipContext[] {
  if (!intake) return [];
  const contexts: LoadingTipContext[] = [];
  if (hasActiveInjury(intake)) contexts.push("injury");
  if (hasWeightGoal(intake)) contexts.push("weight");
  if (isFightClose(intake, nowMs)) contexts.push("fight_week");
  return contexts;
}

// Tips drawn from the athlete's own intake, or the general combat-performance
// bank when nothing in the intake points somewhere more specific.
export function selectLoadingTips(
  intake: PlanRequest | null | undefined,
  nowMs: number = Date.now(),
): LoadingTip[] {
  const contexts = resolveLoadingTipContexts(intake, nowMs);
  const categories = new Set(
    contexts.length > 0 ? contexts.flatMap((context) => CONTEXT_CATEGORIES[context]) : GENERAL_CATEGORIES,
  );
  return LOADING_TIPS.filter((tip) => categories.has(tip.category));
}

// A shuffled pass through the pool: every tip shows once before any repeats,
// and a fresh pass never opens with the tip that closed the previous one.
export function buildTipDeck(
  pool: readonly LoadingTip[],
  random: () => number = Math.random,
  avoidFirstId: string | null = null,
): LoadingTip[] {
  const deck = [...pool];
  for (let i = deck.length - 1; i > 0; i -= 1) {
    const j = Math.floor(random() * (i + 1));
    [deck[i], deck[j]] = [deck[j], deck[i]];
  }
  if (deck.length > 1 && deck[0].id === avoidFirstId) {
    [deck[0], deck[1]] = [deck[1], deck[0]];
  }
  return deck;
}
