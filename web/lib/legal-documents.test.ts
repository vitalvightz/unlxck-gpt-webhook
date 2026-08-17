import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { HEALTH_CONSENT_VERSION, TERMS_VERSION } from "@/lib/compliance";
import {
  LEGAL_DOCUMENTS,
  PRIVACY_HREF,
  PRIVACY_NOTICE,
  TERMS_HREF,
  TERMS_OF_USE,
  buildDataRequestMailto,
  getPrivacyContactEmail,
  type LegalDocument,
} from "@/lib/legal-documents";

/**
 * Anti-drift checks for the in-app legal copy.
 *
 * The canonical Terms and Privacy Notice live on the `docs/regulatory-intended-purpose`
 * branch. The app ships its own rendering of them so an athlete can read what
 * they are agreeing to at the moment they agree, which means two copies exist
 * and can diverge silently. These tests pin every substantive fact — the
 * processor list, the placeholders, the operator, the dates, the versions — so a
 * change to one has to be a deliberate change to the other.
 *
 * The final test upgrades automatically from "pinned facts" to a direct
 * comparison the moment the canonical markdown lands in this repo (it has not
 * yet — it is on the docs branch).
 */

const REPO_ROOT = path.resolve(process.cwd(), "..");

function allText(document: LegalDocument): string {
  return [
    document.title,
    document.status,
    document.intro,
    ...document.sections.flatMap((section) => [
      section.heading,
      ...(section.paragraphs ?? []),
      ...(section.bullets ?? []),
    ]),
  ].join("\n");
}

function everyDocumentText(): string {
  return LEGAL_DOCUMENTS.map(allText).join("\n");
}

// --- what may be published at all -------------------------------------------

test("only the Terms and the Privacy Notice are exposed in-app", () => {
  assert.deepEqual(
    LEGAL_DOCUMENTS.map((document) => document.slug).sort(),
    ["privacy-notice", "terms-of-use"],
  );
  assert.equal(TERMS_HREF, "/legal/terms-of-use");
  assert.equal(PRIVACY_HREF, "/legal/privacy-notice");
});

test("internal compliance documents never leak into athlete-facing copy", () => {
  // The DPIA, processor/DPA register, breach procedure, intended-purpose memo,
  // internal retention procedure and storage/tracking assessment are internal
  // controls. They are not written for athletes and must not be published.
  const published = everyDocumentText().toLowerCase();
  const internalOnly = [
    "dpia",
    "data protection impact assessment",
    "processor register",
    "dpa register",
    // "breach" alone is legitimate contract language in the Terms ("serious
    // breach of these Terms"); it is the internal *procedure* that must not be
    // published.
    "breach procedure",
    "breach-notification",
    "intended purpose",
    "intended-purpose",
    "regulatory boundary",
    "launch gate",
    "storage-access",
    "tracking assessment",
    "residual risk",
    "article 30",
  ];
  for (const phrase of internalOnly) {
    assert.ok(!published.includes(phrase), `athlete-facing copy must not mention "${phrase}"`);
  }
});

// --- processors --------------------------------------------------------------

test("the processor list matches the verified register exactly", () => {
  // Adding or removing a provider is a notice change and a register change.
  // Pinning the list here means one cannot happen without the other.
  const expected = ["Supabase", "OpenAI", "Vercel", "Hetzner", "Resend", "Cloudflare Turnstile"];
  const section = PRIVACY_NOTICE.sections.find((entry) => entry.heading === "Who we use");
  assert.ok(section?.bullets, "Privacy Notice should list processors");

  const named = section.bullets.map((bullet) => bullet.split(" — ")[0].trim());
  assert.deepEqual(named, expected);
});

test("Sentry is named nowhere — UNLXCK does not use it", () => {
  assert.ok(!everyDocumentText().toLowerCase().includes("sentry"));
});

test("the EU hosting locations are stated, not left vague", () => {
  const transfers = PRIVACY_NOTICE.sections.find(
    (entry) => entry.heading === "International transfers",
  );
  const text = (transfers?.paragraphs ?? []).join(" ");
  assert.ok(text.includes("Paris"), "Supabase region should be stated");
  assert.ok(text.includes("Nuremberg"), "backend region should be stated");
  assert.ok(/Standard Contractual Clauses|UK Addendum/.test(text), "safeguard should be named");
});

// --- stale pre-verification wording -----------------------------------------

test("wording that the completed verification made untrue is gone", () => {
  const published = everyDocumentText();
  const stale = [
    "will complete and document",
    "will be finalised before public launch",
    "must be finalised before this notice is used for public launch",
    "Launch status",
    "transfer safeguards and unresolved retention periods",
  ];
  for (const phrase of stale) {
    assert.ok(!published.includes(phrase), `stale wording still present: "${phrase}"`);
  }
});

test("retention is stated as rules rather than deferred", () => {
  const retention = PRIVACY_NOTICE.sections.find(
    (entry) => entry.heading === "How long we keep data",
  );
  const text = (retention?.paragraphs ?? []).join(" ");
  // The periods the internal policy actually defines.
  assert.ok(text.includes("90 days"), "screenshot retention should be stated");
  assert.ok(/irreversibly anonymise/i.test(text));
  // Log periods are genuinely still undefined in the policy, so the notice must
  // describe the rule without inventing a number.
  assert.ok(/as long as their security purpose requires/i.test(text));
  assert.ok(!/\blogs are kept for \d+/i.test(text), "do not state a log period we have not set");
});

