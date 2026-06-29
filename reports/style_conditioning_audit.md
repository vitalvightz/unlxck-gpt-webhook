# Style Conditioning Manual Cleanup Audit

This report is diagnostic only. It does not rewrite, delete, rename, or redose bank entries.

## Summary

- Entries audited: 372
- Late-fight risk flagged: 372

## Summary Counts

### Camp Actions

- redose: 205
- keep: 123
- delete_or_rebuild: 38
- rename_and_redose: 5
- rename: 1

### Late-Fight Actions

- late_blocked: 258
- not_late_eligible: 114

### Quarantine Reason Codes

- missing_late_windows: 372
- high_rpe: 234
- high_intensity: 232
- high_movement_cost: 161
- high_lactate_load: 157
- high_impact_cost: 53
- violent_wording: 39
- overstyled_name: 26
- aggressive_notes: 6

### Systems

- glycolytic: 157
- ATP-PCr: 114
- aerobic: 88
- cognitive: 10
- recovery: 3

### Phases

- SPP: 229
- GPP: 147
- TAPER: 10

## Grouped Review Queues

### Delete/Rebuild Candidates

Entries: 38

| name | system | phases | rpe | intensity | lactate_load | movement_cost | impact_cost | late_windows | overstyled_name_flag | aggressive_notes_flag | dose_risk_flag | late_fight_risk_flag | camp_action | late_fight_action | manual_notes | quarantine_reason_codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Back-Alley Brawler | glycolytic | GPP, SPP | 9 | max | high | high | low |  | False | True | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording, aggressive_notes |
| Gutter War Special | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Smashmouth Shovel Hook | ATP-PCr | SPP | 9 | max | low | low | high |  | False | True | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows, violent_wording, aggressive_notes |
| Backfoot Butcher | glycolytic | GPP | 7 | moderate | high | high | low |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows, violent_wording |
| Fight Night Finisher | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows, violent_wording |
| Cage Mauler | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Back Alley Clinch | glycolytic | SPP | 9 | max | high | high | low |  | False | True | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording, aggressive_notes |
| Prison Rules | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Meat Grinder | glycolytic | GPP | 9 | max | high | high | high |  | True | True | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows, overstyled_name, violent_wording, aggressive_notes |
| Grab & Stab | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording |
| Curb Stomper | ATP-PCr | SPP | 9 | max | low | low | high |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows, overstyled_name, violent_wording |
| Backyard Bouncer | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows, violent_wording |
| Thai Clinch Crusher | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording |
| Knee Executioner | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows, violent_wording |
| Wall War Protocol | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Cage Crusher | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording |
| Clinch Sprawl Hell | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Neck Tie Domination | aerobic | GPP | 7 | moderate | moderate | high | low |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_movement_cost, missing_late_windows, violent_wording |
| Kill Mode Knees | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording |
| Whizzer War | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Philly Shell Torture | glycolytic | SPP | 9 | high | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Roll Under Hell | glycolytic | SPP | 9 | high | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Intercept & Destroy | ATP-PCr | SPP | 9 | high | low | low | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, missing_late_windows, overstyled_name, violent_wording |
| Framing Counter Hell | glycolytic | SPP | 9 | high | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Long Guard Torture | glycolytic | SPP | 9 | high | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Flicker’s Hell | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Low Kick Annihilator | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording |
| Calf Kick Carnage | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording |
| Clinch Knee Devastation | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording |
| Clinch & Destroy | glycolytic | SPP | 9 | high | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Dirty Boxing Hell | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| 3-Minute War | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Trap Bar Death March | glycolytic | GPP, SPP | 9 | high | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Rope & Bag Carnage | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows, violent_wording |
| Mauler’s March | glycolytic | GPP | 9 | high | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Thai Plough | glycolytic | SPP | 9 | max | high | high | low |  | False | True | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording, aggressive_notes |
| Ezekiel from Hell | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Ground-and-Pound Bursts | ATP-PCr | GPP | 9 | max | low | low | low |  | False | True | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, missing_late_windows, violent_wording, aggressive_notes |

### Rename Candidates

Entries: 1

| name | system | phases | rpe | intensity | lactate_load | movement_cost | impact_cost | late_windows | overstyled_name_flag | aggressive_notes_flag | dose_risk_flag | late_fight_risk_flag | camp_action | late_fight_action | manual_notes | quarantine_reason_codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Calf Slicer Hell | ATP-PCr | SPP | 7 | moderate | low | low | low |  | True | False | False | True | rename | late_blocked |  | missing_late_windows, overstyled_name, violent_wording |

### Redose Candidates

Entries: 205

