"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ApiError, getTrainingLibraryEntry, searchTrainingLibrary } from "@/lib/api";
import type { LibraryEntry, LibraryPreview, LibrarySearchResponse } from "@/lib/api-schema.generated";
import { ExerciseDemo } from "./exercise-demo";
import { ExerciseGlyphIcon, type ExerciseGlyphName } from "./exercise-glyph";
import { demoThumbnailUrl } from "@/lib/exercise-demo";
import { InjuryDetailSheet } from "./today/injury-detail-sheet";
import styles from "./training-library.module.css";

type Category = LibraryEntry["category"];
const filterLabels = { type: "Training type", goal: "Goal", sport: "Sport", equipment: "Equipment", body_focus: "Body focus" };
const contentTypes: Record<string, { label: string; icon: ExerciseGlyphName }> = {
  strength_power: { label: "Strength & power", icon: "strength" }, conditioning: { label: "Conditioning", icon: "conditioning" },
  technical_coordination: { label: "Technical drills", icon: "skill" }, rehabilitation: { label: "Rehabilitation", icon: "rehab" },
  care_instruction: { label: "Care", icon: "recovery" }, tactical_educational: { label: "Tactical study", icon: "tactical" },
  visualisation: { label: "Visualisation", icon: "visualisation" },
};
type Filters = Partial<Record<keyof typeof filterLabels, string>>;
const boundaries: Record<Category, string> = {
  training: "Discovery only. Injury, phase, equipment and programming checks still apply.",
  rehab: "Rehab pathway only. Your current stage and clinical clearance still apply.",
  learn: "For learning and care. These entries are not workout exercises.",
};
const readable = (value: string) => value.replaceAll("_", " ").replaceAll("-", " ");
const equipmentText = (entry: LibraryEntry) => entry.equipment === null ? "Equipment unspecified"
  : entry.equipment.length ? entry.equipment.map(readable).join(" · ") : "No equipment";

function DrillPreview({ entry, token, onClose }: { entry: LibraryEntry; token: string; onClose: () => void }) {
  const [detail, setDetail] = useState<LibraryPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void getTrainingLibraryEntry(token, entry.catalogue_id, controller.signal).then(value => {
      if (!controller.signal.aborted) setDetail(value);
    }).catch(reason => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Unable to load drill.");
    });
    return () => controller.abort();
  }, [entry.catalogue_id, token, retry]);
  const current = detail ?? entry;
  return <InjuryDetailSheet title={current.name} onClose={onClose} closeLabel="Close drill preview">
    <div className={`injury-sheet-body ${styles.preview}`}>
      <p className={styles.meta}>{current.context} · {equipmentText(current)}</p>
      <p className={styles.boundary}>{boundaries[current.category]}</p>
      {error ? <div role="alert"><p>{error}</p><button className="secondary-button" onClick={() => { setError(null); setRetry(n => n + 1); }}>Retry preview</button></div>
        : !detail ? <p role="status">Loading drill…</p> : <>
          {detail.media ? <ExerciseDemo media={detail.media} exerciseName={detail.name} /> : null}
          {["Instructions", "Cues"].map(title => detail.guidance[title]?.length ? <section key={title}>
            <h3>{title}</h3>{detail.guidance[title].map(text => <p key={text}>{text}</p>)}
          </section> : null)}
          {Object.entries(detail.guidance).some(([title, lines]) => !["Instructions", "Cues"].includes(title) && lines.length) ?
            <details className={`ex-detail-section ${styles.coaching}`}><summary>Coaching details</summary>
              {Object.entries(detail.guidance).filter(([title]) => !["Instructions", "Cues"].includes(title)).map(([title, lines]) => <section key={title}>
                <h3>{title}</h3>{lines.map(text => <p key={text}>{text}</p>)}
              </section>)}
            </details> : null}
          {!Object.keys(detail.guidance).length ? <p className={styles.meta}>Coaching guidance unavailable.</p> : null}
        </>}
    </div>
  </InjuryDetailSheet>;
}

