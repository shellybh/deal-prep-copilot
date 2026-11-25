# Competitive Battle Card: InsightForge

**Doc ID:** BC-004 | **Owner:** Competitive Intelligence (Marcus Oyelaran) | **Last Updated:** October 21, 2026 | **Classification:** Internal Only

## Competitor Snapshot

InsightForge is an "AI-first" analytics startup founded in 2023. It raised an **$85M Series B in March 2026** and has about **180 employees**. Its pitch is a natural-language interface where business users "just ask questions." It demos very well and tends to win early excitement with business stakeholders.

- **Head-to-head win rate (H1 2026):** 71% (42 wins out of 59 competitive deals)
- **Typical buyer:** VP of Operations or Chief Digital Officer excited about GenAI
- **Where we win:** Once IT Security and Data Governance join the evaluation

## Their Strengths

1. **Slick demo:** Natural-language-to-chart answers in seconds.
2. **Fast time-to-first-value:** A small team can get to a working pilot within a week on clean data.
3. **Aggressive discounting:** Reps routinely offer **up to 50% off** list for first-year logos.
4. **Momentum:** Strong social and analyst buzz around GenAI.

## Their Weaknesses / Our Strengths

1. **Security maturity:** InsightForge holds **SOC 2 Type I only**. Type II is expected in 2027. They do **not** sign HIPAA BAAs. NexaStream has held SOC 2 Type II since 2021 (most recent report: August 2026).
2. **AI transparency:** InsightForge does not show the SQL or data lineage behind its AI answers. **NexaStream Lumen** (GA June 2026) shows the generated SQL, cites source tables, and runs only against the **governed semantic layer**, which reduces hallucinated metrics.
3. **Connectors:** InsightForge has about **40 connectors**. NexaStream has 300+.
4. **Scale:** InsightForge runs in a **single US region**. NexaStream offers five regions (US-East, US-West, EU-Frankfurt, EU-Dublin, APAC-Sydney) for data residency.
5. **Real-time:** InsightForge refreshes on a schedule, with a 15-minute minimum. NexaStream Pulse supports streaming at up to **1M events/second** on Enterprise.

## Pricing Comparison

| Tier | InsightForge | NexaStream |
|---|---|---|
| Entry | Team: $2,500/month (10 users) | Starter: $1,200/month (10 users) |
| Mid | Business: $9,000/month (75 users) | Professional: $4,800/month (50 users) |
| AI usage | Overage at $0.08 per AI query beyond 20,000/month | Lumen add-on: $3,500/month, unlimited governed queries (included in Enterprise) |

Warn prospects: InsightForge's per-query AI overage often **doubles** the bill once adoption scales.

## Landmines

- "Can you show me the SQL behind that AI answer, and prove which table it came from?"
- "Has your security team reviewed a SOC 2 **Type II** report from InsightForge?"
- "Where is your data physically stored, and does that satisfy your EU customers' residency needs?"
- "What's your projected AI query volume at 500 users, and what does that cost under their overage model?"
- "What's the discount at renewal, after the first-year 50% expires?"

## Positioning Guidance

Never dismiss AI. Say: *"We're excited about AI too, and that's exactly why it has to be governed. Lumen gives you the speed of natural language with the auditability your CFO and CISO require."*

## Proof Points

- **Vantage Logistics** (see `casestudy_vantage_logistics.md`) shortlisted InsightForge as the front-runner. InsightForge failed Vantage's vendor security review, and Vantage signed a 2-year NexaStream Enterprise agreement.