// --- placeholders ------------------------------------------------------------

test("the two intended placeholders are present and are the only ones", () => {
  // Both are deliberate: no contact address has been decided yet, and inventing
  // one would be worse than showing it is outstanding.
  const published = everyDocumentText();
  assert.ok(published.includes("[ADD PRIVACY EMAIL BEFORE PUBLIC LAUNCH]"));
  assert.ok(published.includes("[LEGAL/CONTACT EMAIL]"));

  const bracketed = published.match(/\[[^\]]+\]/g) ?? [];
  assert.deepEqual(
    [...new Set(bracketed)].sort(),
    ["[ADD PRIVACY EMAIL BEFORE PUBLIC LAUNCH]", "[LEGAL/CONTACT EMAIL]"],
    "an unexpected placeholder is still in the published copy",
  );
});

test("the operator name is filled in and no longer a placeholder", () => {
  assert.ok(TERMS_OF_USE.intro.includes("operated by Unlxck"));
  assert.ok(!allText(TERMS_OF_USE).includes("[LEGAL OPERATOR NAME]"));
});

test("no data-request route is offered until a real address is configured", () => {
  // A mailto link to a placeholder would be a deletion route that silently
  // goes nowhere, which is worse than showing none.
  if (!getPrivacyContactEmail()) {
    assert.equal(buildDataRequestMailto("subject", "body"), null);
  }
});

// --- versions and dates ------------------------------------------------------

test("document versions track the consent versions the server records", () => {
  // A bumped document version re-collects consent, so these must not drift.
  assert.equal(TERMS_OF_USE.version, TERMS_VERSION);
  assert.equal(PRIVACY_NOTICE.version, HEALTH_CONSENT_VERSION);
});

test("the Terms carry an effective date and the notice a revision date", () => {
  assert.equal(TERMS_OF_USE.effectiveDate, "19 August 2026");
  assert.ok(PRIVACY_NOTICE.lastUpdated, "the notice should say when it was last revised");
  assert.equal(TERMS_OF_USE.lastUpdated, undefined);
});

// --- athlete-facing substance ------------------------------------------------

test("both documents keep the promises the product enforces", () => {
  const terms = allText(TERMS_OF_USE);
  // The under-18 weight-cut rule is enforced in code; the Terms state it.
  assert.ok(/under-18|under 18/.test(terms));
  assert.ok(/dehydration|water-cut/.test(terms));
  assert.ok(terms.includes("13"), "the 13+ eligibility floor should be stated");

  const privacy = allText(PRIVACY_NOTICE);
  assert.ok(privacy.includes("Article 9(2)(a)"), "the health-data lawful basis should be stated");
  assert.ok(/withdraw/i.test(privacy), "withdrawal should be explained");
  assert.ok(/Settings/.test(privacy), "the in-app route should be pointed to");
});

// --- direct comparison, once the canonical docs are in this repo --------------

test("in-app copy matches the canonical docs when they are present", () => {
  const canonical: Array<[LegalDocument, string]> = [
    [TERMS_OF_USE, path.join(REPO_ROOT, "docs", "terms-of-use.md")],
    [PRIVACY_NOTICE, path.join(REPO_ROOT, "docs", "privacy-notice.md")],
  ];

  const present = canonical.filter(([, file]) => existsSync(file));
  if (present.length === 0) {
    // Expected today: the canonical markdown lives on the docs branch and has
    // not merged into this one. The pinned-fact tests above are the check until
    // it does; this upgrades to a real comparison the moment the files land.
    return;
  }

  for (const [document, file] of present) {
    const markdown = readFileSync(file, "utf8");
    // The canonical Terms number their sections ("## 2. Eligibility"); the
    // in-app rendering does not, because the numbering carries no meaning once
    // the sections are cards on a page. Compare on the text alone.
    const headings = [...markdown.matchAll(/^##\s+(.+)$/gm)].map((match) =>
      match[1].trim().replace(/^\d+\.\s*/, ""),
    );
    const rendered = document.sections.map((section) => section.heading);

    for (const heading of headings) {
      // Internal-only trailing sections are deliberately not published.
      if (["Launch status", "Status", "About these Terms"].includes(heading)) {
        continue;
      }
      assert.ok(
        rendered.includes(heading),
        `${document.slug}: canonical section "${heading}" is missing from the in-app copy`,
      );
    }

    // A processor named in the canonical notice must be named in-app, and
    // vice versa — this is the drift that matters most.
    if (document.slug === "privacy-notice") {
      for (const provider of ["Supabase", "OpenAI", "Vercel", "Hetzner", "Resend", "Cloudflare"]) {
        assert.equal(
          markdown.includes(provider),
          allText(document).includes(provider),
          `${provider} appears in only one of the canonical notice and the in-app copy`,
        );
      }
      assert.equal(
        /sentry/i.test(markdown),
        /sentry/i.test(allText(document)),
        "Sentry appears in only one of the canonical notice and the in-app copy",
      );
    }
  }
});
