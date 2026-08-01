import test from "node:test";
import assert from "node:assert/strict";

import {
  getInjuryOverrideBanner,
  getSupplementaryRiskWatch,
  getTierMeta,
  getTodayDecisionBanner,
  resolveTodayDecision,
} from "./today-authoritative.ts";
import type { TodayCommandView } from "./types.ts";

const BASE_STATE: TodayCommandView = {
  active_plan: { id: "11111111-1111-1111-1111-111111111111", name: "Camp", phase: "SPP" },
  today: {
    training_day: "2026-06-18",
    recommendation_state: "train_as_planned",
    recommendation_reason: "Train as planned.",
    decision_tier: "green",
    warnings: [],
    next_session: { session_id: "session-1", title: "Boxing conditioning" },
    session_scope: "today",
    session_label: "Today",
    completion_status: "not_started",
  },
  risk_watch: [],
  open_injuries: [],
  week_summary: {},
  quick_actions: [],
};

const ACTIVE_SEVERE_INJURY: TodayCommandView["open_injuries"][number] = {
  id: "injury-1",
  athlete_id: "athlete-1",
  source: "today",
  body_area: "knee",
  description: "left knee",
  severity: "severe",
  status: "open",
  created_at: "2026-06-18T10:00:00Z",
  updated_at: "2026-06-18T10:00:00Z",
};

test("green remains completable despite stop-sounding prose", () => {
  const resolved = resolveTodayDecision({
    ...BASE_STATE,
    today: {
      ...BASE_STATE.today,
      recommendation_reason: "No training today.\nRed flag detected. Seek medical advice.",
      decision_tier: "green",
    },
  });

  assert.equal(resolved.authoritativeTier, "green");
  assert.equal(resolved.blocksCurrentSession, false);
  assert.equal(resolved.canCompleteSession, true);
  assert.equal(resolved.sessionOutcome, "unchanged");
  assert.equal(resolved.useSafeReplacement, false);
  assert.ok(resolved.banner);
  assert.equal(resolved.banner.displayState, "go");
  assert.equal(resolved.banner.tone, "green");
  assert.equal(resolved.banner.detail, "Your check-in is clear for today's planned work.");
  assert.doesNotMatch(resolved.banner.detail, /Red flag|medical advice/i);
  assert.equal(resolved.banner.action, "Complete today's planned session.");
  assert.equal("blocksTraining" in resolved.banner, false);
});

test("current session before check-in is not classified as blocked", () => {
  const resolved = resolveTodayDecision({
    ...BASE_STATE,
    today: {
      ...BASE_STATE.today,
      recommendation_state: "not_checked_in",
      decision_tier: "not_checked_in",
    },
  });
  assert.equal(resolved.sessionOutcome, "unchanged");
  assert.equal(resolved.banner, null);
});

test("pull-back remains blocking despite green-sounding prose", () => {
  const resolved = resolveTodayDecision({
    ...BASE_STATE,
    today: {
      ...BASE_STATE.today,
      recommendation_state: "pull_back",
      recommendation_reason: "Sharp work ready.\nEverything feels good.\nTrain normally.",
      decision_tier: "pull_back",
    },
  });

  assert.equal(resolved.authoritativeTier, "pull_back");
  assert.equal(resolved.blocksCurrentSession, true);
  assert.equal(resolved.canCompleteSession, false);
  assert.equal(resolved.sessionOutcome, "blocked");
  assert.doesNotMatch(resolved.banner?.action ?? "", /replaced/i);
  assert.equal(
    resolved.banner?.action,
    "Today's planned session is blocked. Follow today's limits.",
  );
  assert.equal(
    resolved.banner?.detail,
    "Your readiness is too low for hard combat work today.",
  );
  assert.doesNotMatch(resolved.banner?.detail ?? "", /Everything feels good|Train normally/);
});

