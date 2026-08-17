// The Terms of Use and Privacy Notice, rendered in-app.
//
// Canonical source: docs/terms-of-use.md and docs/privacy-notice.md on the
// `docs/regulatory-intended-purpose` branch. The app ships its own rendering so
// the documents are readable *inside* the product — consent is only informed if
// the athlete can read what they are agreeing to at the moment they agree, and a
// repository markdown file is not reachable from a phone at signup.
//
// The canonical markdown now lives in this repo, so legal-documents.test.ts
// compares the two copies directly rather than pinning facts about a file it
// could not see. Any edit here needs the same edit in docs/privacy-notice.md or
// docs/terms-of-use.md, and the Service providers and International transfers
// paragraphs are compared verbatim.
//
// When either document changes, update the text here and bump the matching
// version in api/compliance.py and web/lib/compliance.ts. Note which version:
// TERMS_VERSION and HEALTH_CONSENT_VERSION gate acceptance, so bumping either
// re-collects it from every athlete; PRIVACY_NOTICE_VERSION gates nothing and
// is the one to bump when the notice is corrected.
//
// The two remaining bracketed placeholders are real and intentional: no contact
// address has been decided, and inventing one would be worse than showing it is
// outstanding.

import { PRIVACY_NOTICE_VERSION, TERMS_VERSION } from "@/lib/compliance";

export type LegalSection = {
  heading: string;
  paragraphs?: string[];
  bullets?: string[];
};

export type LegalDocument = {
  slug: string;
  title: string;
  version: string;
  /** Terms only: the date this version takes effect. */
  effectiveDate?: string;
  /** Privacy Notice only: when the wording was last revised. */
  lastUpdated?: string;
  status: string;
  intro: string;
  sections: LegalSection[];
};

export const TERMS_OF_USE: LegalDocument = {
  slug: "terms-of-use",
  title: "Terms of Use",
  version: TERMS_VERSION,
  effectiveDate: "19 August 2026",
  status: "A contact address is still to be published.",
  intro:
    "These Terms govern use of UNLXCK, operated by Unlxck (“UNLXCK”, “we”, “us”). By creating an account or using UNLXCK, you agree to these Terms. Our Privacy Notice explains how we use personal data. Health-data consent is requested separately and is not part of accepting these Terms.",
  sections: [
    {
      heading: "Eligibility",
      paragraphs: [
        "UNLXCK is intended for users aged 13 or over. Users must provide accurate age information. Additional privacy and safety protections apply to users under 18. UNLXCK does not currently support accounts for children under 13.",
      ],
    },
    {
      heading: "The service",
      paragraphs: [
        "UNLXCK provides personalised combat-sport training and performance support. Features may include training plans, readiness check-ins, training adaptation, injury-aware exercise restrictions, nutrition and weight-management guidance, progress features and notifications.",
        "UNLXCK may modify, restrict or withhold app-prescribed training when information supplied by the athlete triggers its safety rules.",
      ],
    },
    {
      heading: "Not medical care",
      paragraphs: [
        "UNLXCK supports training, performance, recovery awareness and risk-aware exercise selection. It does not diagnose, treat, cure or prevent disease or injury; provide medical diagnosis, prognosis or medical clearance; or replace a doctor, physiotherapist or other appropriately qualified healthcare professional.",
        "A warning, restriction or recommendation is precautionary. The absence of a warning does not mean that training, sparring or competing is medically safe. Seek appropriate professional or emergency help where circumstances require it.",
      ],
    },
    {
      heading: "Your responsibilities",
      bullets: [
        "Provide information that is reasonably accurate and current.",
        "Use the service and safety guidance responsibly.",
        "Stop training and obtain appropriate help where symptoms or circumstances require it.",
        "Keep account credentials secure.",
        "Do not misuse, interfere with, reverse engineer, circumvent security controls or unlawfully access the service or another user’s data.",
      ],
      paragraphs: [
        "Combat training and competition involve inherent risks. UNLXCK does not control sparring, coaching, competition or training performed outside the service.",
      ],
    },
    {
      heading: "AI and automated adaptation",
      paragraphs: [
        "UNLXCK uses software rules and may use AI-assisted systems to generate or adapt parts of training guidance. Outputs may be incomplete or incorrect. AI cannot override UNLXCK’s server-owned safety restrictions and must not be treated as a clinical assessment.",
        "Recommendations may change when you provide new information or when the service’s rules are updated.",
      ],
    },
    {
      heading: "Users under 18",
      paragraphs: [
        "Under-18 use is subject to UNLXCK’s Children & Age-Appropriate Use Policy. UNLXCK applies additional privacy and safety safeguards to child users. High-risk dehydration, water-cut or aggressive weight-cut protocols are not provided to under-18 users.",
      ],
    },
    {
      heading: "Accounts and suspension",
      paragraphs: [
        "You are responsible for activity on your account. We may restrict or suspend access where reasonably necessary for security, abuse prevention, serious breach of these Terms or protection of users or the service. Where appropriate, we will provide notice and a reasonable explanation.",
      ],
    },
    {
      heading: "Privacy and health data",
      paragraphs: [
        "Our Privacy Notice explains the personal data we collect, why we use it, recipients, retention and your rights. Where UNLXCK relies on explicit consent to process health information, that consent is obtained separately and may be withdrawn as explained in the Privacy Notice. Withdrawal may prevent health-dependent personalisation from continuing.",
      ],
    },
    {
      heading: "Intellectual property",
      paragraphs: [
        "UNLXCK and its software, branding, design and proprietary service content are protected by applicable intellectual-property rights. You retain rights in content you submit. You grant UNLXCK the limited rights necessary to host, process and use that content to operate the service in accordance with these Terms and the Privacy Notice.",
      ],
    },
    {
      heading: "Availability and changes",
      paragraphs: [
        "We may update, improve, remove or replace service features. We do not promise uninterrupted or error-free availability. Material changes affecting users will be communicated where required by law.",
      ],
    },
    {
      heading: "Liability",
      paragraphs: [
        "Nothing in these Terms excludes or limits liability where doing so would be unlawful, including liability that cannot lawfully be excluded under UK consumer law.",
        "To the extent permitted by law, UNLXCK is not responsible for losses that were not reasonably foreseeable when these Terms were agreed or that result from misuse of the service, inaccurate information supplied by a user, or activities outside UNLXCK’s reasonable control.",
        "Nothing in these Terms removes your statutory consumer rights.",
      ],
    },
    {
      heading: "Paid services",
      paragraphs: [
        "If UNLXCK introduces paid subscriptions or purchases, applicable price, payment, renewal, cancellation and refund information will be provided before purchase. Any additional paid-service terms will form part of the agreement where accepted.",
      ],
    },
    {
      heading: "Ending your account",
      paragraphs: [
        "You may stop using UNLXCK and request account deletion through the route identified in the Privacy Notice. We may terminate an account for serious or repeated breach, unlawful use or where reasonably necessary to protect the service or its users. Personal data following closure is handled under the Privacy Notice and retention policy.",
      ],
    },
    {
      heading: "Changes to these Terms",
      paragraphs: [
        "We may update these Terms as the service or law changes. Where a change materially affects your rights or obligations, we will provide appropriate notice and, where required, obtain fresh agreement.",
      ],
    },
    {
      heading: "Law and disputes",
      paragraphs: [
        "These Terms are governed by the laws of England and Wales, subject to any mandatory consumer protections that apply where you live. Nothing in these Terms removes rights you have under applicable consumer law.",
      ],
    },
    {
      heading: "Contact",
      paragraphs: [
        "Questions or complaints about these Terms can be sent to [LEGAL/CONTACT EMAIL].",
      ],
    },
  ],
};

