# Case Study: Vantage Logistics

**Doc ID:** CS-004 | **Account Executive:** Sofia Lindqvist | **Solutions Engineer:** Kwame Asante | **Closed:** June 26, 2026 | **Classification:** Internal Only

## Customer Profile

- **Industry:** Third-Party Logistics (3PL) and Freight
- **Headquarters:** Dallas, Texas
- **Fleet:** 1,800 tractors and 5,200 trailers; 22 distribution centers
- **Contract:** NexaStream Enterprise, 2-year term, **ACV $236,000**
- **Products deployed:** NexaStream Core, Pulse, Flow, Lumen AI Assistant

## The Challenge

Vantage's leadership wanted to use GenAI to improve on-time delivery and cut costly detention fees. Pain points included:

- **On-time delivery (OTD) rate of 87%**, below the 93% contractual target in its top-10 shipper contracts.
- **Detention and demurrage fees of $3.8M per year**, caused by late visibility into delays at loading docks.
- About **140 dispatchers** who spent around **8 hours per week each** manually compiling status reports from telematics, TMS, and email.
- Data spread across **Samsara telematics, McLeod TMS, AWS Kinesis streams, and Salesforce Sales Cloud**.

## The NexaStream Solution

1. **NexaStream Flow** streamed GPS and engine telemetry from **Samsara** via **AWS Kinesis** at about **45,000 events/second** at peak.
2. **NexaStream Pulse** powered a live **Fleet Operations Dashboard**, with geofenced alerts that fire when a truck sits more than 90 minutes at a dock.
3. **NexaStream Lumen** let dispatchers ask questions like "Which loads are at risk of missing their delivery window today?" Every answer showed the generated SQL and the source tables.
4. The **Salesforce connector** pushed shipment-risk scores back into Sales Cloud, so account managers could proactively warn shippers.

Implementation reached production in **34 days** under FastTrack 45.

## Results (First 4 Months, Annualized)

| Metric | Before | After |
|---|---|---|
| On-time delivery rate | 87% | **94%** |
| Detention & demurrage fees | $3.8M/year | $2.5M/year (**$1.3M saved annualized**) |
| Dispatcher reporting time | 8 hrs/week | **2 hrs/week (6 hrs saved each)** |
| Alert-to-action time on dock delays | ~3 hours | **< 10 minutes** |

- **Projected 2-year ROI:** 361%
- **Payback period:** 6 months

> "InsightForge had the flashier demo. NexaStream had the answers our auditors and our dispatchers could both trust." — CIO, Vantage Logistics

## Why We Won

- **Competitor evaluated:** InsightForge, the early front-runner chosen by the COO after an executive demo.
- **Security review:** Vantage's InfoSec team required **SOC 2 Type II** and **SCIM user provisioning**. InsightForge offered only SOC 2 Type I and had no SCIM support, so it failed the vendor security review.
- **AI trust:** In a side-by-side bake-off, InsightForge returned two inconsistent answers to the same on-time-delivery question. Lumen's governed semantic layer gave a consistent, traceable metric.
- **Real-time streaming:** InsightForge's 15-minute scheduled refresh could not support dock-delay alerting.
- **Pricing:** InsightForge offered 50% off year one, but modeled AI query overages ($0.08/query) pushed its year-2 cost **above** NexaStream's. Lumen is included in Enterprise with no per-query fees.

## Deal Mechanics

- Discount: **15%** off list (RVP-approved), with a 2-year price lock.
- Close was accelerated by **Q2 2026 end-of-quarter** timing and a signed mutual action plan with 11 milestones.