test("STOP uses a safe replacement only for today's matched session", () => {
  const resolved = resolveTodayDecision({
    ...BASE_STATE,
    today: {
      ...BASE_STATE.today,
      recommendation_state: "pull_back",
      decision_tier: "stop",
    },
  });

  assert.equal(resolved.authoritativeTier, "stop");
  assert.equal(resolved.sessionIsToday, true);
  assert.equal(resolved.blocksCurrentSession, true);
  assert.equal(resolved.canCompleteSession, false);
  assert.equal(resolved.useSafeReplacement, true);
  assert.equal(resolved.sessionOutcome, "replaced_with_recovery");
  assert.equal(resolved.banner?.action, "Today's planned session is blocked.");
});

test("backend STOP remains visible before check-in when a severe injury is active", () => {
  const resolved = resolveTodayDecision({
    ...BASE_STATE,
    today: {
      ...BASE_STATE.today,
      recommendation_state: "not_checked_in",
      recommendation_reason: null,
      decision_tier: "stop",
    },
    open_injuries: [ACTIVE_SEVERE_INJURY],
  });

  assert.equal(resolved.displayTier, "stop");
  assert.ok(resolved.banner);
  assert.equal(resolved.banner.displayState, "stop");
  assert.equal(resolved.banner.chip, "STOP");
  assert.equal(resolved.banner.title, "Stop today");
  assert.equal(resolved.banner.tone, "red");
  assert.match(resolved.banner.detail, /Active severe injury: Knee/);
  assert.match(resolved.banner.detail, /until it is cleared/);
  assert.doesNotMatch(resolved.banner.detail, /Train as planned|Everything feels good/);
  assert.equal(resolved.blocksCurrentSession, true);
  assert.equal(resolved.severeInjuryBlocksCurrentSession, true);
  assert.equal(resolved.canCompleteSession, false);
});

test("severe-injury STOP copy never leaks stale recommendation text", () => {
  const staleRecommendations: Array<{
    state: TodayCommandView["today"]["recommendation_state"];
    reason: string | null;
  }> = [
    { state: "train_as_planned", reason: "Everything feels good. Train normally." },
    { state: "pull_back", reason: "Only readiness load needs adjusting." },
    { state: "not_checked_in", reason: null },
  ];

  for (const recommendation of staleRecommendations) {
    const resolved = resolveTodayDecision({
      ...BASE_STATE,
      today: {
        ...BASE_STATE.today,
        recommendation_state: recommendation.state,
        recommendation_reason: recommendation.reason,
        decision_tier: "stop",
      },
      open_injuries: [ACTIVE_SEVERE_INJURY],
    });

    assert.equal(resolved.authoritativeTier, "stop");
    assert.equal(resolved.banner?.chip, "STOP");
    assert.match(resolved.banner?.detail ?? "", /Active severe injury: Knee/);
    assert.doesNotMatch(
      resolved.banner?.detail ?? "",
      /Everything feels good|Only readiness load|Train normally/,
    );
    assert.equal(resolved.blocksCurrentSession, true);
  }
});

test("authoritative STOP overrides pull-back presentation as well as session safety", () => {
  const resolved = resolveTodayDecision({
    ...BASE_STATE,
    today: {
      ...BASE_STATE.today,
      recommendation_state: "pull_back",
      recommendation_reason: "Sharp work ready.\nEverything feels good.\nTrain normally.",
      decision_tier: "stop",
    },
  });

  assert.equal(resolved.authoritativeTier, "stop");
  assert.equal(resolved.displayTier, "stop");
  assert.ok(resolved.banner);
  assert.equal(resolved.banner.displayState, "stop");
  assert.equal(resolved.banner.chip, "STOP");
  assert.notEqual(resolved.banner.chip, "PULL BACK");
  assert.equal(resolved.banner.title, "Stop today");
  assert.equal(resolved.banner.detail, "A safety restriction is blocking training today.");
  assert.equal(resolved.banner.action, "Today's planned session is blocked.");
  assert.equal(resolved.banner.tone, "red");
  assert.equal(getTierMeta(resolved.displayTier).label, "Stop today");
  assert.equal(resolved.blocksCurrentSession, true);
  assert.equal(resolved.canCompleteSession, false);
  assert.equal(resolved.useSafeReplacement, true);
});

