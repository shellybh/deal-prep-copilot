# Product Spec Sheet: NexaStream Pulse (Real-Time Dashboards)

**Doc ID:** PS-001 | **Owner:** Product Management, Visualization (Tomás Reyes) | **Current Version:** Pulse 4.2 (released September 15, 2026) | **Classification:** Internal (Customer-shareable with NDA)

## Product Summary

NexaStream Pulse is our real-time dashboarding and alerting layer. It lets business users build live, interactive dashboards on streaming and historical data without writing code. Pulse runs on NexaStream Core and is included in the **Professional and Enterprise** tiers. Starter includes Pulse with **scheduled refresh only** (minimum 15-minute interval).

## Performance Specifications

| Specification | Professional | Enterprise |
|---|---|---|
| Dashboard refresh latency (p95) | 800 ms | 800 ms |
| Dashboard refresh latency (p99) | 1.5 s | 1.2 s |
| Max streaming ingest throughput | 50,000 events/sec | 1,000,000 events/sec |
| Max widgets per dashboard | 100 | 200 |
| Max concurrent dashboard viewers | 2,500 | 50,000 |
| Historical data in a single view | 13 months | 7 years |
| Streaming data hot retention | 30 days | 90 days (configurable to 365) |

## Key Features

1. **Live Streaming Widgets:** Charts update in place as events arrive, with no page reload. They support time-series, geo-maps, gauges, heatmaps, and Sankey diagrams.
2. **Hybrid Queries:** A single chart can blend live streaming data with historical warehouse data (e.g., "today's orders vs. same day last year").
3. **Smart Alerts:** Threshold, anomaly-detection (ML-based), and geofence alerts. Alerts go to **Slack, Microsoft Teams, PagerDuty, email, SMS, and webhooks**. Median alert delivery time is **under 3 seconds**.
4. **No-Code Builder:** Drag-and-drop canvas with 45+ visualization types and a library of **120 industry templates** (finance, healthcare, retail, logistics, SaaS).
5. **Embedded Analytics SDK:** Embed dashboards in customer-facing apps through JavaScript and React SDKs, with row-level security tokens. Embedded sessions count toward API quotas.
6. **Mobile & Wallboard Modes:** Native iOS and Android apps, plus a "Command Center" wallboard mode for TV displays, which MeridianHealth uses.
7. **Lumen Integration (new in 4.2):** Users can ask Lumen to "build a dashboard showing late shipments by region." Lumen generates a draft dashboard and shows its underlying SQL.

## Streaming Sources Supported

- **Apache Kafka** (including Confluent Cloud and Amazon MSK)
- **AWS Kinesis Data Streams**
- **Google Cloud Pub/Sub**
- **Azure Event Hubs**
- **NexaStream Ingest API** (REST, up to 500 records per call)
- **Change Data Capture (CDC)** from PostgreSQL, MySQL, Oracle, and SQL Server

## What's New in Pulse 4.2 (September 2026)

- p95 latency improved from **1.1 s to 800 ms**
- Enterprise viewer concurrency raised from 20,000 to **50,000**
- New **geofence alerting** (built for logistics customers like Vantage Logistics)
- **Dark mode** and WCAG 2.2 AA accessibility compliance

## Roadmap (Non-Binding, Do Not Commit in Contracts)

- **Q1 2027:** Collaborative annotations on live charts
- **Q2 2027:** Offline mode for mobile apps
- **H2 2027:** Predictive "what-if" simulation widgets

## Competitive Differentiation

| Capability | NexaStream Pulse | CloudNova | DataSphere | InsightForge |
|---|---|---|---|---|
| Minimum refresh | Sub-second | 5 min | 15 min | 15 min |
| Native streaming | Yes | Separate service | No | No |
| Unlimited viewers | Enterprise | Usage-based | No ($35/viewer) | No |

## Technical Requirements

Supported browsers: Chrome 120+, Edge 120+, Firefox 121+, Safari 17+. Mobile apps require iOS 17+ or Android 13+.
