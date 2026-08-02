"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";

const TURNSTILE_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY?.trim() ?? "";

type TurnstileOptions = {
  sitekey: string;
  action: string;
  theme: "auto";
  size: "flexible";
  retry: "auto";
  callback: (token: string) => void;
  "expired-callback": () => void;
  "error-callback": () => void;
};

type TurnstileApi = {
  render: (container: HTMLElement, options: TurnstileOptions) => string;
  reset: (widgetId: string) => void;
  remove: (widgetId: string) => void;
};

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

export function isTurnstileConfigured(): boolean {
  return Boolean(TURNSTILE_SITE_KEY);
}

export function TurnstileChallenge({
  action,
  onTokenChange,
  onUnavailable,
  resetKey,
}: {
  action: "login" | "signup" | "password_reset";
  onTokenChange: (token: string | null) => void;
  onUnavailable?: () => void;
  resetKey: number;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const widgetIdRef = useRef<string | null>(null);
  const [scriptReady, setScriptReady] = useState(false);

  useEffect(() => {
    if (!TURNSTILE_SITE_KEY || !scriptReady || !containerRef.current || !window.turnstile) {
      return;
    }

    if (widgetIdRef.current) {
      window.turnstile.remove(widgetIdRef.current);
      widgetIdRef.current = null;
    }

    widgetIdRef.current = window.turnstile.render(containerRef.current, {
      sitekey: TURNSTILE_SITE_KEY,
      action,
      theme: "auto",
      size: "flexible",
      retry: "auto",
      callback: (token) => onTokenChange(token),
      "expired-callback": () => onTokenChange(null),
      "error-callback": () => {
        onTokenChange(null);
        onUnavailable?.();
      },
    });

    return () => {
      if (widgetIdRef.current && window.turnstile) {
        window.turnstile.remove(widgetIdRef.current);
        widgetIdRef.current = null;
      }
    };
  }, [action, onTokenChange, onUnavailable, scriptReady]);

  useEffect(() => {
    if (!resetKey || !widgetIdRef.current || !window.turnstile) {
      return;
    }
    window.turnstile.reset(widgetIdRef.current);
    onTokenChange(null);
  }, [onTokenChange, resetKey]);

  if (!TURNSTILE_SITE_KEY) {
    return null;
  }

  return (
    <div className="field" aria-label="Security verification">
      <Script
        id="cloudflare-turnstile-script"
        src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"
        strategy="afterInteractive"
        onReady={() => setScriptReady(true)}
        onError={() => onUnavailable?.()}
      />
      <div ref={containerRef} style={{ width: "100%" }} />
    </div>
  );
}
