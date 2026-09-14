import type { AppLocale } from "./config";

import en from "@/messages/en.json";
import es from "@/messages/es.json";
import it from "@/messages/it.json";
import ptBR from "@/messages/pt-BR.json";

export type Messages = typeof en;

export const messages: Record<AppLocale, Messages> = {
  en,
  es,
  "pt-BR": ptBR,
  it,
};
