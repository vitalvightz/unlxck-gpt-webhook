import { parseXpProgressResponse, type XpProgress } from "@/lib/xp-progress";

export async function recordAppActivity(token: string): Promise<void> {
  const response = await fetch("/api/xp/activity", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
    },
  });
  if (!response.ok) {
    throw new Error(`App activity request failed (${response.status}).`);
  }
}

export async function getXpProgress(token: string, signal?: AbortSignal): Promise<XpProgress> {
  const response = await fetch("/api/xp/progress", {
    method: "GET",
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
    },
    signal,
  });
  if (!response.ok) {
    throw new Error(`XP progress request failed (${response.status}).`);
  }
  return parseXpProgressResponse(await response.json());
}
