# Competitive Battle Card: CloudNova Analytics

**Doc ID:** BC-001 | **Owner:** Competitive Intelligence (Priya Raman) | **Last Updated:** October 14, 2026 | **Classification:** Internal Only

## Competitor Snapshot

CloudNova Analytics is the analytics service bundled with a major public cloud provider. It launched in 2021 and is usually the "default" option for customers who already have a large committed-spend agreement with that cloud. We meet CloudNova in roughly **34% of mid-market and enterprise opportunities**.

- **Head-to-head win rate (H1 2026):** 58% (65 wins out of 112 competitive deals)
- **Typical buyer:** IT/Infrastructure leader who wants to "consume existing cloud credits"
- **Primary use case they pitch:** Ad-hoc SQL analytics on data already stored in their object storage

## Their Strengths (Be Honest About These)

1. **Cheap storage:** List price of $20/TB/month, slightly below our $23/TB/month.
2. **Credit burn-down:** Customers can pay with pre-committed cloud credits, which makes CloudNova look "free" to procurement.
3. **Brand trust:** Backed by a hyperscaler; low perceived vendor risk.
4. **Native IAM:** Tight integration with that single cloud's identity tooling.

## Our Strengths

1. **True real-time:** NexaStream Pulse refreshes dashboards with **p95 latency of 800 ms**. CloudNova uses micro-batching with a **5-minute minimum refresh interval**.
2. **Predictable pricing:** Our tiered subscription (Professional at $4,800/month, Enterprise from $14,500/month) is fixed. CloudNova charges **$5.50 per TB scanned**, and customers report **30–45% month-to-month bill variance**.
3. **Multi-cloud:** We run on AWS, Azure, and GCP and connect to all three. CloudNova only runs on its parent cloud.
4. **Connector breadth:** 300+ native connectors, including a bidirectional Salesforce connector and a native Snowflake connector. CloudNova relies on third-party tools for Salesforce and has no native Snowflake connector.
5. **Business-user UX:** No-code dashboard builder. CloudNova requires SQL for most work.

## Pricing Comparison (Typical 50-User Mid-Market Deployment)

| Item | NexaStream Professional | CloudNova (estimated) |
|---|---|---|
| Platform fee | $4,800/month fixed | $0 |
| Query/scan cost | Included (10M API calls) | ~$6,000–$9,500/month |
| Storage (5 TB) | Included | $100/month |
| Real-time streaming | Included | Separate service, ~$1,200/month |
| **Est. annual total** | **$57,600** | **$87,600–$129,600** |

## Landmines (Questions to Ask the Prospect)

- "How much did your last three monthly analytics bills vary? Who signs off when the bill spikes?"
- "What's the business cost if your fraud or operations dashboards are five minutes stale?"
- "How will you get Salesforce and Snowflake data into CloudNova without a third-party ETL license?"
- "If you adopt a second cloud in the next three years, what happens to your analytics stack?"
- "Have your business analysts built dashboards in CloudNova without help from a data engineer?"

## Trap Responses

- **"CloudNova is basically free with our credits."** Credits are a sunk commitment, not free money. Every dollar spent on CloudNova scans is a dollar not available for compute. Offer a **3-year TCO model** from the Deal Desk.
- **"We'll just stay on one cloud."** 68% of our Enterprise customers run workloads on 2+ clouds (2026 Customer Survey).

## Proof Points

- **Apex Financial Group** (see `casestudy_apex_financial.md`) picked us over CloudNova after a 14-day POC. Dashboard latency dropped from 4 hours to 900 ms.
