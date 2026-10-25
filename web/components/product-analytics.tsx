"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useAppSession } from "@/components/auth-provider";
import { getProductAnalytics, getAthleteActivity } from "@/lib/api";
import { formatAppDateTime } from "@/lib/date-format";
import {
  humanize,
  percent,
  type ProductReport,
  type AthleteActivity,
} from "@/lib/product-analytics";
import styles from "./product-analytics.module.css";
const stamp = (s: string | null) =>
  s ? formatAppDateTime(s) : "No recorded activity";
function Metric({
  label,
  value,
  definition,
}: {
  label: string;
  value: string | number | null;
  definition: string;
}) {
  return (
    <article className={styles.metric}>
      <h3 title={definition}>{label}</h3>
      <strong>{value ?? "—"}</strong>
      <p>{definition}</p>
    </article>
  );
}
export function ProductAnalytics() {
  const { session } = useAppSession();
  const token = session?.access_token;
  const [days, setDays] = useState(30);
  const [status, setStatus] = useState("");
  const [sport, setSport] = useState("");
  const [planMode, setPlanMode] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<ProductReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({
      days: String(days),
      offset: String(offset),
    });
    if (status) params.set("professional_status", status);
    if (sport) params.set("sport", sport);
    if (planMode) params.set("plan_mode", planMode);
    getProductAnalytics(token, params.toString(), controller.signal)
      .then(setData)
      .catch((e) => {
        if (!controller.signal.aborted)
          setError(
            e instanceof Error ? e.message : "Unable to load analytics.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [token, days, status, sport, planMode, offset, reload]);
  return (
    <section className={`panel ${styles.root}`}>
      <div className="section-heading">
        <div>
          <p className="kicker">Admin / B2C athletes</p>
          <h1>Product Analytics</h1>
          <p className="muted">Verified actions. Clearer product decisions.</p>
        </div>
        <Link className="ghost-button" href="/admin">
          Operational dashboard
        </Link>
      </div>
      <nav className={styles.nav} aria-label="Analytics sections">
        {[
          "Overview",
          "Engagement & Retention",
          "Feature Adoption",
          "Conversion & Drop-offs",
          "Athlete Activity",
          "Errors & Friction",
        ].map((s, i) => (
          <a key={s} href={`#analytics-${i}`}>
            {s}
          </a>
        ))}
      </nav>
      <div className={styles.filters}>
        <label>
          Period
          <select
            value={days}
            onChange={(e) => {
              setDays(Number(e.target.value));
              setOffset(0);
            }}
          >
            {[7, 30, 90, 0].map((n) => (
              <option key={n} value={n}>
                {n ? `${n} days` : "All time"}
              </option>
            ))}
          </select>
        </label>
        <label>
          Fighter status
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All</option>
            {data?.segments.professional_status.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label>
          Combat sport
          <select
            value={sport}
            onChange={(e) => {
              setSport(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All</option>
            {data?.segments.sports.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label>
          Plan usage
          <select
            value={planMode}
            onChange={(e) => {
              setPlanMode(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All</option>
            <option value="plan">Usable plan recorded</option>
            <option value="plan_free">No usable plan recorded</option>
          </select>
        </label>
      </div>
      {loading ? <p role="status">Loading verified activity…</p> : null}
      {error ? (
        <div role="alert">
          <p>{error}</p>
          <button
            className="secondary-button"
            onClick={() => setReload((n) => n + 1)}
          >
            Retry
          </button>
        </div>
      ) : null}
      {!loading && !error && data ? (
        <>
          <p className="muted">
            UTC calendar days · Updated {stamp(data.as_of)} · Admin and
            explicitly excluded internal accounts omitted. Acquisition channel:
            unavailable.
          </p>
          <details className={styles.note}>
            <summary>Definitions & historical coverage</summary>
            <p>
              Meaningful activity includes starting or completing training,
              saving a sparring log, check-in, custom plan, session feedback,
              timer interaction or nutrition save. Sign-ins, views, profile
              updates and generated plans are excluded. Existing records retain
              their original timestamps; missing interaction history is unknown.
              Optional browser events require consent and expire after 180 days.
              Discovery, plan edit and nutrition save counts are deduplicated
              per feature, resource and UTC day. Counts represent recorded
              evidence and may undercount usage.
            </p>
            <p>
              Period filters use today and the preceding N−1 UTC days.
              DAU/WAU/MAU always use rolling 1/7/30 calendar-day windows.
              Cohorts use signup dates in the selected period; Dn means return
              on exactly signup day+n. Only fully elapsed return days enter the
              denominator. Repeat feature use requires meaningful actions on at
              least two distinct UTC days. Manual training saves represent
              completed logs, not observed starts. Onboarding completion means
              the compliant athlete saved a starting-path choice; a draft save
              or that choice records a start. No usable plan recorded does not
              establish an athlete’s intention to remain plan-free.
            </p>
          </details>
          {!data.registered ? (
            <p>No eligible athletes match these filters.</p>
          ) : null}
          <section id="analytics-0">
            <h2>Overview</h2>
            <div className={styles.grid}>
              <Metric
                label="Active athletes"
                value={data.active}
                definition="Distinct athletes with a meaningful action in the selected period."
              />
              <Metric
                label="Registered athletes"
                value={data.registered}
                definition="All eligible registered athletes, after segment filters."
              />
              <Metric
                label="Activated athletes"
                value={data.ever_active}
                definition="Athletes with at least one recorded meaningful action, all time."
              />
              <Metric
                label="Average active days"
                value={data.average_active_days}
                definition="Meaningful athlete-days in the period / all eligible registered athletes."
              />
              <Metric
                label="Sessions started"
                value={data.sessions_started}
                definition="Persisted strength sessions whose observed start falls in the period."
              />
              <Metric
                label="Sessions completed"
                value={data.sessions_completed}
                definition="Completed or modified strength sessions and saved manual training logs in the period."
              />
            </div>
          </section>
          <section id="analytics-1">
            <h2>Engagement & Retention</h2>
            <div className={styles.grid}>
              {(["dau", "wau", "mau"] as const).map((k) => (
                <Metric
                  key={k}
                  label={k.toUpperCase()}
                  value={data[k]}
                  definition={`Distinct meaningful athletes over ${k === "dau" ? 1 : k === "wau" ? 7 : 30} UTC calendar days, including today.`}
                />
              ))}
              <Metric
                label="Stickiness"
                value={percent(data.stickiness)}
                definition="DAU / MAU. No denominator means insufficient data."
              />
              <Metric
                label="New / returning active"
                value={`${data.new_active} / ${data.returning_active}`}
                definition="New: first recorded meaningful action in this period. Returning: first recorded action before it."
              />
              <Metric
                label="Previous-period active"
                value={data.previous_active}
                definition="Distinct active athletes in the preceding equal-length period; unavailable for all time."
              />
              {[1, 7, 30].map((n) => (
                <Metric
                  key={n}
                  label={`D${n} retention`}
                  value={percent(data.retention[n].percent)}
                  definition={`${data.retention[n].returned} returned / ${data.retention[n].eligible} signup-cohort athletes with a fully observed return day.`}
                />
              ))}
              {[7, 14, 30].map((n) => (
                <Metric
                  key={n}
                  label={`Inactive ${n}+ days`}
                  value={data.inactive[n]}
                  definition="Previously active athletes with no recorded action for at least this duration. Never-active athletes counted separately."
                />
              ))}
              <Metric
                label="Never active"
                value={data.never_active}
                definition="Eligible registered athletes without any recorded meaningful action."
              />
            </div>
            <h3>Daily meaningful athletes</h3>
            <div
              className={styles.trend}
              role="img"
              aria-label="Daily meaningful active athletes; exact counts in expandable details"
            >
              {data.trend.map((d) => (
                <div
                  key={d.day}
                  title={`${d.day}: ${d.athletes}`}
                  style={{
                    height: `${Math.max(2, (d.athletes / Math.max(1, ...data.trend.map((x) => x.athletes))) * 100)}%`,
                  }}
                />
              ))}
            </div>
            <details>
              <summary>Daily counts</summary>
              {data.trend.length ? (
                data.trend.map((d) => (
                  <p key={d.day}>
                    {d.day}: {d.athletes}
                  </p>
                ))
              ) : (
                <p>No recorded activity in this period.</p>
              )}
            </details>
            <div className={styles.table}>
              <table>
                <caption>Weekly signup cohorts · exact UTC return days</caption>
                <thead>
                  <tr>
                    <th>Week of</th>
                    <th>Signups</th>
                    {[1, 7, 30].map((n) => (
                      <th key={n}>D{n}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.cohorts.map((c) => (
                    <tr key={c.week}>
                      <td>{c.week}</td>
                      <td>{c.signups}</td>
                      {[1, 7, 30].map((n) => (
                        <td
                          key={n}
                          title={`${c.retention[n].returned}/${c.retention[n].eligible} eligible`}
                        >
                          {percent(c.retention[n].percent)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section id="analytics-2">
            <h2>Feature Adoption</h2>
            <p className="muted">
              Ranked by unique meaningful athletes / all {data.registered}{" "}
              eligible athletes. Discovery is separate from successful use.
            </p>
            {data.features.map((f) => (
              <div key={f.feature} className={styles.feature}>
                <progress
                  max={100}
                  value={f.percent ?? 0}
                  aria-label={`${f.feature} adoption`}
                />
                <details>
                  <summary>
                    <span>{humanize(f.feature)}</span>
                    <span>
                      {f.athletes} athletes · {percent(f.percent)}
                    </span>
                  </summary>
                  <p>
                    {f.uses} actions · {f.repeat_athletes} repeat athletes ·{" "}
                    {f.discovered} athletes opened feature
                  </p>
                  {Object.entries(f.actions).map(([a, n]) => (
                    <p key={a}>
                      {humanize(a)}: {n}
                    </p>
                  ))}
                  {f.completion ? (
                    <p>
                      {f.completion_label
                        ? f.completion_label
                        : f.feature === "plans"
                          ? "Generated plans subsequently completed in training"
                          : "Matched starts completed"}
                      : {f.completion.completed} / {f.completion.started} ·{" "}
                      {percent(f.completion.percent)}
                    </p>
                  ) : (
                    <p>
                      Completion rate unavailable: no separate observed start
                      for this saved action.
                    </p>
                  )}
                  {f.observed_early_exits !== undefined ? (
                    <p>Observed early exits: {f.observed_early_exits}</p>
                  ) : null}
                  {!f.uses && !f.discovered ? (
                    <p>
                      No recorded evidence. Missing historical tracking is not
                      proof of non-use.
                    </p>
                  ) : null}
                </details>
              </div>
            ))}
          </section>
          <section id="analytics-3">
            <h2>Conversion & Drop-offs</h2>
            <p className="muted">
              Signup-cohort conversions. Onboarding stages use server-owned
              workflow timestamps recorded prospectively. Plan-free onboarding
              does not require a generated plan.
            </p>
            <div className={styles.grid}>
              {[...data.conversions, ...data.funnel].map((c) => (
                <Metric
                  key={c.label}
                  label={c.label}
                  value={percent(c.percent)}
                  definition={`${c.converted} / ${c.eligible} eligible${c.median_seconds === null ? "" : ` · median ${Math.round(c.median_seconds / 60)} minutes`}`}
                />
              ))}
            </div>
            <details>
              <summary>Observed drop-offs</summary>
              {Object.entries(data.dropoffs).map(([k, v]) => (
                <p key={k}>
                  {humanize(k)}: {v}
                </p>
              ))}
              <p>
                Session starts without completion after 24 hours:{" "}
                {data.observed_session_abandonments}. These are unresolved
                observed starts, not inferred intent. Current-day onboarding
                drop-offs may still be in progress.
              </p>
            </details>
          </section>
          <section id="analytics-4">
            <h2>Athlete Activity</h2>
            <p className="muted">
              Admin-only recorded activity. Open a profile for its chronological
              timeline.
            </p>
            <div className={styles.table}>
              <table>
                <thead>
                  <tr>
                    <th>Athlete</th>
                    <th>First action</th>
                    <th>Last action</th>
                    <th>Active days 7 / 30</th>
                    <th>Inactive days</th>
                    <th>Observed signals</th>
                  </tr>
                </thead>
                <tbody>
                  {data.athletes.map((p) => (
                    <tr key={p.id}>
                      <td>
                        <Link href={`/admin/athletes/${p.id}`}>
                          {p.id.slice(0, 8)}
                        </Link>
                      </td>
                      <td>{stamp(p.first_activity)}</td>
                      <td>{stamp(p.last_activity)}</td>
                      <td>
                        {p.active_days_7} / {p.active_days_30}
                      </td>
                      <td>{p.inactivity_days ?? "No recorded activity"}</td>
                      <td>{p.signals?.join(" · ") || "None recorded"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className={styles.filters}>
              <button
                disabled={!offset}
                onClick={() => setOffset(Math.max(0, offset - 25))}
              >
                Previous
              </button>
              <span>{data.athlete_total} athletes</span>
              <button
                disabled={offset + 25 >= data.athlete_total}
                onClick={() => setOffset(offset + 25)}
              >
                Next
              </button>
            </div>
          </section>
          <section id="analytics-5">
            <h2>Errors & Friction</h2>
            <p className="muted">
              Failed generation jobs use existing diagnostics. Other operation
              failures are observed prospectively; Sentry remains the source for
              frontend exceptions. No failure or abandonment is inferred from
              missing events.
            </p>
            {data.errors.length ? (
              data.errors.map((e) => (
                <p key={e.feature + e.category}>
                  {humanize(e.feature)} / {humanize(e.category)}: {e.count}{" "}
                  errors · {e.affected_athletes} athletes ·{" "}
                  {e.errors_per_athlete} per affected athlete
                </p>
              ))
            ) : (
              <p>
                No recorded failures in this period. This does not imply
                complete historical error coverage.
              </p>
            )}
            {data.friction_followup.map((f) => (
              <p key={f.feature + f.category}>
                {humanize(f.feature)} / {humanize(f.category)}:{" "}
                {f.no_recorded_return_7d} / {f.eligible_athletes} eligible
                affected athletes had no recorded return within 7 days of their
                last observed error. Only fully elapsed windows; this does not
                establish causation.
              </p>
            ))}
            <Link className="secondary-button" href="/admin">
              Investigate generation jobs & existing diagnostics
            </Link>
          </section>
        </>
      ) : null}
    </section>
  );
}
export function AthleteActivityPanel({ athleteId }: { athleteId: string }) {
  const { session } = useAppSession();
  const token = session?.access_token;
  const [data, setData] = useState<AthleteActivity | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getAthleteActivity(token, athleteId, offset, controller.signal)
      .then(setData)
      .catch((e) => {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : "Unable to load activity.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [token, athleteId, offset]);
  return (
    <article className={`step-card ${styles.root}`}>
      <h2>Activity</h2>
      {error ? (
        <p role="alert">{error}</p>
      ) : loading ? (
        <p role="status">Loading activity…</p>
      ) : data ? (
        <>
          <div className={styles.grid}>
            <Metric
              label="Registered"
              value={stamp(data.summary.registered_at)}
              definition="Account registration timestamp."
            />
            <Metric
              label="First meaningful action"
              value={stamp(data.summary.first_activity)}
              definition="Earliest verified meaningful action."
            />
            <Metric
              label="Latest meaningful activity"
              value={stamp(data.summary.last_activity)}
              definition="Latest verified action, excluding generated plans and profile updates."
            />
            <Metric
              label="Active days 7 / 30"
              value={`${data.summary.active_days_7} / ${data.summary.active_days_30}`}
              definition="Distinct UTC days with meaningful activity."
            />
            <Metric
              label="Sessions started / completed"
              value={`${data.sessions_started} / ${data.sessions_completed}`}
              definition="Observed strength starts / completed strength and manual training logs, all time."
            />
            <Metric
              label="Inactivity days"
              value={data.summary.inactivity_days}
              definition="UTC calendar days since last recorded action; dash means no recorded activity."
            />
          </div>
          <details>
            <summary>Observed engagement signals</summary>
            {data.summary.signals?.length ? (
              data.summary.signals.map((signal) => <p key={signal}>{signal}</p>)
            ) : (
              <p>
                No observed drop-off signals. Missing historical data is not
                proof of successful engagement.
              </p>
            )}
          </details>
          <details>
            <summary>Feature usage counts</summary>
            {data.features.map((f) => (
              <p key={f.feature}>
                {humanize(f.feature)}: {f.uses} meaningful actions
              </p>
            ))}
          </details>
          <details>
            <summary>Latest plan interactions</summary>
            {data.latest_plan_interactions.map((p) => (
              <p key={p.id}>
                {stamp(p.occurred_at)} · {humanize(p.action)}
              </p>
            ))}
          </details>
          <h3>Meaningful activity timeline</h3>
          {data.timeline.length ? (
            <ol>
              {data.timeline.map((e) => (
                <li key={`${e.id}:${e.feature}`}>
                  <time>{stamp(e.occurred_at)}</time> · {humanize(e.feature)} ·{" "}
                  {humanize(e.action)}
                </li>
              ))}
            </ol>
          ) : (
            <p>No recorded activity</p>
          )}
          <div className={styles.filters}>
            <button
              disabled={!offset}
              onClick={() => setOffset(Math.max(0, offset - 50))}
            >
              Previous
            </button>
            <button
              disabled={data.timeline.length < 50}
              onClick={() => setOffset(offset + 50)}
            >
              Next
            </button>
          </div>
        </>
      ) : null}
    </article>
  );
}
