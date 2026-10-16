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
This is a desktop browser test, not a simulated proof of iOS/Android lock behaviour.

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

Tracks cover the current interval exercise only, up to 90 minutes remaining.
Longer/unsupported tracks expose the foreground fallback rather than allocating
unbounded audio. Untimed sets and holds keep their existing timer behaviour.
