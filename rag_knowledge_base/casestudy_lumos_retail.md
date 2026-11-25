# Case Study: Lumos Retail Group

**Doc ID:** CS-003 | **Account Executive:** Jordan Bellamy | **Solutions Engineer:** Aisha Karimi | **Closed:** February 11, 2026 (Expansion: August 4, 2026) | **Classification:** Internal Only

## Customer Profile

- **Industry:** Omnichannel Retail (Home Goods & Apparel)
- **Headquarters:** Portland, Oregon
- **Footprint:** 340 stores across the Pacific Northwest and Mountain West, plus e-commerce (38% of revenue)
- **Annual revenue:** about $2.7 billion
- **Initial contract:** NexaStream Professional, **ACV $86,400** (Professional base plus Lumen add-on and storage overage)
- **Expansion:** Upgraded to Enterprise in August 2026, **new ACV $198,000**
- **Products deployed:** NexaStream Core (with Iceberg interoperability), Flow, Pulse, Lumen

## The Challenge

Lumos's data team chose to build its own lakehouse on **QuantaLake OSS**. After **8 months**, the project had still not reached production:

- **Three of the five data engineers** assigned to the project left within a year, taking key knowledge with them.
- Store managers had no daily inventory visibility, and the stockout rate on top-500 SKUs was **9.4%**.
- Excess inventory carrying cost was estimated at **$14.8M per year**.
- The team had still not chosen a BI tool to put on top of the lakehouse.

## The NexaStream Solution

1. **NexaStream Core** read Lumos's existing **Apache Iceberg tables** directly (Core 2026.3), so the work already done on the QuantaLake POC was preserved rather than discarded.
2. **NexaStream Flow** connected **Shopify Plus, Oracle NetSuite, Manhattan WMS, and AWS S3** using pre-built connectors.
3. **NexaStream Pulse** delivered store-level inventory dashboards to 340 store managers on tablets.
4. **NexaStream Lumen** let merchandising teams ask questions like "Which SKUs will stock out in Region 4 this week?" in natural language.

**Time to first production dashboard:** 23 days (Guided Onboarding, Professional tier).

## Results (First 8 Months)

| Metric | Before | After |
|---|---|---|
| Top-500 SKU stockout rate | 9.4% | **6.5% (31% reduction)** |
| Inventory carrying cost | $14.8M/year | $10.2M/year (**$4.6M saved**) |
| Engineering FTEs on pipeline maintenance | 3.5 | **1.0 (2.5 FTE redeployed)** |
| Time to answer ad-hoc merchandising questions | 2–3 days | **< 5 minutes** |

- **3-year TCO:** about **$640,000 with NexaStream** vs. **$1.02M+** projected for QuantaLake plus a third-party BI tool
- **Payback period:** 4 months

> "We stopped maintaining plumbing and started selling more product." — VP of Data & Analytics, Lumos Retail Group

## Why We Won

- **Competitor evaluated:** QuantaLake (internal POC) plus an informal look at CloudNova.
- **TCO honesty:** A joint TCO workshop with the CFO showed the **hidden staffing cost** of self-managed open source.
- **No lock-in:** Iceberg read/write support addressed the engineering team's biggest objection.
- **All-in-one:** Built-in dashboards and AI meant no separate BI procurement.
- **Land and expand:** Starting on Professional lowered the barrier to entry. The Enterprise upgrade six months later was driven by the need for 99.95% SLA, unlimited viewers, and higher API limits ahead of the holiday season.

## Expansion Notes

The August 2026 upgrade included a **12% volume discount**, approved at RVP level, for a 3-year commitment. See `pricing_volume_discount_rules.md`.
