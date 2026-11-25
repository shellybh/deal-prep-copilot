# NexaStream API Usage Limits & Overage Policy (2026)

**Doc ID:** PR-002 | **Owner:** Product Management, Platform (Elena Vasquez) & Deal Desk | **Effective:** January 1, 2026 (revised October 1, 2026) | **Classification:** Confidential, Internal Only

## Purpose

This document defines API rate limits, monthly quotas, and overage pricing for each NexaStream tier. Sales Engineers should use it to size deals and set customer expectations. Under-sizing API capacity is the **#2 cause of first-year expansion friction** (2026 CS Health Report).

## What Counts as an API Call

One API call is any authenticated request to the **NexaStream REST API (v3)** or **GraphQL API**. This includes:

- Query execution requests (`/v3/query`)
- Dashboard embed token generation (`/v3/embed/token`)
- Data ingestion pushes via the Ingest API (`/v3/ingest`). Each batch of up to 500 records counts as one call.
- Metadata and catalog lookups

**Not counted:** Internal UI usage in the NexaStream web app, native connector syncs run by NexaStream Flow, and Pulse streaming ingestion through Kafka/Kinesis/Pub/Sub (metered separately in events/sec).

## Limits by Tier

| Limit | Starter | Professional | Enterprise |
|---|---|---|---|
| Monthly API calls included | 1,000,000 | 10,000,000 | 100,000,000 |
| Sustained rate limit | 60 requests/min | 600 requests/min | 6,000 requests/min |
| Burst allowance (10-second window) | 20 requests | 200 requests | 2,000 requests |
| Max concurrent queries | 5 | 25 | 150 |
| Max query result size | 100 MB | 1 GB | 10 GB |
| Max API keys per workspace | 5 | 50 | Unlimited |
| Embedded analytics sessions / month | — | 25,000 | 500,000 |
| Webhook endpoints | 2 | 20 | 200 |

When the rate limit is exceeded, the API returns **HTTP 429** with a `Retry-After` header. Requests are throttled, never dropped silently.

## Overage Pricing

| Overage Type | Starter | Professional | Enterprise |
|---|---|---|---|
| API calls (per 10,000 over quota) | $0.60 | $0.40 | $0.25 |
| Embedded sessions (per 1,000 over) | — | $15 | $8 |
| Streaming events (per additional 10K events/sec capacity, monthly) | — | $750 | $500 |

- Overages are billed **monthly in arrears**.
- **Soft-cap grace:** Customers get a **10% grace buffer** over their monthly quota before overage charges apply. This is meant to absorb one-time spikes.
- Customers receive automated email alerts at **75%, 90%, and 100%** of quota.
- Enterprise customers may set a **hard cap** to block overage spend entirely (configurable in Admin Console > Usage).

## API Capacity Packs (Pre-Purchased, Discounted)

| Pack | Calls / month | Price / month | Effective rate per 10K |
|---|---|---|---|
| Boost 25 | +25M | $1,500 | $0.60 → $0.24 (Pro) |
| Boost 100 | +100M | $4,500 | $0.18 |
| Boost 500 | +500M | $17,500 | $0.14 |

Capacity packs are available on **Professional and Enterprise** only and must be co-termed with the main subscription.

## Sizing Guidance for Sales Engineers

- **Rule of thumb:** Each actively used embedded dashboard generates about **4,000 API calls per user per month**.
- A customer embedding analytics in their own SaaS product for 2,000+ end users almost always needs **Enterprise or a Boost pack**.
- If a prospect expects more than **300M calls/month**, involve Platform PM for a custom rate-limit review. Dedicated API clusters are available at a minimum of **$8,000/month**.

## Historical Note

The October 2026 revision raised the Enterprise sustained rate limit from **3,000 to 6,000 requests/min** and lowered Enterprise overage from **$0.30 to $0.25** per 10,000 calls.
