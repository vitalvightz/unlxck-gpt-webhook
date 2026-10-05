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
  { id: "training-nordics", category: "training", text: "Add Nordic hamstring curls. Programmes that included them cut hamstring injuries by up to about half in a large meta-analysis." },
  { id: "training-plyo-quality", category: "training", text: "Keep jump and plyometric work low in volume and high in quality. End the set once height or snap drops." },
  { id: "training-aerobic-base", category: "training", text: "Your aerobic base drives recovery between rounds. Steady, conversational-pace work still earns its place in a fight camp." },
  { id: "training-intervals-specific", category: "training", text: "Build intervals around your sport's work-to-rest pattern, like short bursts with brief recoveries, rather than random circuits." },
  { id: "training-technical-rounds", category: "training", text: "Plenty of skill is built in controlled, technical rounds. Save truly hard sparring for what you can recover from." },
  { id: "training-one-variable", category: "training", text: "Progress one thing at a time: add rounds, intensity or weight, but not all three in the same week." },
  { id: "training-slow-first", category: "training", text: "Groove new techniques slowly and cleanly first, then add speed, resistance and a live partner in stages." },
  { id: "training-grip", category: "training", text: "Grapplers: train grip endurance directly with towel hangs and gi holds. Forearms often fail before the rest of you." },
  { id: "training-rotation", category: "training", text: "Punching power starts from the ground. Train hips and trunk with rotational throws and anti-rotation work, not just arms." },
  { id: "training-single-leg", category: "training", text: "Include single-leg work like split squats. You fight in staggered stances, so balanced leg strength carries over well." },
  { id: "training-rest-heavy-sets", category: "training", text: "Rest two to three minutes between heavy strength sets. Short rests turn strength work into conditioning and lower quality." },
  { id: "training-consistency", category: "training", text: "Consistency beats heroics. Hitting most planned sessions for months does more than one brutal week followed by forced rest." },
  { id: "training-retest", category: "training", text: "Retest a few simple markers every few weeks, like jump height or a timed interval, to see whether training is working." },
  { id: "training-mobility", category: "training", text: "Short daily mobility for hips, upper back and ankles keeps stances and kicks comfortable as training load rises." },

  { id: "recovery-alcohol", category: "recovery", text: "Skip alcohol after hard sessions. In one study it cut post-training muscle protein synthesis by up to 37%, even with protein." },
  { id: "recovery-pre-sleep-protein", category: "recovery", text: "A slow-digesting protein before bed, around 30–40 g from milk-based foods or a shake, supports overnight muscle repair." },
  { id: "recovery-cold-water", category: "recovery", text: "Save ice baths for when fast recovery matters. Regular cold immersion straight after lifting may blunt strength and muscle gains." },
  { id: "recovery-resting-hr", category: "recovery", text: "Check your morning resting heart rate. Several days well above your normal can be a sign of building fatigue." },
  { id: "recovery-deload", category: "recovery", text: "Plan a lighter week every few weeks. Letting fatigue drop is often when the fitness you have built finally shows." },
  { id: "recovery-easy-days", category: "recovery", text: "Easy days should feel easy. Light movement and mobility help you absorb hard training instead of adding fatigue." },
  { id: "recovery-soreness", category: "recovery", text: "If soreness keeps building across the week, flag it to your coach rather than pushing through every session." },
  { id: "recovery-sleep-first", category: "recovery", text: "Sleep is the recovery tool with the strongest evidence. Sort it out before spending money on recovery gadgets." },
  { id: "recovery-cooldown", category: "recovery", text: "A short cooldown of easy movement and slow breathing after hard rounds helps you settle before the next session." },
  { id: "recovery-massage", category: "recovery", text: "Massage and foam rolling can reduce how sore you feel. They are useful extras, not replacements for sleep and food." },
  { id: "recovery-compression", category: "recovery", text: "Compression garments may ease soreness for some athletes. Think of them as optional extras rather than essentials." },
  { id: "recovery-48-hours", category: "recovery", text: "Where your schedule allows, leave around 48 hours between very hard sessions that hammer the same muscle groups." },
  { id: "recovery-double-days", category: "recovery", text: "Training twice in a day? Eat carbohydrates and protein soon after the first session so you are refuelled in time." },
  { id: "recovery-overreaching-signs", category: "recovery", text: "Irritability, poor sleep and fading motivation can be early signs of overreaching. Tell your coach before performance drops." },
  { id: "recovery-life-stress", category: "recovery", text: "Life stress counts as load. Exams, work pressure or family strain can reduce how much training you can absorb." },
  { id: "recovery-illness-check", category: "recovery", text: "Feeling ill? Mild head-cold symptoms may allow light training. Fever, chest symptoms or body aches mean rest and medical advice." },
  { id: "recovery-walks", category: "recovery", text: "Easy walks on rest days keep blood flowing and lift mood without adding meaningful fatigue." },
  { id: "recovery-nasal-breathing", category: "recovery", text: "A few minutes of slow nasal breathing after training can help you shift out of fight-or-flight mode." },
  { id: "recovery-daily-check-in", category: "recovery", text: "Rate sleep, soreness, mood and energy from 1 to 5 each morning. Falling scores flag building fatigue early." },

  { id: "sleep-extension", category: "sleep", text: "Stanford basketball players who slept about two hours more per night sprinted faster and shot roughly 9% more accurately." },
  { id: "sleep-caffeine-cutoff", category: "sleep", text: "Caffeine taken six hours before bed cut sleep by over an hour in one study. Set an early-afternoon caffeine cut-off." },
  { id: "sleep-target", category: "sleep", text: "Aim for seven to nine hours of sleep. During heavy camp blocks, many athletes perform better with even more." },
  { id: "sleep-consistent", category: "sleep", text: "Keep a consistent sleep and wake time, even on rest days. Regular timing supports reaction speed, mood and training quality." },
  { id: "sleep-nap", category: "sleep", text: "A 20–30 minute early-afternoon nap can top up alertness on double-session days without wrecking night sleep." },
  { id: "sleep-room", category: "sleep", text: "Keep your bedroom cool, dark and quiet. A slightly cool room, around 16–19°C, suits sleep for most people." },
  { id: "sleep-alcohol", category: "sleep", text: "Alcohol may make you drowsy, but it fragments sleep later in the night and lowers its quality." },
  { id: "sleep-morning-light", category: "sleep", text: "Get bright outdoor light soon after waking. Morning light helps anchor your body clock and makes evening sleep easier." },
  { id: "sleep-phone", category: "sleep", text: "Put your phone away 30–60 minutes before bed. Late scrolling keeps your brain switched on when it should be winding down." },
  { id: "sleep-wind-down", category: "sleep", text: "After late sessions, use a set wind-down routine: shower, light meal, dim lights. It helps body and mind settle." },
  { id: "sleep-late-meals", category: "sleep", text: "Finish big or spicy meals two to three hours before bed where possible. A heavy stomach makes sleep lighter." },
  { id: "sleep-debt", category: "sleep", text: "Missed sleep adds up. Several short nights in a row can slow reaction time even when you feel fine." },
  { id: "sleep-to-do-list", category: "sleep", text: "Racing mind at night? Write tomorrow's to-do list before bed. In one study it helped people fall asleep faster." },
  { id: "sleep-travel-kit", category: "sleep", text: "Pack a sleep kit for away fights: eye mask, earplugs and your usual pillowcase make strange rooms feel familiar." },
  { id: "sleep-weekend", category: "sleep", text: "Big lie-ins shift your body clock. Keep weekend wake times within about an hour of your weekday ones." },
  { id: "sleep-late-naps", category: "sleep", text: "Avoid naps late in the afternoon or evening. They can make it harder to fall asleep at your usual time." },

  { id: "hydration-sweat-check", category: "hydration", text: "Weigh yourself before and after training. Each kilogram lost is roughly one litre of sweat you need to replace." },
  { id: "hydration-replace-volume", category: "hydration", text: "To rehydrate quickly, drink about 1.25–1.5 litres for every kilogram lost, with some salt, spread over a few hours." },
  { id: "hydration-sodium", category: "hydration", text: "Water alone rehydrates less well than fluids or meals with sodium, which help your body hold on to what you drink." },
  { id: "hydration-two-percent", category: "hydration", text: "Losing more than about 2% of body mass in sweat can start to dull endurance, power and decision-making." },
  { id: "hydration-colour", category: "hydration", text: "Pale-yellow urine is a simple everyday sign you are drinking enough. Darker urine is a cue to drink more." },
  { id: "hydration-heat", category: "hydration", text: "Fighting somewhere hot? Ten to fourteen days of training in heat helps you sweat earlier and lowers strain at the same workload." },
  { id: "hydration-sweat-varies", category: "hydration", text: "Sweat rates vary hugely between athletes, from under half a litre to over two litres an hour. Learn your own." },
  { id: "hydration-salty-sweater", category: "hydration", text: "White salt marks on your kit or stinging eyes suggest salty sweat. You may need more sodium on hard days." },
  { id: "hydration-over-drinking", category: "hydration", text: "Do not force fluids far beyond thirst for hours. Drinking much more than you sweat can dangerously dilute blood sodium." },
  { id: "hydration-pre-session", category: "hydration", text: "Start sessions hydrated: around 5–7 ml of fluid per kilogram of bodyweight roughly four hours before training is a common guide." },
  { id: "hydration-cool-drinks", category: "hydration", text: "Cool drinks are easier to drink in the heat and can help keep body temperature down during long sessions." },
  { id: "hydration-food-counts", category: "hydration", text: "Food supplies a good share of your daily water. Fruit, vegetables, soups and yoghurt all count." },
  { id: "hydration-coffee", category: "hydration", text: "Moderate coffee does not meaningfully dehydrate regular drinkers. It still counts towards your daily fluid intake." },
  { id: "hydration-milk", category: "hydration", text: "Milk makes a strong recovery drink: it supplies fluid, sodium, protein and carbohydrate, and the body retains it well." },
  { id: "hydration-marked-bottle", category: "hydration", text: "Carry a marked bottle through the day. Seeing exactly how much you have drunk beats guessing." },
  { id: "hydration-hot-gyms", category: "hydration", text: "In hot gyms, schedule hard sessions for cooler hours where you can and plan extra drink breaks." },

  { id: "nutrition-protein-daily", category: "nutrition", text: "Most training athletes do well on about 1.4–2.0 g of protein per kilogram of bodyweight each day." },
  { id: "nutrition-protein-spread", category: "nutrition", text: "Spread protein across the day: roughly 20–40 g per meal, every three to four hours, beats one huge dinner." },
  { id: "nutrition-carbs-match-load", category: "nutrition", text: "Match carbohydrates to the work: about 5–7 g per kilogram on moderate days and more on long, hard training days." },
  { id: "nutrition-pre-session", category: "nutrition", text: "Eat a familiar, carbohydrate-based meal two to four hours before training so you are fuelled without feeling heavy." },
  { id: "nutrition-refuel", category: "nutrition", text: "After hard sessions, pair protein with carbohydrates to restore muscle fuel, especially if you train again within a day." },
  { id: "nutrition-under-fuelling", category: "nutrition", text: "Under-eating for weeks can disrupt hormones, bones, mood and performance. Constant fatigue or frequent illness are warning signs." },
  { id: "nutrition-familiar", category: "nutrition", text: "Stick with foods you know agree with you during camp. Big diet changes close to a fight add risk." },
  { id: "nutrition-leucine", category: "nutrition", text: "Choose protein sources rich in leucine, such as dairy, eggs, meat or fish, to best switch on muscle building." },
  { id: "nutrition-plant-protein", category: "nutrition", text: "Plant-based? Combine beans, lentils, tofu and grains, and aim slightly higher on total daily protein." },
  { id: "nutrition-periodise-carbs", category: "nutrition", text: "Carbohydrate needs change day to day. Eat more around hard or double sessions and less on easy or rest days." },
  { id: "nutrition-pre-training-fibre-fat", category: "nutrition", text: "Keep high-fibre and high-fat foods lighter just before training. They digest slowly and can upset your stomach." },
  { id: "nutrition-iron", category: "nutrition", text: "Low iron stores can cause fatigue even without anaemia. If you feel drained for weeks, ask a doctor about blood tests." },
  { id: "nutrition-vitamin-d", category: "nutrition", text: "Vitamin D is often low in winter, especially for indoor athletes. A blood test shows whether you need more." },
  { id: "nutrition-colour", category: "nutrition", text: "Eat a range of coloured fruit and vegetables daily. Variety covers the micronutrients that support immunity and recovery." },
  { id: "nutrition-snacks-ready", category: "nutrition", text: "Keep training-friendly snacks on hand, such as yoghurt, fruit, rice cakes or milk, so recovery never depends on luck." },
  { id: "nutrition-bones", category: "nutrition", text: "Calcium and vitamin D support bone health, which matters most for athletes who train heavily or manage their weight." },
  { id: "nutrition-early-sessions", category: "nutrition", text: "Training early? Even a small carbohydrate snack like a banana or toast beats starting a hard session completely empty." },
  { id: "nutrition-batch-cook", category: "nutrition", text: "Batch-cook protein and carbohydrates twice a week. Ready meals make it far easier to hit targets in busy camp weeks." },
  { id: "nutrition-weight-trend-fuel", category: "nutrition", text: "Your weight trend shows whether intake matches training. Steady, unplanned loss during camp often means you are under-fuelling." },
  { id: "nutrition-sugar-timing", category: "nutrition", text: "Sugary drinks and snacks have a place during and after long, hard sessions, when quick fuel genuinely helps." },

  { id: "weight-gradual", category: "weight_management", text: "Do most of your weight loss gradually through camp, so fight week only needs small, controlled changes." },
  { id: "weight-trend", category: "weight_management", text: "Weigh in at the same time each morning and track the weekly average. Single readings swing with water and food." },
  { id: "weight-same-day-limit", category: "weight_management", text: "With same-day weigh-ins, research advises against acute losses beyond about 5% of body mass, because recovery time is too short." },
  { id: "weight-not-dehydration", category: "weight_management", text: "Dehydration-only cuts are the riskiest route. Research favours small, planned reductions in gut content and stored carbohydrate instead." },
  { id: "weight-low-fibre", category: "weight_management", text: "A short low-fibre phase before weigh-in can lower gut content and scale weight without cutting energy. Plan it with a professional." },
  { id: "weight-rebuild", category: "weight_management", text: "After weigh-in, rebuild steadily with salty fluids and familiar carbohydrates rather than one huge meal that sits heavy." },
  { id: "weight-plan-early", category: "weight_management", text: "Agree your weight plan with a coach or qualified professional early, so fight week brings no surprises." },
  { id: "weight-no-crash", category: "weight_management", text: "Avoid crash diets and extreme dehydration. Strength, focus and safety all suffer when a cut is rushed." },
  { id: "weight-division-choice", category: "weight_management", text: "The bigger the gap between walk-around weight and your class, the harder fight week becomes. Choose your division with that in mind." },
  { id: "weight-weekly-rate", category: "weight_management", text: "Losing roughly 0.5–1% of body mass per week during camp helps protect strength and training quality." },
  { id: "weight-protein-in-deficit", category: "weight_management", text: "In an energy deficit, keep protein high. It helps preserve muscle while body fat comes down." },
  { id: "weight-fuel-hard-sessions", category: "weight_management", text: "Avoid long fasts before hard sessions while dieting. Under-fuelled training lowers quality and makes technique sloppy." },
  { id: "weight-early-drop", category: "weight_management", text: "Fast scale drops in the first days of a diet are mostly water and stored carbohydrate, not fat. Judge progress over weeks." },
  { id: "weight-rehearse-weigh-in", category: "weight_management", text: "Rehearse weigh-in conditions: same scale type, time of day and clothing, so the official reading holds no surprises." },
  { id: "weight-weigh-in-format", category: "weight_management", text: "Evening-before weigh-ins leave more recovery time than same-day ones. Build your whole weight plan around the format." },
  { id: "weight-stop-signals", category: "weight_management", text: "Severe hunger, dizziness, low mood or confusion during a cut are signals to stop and get help." },
  { id: "weight-post-fight", category: "weight_management", text: "Plan post-fight eating too. A steady return to normal meals avoids the big rebound that makes the next camp harder." },
  { id: "weight-track-food", category: "weight_management", text: "Track your food for a couple of weeks early in camp. It shows where calories hide better than any guess." },
  { id: "weight-young-athletes", category: "weight_management", text: "Young athletes who are still growing should not cut weight aggressively. Focus on performance and let weight follow." },

  { id: "supplements-caffeine-dose", category: "supplements", text: "Caffeine at about 3–6 mg per kilogram, taken roughly an hour before training, is well supported for power and endurance." },
  { id: "supplements-caffeine-low", category: "supplements", text: "You may not need much caffeine. Doses as low as 2 mg per kilogram can help, with fewer jitters and sleep problems." },
  { id: "supplements-creatine", category: "supplements", text: "Creatine monohydrate at 3–5 g daily is among the best-researched supplements for strength and power, and is well tolerated." },
  { id: "supplements-creatine-weight", category: "supplements", text: "Creatine often adds 1–2 kg of water weight in the first week. Factor that in if you are making weight." },
  { id: "supplements-beta-alanine", category: "supplements", text: "Beta-alanine, about 4–6 g daily for several weeks, may help hard efforts lasting one to four minutes. Skin tingling is common." },
  { id: "supplements-tested", category: "supplements", text: "If you compete under anti-doping rules, choose batch-tested supplements and check every product before using it." },
  { id: "supplements-basics-first", category: "supplements", text: "Supplements only fill gaps. Consistent meals, sleep and hydration do far more for your performance." },
  { id: "supplements-check-first", category: "supplements", text: "Check with a doctor or pharmacist before starting supplements, especially if you take any regular medication." },
  { id: "supplements-bicarbonate", category: "supplements", text: "Sodium bicarbonate around 0.3 g per kilogram may help repeated hard efforts, but stomach upset is common. Test it in training." },
  { id: "supplements-nitrate", category: "supplements", text: "Beetroot juice giving about 300–600 mg of nitrate, two to three hours before exercise, may help some endurance-type efforts." },
  { id: "supplements-vitamin-d-test", category: "supplements", text: "Vitamin D supplements mainly help when your levels are low. A blood test beats guessing." },
  { id: "supplements-iron-test", category: "supplements", text: "Do not take iron supplements without a blood test first. Too much iron can be harmful." },
  { id: "supplements-protein-powder", category: "supplements", text: "Protein powder is just convenient food. It helps when meals are hard to arrange, but it is not essential." },
  { id: "supplements-caffeine-trial", category: "supplements", text: "Caffeine responses vary by person and habit. Trial your dose in training before relying on it on fight night." },
  { id: "supplements-pre-workouts", category: "supplements", text: "Pre-workout blends often hide big caffeine doses and untested ingredients. Read labels closely and prefer batch-tested products." },
  { id: "supplements-melatonin", category: "supplements", text: "Melatonin may help shift your body clock after long-haul travel. Get advice first, as rules differ between countries." },
  { id: "supplements-creatine-timing", category: "supplements", text: "Creatine works over weeks by slowly topping up muscle stores, so the time of day you take it matters little." },
  { id: "supplements-electrolytes", category: "supplements", text: "Electrolyte tablets suit long or hot sessions and heavy sweaters. For short sessions, water and normal meals usually cover it." },
  { id: "supplements-nothing-new", category: "supplements", text: "Try any new supplement during normal training, never for the first time in fight week or on fight night." },

  { id: "fight-week-taper-volume", category: "fight_week", text: "Taper research points to cutting training volume by roughly 40–60% over the final two weeks while keeping intensity high." },
  { id: "fight-week-keep-frequency", category: "fight_week", text: "Keep your training frequency during the taper. Shorter sessions, not skipped days, keep timing and feel sharp." },
  { id: "fight-week-nothing-new", category: "fight_week", text: "Nothing new in fight week: no new foods, supplements, gear or techniques. Familiar routines remove surprises." },
  { id: "fight-week-rehearse", category: "fight_week", text: "Rehearse your fight-day routine, from meals to warm-up timing, so nothing on the night feels new." },
  { id: "fight-week-sleep-early", category: "fight_week", text: "Bank good sleep in the nights before the fight. Nerves often disrupt the final night, so earlier nights matter most." },
  { id: "fight-week-pre-fight-meal", category: "fight_week", text: "Eat your main pre-fight meal three to four hours out, built on carbohydrates you know sit well, then top up lightly." },
  { id: "fight-week-logistics", category: "fight_week", text: "Sort travel, meals and weigh-in logistics early in fight week so you can focus on rest and preparation." },
  { id: "fight-week-restless", category: "fight_week", text: "Feeling restless during a taper is normal. Trust the work you have already banked in camp." },
  { id: "fight-week-time-zones", category: "fight_week", text: "Travelling across time zones? Your body clock shifts about one day per zone, so arrive early when you can." },
  { id: "fight-week-travel-light", category: "fight_week", text: "Flying east, seek morning light and avoid late light; flying west, do the opposite. Timed light speeds adjustment." },
  { id: "fight-week-travel-illness", category: "fight_week", text: "Long-haul travel raises illness risk. Wash hands often, keep away from sick people and protect your sleep." },
  { id: "fight-week-weigh-in-plan", category: "fight_week", text: "Write your weigh-in plan out hour by hour, including recovery food and drink, so stress does not make decisions." },
  { id: "fight-week-protect-final-days", category: "fight_week", text: "Fit media, tickets and family duties into early fight week. Protect the final days for rest and routine." },
  { id: "fight-week-re-warm", category: "fight_week", text: "Know your fight-night warm-up timing, and keep a short re-warm routine ready in case the card runs late." },
  { id: "fight-week-visualise", category: "fight_week", text: "Visualise your walkout and first round in detail. Familiarity with the moment can take the edge off nerves." },
  { id: "fight-week-fuel", category: "fight_week", text: "Unless your weight plan says otherwise, base meals on carbohydrates in the final days so your muscles are fully fuelled." },
  { id: "fight-week-no-hard-sparring", category: "fight_week", text: "Skip hard sparring in the final week. The injury risk outweighs any fitness you could still gain." },
  { id: "fight-week-gear-check", category: "fight_week", text: "Check gloves, wraps, mouthguard and kit early in fight week, and pack spares so nothing derails your routine." },
  { id: "fight-week-normal-routine", category: "fight_week", text: "Keep bed, wake and meal times normal in fight week. Big routine changes can unsettle sleep and digestion." },

  { id: "injury-stop-signal", category: "injury_safety", text: "Pain that is sharp, worsening or changes how you move is a signal to stop and get it checked." },
  { id: "injury-work-around", category: "injury_safety", text: "Work around an injury, not through it. Train what you safely can while the affected area is protected." },
  { id: "injury-professional-first", category: "injury_safety", text: "Follow guidance from your doctor or physio first. Your training plan should fit around their advice." },
  { id: "injury-concussion-steps", category: "injury_safety", text: "After a suspected concussion, return through graded steps of at least 24 hours each, with medical clearance before any contact." },
  { id: "injury-report-early", category: "injury_safety", text: "Tell your coach about new pain, dizziness or unusual headaches straight away. Early reporting keeps small issues small." },
  { id: "injury-neck-strength", category: "injury_safety", text: "Train your neck. In one study, each extra pound of neck strength was linked to about 5% lower concussion odds." },
  { id: "injury-sleep-link", category: "injury_safety", text: "Young athletes sleeping under eight hours were about 1.7 times more likely to get injured in one study." },
  { id: "injury-gradual-return", category: "injury_safety", text: "Ease back into contact gradually after an injury, and stop the session if symptoms return." },
  { id: "injury-skin-check", category: "injury_safety", text: "Check your skin daily and stay off the mats with any unexplained rash or sore. Skin infections spread fast in grappling." },
  { id: "injury-shower-after", category: "injury_safety", text: "Shower straight after mat sessions and wash kit every time. It is the simplest defence against ringworm and staph." },
  { id: "injury-mouthguard", category: "injury_safety", text: "Wear a well-fitted mouthguard in every contact round. Custom or boil-and-bite guards fit far better than loose stock ones." },
  { id: "injury-headgear", category: "injury_safety", text: "Headgear reduces cuts and bruising in sparring, but it does not make hard head contact safe. Control the intensity." },
  { id: "injury-hand-care", category: "injury_safety", text: "Wrap hands properly and replace worn gloves. Good hand protection limits knuckle and wrist strain across a long camp." },
  { id: "injury-concussion-signs", category: "injury_safety", text: "Headache, fogginess, nausea or light sensitivity after a hit can signal concussion. Stop and get assessed that day." },
  { id: "injury-concussion-same-day", category: "injury_safety", text: "Never return to sparring on the same day as a suspected concussion, even if you quickly feel better." },
  { id: "injury-tap-early", category: "injury_safety", text: "Tap early in drilling and rolling. Joints and tendons give little warning before a submission injury." },
  { id: "injury-fatigue-form", category: "injury_safety", text: "Many injuries happen when you are tired or cold. Warm up fully and stop drilling sharp techniques once form breaks down." },
  { id: "injury-heat-danger", category: "injury_safety", text: "Dizziness, confusion or feeling hot but no longer sweating are danger signs. Stop, cool down and get help immediately." },
  { id: "injury-sparring-partners", category: "injury_safety", text: "Choose sparring partners who match your intent. Controlled partners let you work hard without unnecessary damage." },
  { id: "injury-return-from-break", category: "injury_safety", text: "Coming back from time off? Rebuild training load over several weeks instead of jumping straight back to old volumes." },

  { id: "combat-breathing", category: "combat_performance", text: "Breathing control under pressure starts in training. Practise relaxed exhales during hard rounds and between exchanges." },
  { id: "combat-basics", category: "combat_performance", text: "Footwork and defence win rounds too. Sharp, repeatable basics often decide close fights." },
  { id: "combat-format", category: "combat_performance", text: "Match your conditioning to your fight format. Train the round lengths and rest periods you will actually face." },
  { id: "combat-potentiate", category: "combat_performance", text: "A few explosive jumps or hard pad strikes before a round can briefly sharpen power. Allow a few minutes to recover first." },
  { id: "combat-film", category: "combat_performance", text: "Review sparring footage each week. Fixing one repeated mistake is often worth more than a dozen extra rounds." },
  { id: "combat-shadowboxing", category: "combat_performance", text: "Shadowbox with a clear goal for each round. It builds sharper habits than simply moving through combinations." },
  { id: "combat-visualise", category: "combat_performance", text: "Mental rehearsal helps. Picture your game plan, key adjustments and how you will respond under pressure." },
  { id: "combat-jab", category: "combat_performance", text: "Your jab sets up almost everything. Spend whole rounds working only the jab and its variations." },
  { id: "combat-defensive-exit", category: "combat_performance", text: "Make defence a habit: finish every combination with a defensive move or an angle change on the exit." },
  { id: "combat-ring-craft", category: "combat_performance", text: "Practise cutting off the ring and escaping corners. Position often decides an exchange before a punch is thrown." },
  { id: "combat-pace", category: "combat_performance", text: "Learn your sustainable pace. Fighters who burst early often fade, while spreading output keeps decisions sharp." },
  { id: "combat-feints", category: "combat_performance", text: "Feints cost little energy and reveal how opponents react. Build them into pads and sparring on purpose." },
  { id: "combat-both-stances", category: "combat_performance", text: "Spar against both stances regularly. Unfamiliar southpaw or orthodox angles cause many avoidable mistakes." },
  { id: "combat-clinch", category: "combat_performance", text: "Train clinch and wall work even if you prefer range. Fights end up there, and fatigue there is costly." },
  { id: "combat-corner", category: "combat_performance", text: "Practise taking corner advice between sparring rounds. One clear instruction beats five shouted ones." },
  { id: "combat-between-rounds", category: "combat_performance", text: "Use the minute between rounds well: slow your breathing, sip water and take in one key instruction." },
  { id: "combat-scouting", category: "combat_performance", text: "Study opponents' habits, not their highlights. Look for patterns in how they start rounds and react under pressure." },
  { id: "combat-cue-words", category: "combat_performance", text: "Prepare short, positive cue words for tough moments. Simple self-talk can sharpen focus as fatigue builds." },
  { id: "combat-scenarios", category: "combat_performance", text: "Spar specific scenarios: down on the cards, starting on the wall, or the final minute. Pressure practice transfers." },
  { id: "combat-get-ups", category: "combat_performance", text: "Drill getting back to your feet while exhausted. Wall and ground escapes decide many close MMA rounds." },
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

