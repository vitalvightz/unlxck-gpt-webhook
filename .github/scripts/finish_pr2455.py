from pathlib import Path
import textwrap

workflow = Path('.github/workflows/finish-pr2455.yml').read_text()
start = workflow.index("          from pathlib import Path\n")
end = workflow.index("          PY\n", start)
script = textwrap.dedent(workflow[start:end])
exec(compile(script, '/tmp/apply_pr2455.py', 'exec'))

path = Path('tests/test_stage2_finalizer_packet.py')
text = path.read_text()
old = '''def test_camp_finalizer_packet_exposes_authoritative_deterministic_session_spine():
    stage2_payload = {
        "athlete_model": {},
        "render_mode": "camp_plan",
'''
new = '''def test_camp_finalizer_packet_exposes_authoritative_deterministic_session_spine():
    stage2_payload = {
        "athlete_model": {
            "days_until_fight": 22,
            "fight_date": "2026-09-28",
            "next_fight_date": "2026-09-28",
            "sport": "boxing",
        },
        "render_mode": "camp_plan",
'''
if text.count(old) != 1:
    raise SystemExit(f'expected one camp fixture block, found {text.count(old)}')
path.write_text(text.replace(old, new, 1))
