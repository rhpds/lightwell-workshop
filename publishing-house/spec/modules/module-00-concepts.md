# Module 0 — CVEs, SBOMs, and the Patch Workflow — Foundations

### Brief Overview

Before diving into Lightwell's automation, this module establishes the foundational concepts that make the rest of the lab meaningful. Participants learn what CVEs are and why they matter, what SBOMs are and how they enable precise impact analysis, and why traditional patch workflows are slow. Without this grounding, the "magic" of automated remediation is hard to evaluate — this module makes it concrete.

### Audience and Time

Target persona: platform engineers with OpenShift familiarity but varying depth on supply chain security concepts. No prior knowledge of CVEs, SBOMs, or formal patch processes is assumed. Estimated duration: **5 minutes**.

### Learning Objectives

- Demonstrate understanding of what a CVE is, how severity is scored, and why not all CVEs require the same response
- Demonstrate understanding of what a Software Bill of Materials (SBOM) is and how it links a vulnerability to specific affected components in a running application
- Demonstrate understanding of why traditional patch workflows — manual CVE triage, patch sourcing, testing, and deployment — take weeks and why this is a business risk

### Lab Structure

| Section | Title | Duration |
|---------|-------|----------|
| 1 | What is a CVE? | 1 min |
| 2 | What is an SBOM and why it matters | 2 min |
| 3 | The traditional patch workflow — why it takes weeks | 2 min |

### Detailed Steps

1. Read the brief overview of CVEs: a CVE (Common Vulnerabilities and Exposures) is a public record of a security flaw in software, scored by severity (CVSS). Low scores may be safe to auto-patch; critical scores require careful review.
2. Observe the example CVE record shown in the lab interface — note the affected package, CVSS score, and affected versions.
3. Read the SBOM explainer: a Software Bill of Materials is a machine-readable inventory of every component in a software artifact — libraries, versions, checksums. When a CVE targets a specific library version, an SBOM tells you exactly which of your applications ship that library.
4. Observe how TPA uses the SBOM to pinpoint which of Dinesh's 29 applications are exposed to the flagged CVE — without manual inspection.
5. Read the traditional patch timeline: security team identifies CVE → manually checks which apps are affected → opens tickets → developers source a patch → test in staging → deploy to production. Typical timeline: 2–6 weeks per CVE.
6. Note the contrast: Lightwell processed 298 patches across 29 applications overnight. The rest of this lab explains how.

### Key Takeaways

- A CVE without an SBOM requires manual inspection of every application to determine impact; with an SBOM, impact is computed automatically.
- CVSS severity alone does not determine remediation priority — business criticality of the affected application also matters.
- The gap between "vulnerability published" and "patch deployed" is where organizations are exposed. Lightwell compresses that gap from weeks to hours.

### Infrastructure Notes

This module is presenter-narrated reference content, not interactive lab steps. No cluster interaction required. Content is rendered as Showroom instructional pages only.
