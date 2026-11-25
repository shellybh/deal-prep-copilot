# Case Study: MeridianHealth Systems

**Doc ID:** CS-002 | **Account Executive:** Rachel Okonkwo | **Solutions Engineer:** Luis Fernández | **Closed:** September 17, 2025 | **Classification:** Internal Only

## Customer Profile

- **Industry:** Healthcare Provider (Integrated Delivery Network)
- **Footprint:** 9 hospitals and 46 outpatient clinics across Ohio and Indiana
- **Size:** 14,500 employees; 2,100 licensed beds
- **Contract:** NexaStream Enterprise with HIPAA BAA, 3-year term, **ACV $428,000**
- **Products deployed:** NexaStream Core, Pulse, Flow (HL7/FHIR connector pack), Sentinel

## The Challenge

MeridianHealth had used DataSphere on-premises for 11 years. In early 2025 it faced an **$890,000 annual renewal** plus a forced migration to DataSphere Cloud. Pain points included:

- Operational reports on bed occupancy and Emergency Department (ED) throughput were **24 hours stale**.
- Median ED wait time had risen to **68 minutes**, hurting patient satisfaction scores.
- Per-viewer licensing limited dashboard access to **310 users**, even though more than 2,000 charge nurses and unit managers needed visibility.
- Overspending on agency (temporary) nursing staff was estimated at **$9M per year** because staffing decisions were made on stale data.

## The NexaStream Solution

1. **NexaStream Flow** used the **HL7 v2 and FHIR R4 connector pack** to stream ADT (admit/discharge/transfer) events from Epic in near real time.
2. **NexaStream Pulse** powered a system-wide **Capacity Command Center** with live bed boards and ED queue dashboards across all 9 hospitals.
3. **NexaStream Sentinel** applied **automated PHI masking** and role-based access, so unit managers saw only their own department's patient-level data.
4. Unlimited Viewer seats on Enterprise let MeridianHealth roll out dashboards to **2,350 clinical staff**.

**Implementation:** The rollout was phased by mutual agreement. Phase 1 (3 flagship hospitals) went live in **29 days**, and all 9 hospitals were live by **day 52**.

## Results (First 12 Months)

| Metric | Before | After |
|---|---|---|
| Operational data freshness | 24 hours | **< 2 seconds** |
| Median ED wait time | 68 min | **53 min (22% reduction)** |
| Dashboard users | 310 | **2,350** |
| Annual agency staffing spend | $9.0M | $5.9M (**$3.1M saved**) |
| Analytics licensing cost | $890K/year | $428K/year (**52% reduction**) |

- **3-year ROI:** 538%
- **Payback period:** 5 months

> "For the first time, every charge nurse can see the whole hospital, live." — Chief Nursing Officer, MeridianHealth Systems

## Why We Won

- **Competitor evaluated:** DataSphere (incumbent).
- **Timeline:** DataSphere quoted **7 months and $310,000 in services** for the cloud migration. Our FastTrack 45 commitment, with a 10% fee credit if we missed it, removed the risk.
- **Pricing model:** Unlimited viewers made a 7x increase in users affordable.
- **Real-time:** DataSphere Cloud's minimum 15-minute refresh could not support live bed management.
- **Compliance:** We signed a HIPAA BAA, showed our August SOC 2 Type II report, and ran a live demo of Sentinel PHI masking for the Privacy Officer.
- **Migration Kit:** Automated conversion of 78% of legacy DataSphere reports reduced retraining concerns.

## Reference Status

MeridianHealth is an **approved reference** for healthcare prospects (limit: 2 calls per quarter; coordinate with Customer Marketing).
