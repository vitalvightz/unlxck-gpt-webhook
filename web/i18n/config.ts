export const SUPPORTED_LOCALES = ["en", "es", "pt-BR", "it"] as const;
export type AppLocale = (typeof SUPPORTED_LOCALES)[number];
export const DEFAULT_LOCALE: AppLocale = "en";
export const LOCALE_COOKIE_NAME = "unlxck_locale";
export const LOCALE_OPTIONS = [
  { code: "en", label: "English", shortLabel: "EN" },
  { code: "es", label: "Español", shortLabel: "ES" },
  { code: "pt-BR", label: "Português (Brasil)", shortLabel: "PT" },
  { code: "it", label: "Italiano", shortLabel: "IT" },
] as const;
export function isSupportedLocale(value: string | null | undefined): value is AppLocale {
  return SUPPORTED_LOCALES.includes(value as AppLocale);
}
export function resolveLocale(value: string | null | undefined): AppLocale {
  return isSupportedLocale(value) ? value : DEFAULT_LOCALE;
}