test("future pull-back remains a neutral pending preview", () => {
  const resolved = resolveTodayDecision({
    ...BASE_STATE,
    today: {
      ...BASE_STATE.today,
      recommendation_state: "pull_back",
      decision_tier: "pull_back",
      next_session: {
        ...BASE_STATE.today.next_session,
        session_relation: "next",
      },
      session_scope: "next",
    },
  });

  assert.equal(resolved.authoritativeTier, "pull_back");
  assert.equal(resolved.displayTier, "preview");
  assert.equal(resolved.sessionIsToday, false);
  assert.equal(resolved.blocksCurrentSession, false);
  assert.equal(resolved.canCompleteSession, false);
  assert.equal(resolved.useSafeReplacement, false);
  assert.equal(resolved.sessionOutcome, "preview");
  assert.equal(resolved.severeInjuryBlocksCurrentSession, false);
  assert.equal(resolved.banner?.chip, "PREVIEW");
  assert.equal(resolved.tone, "neutral");
});

test("a future calendar date cannot be made completable by an incorrect today relation", () => {
  const resolved = resolveTodayDecision({
    ...BASE_STATE,
    today: {
      ...BASE_STATE.today,
      training_day: "2026-08-01",
      next_session: {
        session_id: "2026-08-08",
        title: "Fight-Pace Conditioning and Neural Primer",
        calendar_date: "2026-08-08",
        session_relation: "today",
        effective_load: "technical",
      },
      session_scope: "today",
    },
  });

  assert.equal(resolved.sessionIsToday, false);
  assert.equal(resolved.displayTier, "preview");
  assert.equal(resolved.canCompleteSession, false);
  assert.equal(resolved.sessionOutcome, "preview");
});

test("modify is guidance only and never claims the structured session was rewritten", () => {
  const resolved = resolveTodayDecision({
    ...BASE_STATE,
    today: {
      ...BASE_STATE.today,
      recommendation_state: "modify",
      decision_tier: "modify",
      recommendation_reason: "Hard combat work needs to be controlled today.",
    },
  });
  assert.equal(resolved.sessionOutcome, "guidance_only");
  assert.equal(resolved.canCompleteSession, true);
  assert.equal(resolved.banner?.action, "Follow adjusted work and skip extras.");
  assert.deepEqual(
    {
      chip: resolved.banner?.chip,
      action: resolved.banner?.action,
      detail: resolved.banner?.detail,
    },
    {
      chip: "ADJUST",
      action: "Follow adjusted work and skip extras.",
      detail: "Hard combat work needs to be controlled today.",
    },
  );
});

test("severe-injury STOP removes only the known duplicate injury risk", () => {
  const state: TodayCommandView = {
    ...BASE_STATE,
    today: { ...BASE_STATE.today, decision_tier: "stop" },
    open_injuries: [ACTIVE_SEVERE_INJURY],
  };
  const risks: TodayCommandView["risk_watch"] = [
    { category: "active_injury_worse", priority: 1, icon: "bandage", label: "Injury worsening", text: "Knee", tone: "stop" },
    { category: "stop_red_flag", priority: 2, icon: "stop", label: "Stop", text: "Do not train", tone: "stop" },
    { category: "weight_cut", priority: 3, icon: "scale", label: "Weight cut", text: "Hydrate", tone: "watch" },
  ];
  assert.deepEqual(getSupplementaryRiskWatch(risks, resolveTodayDecision(state)), [
    risks[2],
  ]);
});

test("risk filtering preserves stable reminders and distinct pain outside severe STOP", () => {
  const risks: TodayCommandView["risk_watch"] = [
    { category: "reminder", priority: 1, icon: "info", label: "Skin care", text: "Keep it covered", tone: "watch" },
    { category: "high_pain", priority: 2, icon: "pain", label: "High pain", text: "Pain is high", tone: "stop" },
  ];
  assert.deepEqual(getSupplementaryRiskWatch(risks, resolveTodayDecision(BASE_STATE)), risks);
  const pullBack = resolveTodayDecision({
    ...BASE_STATE,
    today: { ...BASE_STATE.today, recommendation_state: "pull_back", decision_tier: "pull_back" },
  });
  assert.deepEqual(getSupplementaryRiskWatch(risks, pullBack), risks);
});

