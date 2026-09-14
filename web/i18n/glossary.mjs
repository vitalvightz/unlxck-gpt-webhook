// Machine-readable form of i18n/translation-context.md.
//
// Azure translates one short UI string at a time, with no surrounding sentence to
// disambiguate it, so "round", "drill" or "intake" come back in their everyday sense
// instead of the combat-sports sense this app means. Two mechanisms use this file to
// stop that:
//
//   * scripts/i18n-catalog.mjs marks up the English text before it goes to Azure —
//     brand terms as `notranslate`, glossary terms with `mstrans:dictionary` so the
//     preferred term is used verbatim.
//   * scripts/i18n-check.mjs fails the build when a catalog contains a rendering
//     listed as `forbidden` for a term the English string actually uses.
//
// `forbidden` patterns are only ever applied to a string whose English source matches
// the entry's `en` pattern, so a word that is a defect for one term stays available as
// the correct translation of another.

/** Product names. These are never machine-translated, in any locale. */
export const BRAND_TERMS = ["UNLXCK", "Unlxck", "Lxcked", "Advanced Intake", "Quick Build", "Fight Lab"];

/**
 * The one brand word a human translator may render as words: the hero line "Lxcked in."
 * is a play on "locked in", and the human es/pt-BR/it taglines deliberately carry the
 * meaning instead of the spelling. Markup still protects it from Azure.
 */
const LOCALISABLE_BRAND_TERMS = new Set(["Lxcked"]);

/**
 * @typedef {object} GlossaryEntry
 * @property {string} id
 * @property {RegExp} en Matches the English source strings this entry applies to.
 * @property {RegExp} [unless] Skips the entry when the English string also uses a
 *   neighbouring term of the app's own that shares the forbidden rendering.
 * @property {string} [hint] Term handed to Azure as a dictionary phrase, when the
 *   English wording is a fixed phrase the translator should not take apart.
 * @property {Record<string, string>} preferred The term to use, per locale.
 * @property {Record<string, RegExp[]>} [forbidden] Renderings treated as defects.
 */

