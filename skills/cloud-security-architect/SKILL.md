---
name: cloud-security-architect
description: |
  Specializes in cloud security architecture, GCP hardening, application and API security, AI/ML/LLM security, privacy-by-design, threat modeling, and compliance mapping for the ResonanceLab acoustic fingerprint platform.
  Use for security reviews, Cloud Run/IAM/Artifact Registry/Cloud Build configuration, upload and browser audio attack-surface analysis, Vertex Gemini explain-path controls, CORS/secrets/rate-limit changes, deployment reviews, external integrations, incident response, and mapping work to MITRE ATT&CK/ATLAS, OWASP, NIST, ISO/IEC 27001, ISO/IEC 42001, CIS, SLSA, and Google Cloud security foundations.
license: MIT
metadata:
  version: v1
  publisher: resonance-labs
---

# Cloud Security Architect Skill

This skill governs security architecture, hardening, threat modeling, incident response, and framework mapping for **ResonanceLab**. It emphasizes browser-based active acoustic sensing, deterministic DSP, optional grounded LLM explanations, derived report exports, and GCP serverless deployment.

For project context, read the root README, FEATURES, docs directory, cloudbuild.yaml, and the other skills before making project-specific recommendations.

---

## 1. Operating Rules

*   **Inspect before advising**: Read the relevant code, docs, Cloud Build substitutions, and deployment scripts before recommending controls. Treat live cloud state as discoverable, not assumed.
*   **Separate current state from target state**: Mark Cloud Storage, GitHub Actions, Cloud Armor, IAP, Binary Authorization, VPC Service Controls, and other broader controls as future or recommended unless local or cloud discovery confirms they exist.
*   **Prefer evidence over assertion**: Provide findings with affected component, observed evidence, impact, recommendation, validation method, and framework mapping.
*   **Do not claim compliance**: Say "supports alignment with" unless an audit has verified scope, evidence, and control operation.
*   **Use exact framework IDs only when verified**: Frameworks drift. Use family/category mappings unless an authoritative source or local reference confirms the exact version and ID.
*   **Do not change production security controls casually**: Ask before modifying IAM, org policies, Cloud Run ingress/auth, CORS, firewall rules, secrets, logging sinks, service accounts, or deploy triggers.

---

## 2. Core Security Invariants

These invariants must not be weakened without explicit security review:

*   **No raw audio to hosted LLM paths**: `/api/v1/explain` receives compact structured DSP evidence only. Reject WAV bytes, PCM samples, raw-audio opt-in flags, and full high-dimensional grids.
*   **Derived reports only by default**: Exported JSON and PNG reports may include metadata, compact grids, descriptors, caveats, validation signals, and derived traces. They must not include raw PCM, WAV blobs, or unreviewed identifying data.
*   **Microphone capture requires explicit user action**: Keep AudioContext unlock and `getUserMedia` behind direct user gestures and HTTPS-capable contexts. Preserve visible microphone and no-headphones safety cues.
*   **Least privilege by default on GCP**: Use a dedicated Cloud Run runtime service account. Hosted Gemini access is opt-in through `_LLM_ENABLED=true` and scoped IAM. Do not use long-lived service account keys.
*   **Strict server-side upload validation**: Validate content type, upload size, recording duration, WAV structure, decoded size, RMS/peak/DC sanity, sample rate, channels, and metadata before DSP work.
*   **Deterministic fallback remains authoritative**: Hosted LLM explanations are additive. The deterministic explain path must remain complete, tested, and available when hosted calls are disabled or fail.
*   **LLM claims require evidence grounding**: LLM claim objects must cite leaf JSON Pointers into the supplied evidence packet. Drop or replace unresolvable, over-broad, or unsupported claims with deterministic fallback text.
*   **Operator questions are context, not evidence**: Free-text operator questions may guide explanation focus, but they must not be included in the evidence packet or valid evidence-reference list.
*   **Security logs are compact and non-sensitive**: Log request IDs, analysis IDs, validation outcomes, rejection reasons, quality signals, and LLM outcomes. Do not log raw audio, full prompts/responses, secrets, or high-dimensional signal grids.
*   **Report exports minimize reflected metadata**: JSON and PNG report paths must keep public-safe DSP evidence while dropping filenames, user-agent strings, device IDs, group IDs, requested constraints, and arbitrary client-supplied metadata.

---

## 3. Data Classification

Classify data by the most sensitive plausible interpretation:

