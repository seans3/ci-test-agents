# Architecture Proposal: Autonomous Triage Agent for kubernetes/perf-tests

## Overview
Implementing an autonomous triage agent for the upstream `kubernetes/perf-tests` repository (specifically targeting the massive 5k-node scalability and density tests driven by ClusterLoader2) is highly viable. 

Because a single 5k-node test run takes hours and generates massive log files, Prometheus metrics, and etcd data, manual triage of failures is incredibly taxing. This proposal outlines a robust, secure, and cost-effective "Release Shepherd Agent" that integrates deeply into the Kubernetes CI/CD stack.

This architecture incorporates critical operational realities, ensuring the system can handle 55GB+ log payloads, protect against malicious code execution, and prevent LLM context-window exhaustion.

---

## Pillar 1: Asynchronous, Stateful Orchestration
A standard GitHub Action or Prow Job pod is insufficient for 5k-node triage due to strict CPU/Memory limits and short timeouts.

*   **Decoupled Control Plane:** Prow acts solely as the trigger. When a 5k periodic job fails, a Prow Webhook triggers an external, stateful orchestration cluster (e.g., Argo Workflows or Temporal).
*   **Heavy Compute Nodes:** The orchestration pods are provisioned with large scratch disks (e.g., 500GB SSDs) and have no restrictive API timeouts, allowing them to safely download, stream, and process massive GCS artifacts and orchestrate long-running sandbox verifications.

## Pillar 2: Deterministic Data Collection & Pre-Processing
LLMs are highly expensive and prone to hallucination when fed tens of thousands of tokens of raw log data. Data must be strictly pre-processed.

*   **Zero-Memory Streaming:** The agent uses Unix pipes (`gcloud storage cat ... | grep`) to extract only errors, panics, and SLO breaches, never loading raw `kube-apiserver` or `build-log` files entirely into memory.
*   **Mathematical Deltas:** Instead of feeding raw TSDB metrics to the LLM, a deterministic Python pre-processor calculates the deltas between the failed run and a known-good baseline (e.g., "LIST pods increased by 30%"). Only the *calculated anomalies* are fed to the LLM context.
*   **Graceful Degradation:** 5k tests often fail abruptly, meaning final `prometheus_snapshot.tar` or `.pprof` artifacts may not be uploaded. The agent is programmed to gracefully degrade to instant-vector JSON metrics or `build-log.txt` parsing if high-fidelity artifacts are missing.

## Pillar 3: Core LLM/Agent Logic (The Triage Engine)
Using an open-source framework (like LangChain) and a capable reasoning model (e.g., `gpt-4o`, `Claude-3.5-Sonnet`, or `Llama-3`), the agent executes a structured analysis loop:

1.  **Flakiness vs. Regression Analysis:** The agent cross-references the failure signature against infrastructure logs. If the core test (`junit.xml`) passed but the cluster failed to delete due to GCE quota limits, it flags the run as an **Infrastructure Flake** and adds an automated `/retest` or `/skip-blocking` comment.
2.  **Culprit Pinpointing (The "Blame" Engine):** For real regressions, the agent extracts the failure signature (e.g., API server lock contention) and analyzes the Git commit window since the last green run. It correlates the technical failure (e.g., caching logic) with specific PRs merged in that window.
3.  **Red-Team Verification:** Before posting any findings, a secondary, adversarial "Red-Team" prompt evaluates the draft to ensure no categorical claims are made without absolute metric proof, preventing the bot from spamming PRs with false accusations.

## Pillar 4: Secure Automated Sandbox Verification (Kubemark)
Spinning up a real 5k-node GCE/AWS cluster to verify a rollback is extremely expensive and slow. The agent instead uses **Kubemark** to simulate control-plane load cheaply.

*   **The Workflow:** The agent creates a temporary branch, reverts the suspected culprit PR, launches a 5k Kubemark test run, and monitors if the SLO metrics return to normal.
*   **Security (Preventing Confused Deputy):** Because this process executes arbitrary code from a PR, it is heavily secured.
    *   **RBAC:** The agent verifies that the user issuing the command is an authorized org member (equivalent to `/lgtm` permissions).
    *   **Network Isolation:** The Kubemark sandbox executes in a deeply isolated, credential-less GCP project (VPC) with absolutely no internet egress, preventing crypto-mining or data exfiltration attacks.

## Pillar 5: Open Source Interaction Interface (Prow Plugin)
Maintainers interact with the agent directly where they work—on GitHub PRs and Issues—via a custom Prow bot plugin.

*   `/triage-perf`: Forces the agent to re-analyze the Prometheus and log dumps for the current PR or issue.
*   `/verify-perf-fix #12345`: Instructs the agent to securely run a Kubemark test with PR #12345 applied to see if it resolves the documented performance degradation.

---

## Reference Architecture Diagram

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
 - Graceful degradation on missing data                     │                                        │
       │                                                    │                                        │
       └────────────────────────────────────────────────────┴────────────────────────────────────────┘
                                                            ▼
                                               [ Final Review & GitHub Post ]
                                               - Red-Team Critique
                                               - Post Markdown Report to PR
```
