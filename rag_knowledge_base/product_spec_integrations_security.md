# Product Spec Sheet: NexaStream Core Platform, Integrations & Security Compliance

**Doc ID:** PS-002 | **Owner:** Product Management, Platform (Elena Vasquez) & Security (CISO Office, Dr. Ian Mercer) | **Current Version:** NexaStream Core 2026.3 (released July 22, 2026) | **Classification:** Internal (Customer-shareable with NDA)

## Platform Overview

NexaStream Core is our cloud-native analytics engine. It separates storage and compute, autoscales, and runs on **AWS, Microsoft Azure, and Google Cloud**. It is the foundation for Pulse (dashboards), Flow (ingestion), Lumen (AI assistant), and Sentinel (governance).

**Key Core 2026.3 capabilities:**
- Native **Apache Iceberg** and **Delta Lake** table read/write support
- Query engine that is **2.3x faster** on the TPC-DS 1TB benchmark than Core 2025.4
- Autoscaling compute clusters from 2 to 512 nodes in **under 45 seconds**

## Data Residency Regions

US-East (Virginia), US-West (Oregon), EU-Frankfurt, EU-Dublin, and APAC-Sydney. **APAC-Tokyo** is planned for **Q1 2027**. Enterprise customers can pin data to a region. Additional regions cost $1,500/month each.

## Featured Integrations

### Amazon Web Services (AWS)
- **Amazon S3:** Direct query and ingestion. Supports Parquet, ORC, Avro, JSON, and CSV.
- **Amazon Redshift:** Federated query and one-time migration tooling.
- **AWS Kinesis & Amazon MSK:** Native streaming into Pulse.
- **AWS PrivateLink:** Private connectivity (Enterprise only).
- **AWS Marketplace:** Customers can buy NexaStream through AWS Marketplace and **burn down their AWS committed spend (EDP)**. Use this against CloudNova's "free credits" argument.

### Snowflake
- **Native Snowflake connector** with **Snowflake Secure Data Sharing**: zero-copy, read-only access without moving data
- Bidirectional writes: results can be written back to Snowflake tables
- Query pushdown to Snowflake compute when cheaper (cost-based optimizer)
- Certified **Snowflake Premier Technology Partner** since 2024

### Salesforce
- **Sales Cloud, Service Cloud, Financial Services Cloud, and Data Cloud** connectors
- **Change Data Capture (CDC)** sync with a default interval of **15 minutes** (5 minutes on Enterprise)
- **Reverse ETL:** Push scores and metrics (e.g., churn risk, shipment risk) back into Salesforce fields
- Embedded Pulse dashboards inside Salesforce Lightning pages

### Other Notable Connectors (300+ total)
Google BigQuery, Databricks, Azure Synapse, dbt Cloud, HubSpot, NetSuite, SAP S/4HANA, Workday, Shopify Plus, Zendesk, ServiceNow, Samsara, Epic (via HL7/FHIR pack), Stripe, and Marketo.

## Security Architecture

- **Encryption at rest:** AES-256. **BYOK / customer-managed keys** through AWS KMS, Azure Key Vault, or GCP KMS (Enterprise).
- **Encryption in transit:** TLS 1.3 enforced. TLS 1.2 is permitted only for legacy connectors.
- **Identity:** SAML 2.0 and OIDC SSO (Professional+), **SCIM 2.0** provisioning (Enterprise), and MFA enforcement.
- **Access control:** Role-based access control (RBAC), row-level and column-level security, and attribute-based policies via Sentinel.
- **Audit logging:** Immutable audit logs retained for **1 year** (Professional) or **7 years** (Enterprise). Exportable to Splunk and Datadog.
- **Network:** IP allowlisting, PrivateLink / Private Service Connect, and VPC peering.

## Compliance Certifications & Attestations

| Framework | Status | Details |
|---|---|---|
| **SOC 2 Type II** | Certified | Annual since 2021. Most recent report: **August 2026** (Security, Availability, Confidentiality) |
| **ISO/IEC 27001:2022** | Certified | Renewed March 2026 |
| **ISO/IEC 27701** | Certified | Privacy extension, March 2026 |
| **GDPR** | Compliant | EU data residency, DPA available, Standard Contractual Clauses |
| **CCPA/CPRA** | Compliant | — |
| **HIPAA** | Compliant | BAA available on **Enterprise only** |
| **PCI DSS** | Level 1 Service Provider | Attested June 2026 |
| **FedRAMP Moderate** | In Process | Target authorization: **Q2 2027**. Do not represent as authorized. |

## Reliability

- Uptime SLA: 99.5% (Starter), 99.9% (Professional), 99.95% (Enterprise)
- Actual trailing-12-month uptime (Oct 2025 – Sep 2026): **99.98%**
- RPO: 15 minutes. RTO: 1 hour (Enterprise, cross-region failover).

## Security Review Support

Sales can request the SOC 2 report, a pen-test summary (latest: **May 2026**, by an independent third party), and the pre-filled **SIG Lite and CAIQ questionnaires** through the Trust Portal (trust.nexastream.example). An NDA is required.
