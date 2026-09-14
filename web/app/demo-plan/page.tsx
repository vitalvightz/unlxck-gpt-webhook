import Link from "next/link";
import { useTranslations as useAppTranslations } from "next-intl";


const demoMeta = [
  { label: "Athlete", value: "Sample Fighter" },
  { label: "Discipline", value: "MMA / Muay Thai" },
  { label: "Fight date", value: "8 weeks out" },
  { label: "Rounds format", value: "3 x 5" },
  { label: "Training days", value: "Mon, Tue, Thu, Fri, Sat" },
  { label: "Sessions per week", value: "5" },
];

const demoWeek = [
  {
    weekday: "Mon",
    focus: "Hard sparring",
    summary: "Primary hard day. Live sparring + technical clean-up.",
    block: "Skill",
  },
  {
    weekday: "Tue",
    focus: "Strength",
    summary: "Max strength lower / upper push. Short conditioning finisher.",
    block: "S&C",
  },
  {
    weekday: "Wed",
    focus: "Recovery",
    summary: "Mobility, light pads, breathwork. No high-intent work.",
    block: "Recovery",
  },
  {
    weekday: "Thu",
    focus: "Technical sparring",
    summary: "Controlled sparring at 60-70%. Tactical drills.",
    block: "Skill",
  },
  {
    weekday: "Fri",
    focus: "Conditioning",
    summary: "Round-specific intervals matched to rounds format.",
    block: "S&C",
  },
  {
    weekday: "Sat",
    focus: "Hard sparring",
    summary: "Secondary hard day. Match-shape rounds + transitions.",
    block: "Skill",
  },
  {
    weekday: "Sun",
    focus: "Off",
    summary: "Full rest. Plan the next week and review notes.",
    block: "Off",
  },
] as const;

const demoCoachNotes = [
  "Hard days are spaced so the nervous system has 48h to recover before another high-intent session.",
  "Strength sits the day after hard sparring on purpose - it preserves the skill quality of the next sparring day.",
  "Conditioning is round-specific (3 x 5 here), so the energy systems trained match what the fight will demand.",
];

export default function DemoPlanPage() {
    const appText = useAppTranslations("AppText");
  return (
    <>
      <section className="hero-panel welcome-panel">
        <div className="hero-panel-copy welcome-copy">
          <p className="eyebrow">{appText("text_9763d47db810")}</p>
          <h1 className="hero-title">{appText("text_97e498d171af")}</h1>
          <p className="overview-command-summary">
            {appText("text_0b38b929f662")}</p>
          <p className="muted welcome-context">
            {appText("text_6945b8635a34")}</p>
          <div className="hero-actions welcome-actions">
            <Link href="/onboarding" className="cta">
              {appText("text_6b72880a3020")}</Link>
            <Link href="/quick-build" className="secondary-button">
              {appText("text_d3916772f715")}</Link>
            <Link href="/" className="ghost-button">
              {appText("text_b59e0c1cc1e1")}</Link>
          </div>
        </div>
      </section>

      <section className="support-panel">
        <div className="form-section-header">
          <p className="kicker">{appText("text_582cd02b9c74")}</p>
          <h2 className="form-section-title">{appText("text_ec02fff20ee0")}</h2>
        </div>
        <div className="overview-detail-grid">
          <div className="overview-detail-column">
            <div className="review-detail-list overview-detail-list">
              {demoMeta.map((item) => (
                <div key={item.label} className="review-detail-row">
                  <div className="overview-detail-heading">
                    <p className="review-detail-label">{item.label}</p>
                  </div>
                  <p className="review-detail-value">{item.value}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="support-panel">
        <div className="form-section-header">
          <p className="kicker">{appText("text_c706a522ada2")}</p>
          <h2 className="form-section-title">{appText("text_ec13f8eb67c7")}</h2>
        </div>
        <div className="demo-week-grid">
          {demoWeek.map((day) => (
            <article key={day.weekday} className="metric-card demo-week-card">
              <div className="demo-week-card-header">
                <span className="label">{day.weekday}</span>
                <span className="badge status-badge-neutral">{day.block}</span>
              </div>
              <p className="plan-card-title">{day.focus}</p>
              <p className="muted">{day.summary}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="support-panel">
        <div className="form-section-header">
          <p className="kicker">{appText("text_573c5bc7b999")}</p>
          <h2 className="form-section-title">{appText("text_0f821af72d93")}</h2>
        </div>
        <ul className="demo-coach-notes">
          {demoCoachNotes.map((note) => (
            <li key={note} className="muted">
              {note}
            </li>
          ))}
        </ul>
        <div className="hero-actions welcome-actions">
          <Link href="/onboarding" className="cta">
            {appText("text_6b72880a3020")}</Link>
          <Link href="/quick-build" className="secondary-button">
            {appText("text_d3916772f715")}</Link>
        </div>
      </section>
    </>
  );
}