test("future mobility preview uses its own session copy, not today's strength or injury copy", () => {
  const resolved = resolveTodayDecision({
    ...BASE_STATE,
    today: {
      ...BASE_STATE.today,
      recommendation_reason:
        "Run the planned work and keep the lifts crisp.\nYour sleep, body, and pain checks are all clear today.\nKeep the injured area clean.",
      next_session: {
        session_id: "mobility-1",
        session_relation: "next",
        session_type: "recovery",
        title: "Mobility Reset",
      },
      session_scope: "next",
    },
  });

  assert.equal(resolved.banner?.chip, "PREVIEW");
  assert.equal(resolved.banner?.title, "Session preview");
  assert.equal(resolved.banner?.detail, "Mobility Reset is next on your plan.");
  assert.equal(
    resolved.banner?.action,
    "Review the mobility and recovery work before it opens.",
  );
  assert.doesNotMatch(
    `${resolved.banner?.detail} ${resolved.banner?.action}`,
    /lifts crisp|pain checks|injured area|clean/i,
  );
  assert.equal(resolved.banner?.safety, undefined);
});

test("future previews cover every canonical session type with short specific copy", () => {
  const expectedActions: Record<string, string> = {
    strength_power: "Review the lifts and loading before it opens.",
    conditioning: "Review the intervals and pace before it opens.",
    skill: "Review the drills and technical focus before it opens.",
    sparring: "Review the rounds and contact plan before it opens.",
    primer: "Review the primer and key movement cues before it opens.",
    recovery: "Review the mobility and recovery work before it opens.",
    rehab: "Review the rehab sequence and pain-free ranges before it opens.",
    fight_or_match: "Review the fight-day plan before it opens.",
    mixed: "Review the session blocks and transitions before it opens.",
  };

  for (const [sessionType, expectedAction] of Object.entries(expectedActions)) {
    const resolved = resolveTodayDecision({
      ...BASE_STATE,
      today: {
        ...BASE_STATE.today,
        next_session: {
          session_id: `preview-${sessionType}`,
          session_relation: "next",
          session_type: sessionType,
          title: `${sessionType} preview`,
        },
        session_scope: "next",
      },
    });

    assert.equal(resolved.banner?.action, expectedAction, sessionType);
    assert.ok(expectedAction.split(/\s+/).length <= 11, sessionType);
  }
});

test("support-session previews cover every generated support category", () => {
  const expectedActions: Record<string, string> = {
    tactical: "Review the tactical cues before it opens.",
    mental: "Review the mindset work before it opens.",
    recovery: "Review the recovery work before it opens.",
    mobility: "Review the mobility work and pain-free ranges before it opens.",
    movement_quality: "Review the movement-quality work before it opens.",
    technical: "Review the technical drills before it opens.",
    footwork: "Review the footwork pattern before it opens.",
    recovery_walk: "Review the easy pace and route before it opens.",
    conditioning_maintenance: "Review the easy conditioning pace before it opens.",
  };

  for (const [supportCategory, expectedAction] of Object.entries(expectedActions)) {
    const resolved = resolveTodayDecision({
      ...BASE_STATE,
      today: {
        ...BASE_STATE.today,
        next_session: {
          session_id: `support-${supportCategory}`,
          session_relation: "next",
          session_type: "skill",
          category: "support_insert",
          support_insert_category: supportCategory,
          title: `${supportCategory} support`,
        },
        session_scope: "next",
      },
    });

    assert.equal(resolved.banner?.action, expectedAction, supportCategory);
    assert.ok(expectedAction.split(/\s+/).length <= 11, supportCategory);
  }
});

