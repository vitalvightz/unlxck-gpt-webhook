"use client";
import { useEffect, useState } from 'react';
import { listCommunityExercises, getCommunityExercise, saveCommunityDraft, decideCommunityExercise } from '@/lib/api';
import type { CommunityEntry, CommunitySearch, CommunityDecision } from '@/lib/api-schema.generated';
import { AdminQueue, AdminQueueList } from './admin-queue';
import { InjuryDetailSheet } from './today/injury-detail-sheet';
import { PrivateExerciseVideo, PrivateExerciseVideoSheet, PrivateVideoPlayer } from './private-exercise-video';
import { Contributor, communityStatus, communityError } from './community-exercises';
import { formatAppDateTime } from '@/lib/date-format';
import fields from './custom-plan-builder.module.css';
import layout from './community-exercises.module.css';

function ReviewSheet({ token, initial, onClose, onChanged }: { token: string; initial: CommunityEntry; onClose: () => void; onChanged: () => void }) {
  const [entry, setEntry] = useState(initial), [name, setName] = useState(initial.name), [equipment, setEquipment] = useState(initial.equipment ?? ''), [notes, setNotes] = useState(initial.notes ?? '');
  const [mediaId, setMediaId] = useState(initial.media_id), [videoOpen, setVideoOpen] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState<string>();
  const [confirmation, setConfirmation] = useState(false), [reason, setReason] = useState('');
  const changed = name !== entry.name || equipment !== (entry.equipment ?? '') || notes !== (entry.notes ?? '') || mediaId !== entry.media_id;
  async function perform(action: CommunityDecision['action'] | 'edit') {
    setBusy(true); setError(undefined);
    try {
      const next = action === 'edit' ? await saveCommunityDraft(token, { name, equipment: equipment || null, notes: notes || null, media_id: mediaId }, entry.revision_id)
        : await decideCommunityExercise(token, entry.revision_id, { action, reason: reason || null, final_confirmation: confirmation });
      setEntry(next); setName(next.name); setEquipment(next.equipment ?? ''); setNotes(next.notes ?? ''); setMediaId(next.media_id); setConfirmation(false); onChanged();
    } catch (reason) { setError(communityError(reason)); } finally { setBusy(false); }
  }
  return <>
    <InjuryDetailSheet title={entry.name} onClose={onClose} busy={busy} panelClassName={layout.dialog}>
      <div className={`${fields.sheet} ${layout.reviewContent}`}>
        <div className={layout.stack}><Contributor entry={entry} /><p className="muted">{communityStatus(entry.status)}{entry.submitted_at ? ` · ${formatAppDateTime(entry.submitted_at)}` : ''}</p>
          {mediaId !== entry.media_id ? mediaId ? <PrivateExerciseVideo token={token} id={mediaId} name={name} /> : <p className="muted">No demonstration video.</p> : entry.media ? <PrivateVideoPlayer key={entry.revision_id} media={entry.media} name={entry.name} /> : <p className="muted">No demonstration video.</p>}
          {entry.equipment ? <p>{entry.equipment}</p> : null}{entry.notes ? <p>{entry.notes}</p> : null}
          {entry.reason ? <p>{entry.reason}</p> : null}
          {entry.reports.length ? <details><summary>Reports ({entry.reports.length})</summary>{entry.reports.map((report, i) => <p key={i}>{String(report.reason)}</p>)}</details> : null}
          <details><summary>Audit history</summary>{entry.audit.map((event, i) => <p className="muted" key={i}>{String(event.action).replaceAll('_', ' ')} · {formatAppDateTime(String(event.created_at))}{(event.details as { reason?: string })?.reason ? ` · ${(event.details as { reason: string }).reason}` : ''}</p>)}</details>
        </div>
        <div className={layout.stack}>
          {error ? <p role="alert">{error}</p> : null}
          {['in_review', 'published'].includes(entry.status) ? <details><summary>Edit exercise</summary><form className={layout.stack} onSubmit={e => { e.preventDefault(); void perform('edit'); }}>
            <label><span>Exercise name</span><input disabled={busy} required maxLength={100} value={name} onChange={e => setName(e.target.value)} /></label>
            <label><span>Equipment (optional)</span><input disabled={busy} maxLength={120} value={equipment} onChange={e => setEquipment(e.target.value)} /></label>
            <label><span>Instructions (optional)</span><textarea disabled={busy} maxLength={2000} value={notes} onChange={e => setNotes(e.target.value)} /></label>
            <div className={layout.actions}><button type="button" className="ghost-button" disabled={busy} onClick={() => setVideoOpen(true)}>{mediaId ? 'Edit or replace video' : 'Add video'}</button>
              {mediaId ? <button type="button" className="ghost-button" disabled={busy} onClick={() => setMediaId(null)}>Remove video</button> : null}</div>
            <button className="secondary-button" disabled={busy || !changed}>Save revision</button>
          </form></details> : null}
          {changed ? <p className="muted">Save the edited revision before verification.</p> : null}
          {entry.status === 'in_review' ? <>
            {entry.verified ? <label className={layout.check}><input type="checkbox" checked={confirmation} disabled={busy || changed} onChange={e => setConfirmation(e.target.checked)} /><span>I confirm this final exercise and demonstration.</span></label> : null}
            <button className="cta" disabled={busy || changed || (entry.verified && !confirmation)} onClick={() => void perform(!entry.verified ? 'verify' : !entry.confirmed ? 'confirm' : 'approve')}>
              {busy ? 'Updating…' : !entry.verified ? entry.media_id ? 'Verify video' : 'Verify exercise' : !entry.confirmed ? 'Confirm final revision' : 'Approve and publish'}
            </button>
          </> : null}
          {['in_review', 'published'].includes(entry.status) || entry.has_publication || entry.reports.some(report => report.status === 'open') ? <details><summary>Review actions</summary><div className={layout.stack}>
            <label><span>Reason</span><textarea maxLength={1000} value={reason} onChange={e => setReason(e.target.value)} /></label>
            <div className={layout.actions}>{entry.status === 'in_review' ? <>
              <button className="secondary-button" disabled={busy || changed || !reason.trim()} onClick={() => void perform('request_changes')}>Request changes</button>
              <button className="ghost-button" disabled={busy || changed || !reason.trim()} onClick={() => void perform('reject')}>Reject</button>
            </> : null}{entry.has_publication || entry.reports.some(report => report.status === 'open') ? <button className="ghost-button" disabled={busy || !reason.trim()} onClick={() => void perform('remove')}>Remove publication</button> : null}</div>
          </div></details> : null}
        </div>
      </div>
    </InjuryDetailSheet>
    {videoOpen ? <PrivateExerciseVideoSheet token={token} name={name} initialMedia={entry.media ?? undefined} onClose={() => setVideoOpen(false)} onAttach={id => { setMediaId(id); setVideoOpen(false); }} /> : null}
  </>;
}
export function AdminCommunityQueue({ token }: { token: string }) {
  const [result, setResult] = useState<CommunitySearch>(), [selected, setSelected] = useState<CommunityEntry>(), [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true), [offset, setOffset] = useState(0), [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void listCommunityExercises(token, 'review', '', offset, controller.signal).then(value => { if (!controller.signal.aborted) { setResult(value); setError(undefined); } })
      .catch(reason => { if (!controller.signal.aborted) setError(communityError(reason)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [token, offset, retry]);
  return <AdminQueue header={<div className="form-section-header"><div><p className="kicker">Community</p><h2>Exercise reviews</h2></div><span className="badge">{loading ? 'Checking' : result?.total ?? 0}</span></div>}>
    {error ? <div role="alert"><p>{error}</p><button className="secondary-button" onClick={() => setRetry(n => n + 1)}>Retry reviews</button></div> : null}
    {!loading && !result?.entries.length ? <p className="muted">No community submissions to review.</p> : null}
    <AdminQueueList className={layout.stack} label="Community exercise reviews">{result?.entries.map(entry => <div className={`list-row ${layout.reviewRow}`} key={entry.revision_id}>
      {/* eslint-disable-next-line @next/next/no-img-element -- existing demonstration thumbnail */}
      {entry.thumbnail ? <img className={layout.reviewThumb} src={entry.thumbnail} alt="" loading="lazy" /> : null}
      <div className={layout.reviewCopy}><strong>{entry.name}</strong><Contributor entry={entry} /><small className="muted">{communityStatus(entry.status)}{entry.submitted_at ? ` · ${formatAppDateTime(entry.submitted_at)}` : ''}</small></div>
      <button className="ghost-button" onClick={async () => { try { setSelected(await getCommunityExercise(token, entry.revision_id, 'review')); } catch (reason) { setError(communityError(reason)); } }}>Review</button>
    </div>)}</AdminQueueList>
    {offset || result?.next_offset != null ? <div className="admin-pager"><button className="ghost-button" disabled={loading || !offset} onClick={() => setOffset(Math.max(0, offset - 30))}>Previous</button><button className="ghost-button" disabled={loading || result?.next_offset == null} onClick={() => setOffset(result?.next_offset ?? 0)}>Next</button></div> : null}
    {selected ? <ReviewSheet key={selected.revision_id} token={token} initial={selected} onClose={() => setSelected(undefined)} onChanged={() => { setLoading(true); setRetry(n => n + 1); }} /> : null}
  </AdminQueue>;
}
