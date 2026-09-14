import englishMessages from "@/messages/en.json";

export type AppTextKey = keyof typeof englishMessages.AppText;

const appTextKeysByEnglishValue = new Map<string, AppTextKey>(
  Object.entries(englishMessages.AppText).map(([key, value]) => [value, key as AppTextKey]),
);

export function translateUiText<T extends (key: AppTextKey) => string>(translate: T, value: string): string {
  const key = appTextKeysByEnglishValue.get(value);
  return key ? translate(key) : value;
}