export const PRIVACY_NOTICE: LegalDocument = {
  slug: "privacy-notice",
  title: "Privacy Notice",
  version: PRIVACY_NOTICE_VERSION,
  lastUpdated: "19 August 2026",
  status: "A privacy contact address is still to be published.",
  intro:
    "UNLXCK uses personal data to create, adapt and deliver personalised training guidance. This notice explains what we use, why, who receives it and your rights.",
  sections: [
    {
      heading: "Who we are",
      paragraphs: [
        "UNLXCK is the controller of personal data used to provide the UNLXCK service.",
        "Privacy contact: [ADD PRIVACY EMAIL BEFORE PUBLIC LAUNCH]",
      ],
    },
    {
      heading: "What we collect",
      bullets: [
        "Account and profile data such as name, email, age, sex, height, weight, sport, goals and schedule.",
        "Training data such as sessions, completion, RPE, notes and plans.",
        "Health-related data such as injuries, pain, soreness, fatigue, sleep, readiness, symptoms and recovery information.",
        "Nutrition and weight-management data, including bodyweight, target weight, appetite, supplements and caffeine.",
        "Feedback, screenshots and support information.",
        "Device, notification, security and diagnostic data.",
      ],
      paragraphs: ["Health information is special-category personal data under UK data-protection law."],
    },
    {
      heading: "Why we use it",
      bullets: [
        "Create and adapt training plans.",
        "Provide readiness, injury, recovery, nutrition and weight-management features.",
        "Restrict or change training where safety rules indicate this is appropriate.",
        "Explain training decisions and maintain training history.",
        "Send requested service and safety notifications.",
        "Operate accounts, prevent abuse, troubleshoot problems and improve UNLXCK.",
      ],
      paragraphs: [
        "UNLXCK is a performance and wellbeing service. It is not intended to diagnose, treat or replace professional medical care.",
      ],
    },
    {
      heading: "Lawful bases",
      paragraphs: [
        "We rely on three lawful bases, depending on what the processing is for.",
        "Article 6(1)(b) UK GDPR (contract) — for the personal data we need in order to provide the service you have asked for: your account, profile, intake, plans, sessions and training history.",
        "Article 6(1)(f) UK GDPR (legitimate interests) — for keeping UNLXCK secure and available, preventing abuse of signup and login, investigating faults, and improving the service. Our interests are running a secure, reliable product and making it work better for athletes. We have weighed those interests against your rights, and you can object to this processing at any time.",
        "Article 9(2)(a) UK GDPR (explicit consent) — for health information: injuries, pain, soreness, fatigue, sleep, readiness and bodyweight, used for personalised training and safety features. This consent is asked for separately, is optional, and can be withdrawn at any time.",
        "We do not use your health information to improve UNLXCK. It is used to build and adapt your own training and to apply safety rules to it. Where we look at how the product is performing, we do that without using health information.",
        "Withdrawing consent does not affect processing already carried out lawfully, but UNLXCK may be unable to provide features that require health data afterwards.",
      ],
    },
    {
      heading: "AI and automated adaptation",
      paragraphs: [
        "UNLXCK uses software rules and AI-assisted processing to help generate and adapt training guidance from the information you provide. Relevant plan context may be sent to service providers supporting this processing.",
        "These systems may change, restrict or withhold training guidance. We have assessed whether that is a decision based solely on automated processing with legal or similarly significant effects under Article 22 UK GDPR, and concluded it is not: it changes what training UNLXCK suggests to you, not your legal position or your access to anything comparable, and you remain free to train differently. We keep that assessment under review, and apply it more cautiously to athletes under 18.",
        "If you think an automated adaptation has got something wrong, contact us using the privacy contact above and a person will look at it.",
      ],
    },
    {
      heading: "Service providers",
      paragraphs: [
        "We use trusted service providers to run UNLXCK, including hosting, databases, AI processing, email and security services. We only share the information they need to provide those services and require appropriate data-protection safeguards.",
      ],
    },
    {
      heading: "International transfers",
      paragraphs: [
        "Some service providers may process limited data outside the UK. Where this creates a restricted transfer, we use approved safeguards, such as the UK Addendum to the Standard Contractual Clauses, and keep a record of the safeguard that applies. You can ask us for a copy of the safeguard we rely on using the privacy contact above.",
      ],
    },
    {
      heading: "How long we keep data",
      paragraphs: [
        "We keep identifiable data only for as long as needed for the purpose it was collected for, then delete it or irreversibly anonymise it.",
        "Your account, profile, intake, plans, training history, injury, readiness and nutrition data are kept while they are needed to provide the service, and are deleted or reviewed for deletion when your account closes or you ask us to delete it.",
        "Feedback is kept while it is needed for support and product improvement, then anonymised or deleted. Beta screenshots are kept for no more than 90 days.",
        "Security and audit logs are kept only for as long as their security purpose requires. Backups are removed on their normal expiry cycle, and data deleted from the live service is not restored back into ordinary use.",
      ],
    },
    {
      heading: "Your rights",
      bullets: [
        "Access your personal data.",
        "Correct inaccurate data.",
        "Request deletion.",
        "Restrict processing.",
        "Receive portable data.",
        "Object to processing we carry out under legitimate interests.",
        "Withdraw consent at any time where processing relies on consent.",
      ],
      paragraphs: [
        "The right to object applies to the processing we carry out under legitimate interests — security, abuse prevention, fault investigation and service improvement. Tell us and we will stop, unless we can show compelling grounds that override your interests. It does not cover what we have to process to provide the service under our agreement with you; for health information, withdraw your consent instead, which you can do at any time without giving a reason.",
        "Requests can be made using the privacy contact above, or from Settings → Privacy. We may verify identity where reasonably necessary.",
      ],
    },
    {
      heading: "Users under 18",
      paragraphs: [
        "Under-18 accounts get high-privacy defaults and additional safety rules. UNLXCK does not provide aggressive weight-cut, dehydration or water-cut guidance to athletes under 18.",
      ],
    },
    {
      heading: "How to reach us",
      paragraphs: [
        "You can exercise any of these rights, or ask a question about this notice, using the privacy contact at the top of this page. In the app you can also review and change your health-data consent, and request account deletion, from Settings → Privacy.",
      ],
    },
    {
      heading: "Complaints",
      paragraphs: [
        "Please contact UNLXCK first if you have a privacy concern. You also have the right to complain to the UK Information Commissioner’s Office (ICO).",
      ],
    },
    {
      heading: "Changes",
      paragraphs: [
        "We will review this notice when our data uses, processors or legal requirements materially change. Where a new use of your personal data requires notice, we will tell you before that processing begins.",
      ],
    },
  ],
};

export const LEGAL_DOCUMENTS: readonly LegalDocument[] = [TERMS_OF_USE, PRIVACY_NOTICE];

export const TERMS_HREF = `/legal/${TERMS_OF_USE.slug}`;
export const PRIVACY_HREF = `/legal/${PRIVACY_NOTICE.slug}`;

/**
 * Where a data-rights request goes.
 *
 * The Privacy Notice still carries a placeholder contact address, so this reads
 * the address from the environment instead of hard-coding one. When it is unset
 * the UI points the athlete at in-app feedback rather than offering a mailto
 * link that goes nowhere.
 */
export function getPrivacyContactEmail(): string {
  return (process.env.NEXT_PUBLIC_PRIVACY_CONTACT_EMAIL ?? "").trim();
}

export function buildDataRequestMailto(subject: string, body: string): string | null {
  const address = getPrivacyContactEmail();
  if (!address) {
    return null;
  }
  return `mailto:${address}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}
