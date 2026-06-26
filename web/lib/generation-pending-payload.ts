```ts
import type { PlanRequest } from "@/lib/types";

import { stableStringify } from "@/lib/stable-stringify";

const PENDING_GENERATION_PAYLOAD_KEY = "unlxck:pending-generation-payload:v1";
const PENDING_GENERATION_MAX_AGE_MS = 5 * 60 * 1000;

export type PendingGenerationPayload = {
  payload: PlanRequest;
  payloadHash: string;
  planSource: string;
  createdAtMs: number;
};

type StoredPendingGenerationPayload = PendingGenerationPayload & {
  version: 1;
};

function getSessionStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function isPlanRequestLike(value: unknown): value is PlanRequest {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Partial<PlanRequest>;

  return Boolean(
    candidate.athlete
      && typeof candidate.athlete === "object"
      && Array.isArray(candidate.key_goals)
      && Array.isArray(candidate.weak_areas)
      && Array.isArray(candidate.training_availability)
      && Array.isArray(candidate.equipment_access),
  );
}

export function buildPlanRequestPayloadHash(payload: PlanRequest): string {
  const serialized = stableStringify(payload);
  let hash = 0x811c9dc5;

  for (let index = 0; index < serialized.length; index += 1) {
    hash ^= serialized.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }

  return `fnv1a32:${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

export function buildGenerationPayloadDebugSummary(payload: PlanRequest) {
  return {
    key_goals: payload.key_goals,
    primary_goal: payload.primary_goal ?? "",
    weak_areas: payload.weak_areas,
    primary_weak_area: payload.primary_weak_area ?? "",
    fatigue_level: payload.fatigue_level ?? "",
    professional_status: payload.athlete.professional_status ?? "",
    equipment_access: payload.equipment_access,
    fight_date: payload.fight_date,
    no_scheduled_fight: payload.no_scheduled_fight ?? false,
    technical_style: payload.athlete.technical_style,
    tactical_style: payload.athlete.tactical_style,
  };
}

export function writePendingGenerationPayload(payload: PlanRequest, planSource: string): boolean {
  const storage = getSessionStorage();
  if (!storage) {
    return false;
  }

  const stored: StoredPendingGenerationPayload = {
    version: 1,
    payload,
    payloadHash: buildPlanRequestPayloadHash(payload),
    planSource,
    createdAtMs: Date.now(),
  };

  try {
    storage.setItem(PENDING_GENERATION_PAYLOAD_KEY, JSON.stringify(stored));
    return true;
  } catch {
    return false;
  }
}

export function readPendingGenerationPayload(): PendingGenerationPayload | null {
  const storage = getSessionStorage();
  if (!storage) {
    return null;
  }

  let parsed: unknown;

  try {
    const raw = storage.getItem(PENDING_GENERATION_PAYLOAD_KEY);
    if (!raw) {
      return null;
    }

    parsed = JSON.parse(raw);
  } catch {
    storage.removeItem(PENDING_GENERATION_PAYLOAD_KEY);
    return null;
  }

  const stored = parsed as Partial<StoredPendingGenerationPayload>;
  const createdAtMs = stored.createdAtMs;
  const ageMs = typeof createdAtMs === "number" ? Date.now() - createdAtMs : Number.NaN;

  if (
    stored.version !== 1
    || typeof createdAtMs !== "number"
    || !Number.isFinite(createdAtMs)
    || !isPlanRequestLike(stored.payload)
    || typeof stored.planSource !== "string"
    || !stored.planSource.trim()
    || !Number.isFinite(ageMs)
    || ageMs < 0
    || ageMs > PENDING_GENERATION_MAX_AGE_MS
  ) {
    storage.removeItem(PENDING_GENERATION_PAYLOAD_KEY);
    return null;
  }

  return {
    payload: stored.payload,
    payloadHash: typeof stored.payloadHash === "string"
      ? stored.payloadHash
      : buildPlanRequestPayloadHash(stored.payload),
    planSource: stored.planSource,
    createdAtMs,
  };
}

export function clearPendingGenerationPayload() {
  getSessionStorage()?.removeItem(PENDING_GENERATION_PAYLOAD_KEY);
}
