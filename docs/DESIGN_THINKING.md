# Design Thinking

> Everything in "pain points", "needs" and "impact" is a **hypothesis to validate**; no interviews have been conducted yet.

## Stakeholders
Hospital pharmacist / store-in-charge; hospital administrator; warehouse manager; state/district procurement officer; supplier account manager; clinicians (indirect users of availability).

## Empathy map (hypothesised) - Hospital pharmacy store-in-charge
| Says | Thinks | Does | Feels |
|---|---|---|---|
| "We ran out of ceftriaxone again." | "Another site probably has extra, but I can't see it." | Phones peers, edits spreadsheets, escalates late | Stressed, blamed for shortages, anxious about expiry write-offs |
| **Pains:** late disruption visibility; no cross-site view; manual expiry tracking; unclear who approves transfers. **Gains wanted:** early warning with reasons, ready-to-approve actions, less wastage. |

## Problem statement
Pharmacy and warehouse teams lack a single, forward-looking view of demand, expiry and supplier/logistics risk, so shortages at one site coexist with surplus or near-expiry stock at another and recovery is slow and manual.

## How Might We
How might we help supply teams *see shortages and expiry losses coming* and *act on a feasible, approved recovery plan* before patients are affected?

## Validation plan (to do)
5-8 interviews (pharmacists, warehouse managers, procurement officers): current tools, last stock-out story, transfer approval path, data availability. Success signal: >= 3 of 5 describe cross-site visibility as a recurring problem. Observe one stock-reconciliation day if possible.

## Ideation -> selection
Ideas: alert-only dashboard; demand forecaster; expiry tracker; marketplace for surplus; redistribution optimizer with approvals; supplier scorecards. Selected (team judgement, impact x feasibility in a hackathon): **integrated forecasting + risk + optimizer + approval loop**, because the redistribution step turns alerts into actions.

## Prototype workflow
Forecast -> detect risk -> simulate disruption -> optimize -> recommend -> human approval -> execute -> audit (see DEMO_WORKFLOW.md).

## Testing strategy
Automated unit/integration tests (TEST_REPORT.md); scenario tests with injected disruptions; usability test with 3-5 users on the Judge Demo; later pilot with real (anonymised) inventory exports.

## Business impact (hypotheses only)
Fewer stock-outs of critical medicines, less expiry wastage, faster recovery decisions, auditability. Impact must be measured in a pilot; simulation results in this project are not real outcomes.
