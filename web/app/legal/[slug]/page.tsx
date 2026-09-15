import Link from "next/link";
import { notFound } from "next/navigation";

import { LEGAL_DOCUMENTS } from "@/lib/legal-documents";
import { getTranslations } from "next-intl/server";
import { translateUiText } from "@/i18n/ui-text";


// Static routes for the two documents, so they are reachable without a session
// (an athlete has to be able to read the Terms *before* accepting them).
export function generateStaticParams() {
  return LEGAL_DOCUMENTS.map((document) => ({ slug: document.slug }));
}

export default async function LegalDocumentPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const appText = await getTranslations("AppText");
  const { slug } = await params;
  const document = LEGAL_DOCUMENTS.find((entry) => entry.slug === slug);
  if (!document) {
    notFound();
  }

  return (
    <section className="panel legal-document">
      <p className="kicker">{appText("text_3a8b686fee0a")}</p>
      <h1>{translateUiText(appText, document.title)}</h1>
      <p className="muted">
        {appText("text_dd167905de0d")}{document.version}
        {document.effectiveDate ? ` · Effective ${document.effectiveDate}` : ""}
        {document.lastUpdated ? ` · Last updated ${document.lastUpdated}` : ""}
        {document.status ? ` · ${document.status}` : ""}
      </p>
      <p className="muted">{appText("text_ce1c2f8c6b2a")}</p>
      <p>{translateUiText(appText, document.intro)}</p>

      {document.sections.map((section) => (
        <section key={section.heading} className="legal-document-section">
          <h2>{translateUiText(appText, section.heading)}</h2>
          {section.bullets ? (
            <ul className="summary-list">
              {section.bullets.map((bullet) => (
                <li key={bullet}>{translateUiText(appText, bullet)}</li>
              ))}
            </ul>
          ) : null}
          {(section.paragraphs ?? []).map((paragraph) => (
            <p key={paragraph}>{translateUiText(appText, paragraph)}</p>
          ))}
        </section>
      ))}

      <p className="muted">
        <Link href="/settings#privacy" className="auth-text-link">
          {appText("text_ea37ec29c386")}</Link>
      </p>
    </section>
  );
}