*   **Raw microphone audio / PCM / WAV**: Highest sensitivity. A room microphone can capture speech, private conversations, or environmental identifiers. Do not store server-side or send to hosted models by default.
*   **Full-resolution spectrograms, traces, and high-dimensional grids**: Sensitive derived data. They may encode environmental details and should be compacted before export or LLM use.
*   **Compact DSP evidence and report JSON**: Lower sensitivity but still potentially identifying. Minimize fields, avoid unnecessary device/location/user identifiers, and document retention.
*   **LLM prompts, responses, and claim metadata**: Sensitive operational data. Prefer logging outcome categories and grounding status over full content.
*   **Secrets, IAM bindings, deploy substitutions, and project IDs**: Operationally sensitive. Keep private values out of committed files and container images.

---

## 4. Review Workflow

Use this workflow for security reviews and architecture changes:

1.  **Scope assets and trust boundaries**: Browser, API, Cloud Run services, service accounts, Artifact Registry, Cloud Build, optional Vertex Gemini, logs, exported reports, local fixtures, and any new integration.
2.  **Trace data flows**: Browser audio capture -> WAV encoding -> upload -> API validation -> DSP -> report/explain/export. Include failure paths and logs.
3.  **Model threats**: Apply STRIDE per boundary, then map cloud/app behaviors to MITRE ATT&CK and AI/ML behaviors to MITRE ATLAS.
4.  **Assess controls**: Review IAM, upload validation, CORS, rate limiting, resource caps, secret handling, logging, supply chain, model boundaries, output grounding, and retention.
5.  **Create a risk register**: Include severity, evidence, impact, recommendation, validation, owner, and framework mapping.
6.  **Validate**: Prefer tests, config inspection, logs, scanner output, policy checks, or cloud evidence. Mark assumptions and evidence gaps plainly.

---

## 5. GCP Security Practices

### 5.1 Identity and Access

*   Use per-service identities for runtime, build, and future jobs. Do not reuse default Compute Engine or App Engine service accounts.
*   Avoid primitive roles and broad admin roles on runtime identities. Prefer predefined or custom roles scoped to required resources.
*   Use Cloud Build and Cloud Run service identities over downloaded keys. If external CI is added, prefer Workload Identity Federation and maintainer-gated privileged workflows.
*   Review IAM on every deploy or LLM-enablement change. Remove stale grants with IAM Recommender or equivalent review evidence.
*   Enforce human access through groups, MFA/SSO, short-lived elevation, and periodic access review where the GCP organization supports it.

### 5.2 Cloud Run Hardening

*   Keep public unauthenticated access only for intentionally public web/API paths. Add authentication or Identity-Aware Proxy before adding user-specific data or private reports.
*   Preserve resource guardrails: max instances, concurrency, memory, CPU, request timeout, upload size, and recording duration.
*   Use explicit CORS origins. Do not use wildcard origins with credentials. Treat `_EXTRA_CORS_ORIGINS` as security-sensitive deploy configuration.
*   Run minimal, non-root containers where feasible. Avoid shell tooling and heavy ML libraries in the primary API image unless justified.
*   Use Secret Manager references for any future secrets. Do not bake secrets into Docker images, source, Cloud Build YAML, or plaintext env vars.
*   Consider restricted ingress, load balancer fronting, Cloud Armor, VPC egress controls, and Private Google Access when the service handles higher-sensitivity data.

### 5.3 Build and Supply Chain

*   Treat fork pull requests and external build triggers as untrusted. Do not expose deploy credentials or secrets to untrusted workflows.
*   Keep the build identity least-privileged for building, pushing, and deploying only the intended services.
*   Pin base images and dependencies. Keep Dockerfile `FROM` lines and Cloud Build step images digest-pinned, keep direct Python dependencies exact-pinned unless a reviewed lockfile/hash workflow replaces them, and avoid unpinned `latest` tags or remote install scripts in builds.
*   Use Artifact Registry vulnerability scanning, dependency scanning, secret scanning, SBOM generation, SLSA-style provenance, and image signing as the project matures.
*   Consider Binary Authorization or deploy admission checks before allowing higher-sensitivity workloads.

### 5.4 Data Protection and Secrets

*   Keep project IDs, private deploy notes, service account keys, datasets, and generated artifacts out of committed files.
*   Use Secret Manager and Cloud KMS where secrets or customer-managed encryption requirements exist.
*   Enforce public access prevention and uniform access for any future Cloud Storage bucket. Serve private artifacts through the app or time-limited signed URLs.
*   Apply lifecycle retention to derived reports and artifacts. Avoid raw-audio retention by default.
*   Consider DLP inspection and VPC Service Controls for high-sensitivity deployments or regulated datasets.

### 5.5 Logging, Detection, and Response

*   Preserve structured logging with request correlation and rejection reasons.
*   Enable and review Cloud Audit Logs for administrative changes. Consider Data Access logs for sensitive services.
*   Use Security Command Center, Cloud Run threat detection, artifact vulnerability findings, and budget/quota alerts where available.
*   Alert on IAM changes, service account key creation, deploy failures, CORS expansion, abnormal upload volume, LLM cost spikes, and repeated validation failures.

