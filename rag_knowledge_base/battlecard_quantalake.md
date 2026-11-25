# Competitive Battle Card: QuantaLake

**Doc ID:** BC-003 | **Owner:** Competitive Intelligence (Marcus Oyelaran) | **Last Updated:** October 2, 2026 | **Classification:** Internal Only

## Competitor Snapshot

QuantaLake is an open-source lakehouse project built on Apache Iceberg. It has a commercial managed offering called **QuantaLake Cloud**. It is popular with engineering-led organizations and data teams that prefer to "build, not buy." We meet QuantaLake most often in **retail, e-commerce, and tech-forward mid-market** accounts.

- **Head-to-head win rate (H1 2026):** 49% (38 wins out of 78 competitive deals). This is our toughest matchup.
- **Typical buyer:** Head of Data Engineering or a Principal Engineer
- **Typical loss reason:** "We already have engineers who can run it."

## Their Strengths

1. **Low entry cost:** The OSS edition is free. QuantaLake Cloud is priced at **$0.90 per compute-unit-hour**.
2. **Open formats:** Iceberg tables avoid vendor lock-in, which engineers care about strongly.
3. **Developer community:** 22,000+ GitHub stars and an active Slack community.
4. **Flexibility:** Teams can customize almost every layer of the stack.

## Their Weaknesses / Our Strengths

1. **Hidden staffing cost:** A production QuantaLake deployment typically needs **2–4 dedicated data engineers**. At about **$180,000 fully loaded per engineer**, that is $360,000–$720,000 per year before any compute.
2. **No BI layer:** QuantaLake has no native dashboards. Customers must buy and integrate a separate BI tool. NexaStream includes Pulse dashboards and the Lumen AI assistant.
3. **Compliance gaps:** SOC 2 Type II covers **QuantaLake Cloud only**. Self-hosted OSS deployments carry no attestations. NexaStream holds SOC 2 Type II, ISO 27001, GDPR, and HIPAA across the whole platform.
4. **Support:** The free tier has community-only support. NexaStream Enterprise has a **1-hour P1 response SLA** and a dedicated CSM.
5. **We neutralize lock-in fears:** Since the **NexaStream Core 2026.3 release (July 2026)**, Core natively reads and writes **Apache Iceberg tables**, so customers keep open formats.

## Pricing / TCO Comparison (3-Year, Mid-Market Retailer)

| Cost Element | NexaStream (Pro → Enterprise) | QuantaLake (Cloud + BI tool) |
|---|---|---|
| Subscription / compute | $480,000 | $210,000 |
| Separate BI licenses | $0 | $150,000 |
| Data engineering staff | ~1 FTE ($160,000 over 3 yrs, partial) | 2.5 FTE ($1,350,000) |
| **Approx. 3-year TCO** | **~$640,000** | **~$1,020,000+** (lower-bound estimate) |

*Always build a custom TCO with the Deal Desk. These figures come from the Lumos Retail evaluation.*

## Landmines

- "How many engineers spend more than half their time keeping the lakehouse running instead of delivering insights?"
- "What happens to your pipeline if your lead QuantaLake engineer leaves?"
- "Which BI tool will sit on top of QuantaLake, and who owns that integration?"
- "Does your auditor accept self-hosted OSS without a SOC 2 report?"
- "How long has your internal POC been running? Has it reached production?"

## Positioning Guidance

Do **not** attack open source. Say: *"We love Iceberg too. NexaStream lets your engineers stop maintaining plumbing and start shipping analytics."*

## Proof Points

- **Lumos Retail Group** (see `casestudy_lumos_retail.md`) dropped a QuantaLake POC that had stalled for 8 months and redeployed 2.5 engineering FTEs.