/** @type {GlossaryEntry[]} */
export const GLOSSARY = [
  {
    id: "fight-camp",
    en: /\bfight[- ]camps?\b/i,
    hint: "fight camp",
    preferredPlural: { es: "camps de pelea", "pt-BR": "camps de luta", fr: "camps de combat", it: "camp di combattimento" },
    preferred: { es: "camp de pelea", "pt-BR": "camp de luta", fr: "camp de combat", it: "camp di combattimento" },
    forbidden: {
      es: [/campament/i],
      "pt-BR": [/acampament/i],
      fr: [/camping/i],
      it: [/campeggi/i],
    },
  },
  {
    id: "camp",
    en: /\bcamps?\b/i,
    hint: "camp",
    preferredPlural: { es: "camps", "pt-BR": "camps", fr: "camps", it: "camp" },
    preferred: { es: "camp", "pt-BR": "camp", fr: "camp", it: "camp" },
    forbidden: {
      es: [/campament/i],
      "pt-BR": [/acampament/i],
      fr: [/camping/i],
      it: [/campeggi/i, /\bcampo\b/i],
    },
  },
  {
    id: "round",
    en: /\brounds?\b/i,
    hint: "round",
    preferredPlural: { es: "rounds", "pt-BR": "rounds", fr: "rounds", it: "round" },
    preferred: { es: "round", "pt-BR": "round", fr: "round", it: "round" },
    forbidden: {
      es: [/munici[oó]n/i, /cartuch/i, /proyectil/i, /\bbalas?\b/i, /\bvueltas?\b/i, /\brondas?\b/i],
      "pt-BR": [/muni[cç][aã]o/i, /cartuch/i, /proj[eé]ti/i, /\bbalas?\b/i, /\brodadas?\b/i],
      fr: [/munition/i, /cartouch/i, /projectile/i, /\bballes?\b/i, /\bmanches?\b/i],
      it: [/munizion/i, /cartucc/i, /proiettil/i, /\bgiri?\b/i, /\bturni?\b/i],
    },
  },
  {
    id: "heavy-bag",
    en: /\bheavy bags?\b/i,
    hint: "heavy bag",
    preferredPlural: { es: "sacos pesados", "pt-BR": "sacos pesados", fr: "sacs de frappe", it: "sacchi pesanti" },
    preferred: { es: "saco pesado", "pt-BR": "saco pesado", fr: "sac de frappe", it: "sacco pesante" },
    forbidden: {
      es: [/bolsa pesada/i, /maleta/i],
      "pt-BR": [/bolsa pesada/i, /\bmala\b/i],
      fr: [/sacs? lourds?/i, /valise/i],
      it: [/borsa pesante/i, /valigia/i],
    },
  },
  {
    id: "drill",
    en: /\bdrills?\b/i,
    hint: "drill",
    preferredPlural: { es: "ejercicios", "pt-BR": "exercícios", fr: "exercices", it: "esercizi" },
    preferred: { es: "ejercicio", "pt-BR": "exercício", fr: "exercice", it: "esercizio" },
    forbidden: {
      es: [/taladr/i, /broca/i, /perforaci/i],
      "pt-BR": [/furadeir/i, /broca/i, /perfura[cç]/i],
      fr: [/perceuse/i, /\bforet\b/i, /perforat/i],
      it: [/trapan/i, /punta da/i, /perforaz/i],
    },
  },
  {
    id: "sparring",
    en: /\bsparring\b/i,
    unless: /\bcombat\b/i,
    hint: "sparring",
    preferred: { es: "sparring", "pt-BR": "sparring", fr: "sparring", it: "sparring" },
    forbidden: {
      es: [/\bcombates?\b/i, /\bpeleas?\b/i],
      "pt-BR": [/\bcombates?\b/i],
      fr: [/\bcombats?\b/i],
      it: [/\bcombattiment/i],
    },
  },
  {
    id: "intake",
    en: /\bintake\b/i,
    hint: "intake",
    preferred: { es: "cuestionario", "pt-BR": "questionário", fr: "questionnaire", it: "questionario" },
    forbidden: {
      es: [/admisi[oó]n/i, /ingesta/i, /\bingresos?\b/i],
      "pt-BR": [/admiss[aã]o/i, /ingest[aã]o/i, /entrada de ar/i, /\bturma\b/i],
      fr: [/admission/i, /effectifs/i, /groupe d[’']accueil/i, /\bapports?\b/i],
      it: [/aspirazione/i, /accoglienza/i, /ammissione/i, /reclutamento/i, /\bingressi?o?\b/i, /assunzione/i],
    },
  },
  {
    id: "save",
    en: /\bsav(?:e|es|ed|ing)\b/i,
    preferred: { es: "guardar", "pt-BR": "salvar", fr: "enregistrer", it: "salvare" },
    forbidden: {
      es: [/\bahorrad/i, /\bahorrar/i],
      "pt-BR": [/economiz/i],
      fr: [/[eé]conomis/i],
      it: [/risparmi/i],
    },
  },
  {
    id: "resume",
    en: /\bresum(?:e|ed|able|ing)\b/i,
    preferred: { es: "reanudar", "pt-BR": "retomar", fr: "reprendre", it: "riprendere" },
    forbidden: {
      es: [/curr[ií]culum/i],
      "pt-BR": [/curr[ií]culo/i],
      fr: [/\bCV\b/],
      it: [/curriculum/i],
    },
  },
  {
    id: "readiness",
    en: /\breadiness\b/i,
    preferred: { es: "preparación", "pt-BR": "prontidão", fr: "préparation", it: "prontezza" },
    forbidden: {
      es: [/voluntad/i],
      "pt-BR": [/vontade/i],
      fr: [/volont[eé]/i, /empressement/i],
      it: [/volont[aà]/i, /disponibilit[aà] a/i],
    },
  },
  {
    id: "check-in",
    en: /\bcheck[- ]?ins?\b/i,
    hint: "check-in",
    preferred: { es: "check-in", "pt-BR": "check-in", fr: "check-in", it: "check-in" },
    forbidden: {
      es: [/facturaci[oó]n/i, /registro de entrada al hotel/i],
      "pt-BR": [/faturament/i],
      fr: [/enregistrement (?:à l[’']h[oô]tel|de vol)/i],
      it: [/registrazione in hotel/i],
    },
  },
  {
    id: "settings",
    en: /\bsettings?\b/i,
    hint: "settings",
    preferred: { es: "ajustes", "pt-BR": "configurações", fr: "paramètres", it: "impostazioni" },
    forbidden: {
      es: [/escenari/i, /paisaj/i, /decorad/i],
      "pt-BR": [/cen[aá]ri/i, /paisag/i],
      fr: [/\bd[eé]cors?\b/i, /paysage/i, /sc[eé]nario/i],
      it: [/scenari/i, /paesagg/i],
    },
  },
  {
    id: "focus",
    en: /\bfocus\b/i,
    preferred: { es: "enfoque", "pt-BR": "foco", fr: "focus", it: "focus" },
    forbidden: {
      es: [/gorra/i, /capuch/i, /\btap[oó]n\b/i, /\btapa\b/i],
      "pt-BR": [/\bbon[eé]\b/i, /capuz/i, /\btampa\b/i],
      fr: [/casquett/i, /capuchon/i, /bouchon/i, /couvercle/i, /mise au point/i],
      it: [/cappucci/i, /berrett/i, /\btappo\b/i, /coperchio/i, /messa a fuoco/i],
    },
  },
  {
    id: "focus-cap",
    en: /\bfocus cap\b/i,
    hint: "focus cap",
    preferred: { es: "límite de enfoque", "pt-BR": "limite de foco", fr: "limite de focus", it: "limite di focus" },
  },
  {
    id: "session",
    en: /\bsessions?\b/i,
    preferred: { es: "sesión", "pt-BR": "sessão", fr: "séance", it: "sessione" },
  },
  {
    id: "fight-date",
    en: /\bfight (?:date|day)\b/i,
    hint: "fight date",
    preferred: { es: "fecha de la pelea", "pt-BR": "data da luta", fr: "date du combat", it: "data del combattimento" },
    forbidden: {
      es: [/\bcita\b/i, /\bd[aá]til/i],
      "pt-BR": [/\bencontro\b/i, /\bt[aâ]mara/i],
      fr: [/rendez-vous/i, /\bdattes?\b/i],
      it: [/appuntamento/i],
    },
  },
  {
    id: "training",
    en: /\btraining\b/i,
    preferred: { es: "entrenamiento", "pt-BR": "treino", fr: "entraînement", it: "allenamento" },
    forbidden: {
      es: [/\bformaci[oó]n/i],
      "pt-BR": [/\bforma[cç][aã]o/i],
      fr: [/\bformation/i],
      it: [/\bformazione/i],
    },
  },
  {
    id: "training-load",
    en: /\btraining load\b/i,
    hint: "training load",
    preferred: { es: "carga de entrenamiento", "pt-BR": "carga de treino", fr: "charge d’entraînement", it: "carico di allenamento" },
  },
  {
    id: "recovery",
    en: /\brecovery\b/i,
    preferred: { es: "recuperación", "pt-BR": "recuperação", fr: "récupération", it: "recupero" },
  },
  {
    id: "injury",
    en: /\binjur(?:y|ies)\b/i,
    preferred: { es: "lesión", "pt-BR": "lesão", fr: "blessure", it: "infortunio" },
    forbidden: {
      es: [/\binsulto/i, /\bagravio/i, /\bherida/i],
      "pt-BR": [/\binsulto/i, /\bferida/i],
      fr: [/\binjure/i],
      it: [/\bingiuria/i, /\bferit[ae]\b/i],
    },
  },
  {
    id: "coach",
    en: /\bcoach(?:es|ing)?\b/i,
    preferred: { es: "entrenador", "pt-BR": "treinador", fr: "coach", it: "coach" },
    forbidden: {
      es: [/vag[oó]n/i, /autob[uú]s/i, /autocar/i],
      "pt-BR": [/vag[aã]o/i, /[oô]nibus/i],
      fr: [/\bwagon/i, /autocar/i],
      it: [/vagone/i, /pullman/i, /carrozza/i],
    },
  },
  {
    id: "gym",
    en: /\bgyms?\b/i,
    preferred: { es: "gimnasio", "pt-BR": "academia", fr: "salle", it: "palestra" },
    forbidden: {
      es: [/gimnasia/i],
      "pt-BR": [/gin[aá]sio/i],
      fr: [/gymnase/i],
      it: [/ginnasti/i],
    },
  },
  {
    id: "plan",
    en: /\bplans?\b/i,
    preferred: { es: "plan", "pt-BR": "plano", fr: "plan", it: "piano" },
    forbidden: {
      // "segundo plano" is the correct Spanish for "in the background".
      es: [/(?<!segundo )\bplanos?\b/i],
      "pt-BR": [/\bplantas?\b/i],
      fr: [/\bforfaits?\b/i],
      it: [/\bpiante\b/i, /pianoforte/i],
    },
  },
  {
    id: "taper",
    en: /\btaper\b/i,
    hint: "taper",
    preferred: { es: "descarga", "pt-BR": "polimento", fr: "affûtage", it: "scarico" },
    forbidden: {
      es: [/conicidad/i, /estrechamiento/i],
      "pt-BR": [/conicidade/i, /afunilament/i],
      fr: [/conicit[eé]/i, /effilement/i],
      it: [/conicit[aà]/i, /rastremaz/i],
    },
  },
  {
    id: "strength-and-conditioning",
    en: /\b(?:S&(?:amp;)?C|strength and conditioning)\b/i,
    hint: "strength and conditioning",
    preferred: { es: "preparación física", "pt-BR": "preparação física", fr: "préparation physique", it: "preparazione fisica" },
    forbidden: {
      es: [/aire acondicionado/i, /combustible/i],
      "pt-BR": [/ar-condicionado/i, /combust[ií]vel/i],
      fr: [/climatisation/i, /carburant/i],
      it: [/aria condizionata/i, /carburante/i],
    },
  },
  {
    id: "stage",
    en: /\bStage \d\b/,
    preferred: { es: "etapa", "pt-BR": "etapa", fr: "étape", it: "fase" },
  },
  {
    id: "feedback",
    en: /\bfeedback\b/i,
    preferred: { es: "comentarios", "pt-BR": "feedback", fr: "retour", it: "feedback" },
    forbidden: {
      es: [/retroalimentaci[oó]n/i],
      "pt-BR": [/realimenta[cç][aã]o/i],
      fr: [/larmes/i, /retour de retour/i],
      it: [/retroazione/i],
    },
  },
  {
    id: "walking-around-weight",
    en: /\bwalking[- ]around weight\b/i,
    hint: "walking-around weight",
    preferred: { es: "peso fuera de competición", "pt-BR": "peso fora de competição", fr: "poids hors compétition", it: "peso fuori gara" },
    forbidden: {
      es: [/caminar por/i, /\bpaseo\b/i],
      "pt-BR": [/andar pela/i, /passeio/i],
      fr: [/faire le tour/i, /promenade/i],
      it: [/giro di camminata/i, /passeggiata/i],
    },
  },
];

const escapeRegExp = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Carries the English phrase's leading capital onto the prescribed translation. */
function matchCase(match, translation) {
  if (!/^\p{Lu}/u.test(match)) return translation;
  return translation.charAt(0).toLocaleUpperCase() + translation.slice(1);
}

/** Every phrase worth marking up in one English string, longest phrase first. */
function markupCandidates(locale) {
  const candidates = BRAND_TERMS.map((term) => ({ phrase: term, sensitive: true, translation: "" }));
  for (const entry of GLOSSARY) {
    if (!entry.hint) continue;
    const singular = entry.preferred[locale];
    const plural = entry.preferredPlural?.[locale];
    if (singular) candidates.push({ phrase: entry.hint, sensitive: false, translation: singular });
    if (plural) candidates.push({ phrase: `${entry.hint}s`, sensitive: false, translation: plural });
  }
  return candidates.sort((left, right) => right.phrase.length - left.phrase.length);
}

/**
 * Wraps brand terms and glossary phrases in the markup Azure Translator honours for
 * `textType=html`: `notranslate` leaves a product name alone, and `mstrans:dictionary`
 * pins a term to the translation this glossary prescribes.
 *
 * Matches are taken from the original text and never overlap, so a phrase is marked up
 * once and no replacement lands inside the markup of another.
 */
export function applyGlossaryMarkup(text, locale) {
  const spans = [];
  const covered = (start, end) => spans.some((span) => start < span.end && end > span.start);
  for (const { phrase, sensitive, translation } of markupCandidates(locale)) {
    const pattern = new RegExp(`\\b${escapeRegExp(phrase)}\\b`, sensitive ? "g" : "gi");
    for (const match of text.matchAll(pattern)) {
      const start = match.index;
      const end = start + match[0].length;
      if (covered(start, end)) continue;
      spans.push({
        start,
        end,
        value: translation
          ? `<mstrans:dictionary translation="${matchCase(match[0], translation)}">${match[0]}</mstrans:dictionary>`
          : `<span class="notranslate">${match[0]}</span>`,
      });
    }
  }
  return spans
    .sort((left, right) => right.start - left.start)
    .reduce((result, span) => `${result.slice(0, span.start)}${span.value}${result.slice(span.end)}`, text);
}

/** True when any glossary or brand markup survived the round trip through Azure. */
export function hasResidualMarkup(text) {
  return /mstrans:dictionary|class="notranslate"/i.test(text);
}

/**
 * Unwraps glossary and brand markup, keeping the text inside it. Azure normally
 * consumes the tags itself; this is the fallback for the batches where it echoes them.
 */
export function stripGlossaryMarkup(text) {
  return text
    .replace(/<mstrans:dictionary\b[^>]*>([\s\S]*?)<\/mstrans:dictionary>/gi, "$1")
    .replace(/<span\b[^>]*class=["']notranslate["'][^>]*>([\s\S]*?)<\/span>/gi, "$1");
}

/**
 * Brand terms present in the English string but missing from the translation — the
 * product name was translated as an ordinary word (UNLXCK read as "unlock", Quick
 * Build turned into "construction rapide").
 *
 * @returns {string[]}
 */
export function brandViolations(source, translation) {
  return BRAND_TERMS.filter((term) => {
    if (LOCALISABLE_BRAND_TERMS.has(term)) return false;
    if (!new RegExp(`\\b${escapeRegExp(term)}\\b`).test(source)) return false;
    return !new RegExp(`\\b${escapeRegExp(term)}\\b`, "i").test(translation);
  });
}

/**
 * Glossary defects in one translated string: a rendering listed as forbidden for a
 * term the English source actually uses.
 *
 * @returns {{ term: string, rendering: string }[]}
 */
export function glossaryViolations(source, translation, locale) {
  const violations = [];
  for (const entry of GLOSSARY) {
    if (!entry.en.test(source)) continue;
    if (entry.unless?.test(source)) continue;
    for (const pattern of entry.forbidden?.[locale] ?? []) {
      const match = pattern.exec(translation);
      if (match) violations.push({ term: entry.id, rendering: match[0] });
    }
  }
  return violations;
}
