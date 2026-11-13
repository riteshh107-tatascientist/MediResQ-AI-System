# Demo Workflow (5-7 minutes)

Login: `scm` (Supply Chain Manager) with the demo password from README.
1. **Home** -> click *Enter Dashboard*. Point out the animated header, synthetic-data badge, KPIs, resilience index.
2. **Dashboard** -> baseline: Civil Hospital Beta (H-02) Ceftriaxone is *Low* risk (inbound shipment from S-03 arrives in 2 days).
3. **Optimization & Recovery -> Judge demo** -> *Run end-to-end demo scenario*: injects a **simulated 7-day delay** at supplier Nova Generic Healthcare (S-03).
4. Show the result table: baseline vs disrupted vs recovered (stock-out days, fill rate, cost).
5. **Redistribution plan**: Ceftriaxone sourced from several locations; point to FEFO batches, the excluded quarantined and short-dated batches, ETA, cost, reasoning.
6. **Stock-out Early Warning**: H-02 now High/Critical with reasons; explain heuristic score vs model probability.
7. **Alerts & Approvals** -> Approve one transfer, *Modify* another (comment required), *Execute*; show audit history.
8. **Analytics & Assistant** -> ask "Which supplier has the highest delay?"; run the policy comparison and discuss the service-vs-inventory trade-off honestly.
9. **What-if simulator** -> demand +30% and warehouse disruption; if infeasible, show the explanation table.
