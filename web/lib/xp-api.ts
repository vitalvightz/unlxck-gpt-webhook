import { parseXpProgressResponse, type XpProgress } from "@/lib/xp-progress";

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