| name | system | phases | rpe | intensity | lactate_load | movement_cost | impact_cost | late_windows | overstyled_name_flag | aggressive_notes_flag | dose_risk_flag | late_fight_risk_flag | camp_action | late_fight_action | manual_notes | quarantine_reason_codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Concrete Hands Circuit | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Pavement Pounder | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Ding-Dong Roundhouse | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Brick Fist Protocol | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Last Call Circuit | glycolytic | SPP | 9 | high | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Blackout Blitz | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Meat Locker | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Dive Bar Duelist | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Liver Hunter | ATP-PCr | SPP | 9 | max | low | low | moderate |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Alleyway Ambush | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Bouncer's Revenge | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Rooftop Rumble | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Glass Jaw Redemption | aerobic | GPP | 7 | moderate | moderate | high | low |  | False | False | True | True | redose | late_blocked |  | high_movement_cost, missing_late_windows |
| Ditch Digger | glycolytic | GPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Piledriver Circuit | ATP-PCr | GPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Concrete Clinch | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Junkyard Judo | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Barroom Brawl | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Gutter Fight Finisher | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Backfist Brawler | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Alleyway Sprawl | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Dogfight Drill | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Headbutt Conditioning | aerobic | GPP | 7 | moderate | moderate | high | low |  | False | False | True | True | redose | late_blocked |  | high_movement_cost, missing_late_windows |
| Last Man Standing | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Dirty Boxing Marathon | glycolytic | SPP | 9 | high | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Cage Clinch Gauntlet | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Plumb Power Circuit | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Greco-Roman Grinder | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Rope-A-Dope Clinch | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Judo Clinch Transition | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Muay Thai Matrix | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Boxer's Clinch Control | aerobic | GPP | 7 | moderate | moderate | high | low |  | False | False | True | True | redose | late_blocked |  | high_movement_cost, missing_late_windows |
| Smesh Prep Circuit | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Dutch Clinch Drill | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Plumb Power Rotations | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Clinch Control 3.0 | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Elbow Alley | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Collar Tie Counter | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Clinch Gas Tank | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Clinch Finisher | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Pull Counter Matrix | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Check Hook Crucible | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Slip & Rip Protocol | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Interception Drill | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Pull-Back Sniper | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Clinch Counter Chaos | glycolytic | SPP | 9 | high | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Reaction Overload | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Counter Puncher's Gauntlet | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Slipping Symphony | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Counter Knee Matrix | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Rolling Thunder | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Check Hook Matrix | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Counter Uppercut Drill | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Matrix Shuffle | aerobic | SPP | 9 | high | moderate | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Phantom Step | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Sniper’s Retreat | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Ring Generalship | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Telescope Drill | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Flicker’s Gauntlet | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Outfighter’s Crucible | glycolytic | SPP | 9 | high | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Pendulum Step | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Sniper’s Delight | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Teep & Retreat | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Flicker’s Endurance | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Matador Drill | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Range Master | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Head Hunter Protocol | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Teep Matrix | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Dutch Destroyer | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Question Mark Kick Drill | ATP-PCr | SPP | 7 | moderate | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_impact_cost, missing_late_windows |
| Elbow-Kick Synergy | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Spinning Back Kick | ATP-PCr | SPP | 9 | high | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Switch Kick Storm | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Body Kick Barrage | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Step-Through Knee | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Flying Knee Drill | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Scoop Kick Counter | glycolytic | SPP | 9 | high | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Jumping Roundhouse | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Side Kick Sniper | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Low-High Deception | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Teep-to-Knee | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Pressure Cooker | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Brawler's Gauntlet | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Ring-Cut Sprint | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Puncher's Circuit | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Rope & Smash | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Last 10 Seconds | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Titan's Test | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Barbell Smash & Dash | glycolytic | SPP | 9 | high | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Tire Flip Fury | glycolytic | GPP, SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Sledgehammer Showdown | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Trap Bar Tackle | glycolytic | SPP | 8 | zone 2 | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Tire Slam & Jam | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Clinch Grinder | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Dirty Boxer’s Feast | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Wall & Maul | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Tire Dominator | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Chain Gang | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Knee Harvest | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Pitbull Protocol | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Crowbar Clinch | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Smother Squad | glycolytic | SPP | 9 | high | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Trench Warfare | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Dump Truck | ATP-PCr | SPP | 7 | moderate | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_impact_cost, missing_late_windows |
| Muay Dump | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Octopus Guard | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Brick Wall | glycolytic | GPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Chain Reactor | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Grim Reaper | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Pressure Cooker Deluxe | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Takedown to Backtake Scramble | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Sprawl to Spin Drill | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Cage Wrestle Chaos | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Turtle to Guard Scramble | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Shot to Granby Roll | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Stand-Up Sprint | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Submission to Sweep Chain | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Clinch to Takedown Scramble | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Strike to Takedown Scramble | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Arm Drag to Backtake | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Front Headlock Escapes | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Cage to Center Scramble | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Rolling Backtake Drill | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Strike to Submission Chain | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Granby to Single Leg | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Clinch to Spin Drill | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Guard Recovery Sprint | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Standing Backtake Drill | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Mat Shark | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Stranglehold | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Limb Collector | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Heel Hook Highway | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Guillotine Gauntlet | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| D’Arce Depth Charge | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Kneebar Khaos | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| North-South Chokehold | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Peruvian Necktie Drill | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Buggy Choke Crucible | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Electric Chair Sweep | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Loop Choke Loop | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Anaconda Ambush | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Crucifix Collector | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Toe Hold Torment | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Clinch Knee Storm Intervals | glycolytic | GPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Forward-Blast Heavy Bag Intervals | glycolytic | GPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Wall-Wrestler Pummel Rounds | glycolytic | GPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Switch-Kick Endurance Drill | glycolytic | GPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Brawler's Body Shot Barrage | glycolytic | GPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Clinch-to-Strike Transition Drill | glycolytic | GPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Sprawl-to-Strike Intervals | glycolytic | GPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Counter Striker's Shell Defense Drill | glycolytic | GPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Submission Chain Fatigue Drill | glycolytic | GPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Teep-and-Clinch Gauntlet | glycolytic | GPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Sprawl-to-Takedown Reaction Drill | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Lateral Escape Plyo Pushoffs | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Guillotine Shot Sprints | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Switch-Kick Power Bursts | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Takedown Shot Reaction Drill | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Cross-Counter Plyo Pushups | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Thai Plum Explosion Drill | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Sprawl-to-Shot Sprints | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Lateral Plyo Pushoffs | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Neck Snap Drill | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Switch-Kick Acceleration | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Overhand Right Bursts | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Blast Double Sprints | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Knee Strike Bursts | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Guillotine Shot Reactions | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| MT Teep Acceleration Drill | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Reactive Sprawl Jumps | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Forward Lunge Strikes | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Takedown-to-Knee Drill | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Switch-Kick Plyos | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| BJJ Explosive Guard Pull | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Dump Explosions | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Slip-Counter Springs | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Cage-Push Escapes | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Liver Hook Bursts | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Long Guard Snap | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Reshot Chains | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Axe Kick Acceleration | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Swarm Entry Sprints | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Strike-to-Clinch Drill | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Hip Slam Drill | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Pull-Counter Springs | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Corner Knee Bursts | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Scrambler's Standup Explosions | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Uppercut Barrage | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Spinning Back Kick Accelerations | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Thai Skip Rope | aerobic | GPP | 7 | moderate | moderate | low | high |  | False | False | True | True | redose | late_blocked |  | high_impact_cost, missing_late_windows |
| Rope Clinch Frames | aerobic | SPP | 5 | low | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_impact_cost, missing_late_windows |
| Swimming Endurance Circuits | aerobic | GPP | 8 | zone 2 | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, missing_late_windows |
| Bike Sprints (Assault) | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Upper Body Sled Push | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Elliptical Machine Intervals | glycolytic | GPP | 8 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Parallette Push-Ups (Low-Impact) | glycolytic | GPP | 7 | moderate | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| Wall Sit Series (Isometric) | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Bike Sprints (Fixed Gear Recovery) | glycolytic | GPP | 7 | moderate | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Banded Sled Push (Light) | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Rowing Machine Sprint Intervals | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Pillow Punch Combinations (Air Work) | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Reverse Sled Drag (Quad Emphasis) | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Cable Woodchops (Light Load) | glycolytic | SPP | 7 | moderate | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Stair Climbing (No Sprinting) | glycolytic | GPP | 6 | zone 2 | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Banded Core Chop (Anti-Rotation) | aerobic | GPP | 5 | low | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_impact_cost, missing_late_windows |