---

## 6. Application and API Security

### 6.1 Upload and DSP Boundary

*   Treat uploaded audio as hostile binary input. Validate before decoding, bound memory use, and reject malformed or oversized content before DSP runs.
*   Keep upload limits and allowed content types in configuration and probe metadata.
*   Prefer hardened PCM WAV decoding. Keep lossy or flexible decoding constrained and tested before enabling.
*   Add tests for parser-bomb, duration, sample-rate, channel, oversized body, truncated WAV, and malformed metadata cases.

### 6.2 API Hardening

*   Use Pydantic v2 schemas and explicit response models for request and response boundaries.
*   Add object-level and function-level authorization before introducing user accounts, private reports, cloud storage, or tenant-specific artifacts.
*   Rate limit `/api/v1/analyze` and `/api/v1/explain` when public traffic or hosted LLM calls are enabled.
*   Return safe error responses with request IDs. Do not expose stack traces, internal paths, dependency versions, or cloud identifiers.
*   Keep CORS, security headers, payload caps, and middleware behavior covered by tests.

### 6.3 Frontend and Browser Security

*   Keep Web Audio, microphone, storage, and browser-only APIs behind SSR guards and explicit user gestures.
*   Preserve amplitude clamps, fades, and no-headphones warnings as safety controls.
*   Render LLM, metadata, and report text as escaped text. Do not use untrusted `innerHTML` or Svelte `{@html}`.
*   Add a strict Content Security Policy when external scripts, analytics, auth, or hosted report views are introduced.
*   Keep all credentials server-side. The browser must not hold cloud API keys or service account material.

---

## 7. AI/ML and LLM Security

The current AI boundary is optional Vertex Gemini explanation over compact DSP evidence. Reassess this section if RAG, tools, agents, fine-tuning, training data, or user-specific retrieval is added.

### 7.1 Prompt and Data Boundary

*   Separate system instructions from user- or analysis-derived data. Treat every user-influenced field as untrusted.
*   Treat operator questions as untrusted prompt context, not citable evidence.
*   Strip unnecessary identifiers before hosted model calls.
*   Keep the system prompt static, scoped to explaining acoustic reports, and explicit about prohibited claims: no raw audio, no geometry reconstruction, no identity inference, no medical/legal/safety conclusions, and no certainty beyond evidence.

### 7.2 Output Controls

*   Require one top-level JSON object from hosted explanations.
*   Validate schema, evidence references, and grounding status server-side before returning or rendering model output.
*   Render model output as data only. Do not execute, evaluate, route, or authorize actions from model text.
*   Surface deterministic baseline and caveats alongside hosted explanations to reduce overreliance.

### 7.3 Access and Abuse Controls

*   Enable hosted LLM calls only through `_LLM_ENABLED=true`, explicit model/provider settings, and scoped Vertex IAM on the runtime service account.
*   Use request body caps, token caps, max instances, concurrency, quota, and budget alerts to control cost and denial-of-wallet risk.
*   Log outcome categories, fallback reasons, grounding failures, and safety refusals without logging full prompts or responses.

### 7.4 AI Governance

*   Maintain a lightweight AI risk assessment and impact assessment for the explain feature.
*   Red-team hosted mode before enabling it and after changes to prompts, evidence shape, model ID, retrieval, tools, or output handling.
*   Document model selection, intended use, limitations, monitoring signals, and rollback plan.

---

## 8. Framework Mapping Heuristics

Use mappings to communicate coverage, not to imply certification or one-to-one equivalence.

| Control Area | Primary Framework Anchors |
| :--- | :--- |
| Governance and risk | NIST CSF Govern/Identify, NIST AI RMF Govern/Map, ISO/IEC 27001 ISMS, ISO/IEC 42001 AIMS, OWASP SAMM |
| IAM and least privilege | NIST CSF Protect, NIST SP 800-53 AC/IA families, ISO/IEC 27001 access controls, MITRE ATT&CK credential and privilege techniques |
| Cloud workload hardening | Google Cloud security foundations, CIS Google Cloud Benchmark, NIST SP 800-53 CM/SC/SI families, MITRE ATT&CK cloud/container techniques |
| App and API security | OWASP Top 10, OWASP API Security Top 10, OWASP ASVS, NIST SSDF, MITRE ATT&CK initial-access and web exploitation techniques |
| Upload and binary parsing | OWASP input validation guidance, NIST SSDF, NIST SP 800-53 SI family, API resource-consumption risks |
| CI/CD supply chain | NIST SSDF, SLSA, OWASP SAMM, OWASP vulnerable/outdated components and software/data integrity failures, MITRE supply-chain techniques |
| Data protection and privacy | NIST CSF Protect, NIST SP 800-53 SC/MP/PT families, ISO/IEC 27001 data protection controls, GCP DLP/KMS/VPC-SC evidence |
| LLM and AI/ML security | OWASP LLM Top 10, OWASP ML Top 10, MITRE ATLAS, NIST AI RMF, ISO/IEC 42001, ISO/IEC 23894 |
| Detection and response | NIST CSF Detect/Respond/Recover, NIST SP 800-53 AU/IR/CP families, MITRE ATT&CK detections and mitigations |