const SEEN_TIPS_STORAGE_KEY = "unlxck:loading-tips-seen";
// Kept below the bank size so a returning athlete always has fresh tips first.
const SEEN_TIPS_LIMIT = 150;

// Per-browser memory of recently shown tips, so the next build opens on tips
// this athlete has not read yet. Storage can be missing or blocked; tips still
// work without it.
export function readSeenTipIds(): string[] {
  try {
    const raw = window.localStorage.getItem(SEEN_TIPS_STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === "string") : [];
  } catch {
    return [];
  }
}

export function rememberSeenTip(id: string): void {
  try {
    const next = [...readSeenTipIds().filter((seen) => seen !== id), id].slice(-SEEN_TIPS_LIMIT);
    window.localStorage.setItem(SEEN_TIPS_STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Storage unavailable: the athlete may see repeats across builds, nothing more.
  }
}

function shuffle<T>(items: readonly T[], random: () => number): T[] {
  const out = [...items];
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

// One full pass through the whole bank: the athlete's contextual tips first,
// then everything else, with recently seen tips moved to the back. Every tip
// shows once before any repeats, and a fresh pass never opens with the tip
// that closed the previous one.
export function buildTipDeck(
  primary: readonly LoadingTip[],
  {
    random = Math.random,
    avoidFirstId = null,
    recentlySeen = [],
  }: { random?: () => number; avoidFirstId?: string | null; recentlySeen?: readonly string[] } = {},
): LoadingTip[] {
  const primaryIds = new Set(primary.map((tip) => tip.id));
  const seen = new Set(recentlySeen);
  const contextual = shuffle(primary, random);
  const rest = shuffle(LOADING_TIPS.filter((tip) => !primaryIds.has(tip.id)), random);
  const isFresh = (tip: LoadingTip) => !seen.has(tip.id);
  const deck = [
    ...contextual.filter(isFresh),
    ...rest.filter(isFresh),
    ...contextual.filter((tip) => !isFresh(tip)),
    ...rest.filter((tip) => !isFresh(tip)),
  ];
  if (deck.length > 1 && deck[0].id === avoidFirstId) {
    [deck[0], deck[1]] = [deck[1], deck[0]];
  }
  return deck;
}
