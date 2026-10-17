# Round timer release checks

Round bells and work warnings are rendered into a local WAV and played by an
HTML audio element. They do not need JavaScript to run at each deadline. The
timestamp-based engine remains responsible for displayed time and completed rounds.
Voice, vibration and the rest countdown beeps remain best effort in the background.

This improves background playback; it is not a guarantee against a phone stopping
media, killing the browser, battery restrictions or a call taking over audio.
An installed PWA has these same OS restrictions. Do not describe it as certified
for locked-screen training until the device checks below pass.

## Automated checks

From `web/`:

```powershell
npm run typecheck
node --import tsx --import ./test/register-css-stub.mjs --test "lib/session-timer/*.test.ts" "components/session-timer/*.test.tsx"
npm run lint
```

For production build/browser checks, use the frontend quality-gate environment
documented in the repository. The browser tests isolate external requests and use
no athlete data. Build first, then run:

```powershell
npm run build
npm run test:e2e -- e2e/round-timer.spec.ts --workers=1
```

The Chromium test checks real PCM at each bell deadline, pauses the page's main
JavaScript thread while media continues, verifies the clock catches up, and checks
pause/resume, edits, interruptions, minimising, reloading and the final bell decay.
It also checks same-round warning replay after suspension, denial of the second
asynchronous playback attempt, and maximum-length track loading, seeking near the
last bell and repeated source replacement. Over-limit sessions must fall back
without retaining an audio blob.
This is a desktop browser test, not a simulated proof of iOS/Android lock behaviour.

For optional native browser memory measurements on Windows, set
`$env:ROUND_TIMER_PROFILE_MEMORY='1'` before the browser run. The long-track test
attaches startup timing, WAV size and combined Chromium process private/working-set
bytes before load, after load/seek and after release. This includes native media
allocations, rather than only JavaScript heap. It does not establish a phone memory
budget or a full-duration playback soak result. Revoking a URL and dropping source
references does not require the browser to return all reserved memory immediately.

### Desktop resource snapshots, 17 October 2026

One local Windows Chromium run per format, through Playwright 1.60.0. Values below
use decimal MB. Native memory is summed across Chromium processes and includes
other browser allocations; these are observations, not portable memory ceilings.

| Track | WAV bytes | Start to playing | Private bytes added at load | Private bytes above baseline after three replacements and release |
| --- | ---: | ---: | ---: | ---: |
| Original 90-minute limit | 172,928,044 | 1,049 ms | 139,755,520 (~139.8 MB) | 222,236,672 (~222.2 MB) |
| Current 50-minute limit | 96,128,044 | 248 ms | 63,123,456 (~63.1 MB) | 114,589,696 (~114.6 MB) |

Both tracks loaded and decoded near the final bell; neither run waited through the
full workout duration. The 90-minute source is now rejected. In the replacement
test, increasing round length crosses the limit and drops the source; decreasing
it builds a new one. Only the current object URL remains during playback and none
remain after pause. Native reservations persisting after release are a reason to
keep phone memory profiling on the device checklist, not evidence of mobile safety.

## Required physical-device checks before pro trials

Run on current iPhone Safari and Android Chrome, both in a browser tab and installed
to the home screen. Record phone, OS/browser versions, mode, date and actual results.

1. Open `/timer`. Set 3 rounds × 30 seconds, 10 seconds rest, 5 seconds prep.
   Enable sound and the 10-second warning; check device volume. Start and wait for
   “Round audio playing”. Confirm prep, each start bell, work warning, rest/end
   bell and the final bell. No rest should follow the final round.
2. Repeat with the phone locked immediately after playback starts. Hear every bell
   and warning against a second clock. Unlock during round 3 and confirm the
   displayed phase and time match, with no repeated old bells.
3. Repeat while using another app and while another browser tab is selected.
4. Run 3 rounds × 3 minutes with 1-minute rests while locked/backgrounded. This
   crosses the five-minute throttling window. Confirm every deadline by a second
   clock, including the last bell.
5. Minimise inside Unlxck and navigate around. Confirm bells continue and the screen
   stays awake when the browser grants a wake lock. Expand, pause for 10 seconds,
   resume and check the schedule shifts by 10 seconds.
6. Add/remove 10 seconds, edit the format, end a round early and turn sounds off/on.
   Confirm only one track plays, old deadlines no longer sound and volume changes
   affect bells. Check Bluetooth/headphones if athletes use them.
7. Interrupt audio with a call or other media. On return, confirm the interruption
   message and “Enable round audio” recovery. The clock continues during an audio
   interruption; recovery skips missed bells and aligns to the current round.
8. Reload during a round, return from the back/forward cache, then close and reopen
   the app. Confirm the correct saved phase; if autoplay is denied, explicitly
   enable audio. Closing the browser must never be promised to keep bells playing.

Also test low-power mode and iPhone silent mode. A failure is a release blocker for
any claim that background playback works on that device/mode. Keep the timer visible
as the recommended training setup until the target devices have passed.
Profile memory through repeated edits on the target phones, especially lower-memory
models; a passing desktop resource check does not remove this requirement.

Tracks cover the current interval exercise only, up to 50 minutes remaining,
with a hard 96 MiB WAV limit. The maximum normal track is 96,128,044 bytes including
four seconds of bell decay. Twelve three-minute boxing rounds with eleven
one-minute rests take 47 minutes and fit this limit. Longer/unsupported tracks
expose the foreground fallback; the clock still runs. A 90-minute track is rejected
before source allocation. Untimed sets and holds keep their existing timer behaviour.
