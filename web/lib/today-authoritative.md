# Today frontend safety authority

The Today UI must not infer training clearance from backend prose or reclassify injuries in the browser.

`today-authoritative.ts` preserves the existing display-copy formatter but overwrites all behavioural fields from the backend recommendation state:

- display state
- chip
- tone
- training block

The command-view backend remains responsible for readiness, injury severity and session clearance.
