# Module 02 — Vulnerability Analysis with Trusted Profile Analyzer

## Brief Overview

With Event-Driven Ansible having passed patch data downstream, this module focuses on how Red Hat Trusted Profile Analyzer (TPA) determines the environmental impact of each vulnerability. Participants use TPA to examine CVE scope, explore Software Bill of Materials (SBOM) lineage data, and understand which applications and container images are affected by the high-risk items flagged in Module 01. The analysis performed here provides the evidentiary basis that informs the Deep Agent's risk assessment in Module 03.

## Audience and Time

- **Target persona:** Platform engineers and security-focused operations engineers with intermediate OpenShift and CI/CD experience
- **Prerequisites for this module:** Completion of Modules 00 and 01; familiarity with CVE identifiers and SBOM concepts from Module 00
- **Estimated duration:** 30 minutes

## Learning Objectives

- Navigate the Trusted Profile Analyzer console to locate and review CVEs associated with the flagged patches
- Analyze CVE impact scope using SBOM data to assess which components, images, and applications are affected
- Explore SBOM lineage to trace a vulnerability from its origin package through to deployed container images
- Verify which applications carry elevated business risk based on TPA's environmental impact findings

## Lab Structure

| Section | Title | Duration |
|---------|-------|----------|
| 1 | Navigating the Trusted Profile Analyzer Console | 5 min |
| 2 | Reviewing CVE Impact and SBOM Data | 15 min |
| 3 | Interpreting Environmental and Business Risk | 10 min |

## Detailed Steps

1. Open the Trusted Profile Analyzer console using the URL provided in the lab environment details.
2. Navigate to the vulnerability list view and apply a filter to display only vulnerabilities associated with the current batch of Lightwell patches.
3. Select the highest-severity CVE from the filtered list and open its detail view.
4. Review the CVE detail fields: severity score, affected package name and version, and the fix version delivered by the Lightwell patch.
5. Locate the SBOM panel within the CVE detail view and expand the dependency tree to identify which container images include the affected package.
6. Observe that TPA cross-references the SBOM data against the running workloads in the environment to produce an impact scope list.
7. Review the impact scope list and identify which of the 29 applications in the overnight batch are affected by this CVE.
8. Navigate to a second flagged CVE and repeat the SBOM lineage review to compare the impact scope between the two vulnerabilities.
9. Use the business context fields — application criticality tier and data classification — to evaluate which affected application presents the highest remediation priority.
10. Note the risk tier that TPA has assigned to each CVE; this risk tier is the input that the Lightwell Deep Agent uses in the next module to generate merge requests.
11. Return to the TPA vulnerability list and confirm that all flagged items from the Lightwell dashboard are accounted for in TPA's impact analysis.

## Key Takeaways

- TPA consumes the patch event data passed by Event-Driven Ansible and correlates it against SBOM lineage and running workload data to determine environmental impact
- SBOM data enables participants to trace a vulnerable package from its origin through to the specific container images deployed in the environment
- Environmental impact scope — not just CVSS score alone — drives the risk tier assigned to each patch
- The risk tier and impact scope produced by TPA flow directly into the Lightwell Deep Agent's remediation strategy in the next module

## Infrastructure Notes

- TPA is pre-deployed with SBOM ingestion and CVE feed integration already configured; participants do not configure connectors or import SBOMs in this module
- The CVE data and SBOM corpus are seeded by pre-provisioning automation to reflect the overnight patch batch state
