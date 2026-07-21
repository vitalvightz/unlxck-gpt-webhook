"use client";

import { deletePushSubscription, getPushSettings, savePushSubscription } from "@/lib/api";

/**
 * Web push opt-in flow for the PWA.
 *
 * The service worker (public/sw.js) only registers in production builds, so in
 * dev the state reads as "unsupported" — expected, not a bug. On iOS, push is
 * only available once the app is installed to the home screen (iOS 16.4+),
 * which `isPushSupported` surfaces naturally via the missing PushManager.
 */

export type PushOptInState =
  | "unsupported"
  | "server-disabled"
  | "denied"
  | "unsubscribed"
  | "subscribed";

export function isPushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

async function getReadyRegistration(): Promise<ServiceWorkerRegistration | null> {
  if (!isPushSupported()) {
    return null;
  }
  try {
    // `ready` resolves only once a SW controls the page; in dev no SW ever
    // registers, so guard with the current registration instead of hanging.
    const registration = await navigator.serviceWorker.getRegistration();
    return registration ?? null;
  } catch {
    return null;
  }
}

export async function getExistingPushSubscription(): Promise<PushSubscription | null> {
  const registration = await getReadyRegistration();
  if (!registration) {
    return null;
  }
  try {
    return await registration.pushManager.getSubscription();
  } catch {
    return null;
  }
}

export async function getPushOptInState(token: string | null): Promise<PushOptInState> {
  if (!isPushSupported()) {
    return "unsupported";
  }
  if (Notification.permission === "denied") {
    return "denied";
  }
  if (await getExistingPushSubscription()) {
    return "subscribed";
  }
  if (token) {
    try {
      const settings = await getPushSettings(token);
      if (!settings.enabled) {
        return "server-disabled";
      }
    } catch {
      // Treat a transient settings failure as available; subscribing re-checks.
    }
  }
  return "unsubscribed";
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i += 1) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

function deviceTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch {
    return "";
  }
}

/**
 * Request permission, subscribe the browser, and save the subscription
 * server-side. Throws with a human-readable message on any failure so callers
 * can surface it inline.
 */
export async function subscribeToPushNotifications(token: string): Promise<void> {
  if (!isPushSupported()) {
    throw new Error(
      "Notifications aren't available in this browser. On iPhone, install UNLXCK to your home screen first.",
    );
  }
  const settings = await getPushSettings(token);
  if (!settings.enabled || !settings.public_key) {
    throw new Error("Notifications aren't enabled on the server yet.");
  }
  const registration = await getReadyRegistration();
  if (!registration) {
    throw new Error("The app isn't installed as a PWA yet, so notifications can't be enabled.");
  }
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("Notifications were not allowed. You can enable them in browser settings.");
  }
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(settings.public_key) as BufferSource,
  });
  const json = subscription.toJSON();
  if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
    throw new Error("The browser returned an incomplete push subscription.");
  }
  await savePushSubscription(token, {
    endpoint: json.endpoint,
    keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
    timezone: deviceTimezone(),
  });
}

export async function unsubscribeFromPushNotifications(token: string): Promise<void> {
  const subscription = await getExistingPushSubscription();
  if (!subscription) {
    return;
  }
  const endpoint = subscription.endpoint;
  try {
    await subscription.unsubscribe();
  } catch {
    // Even if the browser-side unsubscribe fails, removing the server row
    // stops sends; the dead endpoint would be pruned on the next push anyway.
  }
  await deletePushSubscription(token, endpoint);
}