test("block metadata frames every canonical block when session type is unavailable", () => {
  const expectedActions: Record<string, string> = {
    preparation: "Review the preparation sequence before it opens.",
    mobility_activation: "Review the mobility and activation work before it opens.",
    plyometric_power: "Review the explosive work and rest periods before it opens.",
    speed: "Review the speed work and rest periods before it opens.",
    strength: "Review the lifts and loading before it opens.",
    strength_speed: "Review the power lifts and loading before it opens.",
    accessory: "Review the accessory work before it opens.",
    conditioning: "Review the intervals and pace before it opens.",
    skill: "Review the drills and technical focus before it opens.",
    sparring: "Review the rounds and contact plan before it opens.",
    cooldown_recovery: "Review the cooldown and recovery work before it opens.",
    nutrition: "Review the nutrition steps before it opens.",
    mindset: "Review the mindset cues before it opens.",
    rehab: "Review the rehab sequence and pain-free ranges before it opens.",
  };

  for (const [blockType, expectedAction] of Object.entries(expectedActions)) {
    const resolved = resolveTodayDecision({
      ...BASE_STATE,
      today: {
        ...BASE_STATE.today,
        next_session: {
          session_id: `block-${blockType}`,
          session_relation: "next",
          title: `${blockType} block`,
          blocks: [{ block_type: blockType }],
        },
        session_scope: "next",
      },
    });

    assert.equal(resolved.banner?.action, expectedAction, blockType);
    assert.ok(expectedAction.split(/\s+/).length <= 11, blockType);
  }
});

test("future STOP remains a neutral pending preview without remediation or replacement", () => {
  const resolved = resolveTodayDecision({
    ...BASE_STATE,
    today: {
      ...BASE_STATE.today,
      recommendation_state: "pull_back",
      decision_tier: "stop",
      next_session: {
        ...BASE_STATE.today.next_session,
        session_relation: "next",
      },
      session_scope: "next",
    },
    open_injuries: [ACTIVE_SEVERE_INJURY],
  });

  assert.equal(resolved.authoritativeTier, "stop");
  assert.equal(resolved.displayTier, "preview");
  assert.equal(resolved.sessionIsToday, false);
  assert.equal(resolved.blocksCurrentSession, false);
  assert.equal(resolved.canCompleteSession, false);
  assert.equal(resolved.useSafeReplacement, false);
  assert.equal(resolved.severeInjuryBlocksCurrentSession, false);
  assert.equal(resolved.banner?.chip, "PREVIEW");
  assert.equal(resolved.tone, "neutral");
});

test("severe-injury remediation respects the backend exemption", () => {
  const resolved = resolveTodayDecision({
    ...BASE_STATE,
    today: {
      ...BASE_STATE.today,
      recommendation_state: "pull_back",
      decision_tier: "stop",
      injury_hold_exempt: true,
    },
    open_injuries: [ACTIVE_SEVERE_INJURY],
  });

  assert.equal(resolved.blocksCurrentSession, true);
  assert.equal(resolved.severeInjuryBlocksCurrentSession, false);
});

test("the banner adapter stays presentation-only", () => {
  const banner = getTodayDecisionBanner("pull_back", "Train normally.");
  assert.ok(banner);
  assert.equal("blocksTraining" in banner, false);
});

test("the legacy injury presentation export is preserved without overriding backend safety", () => {
  const state: TodayCommandView = {
    ...BASE_STATE,
    open_injuries: [
      {
        id: "injury-1",
        athlete_id: "athlete-1",
        source: "today",
        body_area: "knee",
        description: "left knee",
        severity: "severe",
        status: "open",
        created_at: "2026-06-18T10:00:00Z",
        updated_at: "2026-06-18T10:00:00Z",
      },
    ],
  };

  const injuryBanner = getInjuryOverrideBanner(state, "Boxing conditioning");
  const resolved = resolveTodayDecision(state);

  assert.equal(injuryBanner?.chip, "INJURY HOLD");
  assert.match(injuryBanner?.detail ?? "", /Active severe injury: Knee/);
  assert.equal(resolved.authoritativeTier, "green");
  assert.equal(resolved.banner?.chip, "GO");
  assert.equal(resolved.blocksCurrentSession, false);
});

