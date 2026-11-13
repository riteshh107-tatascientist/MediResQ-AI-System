# SAP Alignment (conceptual only)

**MediResQ AI is an independent Python prototype. It is not endorsed by SAP, not certified, and has no actual SAP integration.** The table shows conceptual alignment with SAP capabilities so judges can see where it could plug in.

| MediResQ AI module | Conceptual SAP counterpart | Status |
|---|---|---|
| Demand forecasting (baselines, ETS, RF, GBM, WAPE) | SAP IBP demand planning (statistical forecasting, forecast error measures) | Concept only |
| Safety stock, reorder points, FEFO, expiry | SAP IBP inventory planning (multi-echelon safety stock) | Concept only |
| Recovery planner + redistribution optimizer | SAP IBP response and supply planning (supply optimizer, response to disruptions) | Concept only |
| Shipment/supplier monitoring, alerts | SAP supply-chain visibility / alerting | Concept only |
| What-if simulator | SAP IBP scenario simulation | Concept only |
| Future integration layer | SAP BTP (APIs, event mesh, analytics) | Proposed, not built |
| Future transactional source/sink | SAP S/4HANA (materials, batches, purchase orders, stock transfers) | Proposed, not built |

## Possible integration path (hypothesis)
1. Read stock, batch, PO and consumption data from S/4HANA via OData APIs (authorized access required).
2. Run MediResQ forecasting/optimization as a BTP service.
3. Write approved transfers/POs back as stock transport orders / purchase requisitions.
None of this is implemented or tested.
