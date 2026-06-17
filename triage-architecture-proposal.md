# Architecture Proposal & Red-Team Analysis: Autonomous Triage Agent for kubernetes/perf-tests

## 1. Overview of Proposed Architecture
The proposed architecture outlines an autonomous, LLM-driven "Release Shepherd Agent" tailored for the `kubernetes/perf-tests` repository. It is designed to triage 5k-node scalability test failures (driven by ClusterLoader2) by pulling Prometheus metrics, parsing logs, and identifying culprit commits. It features GitOps integration via Prow (`/triage-perf`, `/verify-perf-fix`) and utilizes Kubemark for cheap, automated rollback verification.

## 2. Red-Team Critique: Operational and Deployment Gaps

While the high-level logic (Flake -> Blame -> Verify) is sound, a red-team analysis of the deployment realities reveals critical gaps in execution, security, and data management.

### Gap A: Execution Environment (Where does this actually run?)
The architecture diagram glosses over the physical compute requirements.
*   **The Reality:** Filtering 55GB of logs and orchestrating a Kubemark cluster cannot run inside a lightweight GitHub Action runner or a standard Prow Job pod (which typically have strict CPU/Memory limits and short timeouts).
*   **The Gap:** If the "Data Parser" runs inside a standard Prow pod, it will OOM-kill when attempting to stream `kube-apiserver.log`. If it orchestrates Kubemark, the pod will timeout before the 3-hour Kubemark test completes.
*   **Required Fix:** The triage agent must be decoupled into an asynchronous, stateful control plane. Prow should only trigger an external orchestration cluster (e.g., a dedicated Kubernetes cluster running Argo Workflows or Temporal) that has attached high-IOPS scratch disks for log processing and long-lived pods to monitor the Kubemark execution.

### Gap B: Artifact Retention and Temporal Skew
The architecture assumes all artifacts are immediately available upon test failure.
*   **The Reality:** The 5k-node tests often fail abruptly (e.g., infrastructure teardown panics), meaning the final Prometheus snapshot (`prometheus_snapshot.tar`) or `.pprof` files may not have been successfully uploaded to the GCS bucket.
*   **The Gap:** If the agent blindly requests the snapshot and it isn't there, the LangChain workflow will crash. Furthermore, the agent assumes the "last green run" is easily comparable, but Kubernetes is a fast-moving target; a baseline from 3 weeks ago may have fundamentally different metric topologies due to upstream API changes.
*   **Required Fix:** The agent must gracefully degrade. If TSDB snapshots are missing, it must fall back to instant-vector JSON metrics. For baselines, it must enforce a strict temporal window (e.g., "baseline must be within the last 5 days") or abort the comparison.

### Gap C: Security and the Confused Deputy Problem
The architecture proposes `/verify-perf-fix #12345` as a Prow slash command.
*   **The Reality:** PR #12345 contains arbitrary code submitted by an external contributor.
*   **The Gap:** If the triage agent automatically pulls PR code and spins up a Kubemark cluster in a privileged Google Cloud environment based on a GitHub comment, it is vulnerable to a "Confused Deputy" attack. A malicious contributor could introduce a cryptocurrency miner or exfiltrate GCP credentials, using the agent to execute the payload.
*   **Required Fix:** The agent MUST verify that the user issuing `/verify-perf-fix` is an authorized org member (`/lgtm` equivalent). Furthermore, the Kubemark sandbox must run in a deeply isolated, credential-less GCP project with absolutely no egress to the internet.

### Gap D: The Cost of API Context Windows
The MVP stack suggests using `gpt-4o` or `Claude-3.5-Sonnet`.
*   **The Reality:** Even aggressively filtered `kube-apiserver` panics or Prometheus metric dumps can span tens of thousands of tokens.
*   **The Gap:** Pumping 50,000 tokens of raw metrics into an LLM for every failing 5k test run will result in massive API costs and frequent context-window exhaustion (resulting in truncation and hallucination).
*   **Required Fix:** The architecture must incorporate deterministic pre-processing. A Python script should mathematically calculate the metric deltas (Failed Run vs. Baseline) and only feed the *anomalies* (e.g., "LIST pods increased by 30%") to the LLM. The LLM should be used for reasoning, not data parsing.

## 3. Revised Reference Architecture

To address these gaps, the architecture should be updated as follows:

```text
[ GitHub PR / Prow ] ──(Webhook + Auth Check)──> [ External Triage Control Plane (Argo/Temporal) ]
                                                            │
                                                            ▼
                                                [ Stateful Orchestrator Pod ]
                                         (Has 500GB Scratch Disk, No API Timeouts)
                                                            │
       ┌────────────────────────────────────────────────────┼────────────────────────────────────────┐
       ▼                                                    ▼                                        ▼
[Deterministic Filter Phase]                      [Heuristic Reasoner (LLM)]              [Isolated Sandbox Phase]
 - Stream GCS logs to disk                        - Ingest filtered anomalies             - Triggered ONLY by core maintainers
 - Use jq/grep to extract errors                  - Identify Flake vs. Regression         - Runs Kubemark in credential-less GCP VPC
 - Calculate math deltas against baseline         - Draft Culprit Hypothesis              - Returns test exit code to Orchestrator
       │                                                    │                                        │
       └────────────────────────────────────────────────────┴────────────────────────────────────────┘
                                                            ▼
                                               [ Final Review & GitHub Post ]
                                               - Post Markdown Report to PR
```
