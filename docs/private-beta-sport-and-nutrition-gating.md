# Private beta sport and nutrition gating

Tracks implementation for issue #2187.

## Required behaviour

- Keep Boxing, Kickboxing, and MMA selectable in plan intake.
- Render every other listed sport as visible but disabled.
- Disabled sports must show `🚫 COMING SOON`, ignore pointer and keyboard activation, and expose an accessible disabled state.
- Clear or reject unsupported sports restored from saved drafts before continuation or submission.
- Disable the intake `Open nutrition workspace` action with the same muted `🚫 COMING SOON` treatment.
- Reuse the existing role-selection coming-soon styling where possible.
- Add tests for supported selections, blocked pointer/keyboard activation, restored drafts, and nutrition navigation blocking.
