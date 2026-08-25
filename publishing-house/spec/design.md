# Get Ready for Lightwell: Patch to Production at the Speed of AI

## Overview

This lab demonstrates how Red Hat Lightwell transforms open source vulnerability remediation from a weeks-long manual process into a continuous, policy-driven automated operation. Participants step into the role of Dinesh, a platform engineer at a fictional financial services company, arriving to find that Lightwell has already processed 298 patches across 29 applications overnight — analyzing CVEs, assessing business risk, generating merge requests, and auto-merging the safe ones. A handful of high-risk items remain flagged for expert review.

The remediation pipeline begins when Lightwell patches are automatically delivered into a JFrog Artifactory environment. The arrival of a new patch in Artifactory triggers an Event-Driven Ansible workflow, which passes patch data to Red Hat Trusted Profile Analyzer for environmental impact analysis. From there, the Lightwell Deep Agent assesses risk, generates merge requests, and routes high-risk items for human review. Approved patches move through the Trusted Software Factory for build, signing, and verification, before being deployed across a multi-cluster fleet via RHACM and OpenShift GitOps. Participants work through the flagged items and observe the full pipeline close the loop end-to-end.

## Target Audience

- **Role:** Platform engineers and security-focused operations engineers
- **Experience level:** Intermediate
- **What they already know:** Familiarity with OpenShift, CI/CD pipelines, and basic vulnerability management concepts (CVEs, SBOMs, patch workflows)
- **What they don't know:** How Lightwell orchestrates automated, AI-assisted remediation across a multi-product Red Hat stack; how TPA, OpenShift AI, Trusted Software Factory, and RHACM fit together in a continuous patching pipeline

## Prerequisites

- Basic familiarity with OpenShift (navigating the console, understanding namespaces and deployments)
- Conceptual understanding of CVEs and software supply chain security
- No prior Lightwell experience required

Can the lab validate these automatically? No — trust-based.

## Learning Objectives

1. Explore the Lightwell dashboard to interpret automated patch assessments and identify items requiring manual review
2. Analyze CVE impact scope using Red Hat Trusted Profile Analyzer and SBOM data to assess business risk
3. Evaluate and approve AI-generated merge requests produced by the Lightwell Deep Agent
4. Observe a patch moving through the Trusted Software Factory build, sign, and verify pipeline
5. Deploy patched container images across a multi-cluster fleet using Red Hat Advanced Cluster Management and OpenShift GitOps
6. Verify end-to-end remediation closure, including automated ServiceNow ticket resolution

## Content Type

Lab

## Products & Technologies

- Red Hat Lightwell
- Red Hat OpenShift Container Platform
- Red Hat OpenShift AI
- Red Hat Trusted Profile Analyzer
- Red Hat Ansible Automation Platform (Event-Driven Ansible)
- Trusted Software Factory
- Red Hat Advanced Cluster Management
- Red Hat OpenShift GitOps
- JFrog Artifactory (community, patch ingestion and trigger)
- GitLab (upstream, merge request target)
- ServiceNow (external ITSM integration)

## Module Map

| Module | Title | Duration |
|--------|-------|----------|
| 1 | Patch Ingestion — From Lightwell to Artifactory to Ansible | 20 min |
| 2 | Vulnerability Analysis with Trusted Profile Analyzer | 20 min |
| 3 | AI-Assisted Remediation — Reviewing and Approving Patches | 25 min |
| 4 | Build, Deploy, and Close the Loop | 25 min |
| — | **Total hands-on** | **90 min** |
| — | Intro / orientation | ~5 min |
| — | **Total lab** | **~95 min** |

## Difficulty Level

Intermediate

## Environment

**Learner view:** Participants access a fully pre-deployed environment on OpenShift. The Lightwell dashboard shows 298 patches already processed across 29 applications — auto-merged safe patches are visible in the history, and a small set of high-risk items are queued for manual review. A JFrog Artifactory instance is pre-loaded with the latest Lightwell patch bundles. RHOAI (with Deep Agent skills pre-configured), TPA, TSF, RHACM, and OpenShift GitOps are all deployed and integrated. GitLab repositories are pre-populated with sample applications. A ServiceNow sandbox is pre-wired for ticket management.

**Automation needed:** Yes. Pre-provisioning must deploy the full stack (Lightwell, RHOAI, TPA, TSF, RHACM, GitOps), configure Artifactory with patch bundles and the EDA webhook trigger, seed the platform with CVE data and overnight patch state, configure Deep Agent skills in RHOAI, populate GitLab repositories, and wire in the ServiceNow integration. Participants begin at the "morning review" state — not at a clean install.

## Infrastructure Requirements

- **Cloud provider:** CNV
- **Cluster type:** Multinode
- **OCP version:** 4.22
- **Topology:** Shared-cluster, 20 max concurrent users
- **Sizing:** 3 control plane (16 vCPU, 64GB RAM); 6 workers (16 vCPU, 64GB RAM, 200GB disk)
- **Automation approach:** GitOps (Helm + ArgoCD)
- **AI/MaaS:** MaaS — open-source model (Opus-tier equivalent) via LangChain Deep Agent harness on OpenShift AI
- **External services:** Lightwell Network (patch delivery), ServiceNow sandbox, quay.io, registry.access.redhat.com
- **AAP version:** Latest GA
- **Non-GA products:** None (all products are GA)
