import Link from "next/link";

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
  "Hard days are spaced 48h apart so the nervous system recovers.",
  "Strength follows hard sparring on purpose, protecting skill quality for the next sparring day.",
  "Conditioning is round-specific (3 x 5 here), matching the fight's energy demands.",
];

export default function DemoPlanPage() {
  return (
    <>
      <section className="hero-panel welcome-panel">
        <div className="hero-panel-copy welcome-copy">
          <p className="eyebrow">Demo plan</p>
          <h1 className="hero-title">This is what a generated camp looks like.</h1>
          <p className="overview-command-summary">
            A sample week from a structured camp. Nothing is generated or saved.
          </p>
          <p className="muted welcome-context">
            Your own plan is shaped by your fight date, training days, restrictions and goals.
          </p>
          <div className="hero-actions welcome-actions">
            <Link href="/quick-build" className="cta">
              Build my plan
            </Link>
            <Link href="/" className="ghost-button">
              Back to dashboard
            </Link>
          </div>
        </div>
      </section>

      <section className="support-panel">
        <div className="form-section-header">
          <p className="kicker">Camp progress</p>
          <h2 className="form-section-title">Sample athlete setup</h2>
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
          <p className="kicker">Week 4 of 8 - SPP</p>
          <h2 className="form-section-title">Sample weekly structure</h2>
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
          <p className="kicker">Why this layout</p>
          <h2 className="form-section-title">Planner reasoning</h2>
        </div>
        <ul className="demo-coach-notes">
          {demoCoachNotes.map((note) => (
            <li key={note} className="muted">
              {note}
            </li>
          ))}
        </ul>
        <div className="hero-actions welcome-actions">
          <Link href="/quick-build" className="cta">
            Build my plan
          </Link>
        </div>
      </section>
    </>
  );
}
