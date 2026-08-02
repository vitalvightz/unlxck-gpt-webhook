# Private beta sport and nutrition gating

Tracks implementation for issue #2187.

## Required behaviour

- Keep Boxing, Kickboxing, and MMA selectable in plan intake.
- Render every other listed sport as visible but disabled.
- Disabled sports must show `🚫 COMING SOON` and ignore pointer and keyboard activation.
- Clear unsupported sports restored from saved drafts.
- Keep the existing nutrition destination intact, but block nutrition link activation during private beta and show `🚫 COMING SOON`.
- This is temporary beta gating; no new automated tests are required for this PR.
