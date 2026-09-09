"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useAppSession } from "@/components/auth-provider";
import { useToast } from "@/components/toast-provider";
import { LOCALE_COOKIE_NAME, LOCALE_OPTIONS, isSupportedLocale, resolveLocale, type AppLocale } from "@/i18n/config";
import { updateMe } from "@/lib/api";

function writeLocaleCookie(locale: AppLocale) {
  document.cookie = `${LOCALE_COOKIE_NAME}=${encodeURIComponent(locale)}; Path=/; Max-Age=31536000; SameSite=Lax${location.protocol === "https:" ? "; Secure" : ""}`;
}
function readLocaleCookie() {
  return document.cookie.split("; ").find((value) => value.startsWith(`${LOCALE_COOKIE_NAME}=`))?.split("=")[1] ?? null;
}

export function LanguageSwitcher() {
  const router = useRouter();
  const t = useTranslations("LanguageSwitcher");
  const locale = resolveLocale(useLocale());
  const { session, me, replaceMe } = useAppSession();
  const { showToast } = useToast();
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<AppLocale | null>(null);
  const current = LOCALE_OPTIONS.find((option) => option.code === locale) ?? LOCALE_OPTIONS[0];

  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => { if (!rootRef.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", close);
    window.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", close); window.removeEventListener("keydown", escape); };
  }, [open]);

  useEffect(() => {
    const profileLocale = me?.profile.athlete_locale;
    if (readLocaleCookie() || !isSupportedLocale(profileLocale) || profileLocale === locale) return;
    writeLocaleCookie(profileLocale);
    document.documentElement.setAttribute("lang", profileLocale);
    router.refresh();
  }, [locale, me?.profile.athlete_locale, router]);

  async function selectLocale(next: AppLocale) {
    if (pending || next === locale) return setOpen(false);
    setPending(next); setOpen(false); writeLocaleCookie(next); document.documentElement.setAttribute("lang", next);
    if (session?.access_token && me?.profile.athlete_locale !== next) {
      try { replaceMe(await updateMe(session.access_token, { athlete_locale: next })); }
      catch { showToast(t("saveError"), { tone: "error" }); }
    }
    router.refresh(); setPending(null);
  }
  return <div ref={rootRef} className="unlxck-language-switcher">
    <button type="button" className="unlxck-language-switcher-trigger" aria-label={t("current", { language: current.label })} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((value) => !value)} disabled={pending !== null}>
      <span aria-hidden="true">◎</span><span>{current.shortLabel}</span><span aria-hidden="true">⌄</span>
    </button>
    {open ? <div className="unlxck-language-menu" role="menu" aria-label={t("choose")}>
      <p>{t("choose")}</p>{LOCALE_OPTIONS.map((option) => <button key={option.code} type="button" role="menuitemradio" aria-checked={option.code === locale} onClick={() => void selectLocale(option.code)}><span>{option.label}</span><span>{option.shortLabel}</span></button>)}
    </div> : null}
  </div>;
}
