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
// that encourages a rapid or dehydration-led weight cut. Numbers come from
// published position stands and studies:
// - ISSN position stands: protein (2017), caffeine (2021), creatine (2017),
//   beta-alanine (2015).
// - ACSM / Academy of Nutrition and Dietetics / Dietitians of Canada joint
//   position on nutrition and athletic performance (2016).
// - IOC consensus statements: REDs (2023) and concussion in sport (Amsterdam
//   2022, published 2023).
// - Combat-sport weight making: Reale, Slater & Burke (GSSI SSE #183; AIS
//   Making Weight guidelines).
// - Single studies: Mah 2011 (sleep extension), Drake 2013 (caffeine and
//   sleep), Parr 2014 (alcohol and muscle protein synthesis), Res 2012
//   (pre-sleep protein), Collins 2014 (neck strength), Roberts 2015 (cold
//   water immersion), Milewski 2014 (sleep and injury), Bosquet 2007 (taper
//   meta-analysis), Gabbett 2016 (training load spikes).
export const LOADING_TIPS: readonly LoadingTip[] = [
  { id: "training-load-spikes", category: "training", text: "Avoid big jumps in weekly load. Injury risk climbs when one week runs well above your recent four-week average." },
  { id: "training-chronic-base", category: "training", text: "A steady base protects you. Athletes who build load gradually handle hard weeks with fewer injuries than those who spike." },
  { id: "training-session-rpe", category: "training", text: "Rate each session 1–10 for effort and multiply by minutes. That simple load score shows when weeks are creeping up." },
  { id: "training-ramp-warm-up", category: "training", text: "Use a RAMP warm-up: raise heart rate, activate and mobilise key areas, then potentiate with a few fast, explosive reps." },
  { id: "training-separate-hard-days", category: "training", text: "Keep hard sparring and heavy lifting on separate days when possible, so both get your full intensity and focus." },
  { id: "training-power-fresh", category: "training", text: "Do speed and power work early in a session while you are fresh. Fatigue blunts the quality those drills need." },
  { id: "training-keep-lifting", category: "training", text: "Keep lifting through camp. One or two short, heavy strength sessions a week can hold strength while skill work leads." },
  { id: "training-defend-tired", category: "training", text: "Drill defence while tired. Late rounds test whether your guard and footwork still hold up under real fatigue." },

  { id: "recovery-alcohol", category: "recovery", text: "Skip alcohol after hard sessions. In one study it cut post-training muscle protein synthesis by up to 37%, even with protein." },
  { id: "recovery-pre-sleep-protein", category: "recovery", text: "A slow-digesting protein before bed, around 30–40 g from milk-based foods or a shake, supports overnight muscle repair." },
  { id: "recovery-cold-water", category: "recovery", text: "Save ice baths for when fast recovery matters. Regular cold immersion straight after lifting may blunt strength and muscle gains." },
  { id: "recovery-resting-hr", category: "recovery", text: "Check your morning resting heart rate. Several days well above your normal can be a sign of building fatigue." },
  { id: "recovery-deload", category: "recovery", text: "Plan a lighter week every few weeks. Letting fatigue drop is often when the fitness you have built finally shows." },
  { id: "recovery-easy-days", category: "recovery", text: "Easy days should feel easy. Light movement and mobility help you absorb hard training instead of adding fatigue." },
  { id: "recovery-soreness", category: "recovery", text: "If soreness keeps building across the week, flag it to your coach rather than pushing through every session." },

  { id: "sleep-extension", category: "sleep", text: "Stanford basketball players who slept about two hours more per night sprinted faster and shot roughly 9% more accurately." },
  { id: "sleep-caffeine-cutoff", category: "sleep", text: "Caffeine taken six hours before bed cut sleep by over an hour in one study. Set an early-afternoon caffeine cut-off." },
  { id: "sleep-target", category: "sleep", text: "Aim for seven to nine hours of sleep. During heavy camp blocks, many athletes perform better with even more." },
  { id: "sleep-consistent", category: "sleep", text: "Keep a consistent sleep and wake time, even on rest days. Regular timing supports reaction speed, mood and training quality." },
  { id: "sleep-nap", category: "sleep", text: "A 20–30 minute early-afternoon nap can top up alertness on double-session days without wrecking night sleep." },
  { id: "sleep-room", category: "sleep", text: "Keep your bedroom cool, dark and quiet. A slightly cool room, around 16–19°C, suits sleep for most people." },

  { id: "hydration-sweat-check", category: "hydration", text: "Weigh yourself before and after training. Each kilogram lost is roughly one litre of sweat you need to replace." },
  { id: "hydration-replace-volume", category: "hydration", text: "To rehydrate quickly, drink about 1.25–1.5 litres for every kilogram lost, with some salt, spread over a few hours." },
  { id: "hydration-sodium", category: "hydration", text: "Water alone rehydrates less well than fluids or meals with sodium, which help your body hold on to what you drink." },
  { id: "hydration-two-percent", category: "hydration", text: "Losing more than about 2% of body mass in sweat can start to dull endurance, power and decision-making." },
  { id: "hydration-colour", category: "hydration", text: "Pale-yellow urine is a simple everyday sign you are drinking enough. Darker urine is a cue to drink more." },
  { id: "hydration-heat", category: "hydration", text: "Fighting somewhere hot? Ten to fourteen days of training in heat helps you sweat earlier and lowers strain at the same workload." },

  { id: "nutrition-protein-daily", category: "nutrition", text: "Most training athletes do well on about 1.4–2.0 g of protein per kilogram of bodyweight each day." },
  { id: "nutrition-protein-spread", category: "nutrition", text: "Spread protein across the day: roughly 20–40 g per meal, every three to four hours, beats one huge dinner." },
  { id: "nutrition-carbs-match-load", category: "nutrition", text: "Match carbohydrates to the work: about 5–7 g per kilogram on moderate days and more on long, hard training days." },
  { id: "nutrition-pre-session", category: "nutrition", text: "Eat a familiar, carbohydrate-based meal two to four hours before training so you are fuelled without feeling heavy." },
  { id: "nutrition-refuel", category: "nutrition", text: "After hard sessions, pair protein with carbohydrates to restore muscle fuel, especially if you train again within a day." },
  { id: "nutrition-under-fuelling", category: "nutrition", text: "Under-eating for weeks can disrupt hormones, bones, mood and performance. Constant fatigue or frequent illness are warning signs." },
  { id: "nutrition-familiar", category: "nutrition", text: "Stick with foods you know agree with you during camp. Big diet changes close to a fight add risk." },

  { id: "weight-gradual", category: "weight_management", text: "Do most of your weight loss gradually through camp, so fight week only needs small, controlled changes." },
  { id: "weight-trend", category: "weight_management", text: "Weigh in at the same time each morning and track the weekly average. Single readings swing with water and food." },
  { id: "weight-same-day-limit", category: "weight_management", text: "With same-day weigh-ins, research advises against acute losses beyond about 5% of body mass, because recovery time is too short." },
  { id: "weight-not-dehydration", category: "weight_management", text: "Dehydration-only cuts are the riskiest route. Research favours small, planned reductions in gut content and stored carbohydrate instead." },
  { id: "weight-low-fibre", category: "weight_management", text: "A short low-fibre phase before weigh-in can lower gut content and scale weight without cutting energy. Plan it with a professional." },
  { id: "weight-rebuild", category: "weight_management", text: "After weigh-in, rebuild steadily with salty fluids and familiar carbohydrates rather than one huge meal that sits heavy." },
  { id: "weight-plan-early", category: "weight_management", text: "Agree your weight plan with a coach or qualified professional early, so fight week brings no surprises." },
  { id: "weight-no-crash", category: "weight_management", text: "Avoid crash diets and extreme dehydration. Strength, focus and safety all suffer when a cut is rushed." },

  { id: "supplements-caffeine-dose", category: "supplements", text: "Caffeine at about 3–6 mg per kilogram, taken roughly an hour before training, is well supported for power and endurance." },
  { id: "supplements-caffeine-low", category: "supplements", text: "You may not need much caffeine. Doses as low as 2 mg per kilogram can help, with fewer jitters and sleep problems." },
  { id: "supplements-creatine", category: "supplements", text: "Creatine monohydrate at 3–5 g daily is among the best-researched supplements for strength and power, and is well tolerated." },
  { id: "supplements-creatine-weight", category: "supplements", text: "Creatine often adds 1–2 kg of water weight in the first week. Factor that in if you are making weight." },
  { id: "supplements-beta-alanine", category: "supplements", text: "Beta-alanine, about 4–6 g daily for several weeks, may help hard efforts lasting one to four minutes. Skin tingling is common." },
  { id: "supplements-tested", category: "supplements", text: "If you compete under anti-doping rules, choose batch-tested supplements and check every product before using it." },
  { id: "supplements-basics-first", category: "supplements", text: "Supplements only fill gaps. Consistent meals, sleep and hydration do far more for your performance." },
  { id: "supplements-check-first", category: "supplements", text: "Check with a doctor or pharmacist before starting supplements, especially if you take any regular medication." },

  { id: "fight-week-taper-volume", category: "fight_week", text: "Taper research points to cutting training volume by roughly 40–60% over the final two weeks while keeping intensity high." },
  { id: "fight-week-keep-frequency", category: "fight_week", text: "Keep your training frequency during the taper. Shorter sessions, not skipped days, keep timing and feel sharp." },
  { id: "fight-week-nothing-new", category: "fight_week", text: "Nothing new in fight week: no new foods, supplements, gear or techniques. Familiar routines remove surprises." },
  { id: "fight-week-rehearse", category: "fight_week", text: "Rehearse your fight-day routine, from meals to warm-up timing, so nothing on the night feels new." },
  { id: "fight-week-sleep-early", category: "fight_week", text: "Bank good sleep in the nights before the fight. Nerves often disrupt the final night, so earlier nights matter most." },
  { id: "fight-week-pre-fight-meal", category: "fight_week", text: "Eat your main pre-fight meal three to four hours out, built on carbohydrates you know sit well, then top up lightly." },
  { id: "fight-week-logistics", category: "fight_week", text: "Sort travel, meals and weigh-in logistics early in fight week so you can focus on rest and preparation." },
  { id: "fight-week-restless", category: "fight_week", text: "Feeling restless during a taper is normal. Trust the work you have already banked in camp." },

  { id: "injury-stop-signal", category: "injury_safety", text: "Pain that is sharp, worsening or changes how you move is a signal to stop and get it checked." },
  { id: "injury-work-around", category: "injury_safety", text: "Work around an injury, not through it. Train what you safely can while the affected area is protected." },
  { id: "injury-professional-first", category: "injury_safety", text: "Follow guidance from your doctor or physio first. Your training plan should fit around their advice." },
  { id: "injury-concussion-steps", category: "injury_safety", text: "After a suspected concussion, return through graded steps of at least 24 hours each, with medical clearance before any contact." },
  { id: "injury-report-early", category: "injury_safety", text: "Tell your coach about new pain, dizziness or unusual headaches straight away. Early reporting keeps small issues small." },
  { id: "injury-neck-strength", category: "injury_safety", text: "Train your neck. In one study, each extra pound of neck strength was linked to about 5% lower concussion odds." },
  { id: "injury-sleep-link", category: "injury_safety", text: "Young athletes sleeping under eight hours were about 1.7 times more likely to get injured in one study." },
  { id: "injury-gradual-return", category: "injury_safety", text: "Ease back into contact gradually after an injury, and stop the session if symptoms return." },

  { id: "combat-breathing", category: "combat_performance", text: "Breathing control under pressure starts in training. Practise relaxed exhales during hard rounds and between exchanges." },
  { id: "combat-basics", category: "combat_performance", text: "Footwork and defence win rounds too. Sharp, repeatable basics often decide close fights." },
  { id: "combat-format", category: "combat_performance", text: "Match your conditioning to your fight format. Train the round lengths and rest periods you will actually face." },
  { id: "combat-potentiate", category: "combat_performance", text: "A few explosive jumps or hard pad strikes before a round can briefly sharpen power. Allow a few minutes to recover first." },
  { id: "combat-film", category: "combat_performance", text: "Review sparring footage each week. Fixing one repeated mistake is often worth more than a dozen extra rounds." },
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
