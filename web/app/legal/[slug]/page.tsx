import Link from "next/link";
import { notFound } from "next/navigation";

import { LEGAL_DOCUMENTS } from "@/lib/legal-documents";

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
  const { slug } = await params;
  const document = LEGAL_DOCUMENTS.find((entry) => entry.slug === slug);
  if (!document) {
    notFound();
  }

  return (
    <section className="panel legal-document">
      <p className="kicker">UNLXCK</p>
      <h1>{document.title}</h1>
      <p className="muted">
        Version {document.version} · {document.status}
      </p>
      <p>{document.intro}</p>

      {document.sections.map((section) => (
        <section key={section.heading} className="legal-document-section">
          <h2>{section.heading}</h2>
          {section.bullets ? (
            <ul className="summary-list">
              {section.bullets.map((bullet) => (
                <li key={bullet}>{bullet}</li>
              ))}
            </ul>
          ) : null}
          {(section.paragraphs ?? []).map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
        </section>
      ))}

      <p className="muted">
        <Link href="/settings#privacy" className="auth-text-link">
          Back to Settings
        </Link>
      </p>
    </section>
  );
}