### Rename + Redose Candidates

Entries: 5

| name | system | phases | rpe | intensity | lactate_load | movement_cost | impact_cost | late_windows | overstyled_name_flag | aggressive_notes_flag | dose_risk_flag | late_fight_risk_flag | camp_action | late_fight_action | manual_notes | quarantine_reason_codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Phone Booth Killer | glycolytic | GPP | 9 | high | high | high | high |  | True | False | True | True | rename_and_redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows, overstyled_name |
| Corner Beast Mode | glycolytic | SPP | 9 | high | high | high | high |  | True | False | True | True | rename_and_redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows, overstyled_name |
| Parking Lot Punisher | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | rename_and_redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name |
| Thug Plank | glycolytic | GPP | 9 | high | high | high | low |  | True | False | True | True | rename_and_redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name |
| Switch Stance Killer | glycolytic | SPP | 9 | high | high | high | low |  | True | False | True | True | rename_and_redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name |

### GPP/SPP Keep But No Late-Fight

Entries: 123

| name | system | phases | rpe | intensity | lactate_load | movement_cost | impact_cost | late_windows | overstyled_name_flag | aggressive_notes_flag | dose_risk_flag | late_fight_risk_flag | camp_action | late_fight_action | manual_notes | quarantine_reason_codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Iron Chin Builder | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Junkyard Dog | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Cement Shoes | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Knuckle Dragger | aerobic | GPP | 4 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Counter Sniper Drill | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Counter Kick Matrix | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Sniper's Timing | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Ghost Protocol | glycolytic | SPP | 4 | zone 2 | high | high | low |  | False | False | False | True | keep | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| Octagon Geometry | aerobic | SPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Sniper’s Load | ATP-PCr | GPP | 4 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Elusive Rhythms | aerobic | SPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Sniper’s Grip | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Ax Kick Annihilation | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Cartwheel Kick | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Hammer Kick | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Crescent Kick Precision | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Back Kick Blitz | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Capoeira Kick Flow | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Sled Dragger's Delight | glycolytic | GPP, SPP | 7 | moderate | high | high | low |  | False | False | False | True | keep | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| Barbell Bully | aerobic | GPP | 6 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Sled Push Punishment | glycolytic | SPP | 7 | moderate | high | high | low |  | False | False | False | True | keep | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| Cage Bully | glycolytic | SPP | 7 | moderate | high | high | low |  | False | False | False | True | keep | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| Guard Pass to Backtake | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Flying Sub Scramble | glycolytic | SPP | 7 | moderate | high | high | low |  | False | False | False | True | keep | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| Twister Protocol | glycolytic | SPP | 7 | moderate | high | high | low |  | False | False | False | True | keep | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| Gogoplata Grinder | glycolytic | SPP | 7 | moderate | high | high | low |  | False | False | False | True | keep | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| Bicep Slicer Drill | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Inverted Triangle Matrix | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Mir Lock Madness | glycolytic | SPP | 7 | moderate | high | high | low |  | False | False | False | True | keep | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| Japanese Necktie Drill | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Long-Distance Shadowboxing | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Clinch Marching Rounds | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Grappler's Flow Roll | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Teep Maintenance Drill | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Cage Cutting Footwork | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Pummeling Endurance Rounds | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Kick Defense March | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Brawler's Forward Shadow | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Hybrid Stance Switch Drill | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Octagon Footwork Gauntlet | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Counter Striker's Retreat Drill | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Submission Hunter's Guard Retention | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Kicker's Range Management | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Wrestler's Wall-Walk Drill | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Pressure Fighter's Cutoff Circuit | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Hybrid's Stance Transition Drill | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Clinch Fighter's Neck Endurance | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Scrambler's Turtle Recovery | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Brawler's Body Shot Guard | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Distance Striker's Angle Drill | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| MMA Wall-Walk Conditioning | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Counter Striker's Parry Drill | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Kicker's Switch Stance March | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Grappler's Standup Chain | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Pressure Fighter's Cutoff Shadow | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Clinch Fighter's Frame Endurance | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Hybrid's Transition Circuit | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Scrambler's Hip Escape Marathon | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Distance Striker's Teep Maintenance | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Shadow Flow Rounds | aerobic | SPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Referee Break Counters | aerobic | SPP | 4 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Overhook Uppercut Drill | aerobic | SPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Corner Mauling Circuit | aerobic | SPP | 4 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Slip-Clinch Reaction | aerobic | SPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
## Grouped Review Queues
| Clinch Auditory Triggers | cognitive | SPP, TAPER | 4 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Wrestling Chess | cognitive | SPP, TAPER | 4 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Kick Pattern Recall | cognitive | SPP, TAPER | 5 | low | moderate | moderate | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Takedown Dilemma | cognitive | SPP, TAPER | 4 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Brawler's Puzzle Defense | cognitive | SPP, TAPER | 6 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Distance Striker's Math Dodge | cognitive | SPP, TAPER | 6 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Grappler's Blindfold Pummeling | cognitive | SPP, TAPER | 5 | low | moderate | moderate | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Pressure Fighter's Shadowboxing Riddle | cognitive | SPP, TAPER | 4 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Hybrid's Stance-Switch Reaction | cognitive | SPP, TAPER | 4 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Sled Drag Low-Impact Intervals | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Rowing Machine Steady State | aerobic | GPP | 6 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Landmine Rotations (Light Load) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Banded Shadowboxing | glycolytic | SPP | 7 | moderate | high | high | low |  | False | False | False | True | keep | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| Dumbbell Turkish Get-Ups (Light) | ATP-PCr | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Core Plank Progressions | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Assisted Chinnups (Light Load) | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Bike Steady-State (Easy Gear) | aerobic | GPP | 5 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Prone Superman Holds | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Sled Reverse Drag (Backward Walking) | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Medicine Ball Chest Pass (Light Load) | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Glute Bridge March (Isometric Base) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Pallof Press (Anti-Rotation) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Quadruped Shoulder Taps | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Dead Bug Progressions | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Farmer Carry (Seated Starting Position) | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Assisted Dip Machine (Light Load) | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Pool Walking (Shallow End) | aerobic | GPP | 5 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Incline Treadmill Walk | aerobic | GPP | 6 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Banded Pull-Aparts (Light) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Arch Walks (Barefoot Activation) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Side-Lying Leg Raise (Hip Stability) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Medicine Ball Rotational Slam (Light) | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Tall Kneeling Core Holds | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Incline Push-Up Progression | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Banded Face Pulls (Rear Delt) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Half-Kneeling Hip Flexor Stretch | recovery | GPP | 5 | low | moderate | moderate | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Dumbbell Bent-Row (Light Load) | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Bird Dog Holds (Core Stability) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Elliptical Backward Movement | aerobic | GPP | 6 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Push-Up Hold (Isometric Chest) | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Wall Plank Hold | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Single-Leg Balance Series | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Assisted Squat (TRX) | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Landmine Single-Arm Press (Light) | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Quad Foam Rolling (Active Recovery) | recovery | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Side-Plank Hold (Core Lateral) | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Hanging Leg Raise (Assisted) | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Chest-Supported Dumbbell Row | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Tall-Kneeling Pallof Press | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Swimming Technique Drills | aerobic | GPP | 6 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Kettle Bell Sumo Squat (Light Load) | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Foam Roll Hamstring (Seated) | recovery | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Resistance Band Chest Fly | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Assisted Pullup (Heavy Band) | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Banded External Rotation (Shoulder) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Water Jogging (Deep End) | aerobic | GPP | 6 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Half-Kneeling Landmine Press | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Tempo Shadowboxing (Slow Reps) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |

### Potential Late Support Candidates

Entries: 0

### Potential Late Technical Candidates

Entries: 0

### Manual Review

Entries: 0

## All Entries

| name | system | phases | rpe | intensity | lactate_load | movement_cost | impact_cost | late_windows | overstyled_name_flag | aggressive_notes_flag | dose_risk_flag | late_fight_risk_flag | camp_action | late_fight_action | manual_notes | quarantine_reason_codes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Concrete Hands Circuit | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Pavement Pounder | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Back-Alley Brawler | glycolytic | GPP, SPP | 9 | max | high | high | low |  | False | True | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording, aggressive_notes |
| Ding-Dong Roundhouse | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Phone Booth Killer | glycolytic | GPP | 9 | high | high | high | high |  | True | False | True | True | rename_and_redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows, overstyled_name |
| Brick Fist Protocol | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Gutter War Special | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Last Call Circuit | glycolytic | SPP | 9 | high | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Iron Chin Builder | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Corner Beast Mode | glycolytic | SPP | 9 | high | high | high | high |  | True | False | True | True | rename_and_redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows, overstyled_name |
| Blackout Blitz | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Smashmouth Shovel Hook | ATP-PCr | SPP | 9 | max | low | low | high |  | False | True | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows, violent_wording, aggressive_notes |
| Backfoot Butcher | glycolytic | GPP | 7 | moderate | high | high | low |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows, violent_wording |
| Meat Locker | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Junkyard Dog | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Fight Night Finisher | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows, violent_wording |
| Dive Bar Duelist | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Cement Shoes | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Liver Hunter | ATP-PCr | SPP | 9 | max | low | low | moderate |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Alleyway Ambush | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Knuckle Dragger | aerobic | GPP | 4 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Bouncer's Revenge | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Rooftop Rumble | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Glass Jaw Redemption | aerobic | GPP | 7 | moderate | moderate | high | low |  | False | False | True | True | redose | late_blocked |  | high_movement_cost, missing_late_windows |
| Parking Lot Punisher | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | rename_and_redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name |
| Cage Mauler | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Ditch Digger | glycolytic | GPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Back Alley Clinch | glycolytic | SPP | 9 | max | high | high | low |  | False | True | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording, aggressive_notes |
| Piledriver Circuit | ATP-PCr | GPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Concrete Clinch | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Junkyard Judo | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Thug Plank | glycolytic | GPP | 9 | high | high | high | low |  | True | False | True | True | rename_and_redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name |
| Barroom Brawl | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Prison Rules | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Gutter Fight Finisher | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Meat Grinder | glycolytic | GPP | 9 | max | high | high | high |  | True | True | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows, overstyled_name, violent_wording, aggressive_notes |
| Backfist Brawler | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Alleyway Sprawl | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Dogfight Drill | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Headbutt Conditioning | aerobic | GPP | 7 | moderate | moderate | high | low |  | False | False | True | True | redose | late_blocked |  | high_movement_cost, missing_late_windows |
| Grab & Stab | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording |
| Curb Stomper | ATP-PCr | SPP | 9 | max | low | low | high |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows, overstyled_name, violent_wording |
| Last Man Standing | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Backyard Bouncer | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows, violent_wording |
| Thai Clinch Crusher | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording |
| Dirty Boxing Marathon | glycolytic | SPP | 9 | high | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Cage Clinch Gauntlet | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Plumb Power Circuit | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Greco-Roman Grinder | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Rope-A-Dope Clinch | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Knee Executioner | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows, violent_wording |
| Wall War Protocol | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Judo Clinch Transition | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Muay Thai Matrix | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Boxer's Clinch Control | aerobic | GPP | 7 | moderate | moderate | high | low |  | False | False | True | True | redose | late_blocked |  | high_movement_cost, missing_late_windows |
| Smesh Prep Circuit | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Dutch Clinch Drill | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Cage Crusher | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording |
| Plumb Power Rotations | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Clinch Sprawl Hell | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Neck Tie Domination | aerobic | GPP | 7 | moderate | moderate | high | low |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_movement_cost, missing_late_windows, violent_wording |
| Kill Mode Knees | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording |
| Clinch Control 3.0 | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Elbow Alley | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Collar Tie Counter | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Clinch Gas Tank | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Whizzer War | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Clinch Finisher | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Pull Counter Matrix | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Check Hook Crucible | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Slip & Rip Protocol | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Philly Shell Torture | glycolytic | SPP | 9 | high | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Counter Sniper Drill | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Roll Under Hell | glycolytic | SPP | 9 | high | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Interception Drill | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Counter Kick Matrix | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Pull-Back Sniper | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Clinch Counter Chaos | glycolytic | SPP | 9 | high | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Reaction Overload | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Counter Puncher's Gauntlet | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Slipping Symphony | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Intercept & Destroy | ATP-PCr | SPP | 9 | high | low | low | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, missing_late_windows, overstyled_name, violent_wording |
| Counter Knee Matrix | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Rolling Thunder | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Framing Counter Hell | glycolytic | SPP | 9 | high | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Sniper's Timing | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Check Hook Matrix | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Counter Uppercut Drill | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Matrix Shuffle | aerobic | SPP | 9 | high | moderate | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Phantom Step | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Sniper’s Retreat | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Ring Generalship | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Telescope Drill | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Flicker’s Gauntlet | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Outfighter’s Crucible | glycolytic | SPP | 9 | high | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Ghost Protocol | glycolytic | SPP | 4 | zone 2 | high | high | low |  | False | False | False | True | keep | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| Pendulum Step | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Long Guard Torture | glycolytic | SPP | 9 | high | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Sniper’s Delight | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Octagon Geometry | aerobic | SPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Teep & Retreat | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Flicker’s Endurance | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Matador Drill | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Sniper’s Load | ATP-PCr | GPP | 4 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Range Master | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Elusive Rhythms | aerobic | SPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Flicker’s Hell | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Sniper’s Grip | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Low Kick Annihilator | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording |
| Head Hunter Protocol | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Teep Matrix | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Dutch Destroyer | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Question Mark Kick Drill | ATP-PCr | SPP | 7 | moderate | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_impact_cost, missing_late_windows |
| Elbow-Kick Synergy | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Calf Kick Carnage | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording |
| Spinning Back Kick | ATP-PCr | SPP | 9 | high | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Switch Kick Storm | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Ax Kick Annihilation | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Body Kick Barrage | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Step-Through Knee | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Flying Knee Drill | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Scoop Kick Counter | glycolytic | SPP | 9 | high | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Cartwheel Kick | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Clinch Knee Devastation | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording |
| Switch Stance Killer | glycolytic | SPP | 9 | high | high | high | low |  | True | False | True | True | rename_and_redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name |
| Hammer Kick | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Jumping Roundhouse | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Side Kick Sniper | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Crescent Kick Precision | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Low-High Deception | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Back Kick Blitz | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Teep-to-Knee | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Capoeira Kick Flow | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Pressure Cooker | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Brawler's Gauntlet | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Ring-Cut Sprint | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Clinch & Destroy | glycolytic | SPP | 9 | high | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Dirty Boxing Hell | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| 3-Minute War | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Puncher's Circuit | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Rope & Smash | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Last 10 Seconds | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Titan's Test | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Trap Bar Death March | glycolytic | GPP, SPP | 9 | high | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Barbell Smash & Dash | glycolytic | SPP | 9 | high | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Tire Flip Fury | glycolytic | GPP, SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Sled Dragger's Delight | glycolytic | GPP, SPP | 7 | moderate | high | high | low |  | False | False | False | True | keep | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| Sledgehammer Showdown | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Rope & Bag Carnage | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows, violent_wording |
| Trap Bar Tackle | glycolytic | SPP | 8 | zone 2 | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Barbell Bully | aerobic | GPP | 6 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Tire Slam & Jam | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Sled Push Punishment | glycolytic | SPP | 7 | moderate | high | high | low |  | False | False | False | True | keep | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| Clinch Grinder | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Cage Bully | glycolytic | SPP | 7 | moderate | high | high | low |  | False | False | False | True | keep | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| Dirty Boxer’s Feast | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Mauler’s March | glycolytic | GPP | 9 | high | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Thai Plough | glycolytic | SPP | 9 | max | high | high | low |  | False | True | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, violent_wording, aggressive_notes |
| Wall & Maul | glycolytic | SPP | 9 | max | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Tire Dominator | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Chain Gang | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Knee Harvest | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Pitbull Protocol | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Crowbar Clinch | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Smother Squad | glycolytic | SPP | 9 | high | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Trench Warfare | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Dump Truck | ATP-PCr | SPP | 7 | moderate | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_impact_cost, missing_late_windows |
| Muay Dump | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Octopus Guard | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Brick Wall | glycolytic | GPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Chain Reactor | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Grim Reaper | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Pressure Cooker Deluxe | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Takedown to Backtake Scramble | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Sprawl to Spin Drill | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Cage Wrestle Chaos | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Turtle to Guard Scramble | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Shot to Granby Roll | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Stand-Up Sprint | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Submission to Sweep Chain | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Clinch to Takedown Scramble | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Guard Pass to Backtake | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Strike to Takedown Scramble | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Arm Drag to Backtake | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Front Headlock Escapes | glycolytic | SPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Cage to Center Scramble | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Rolling Backtake Drill | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Strike to Submission Chain | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Granby to Single Leg | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Flying Sub Scramble | glycolytic | SPP | 7 | moderate | high | high | low |  | False | False | False | True | keep | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| Clinch to Spin Drill | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Guard Recovery Sprint | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Standing Backtake Drill | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Mat Shark | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Stranglehold | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Limb Collector | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Heel Hook Highway | ATP-PCr | SPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Guillotine Gauntlet | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Twister Protocol | glycolytic | SPP | 7 | moderate | high | high | low |  | False | False | False | True | keep | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| D’Arce Depth Charge | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Calf Slicer Hell | ATP-PCr | SPP | 7 | moderate | low | low | low |  | True | False | False | True | rename | late_blocked |  | missing_late_windows, overstyled_name, violent_wording |
| Kneebar Khaos | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| North-South Chokehold | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Peruvian Necktie Drill | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Gogoplata Grinder | glycolytic | SPP | 7 | moderate | high | high | low |  | False | False | False | True | keep | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| Buggy Choke Crucible | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Electric Chair Sweep | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Bicep Slicer Drill | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Loop Choke Loop | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Inverted Triangle Matrix | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Ezekiel from Hell | glycolytic | SPP | 9 | max | high | high | low |  | True | False | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows, overstyled_name, violent_wording |
| Anaconda Ambush | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Crucifix Collector | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Toe Hold Torment | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Mir Lock Madness | glycolytic | SPP | 7 | moderate | high | high | low |  | False | False | False | True | keep | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| Japanese Necktie Drill | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Clinch Knee Storm Intervals | glycolytic | GPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Forward-Blast Heavy Bag Intervals | glycolytic | GPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Wall-Wrestler Pummel Rounds | glycolytic | GPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Switch-Kick Endurance Drill | glycolytic | GPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Brawler's Body Shot Barrage | glycolytic | GPP | 9 | max | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Clinch-to-Strike Transition Drill | glycolytic | GPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Sprawl-to-Strike Intervals | glycolytic | GPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Counter Striker's Shell Defense Drill | glycolytic | GPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Submission Chain Fatigue Drill | glycolytic | GPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Teep-and-Clinch Gauntlet | glycolytic | GPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Sprawl-to-Takedown Reaction Drill | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Lateral Escape Plyo Pushoffs | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Guillotine Shot Sprints | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Switch-Kick Power Bursts | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Takedown Shot Reaction Drill | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Cross-Counter Plyo Pushups | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Thai Plum Explosion Drill | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Sprawl-to-Shot Sprints | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Lateral Plyo Pushoffs | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Neck Snap Drill | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Switch-Kick Acceleration | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Overhand Right Bursts | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Blast Double Sprints | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Knee Strike Bursts | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Guillotine Shot Reactions | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| MT Teep Acceleration Drill | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Reactive Sprawl Jumps | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Forward Lunge Strikes | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Takedown-to-Knee Drill | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Switch-Kick Plyos | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| BJJ Explosive Guard Pull | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Dump Explosions | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Slip-Counter Springs | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Cage-Push Escapes | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Liver Hook Bursts | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Long Guard Snap | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Reshot Chains | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Axe Kick Acceleration | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Swarm Entry Sprints | ATP-PCr | GPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Strike-to-Clinch Drill | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Hip Slam Drill | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Pull-Counter Springs | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Ground-and-Pound Bursts | ATP-PCr | GPP | 9 | max | low | low | low |  | False | True | True | True | delete_or_rebuild | late_blocked |  | high_rpe, high_intensity, missing_late_windows, violent_wording, aggressive_notes |
| Corner Knee Bursts | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Scrambler's Standup Explosions | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Uppercut Barrage | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Spinning Back Kick Accelerations | ATP-PCr | GPP | 9 | max | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Long-Distance Shadowboxing | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Clinch Marching Rounds | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Grappler's Flow Roll | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Teep Maintenance Drill | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Cage Cutting Footwork | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Pummeling Endurance Rounds | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Kick Defense March | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Brawler's Forward Shadow | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Hybrid Stance Switch Drill | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Thai Skip Rope | aerobic | GPP | 7 | moderate | moderate | low | high |  | False | False | True | True | redose | late_blocked |  | high_impact_cost, missing_late_windows |
| Octagon Footwork Gauntlet | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Counter Striker's Retreat Drill | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Submission Hunter's Guard Retention | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Kicker's Range Management | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Wrestler's Wall-Walk Drill | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Pressure Fighter's Cutoff Circuit | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Hybrid's Stance Transition Drill | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Clinch Fighter's Neck Endurance | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Scrambler's Turtle Recovery | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Brawler's Body Shot Guard | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Distance Striker's Angle Drill | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| MMA Wall-Walk Conditioning | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Counter Striker's Parry Drill | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Kicker's Switch Stance March | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Grappler's Standup Chain | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Pressure Fighter's Cutoff Shadow | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Clinch Fighter's Frame Endurance | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Hybrid's Transition Circuit | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Scrambler's Hip Escape Marathon | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Distance Striker's Teep Maintenance | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Shadow Flow Rounds | aerobic | SPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Rope Clinch Frames | aerobic | SPP | 5 | low | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_impact_cost, missing_late_windows |
| Referee Break Counters | aerobic | SPP | 4 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Overhook Uppercut Drill | aerobic | SPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Corner Mauling Circuit | aerobic | SPP | 4 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Slip-Clinch Reaction | aerobic | SPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Reaction Jab Matrix | cognitive | SPP, TAPER | 7 | moderate | moderate | moderate | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Clinch Auditory Triggers | cognitive | SPP, TAPER | 4 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Wrestling Chess | cognitive | SPP, TAPER | 4 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Kick Pattern Recall | cognitive | SPP, TAPER | 5 | low | moderate | moderate | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Takedown Dilemma | cognitive | SPP, TAPER | 4 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Brawler's Puzzle Defense | cognitive | SPP, TAPER | 6 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Distance Striker's Math Dodge | cognitive | SPP, TAPER | 6 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Grappler's Blindfold Pummeling | cognitive | SPP, TAPER | 5 | low | moderate | moderate | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Pressure Fighter's Shadowboxing Riddle | cognitive | SPP, TAPER | 4 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Hybrid's Stance-Switch Reaction | cognitive | SPP, TAPER | 4 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Sled Drag Low-Impact Intervals | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Swimming Endurance Circuits | aerobic | GPP | 8 | zone 2 | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, missing_late_windows |
| Bike Sprints (Assault) | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Rowing Machine Steady State | aerobic | GPP | 6 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Upper Body Sled Push | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Elliptical Machine Intervals | glycolytic | GPP | 8 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Parallette Push-Ups (Low-Impact) | glycolytic | GPP | 7 | moderate | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| Landmine Rotations (Light Load) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Banded Shadowboxing | glycolytic | SPP | 7 | moderate | high | high | low |  | False | False | False | True | keep | late_blocked |  | high_lactate_load, high_movement_cost, missing_late_windows |
| Dumbbell Turkish Get-Ups (Light) | ATP-PCr | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Core Plank Progressions | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Assisted Chinnups (Light Load) | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Bike Steady-State (Easy Gear) | aerobic | GPP | 5 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Wall Sit Series (Isometric) | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Prone Superman Holds | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Sled Reverse Drag (Backward Walking) | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Medicine Ball Chest Pass (Light Load) | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Glute Bridge March (Isometric Base) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Pallof Press (Anti-Rotation) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Bike Sprints (Fixed Gear Recovery) | glycolytic | GPP | 7 | moderate | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Quadruped Shoulder Taps | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Dead Bug Progressions | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Banded Sled Push (Light) | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Rowing Machine Sprint Intervals | ATP-PCr | SPP | 9 | max | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_impact_cost, missing_late_windows |
| Farmer Carry (Seated Starting Position) | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Pillow Punch Combinations (Air Work) | ATP-PCr | SPP | 9 | high | low | low | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, missing_late_windows |
| Assisted Dip Machine (Light Load) | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Pool Walking (Shallow End) | aerobic | GPP | 5 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Incline Treadmill Walk | aerobic | GPP | 6 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Banded Pull-Aparts (Light) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Arch Walks (Barefoot Activation) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Side-Lying Leg Raise (Hip Stability) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Reverse Sled Drag (Quad Emphasis) | glycolytic | SPP | 9 | high | high | high | low |  | False | False | True | True | redose | late_blocked |  | high_rpe, high_intensity, high_lactate_load, high_movement_cost, missing_late_windows |
| Medicine Ball Rotational Slam (Light) | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Tall Kneeling Core Holds | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Incline Push-Up Progression | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Cable Woodchops (Light Load) | glycolytic | SPP | 7 | moderate | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Stair Climbing (No Sprinting) | glycolytic | GPP | 6 | zone 2 | high | high | high |  | False | False | True | True | redose | late_blocked |  | high_lactate_load, high_movement_cost, high_impact_cost, missing_late_windows |
| Banded Face Pulls (Rear Delt) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Half-Kneeling Hip Flexor Stretch | recovery | GPP | 5 | low | moderate | moderate | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Dumbbell Bent-Row (Light Load) | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Bird Dog Holds (Core Stability) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Elliptical Backward Movement | aerobic | GPP | 6 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Push-Up Hold (Isometric Chest) | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Banded Core Chop (Anti-Rotation) | aerobic | GPP | 5 | low | low | low | high |  | False | False | True | True | redose | late_blocked |  | high_impact_cost, missing_late_windows |
| Wall Plank Hold | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Single-Leg Balance Series | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Assisted Squat (TRX) | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Landmine Single-Arm Press (Light) | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Quad Foam Rolling (Active Recovery) | recovery | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Side-Plank Hold (Core Lateral) | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Hanging Leg Raise (Assisted) | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Chest-Supported Dumbbell Row | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Tall-Kneeling Pallof Press | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Swimming Technique Drills | aerobic | GPP | 6 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Kettle Bell Sumo Squat (Light Load) | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Foam Roll Hamstring (Seated) | recovery | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Resistance Band Chest Fly | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Assisted Pullup (Heavy Band) | aerobic | GPP | 7 | moderate | moderate | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Banded External Rotation (Shoulder) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Water Jogging (Deep End) | aerobic | GPP | 6 | zone 2 | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Half-Kneeling Landmine Press | ATP-PCr | SPP | 7 | moderate | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
| Tempo Shadowboxing (Slow Reps) | aerobic | GPP | 5 | low | low | low | low |  | False | False | False | True | keep | not_late_eligible |  | missing_late_windows |