### Common ResonanceLab Risk Mappings

*   **Raw audio leakage**: OWASP sensitive data exposure themes, NIST data protection, ISO/IEC 42001 impact assessment, MITRE exfiltration patterns.
*   **Public analyze endpoint abuse**: OWASP API unrestricted resource consumption, NIST availability controls, Cloud Run max-instance and timeout guardrails.
*   **Prompt injection or unsupported LLM claims**: OWASP LLM prompt injection and output-handling risks, MITRE ATLAS AI attack patterns, NIST AI RMF measure/manage.
*   **Fork or build pipeline compromise**: NIST SSDF, SLSA, OWASP software integrity risks, MITRE supply-chain compromise.
*   **Overclaiming acoustic capability**: NIST AI RMF governance and ISO/IEC 42001 AI policy/objective controls; maintain "fingerprint/proxy/report/caveat" language.

---

## 9. Secure Development and Review Practices

*   Require security review for changes to IAM, Cloud Build, Cloud Run deploy flags, CORS, upload validation, report export shape, LLM evidence packets, prompt/output handling, secrets, or external integrations.
*   Prefer tests and policy checks over prose-only assurances.
*   Update relevant docs and skills when security-sensitive behavior changes.
*   Add or update tests for validation limits, CORS, hosted LLM gating, raw-audio rejection, evidence grounding, deterministic fallback, and report schemas.
*   Keep dependency additions small and justified. Avoid heavy ML libraries in the API container unless a reviewed feature requires them.
*   Use "disabled by default" for new risky capabilities: hosted model calls, persistence, public report sharing, user accounts, external callbacks, and privileged tools.

---

## 10. Best Practices Checklist

| Area | Recommended Practice | Prohibited Practice |
| :--- | :--- | :--- |
| **GCP IAM** | Dedicated least-privilege service accounts and reviewed Vertex access. | Runtime `owner`/`editor`, default service accounts, or downloaded keys. |
| **Cloud Run** | Gen2, explicit CORS, resource caps, safe timeouts, scoped env vars. | Unbounded concurrency, wildcard credentialed CORS, or secrets in images. |
| **Uploads** | Layered validation, bounded decode, content-type and WAV checks. | Trusting client metadata or decoding unbounded binaries. |
| **LLM Path** | Compact grounded JSON, IAM auth, disabled by default, deterministic fallback. | Raw WAV/PCM/full grids to a hosted model or ungrounded claims. |
| **Reports** | Derived JSON/PNG only with minimized metadata, caveats, and local comparison first. | Raw audio retention, arbitrary metadata reflection, or public sharing without review. |
| **Secrets** | Secret Manager, KMS where needed, secret scanning and rotation. | Secrets in source, logs, Docker images, or local notes committed to git. |
| **Supply Chain** | Digest-pinned images, exact direct dependency pins, scanning, SBOM/provenance, reviewed deploy identity. | Untrusted fork workflows with deploy credentials, unpinned build images, or floating direct dependency ranges. |
| **Observability** | Request IDs, rejection reasons, quality signals, LLM outcomes. | Raw audio, secrets, full prompts/responses, or high-dimensional grids in logs. |

---

## 11. Incident Response Guidance

*   **Leaked credential or private file**: Rotate first, revoke access, freeze affected deploys, then follow the repository history-cleanup runbook.
*   **Raw audio exposure**: Stop retention/export path, identify affected artifacts/logs, remove access, notify maintainers, assess legal/privacy obligations, and add tests to prevent recurrence.
*   **LLM cost or abuse spike**: Disable hosted mode, reduce quotas/max instances, inspect request patterns, add rate limiting, and review prompt/body caps.
*   **Malicious build or dependency compromise**: Disable deploy trigger, revoke build identity tokens, rebuild from known-good dependencies, inspect Artifact Registry images, and rotate secrets.
*   **Unsupported model claims**: Disable hosted explanations or force deterministic fallback, inspect grounding failures, tighten schema/prompt, and add regression tests.

When uncertain, choose the safer default: disabled, least privilege, compact evidence, deterministic first, explicit user consent, and documented caveats.