export function TrainingLibrary({ accessToken }: { accessToken: string }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<Category>("training");
  const [filters, setFilters] = useState<Filters>({});
  const [filterOpen, setFilterOpen] = useState(false);
  const [selected, setSelected] = useState<LibraryEntry | null>(null);
  const [result, setResult] = useState<LibrarySearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [paging, setPaging] = useState(false);
  const [retry, setRetry] = useState(0);
  const generation = useRef(0);
  const pageRequest = useRef<AbortController | null>(null);
  const count = Object.values(filters).filter(Boolean).length;

  useEffect(() => {
    const controller = new AbortController();
    const requestGeneration = ++generation.current;
    pageRequest.current?.abort();
    const timer = setTimeout(() => {
      const params = new URLSearchParams({ q: query, category });
      Object.entries(filters).forEach(([key, value]) => { if (value) params.set(key, value); });
      void searchTrainingLibrary(accessToken, params, controller.signal).then(value => {
        if (!controller.signal.aborted && generation.current === requestGeneration) setResult(value);
      }).catch(reason => {
        if (!controller.signal.aborted && generation.current === requestGeneration) { setResult(null); setError(reason instanceof Error ? reason.message : "Unable to search library."); }
      }).finally(() => { if (!controller.signal.aborted && generation.current === requestGeneration) setLoading(false); });
    }, query ? 200 : 0);
    return () => { clearTimeout(timer); controller.abort(); pageRequest.current?.abort(); };
  }, [accessToken, query, category, filters, retry]);

  function changeSearch(update: () => void) {
    generation.current++;
    pageRequest.current?.abort();
    setLoading(true); setPaging(false); setError(null); update();
  }

  async function more() {
    if (!result || result.next_offset === null || paging || loading) return;
    const requestGeneration = generation.current;
    const controller = new AbortController();
    pageRequest.current = controller;
    setPaging(true); setError(null);
    const params = new URLSearchParams({ q: query, category, offset: String(result.next_offset), revision: result.revision });
    Object.entries(filters).forEach(([key, value]) => { if (value) params.set(key, value); });
    try {
      const next = await searchTrainingLibrary(accessToken, params, controller.signal);
      if (generation.current === requestGeneration && !controller.signal.aborted) {
        setResult({ ...next, entries: [...result.entries, ...next.entries] });
      }
    } catch (reason) {
      if (controller.signal.aborted || generation.current !== requestGeneration) return;
      if (reason instanceof ApiError && reason.status === 409) {
        changeSearch(() => setRetry(n => n + 1));
      } else setError(reason instanceof Error ? reason.message : "Unable to load more drills.");
    } finally { if (generation.current === requestGeneration) setPaging(false); }
  }

  return <section className={styles.library} aria-label="Training library">
    <header className={styles.header}>
      <div className={styles.headerTop}>
        <Link href="/plan" className={styles.back}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14 6-6 6 6 6" /></svg>Plan</Link>
        <p className={styles.eyebrow}>UNLXCK / LIBRARY</p>
      </div>
      <h1>Find a Drill</h1>
    </header>
    <div className={styles.searchRow}>
      <label className={styles.search}><span className="sr-only">Search drills</span>
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10" cy="10" r="6" /><path d="m15 15 5 5" /></svg>
        <input type="search" maxLength={100} placeholder="Name, goal or equipment" value={query}
          onChange={event => changeSearch(() => setQuery(event.target.value))} />
      </label>
      <button className={`secondary-button ${styles.filterButton}`} onClick={() => setFilterOpen(true)} aria-haspopup="dialog">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 17h16M8 4v6M16 14v6" /></svg>
        Filters{count ? ` (${count})` : ""}
      </button>
    </div>
    <div className={styles.categories} role="group" aria-label="Library category">
      {(["training", "rehab", "learn"] as const).map(value => <button key={value} aria-pressed={category === value}
        onClick={() => { if (value !== category) changeSearch(() => { setCategory(value); setFilters({}); }); }}>
        {value === "training" ? "Training" : value === "rehab" ? "Rehab" : "Learn"}
      </button>)}
    </div>
    {category !== "training" ? <p className={styles.boundary}>{boundaries[category]}</p> : null}
    <div className={styles.resultHeading}>
      <p role="status" aria-live="polite">{loading ? "Searching…" : result ? `${result.total.toLocaleString()} ${category === "learn" ? result.total === 1 ? "entry" : "entries" : result.total === 1 ? "drill" : "drills"}` : "Library unavailable"}</p>
      {count ? <button className={styles.reset} onClick={() => changeSearch(() => setFilters({}))}>Reset filters</button> : null}
    </div>
    {error ? <div className={styles.empty} role="alert"><p>{error}</p>
      <button className="secondary-button" onClick={() => changeSearch(() => setRetry(n => n + 1))}>Retry search</button>
    </div> : null}
    {!loading && result ? <>
      {result.entries.length ? <ul className={styles.results} aria-label="Drill results">
        {result.entries.map(entry => <li key={entry.catalogue_id}>
          <button className={styles.drill} onClick={() => setSelected(entry)} aria-haspopup="dialog">
            <span className={styles.thumbnail} aria-hidden="true">
              <ExerciseGlyphIcon name={contentTypes[entry.content_type]?.icon ?? "skill"} />
              {entry.media ? <>
                {/* eslint-disable-next-line @next/next/no-img-element -- same curated YouTube facade as Today */}
                <img src={demoThumbnailUrl(entry.media.video_id, "mq")} alt="" loading="lazy"
                  onError={event => { event.currentTarget.style.display = "none"; }} />
                <span className={styles.play} />
              </> : null}
            </span>
            <span className={styles.drillCopy}><span className={styles.name}>{entry.name}</span>
              <span className={styles.focus}>{entry.focus.length ? entry.focus.slice(0, 2).join(" · ") : contentTypes[entry.content_type]?.label}</span>
              {entry.discovery_match ? <span className={styles.meta}>{entry.discovery_match}</span> : null}
              <span className={styles.meta}>{equipmentText(entry)} · {entry.context}</span>
              {entry.media ? <span className="sr-only">Has demo video.</span> : null}
            </span><span className={styles.chevron} aria-hidden="true" />
          </button>
        </li>)}
      </ul> : <div className={styles.empty}><h2>No drills found</h2><p>Try a shorter name or reset your filters.</p>
        <button className="secondary-button" onClick={() => changeSearch(() => { setQuery(""); setFilters({}); })}>Reset search</button>
      </div>}
      {result.next_offset !== null ? <button className={`secondary-button ${styles.more}`} disabled={paging} onClick={() => void more()}>{paging ? "Loading…" : "Load more"}</button> : null}
    </> : null}
    {filterOpen ? <InjuryDetailSheet title="Filters" onClose={() => setFilterOpen(false)} closeLabel="Close filters">
      <div className={`injury-sheet-body ${styles.filters}`}>
        {Object.entries(filterLabels).map(([key, title]) => {
          const field = key as keyof Filters;
          const choices = result?.facets[field] ?? [];
          return <label className="field" key={key}><span>{title}</span>
            <select value={filters[field] ?? ""} onChange={event => changeSearch(() => setFilters(previous => ({ ...previous, [field]: event.target.value })))}>
              <option value="">All</option>
              {filters[field] && !choices.some(choice => choice.value === filters[field]) ? <option value={filters[field]}>{readable(filters[field]!)}</option> : null}
              {choices.map(choice => <option key={choice.value} value={choice.value}>{choice.label} ({choice.count})</option>)}
            </select>
          </label>;
        })}
        <p className={styles.meta}>Goal filters use source labels. Related matches are for discovery.</p>
        <div className={styles.filterActions}>
          <button className="injury-sheet-save" onClick={() => setFilterOpen(false)}>Show results</button>
          <button className={styles.reset} onClick={() => changeSearch(() => setFilters({}))}>Reset filters</button>
        </div>
      </div>
    </InjuryDetailSheet> : null}
    {selected ? <DrillPreview key={selected.catalogue_id} entry={selected} token={accessToken} onClose={() => setSelected(null)} /> : null}
  </section>;
}