test("backend instructions survive compatible authoritative tiers", () => {
  const cases = [
    {
      state: "train_as_planned" as const,
      tier: "green" as const,
      reason: "Train as planned\nYour check-in is clear, with the left shoulder abrasion still being tracked.\nKeep the left shoulder abrasion clean and covered; stop if it opens or bleeds.\nSkin injury — No session change",
      action: "Keep the left shoulder abrasion clean and covered; stop if it opens or bleeds.",
    },
    {
      state: "train_as_planned" as const,
      tier: "green" as const,
      reason: "Train as planned\nYour ankle is stable and still being tracked.\nKeep load off the ankle.",
      action: "Keep load off the ankle.",
    },
    {
      state: "modify" as const,
      tier: "modify" as const,
      reason: "Reduce volume today\nPoor sleep has reduced your readiness.\nCut 1 round and 1 set from today's work.",
      action: "Cut 1 round and 1 set from today's work.",
    },
    {
      state: "pull_back" as const,
      tier: "pull_back" as const,
      reason: "Pull back today\nA moderate wrist injury needs protection.\nAvoid impact and contact through the wrist.",
      action: "Avoid impact and contact through the wrist.",
    },
  ];

  for (const item of cases) {
    const resolved = resolveTodayDecision({
      ...BASE_STATE,
      today: {
        ...BASE_STATE.today,
        recommendation_state: item.state,
        decision_tier: item.tier,
        recommendation_reason: item.reason,
      },
    });
    assert.equal(resolved.banner?.action, item.action);
  }
  const abrasion = resolveTodayDecision({
    ...BASE_STATE,
    today: { ...BASE_STATE.today, recommendation_reason: cases[0].reason },
  });
  assert.equal(abrasion.banner?.chip, "GO");
  assert.match(abrasion.banner?.detail ?? "", /shoulder abrasion/);
  assert.equal(abrasion.banner?.safety, "Skin injury — No session change");
  assert.doesNotMatch(abrasion.banner?.action ?? "", /Session unchanged/i);
  assert.equal(resolveTodayDecision({ ...BASE_STATE, today: { ...BASE_STATE.today, recommendation_state: "pull_back", decision_tier: "pull_back", recommendation_reason: cases[3].reason } }).canCompleteSession, false);
});

test("STOP copy compatibility preserves hard stops and rejects weaker advice", () => {
  const compatible = resolveTodayDecision({
    ...BASE_STATE,
    today: { ...BASE_STATE.today, recommendation_state: "pull_back", decision_tier: "stop", recommendation_reason: "No training today\nA severe injury blocks the planned session.\nRehab only today." },
  });
  assert.equal(compatible.banner?.action, "Rehab only today.");
  assert.equal(compatible.useSafeReplacement, true);

  const stale = resolveTodayDecision({
    ...BASE_STATE,
    today: { ...BASE_STATE.today, recommendation_state: "modify", decision_tier: "stop", recommendation_reason: "Reduce volume\nOnly a small adjustment is needed.\nCut 1 round." },
  });
  assert.equal(stale.banner?.action, "Today's planned session is blocked.");
  assert.doesNotMatch(stale.banner?.action ?? "", /Cut 1 round/);
});

test("stop red flags are hidden when today's main tier already blocks", () => {
  const stopRisk = { category: "stop_red_flag", priority: 1, icon: "stop", label: "Stop", text: "Do not train", tone: "stop" };
  const weightRisk = { category: "weight_cut", priority: 2, icon: "scale", label: "Weight cut", text: "Hydrate", tone: "watch" };
  const risks: TodayCommandView["risk_watch"] = [stopRisk, weightRisk];
  for (const tier of ["pull_back", "stop"] as const) {
    const decision = resolveTodayDecision({ ...BASE_STATE, today: { ...BASE_STATE.today, recommendation_state: "pull_back", decision_tier: tier } });
    assert.deepEqual(getSupplementaryRiskWatch(risks, decision), [weightRisk]);
  }
  assert.deepEqual(getSupplementaryRiskWatch(risks, resolveTodayDecision(BASE_STATE)), risks);
});
