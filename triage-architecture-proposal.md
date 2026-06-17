# Architecture Proposal: Local-First Triage Agent Swarm for kubernetes/perf-tests

## Overview
Implementing a fully automated, CI-integrated triage agent for the upstream `kubernetes/perf-tests` repository (specifically the 5k-node scalability tests) involves significant infrastructure friction. Changing the CI/CD pipeline (Prow, Argo, sandboxes) requires widespread consensus and dedicated compute resources.

To enable immediate, high-impact adoption without requiring *any* changes to the existing CI infrastructure, we propose a **"Low-Resource, Local-First" Architecture**. 

This approach brings the triage swarm directly to the performance engineer's local environment. It relies on standard CLI tools, zero-memory data streaming, persistent local history, and a library of portable agent skills that can be executed on a standard developer laptop.

---

## Pillar 1: Foundational Skills (Portable Procedural Knowledge)
Instead of hardcoding logic into a monolithic bot, triage logic is decoupled into atomic, portable "Skills" (packaged as `.skill` files). These skills provide procedural guardrails that any generic LLM CLI agent can ingest dynamically.

Examples of foundational skills created for this endeavor:
*   **`cl2-artifacts-reference`**: Provides the exact GCS bucket topologies and parsing rules for ClusterLoader2 outputs.
*   **`flakiness-triage`**: Establishes strict rules for differentiating between infrastructure teardown deadlocks and genuine code regressions.
*   **`journaling-execution-memory`**: Forces the agent to maintain an externalized scratchpad of its hypotheses, preventing context-window decay.

## Pillar 2: Specialized Triage Agents (The Swarm)
Rather than using a single, massive context window to process 55GB of logs, the architecture employs a swarm of narrowly focused sub-agents. 

When invoked by the local orchestrator, these agents ingest specific, pre-filtered snippets:
*   **`metrics-expert`**: Correlates Prometheus JSON summaries and identifies anomalies like the "Thundering Herd" or SLO breaches.
*   **`control-plane-expert`**: Analyzes specific API server errors (`context deadline exceeded`, `HTTP 429`) and Go panics.
*   **`infra-expert`**: Investigates GCP provisioning and `kubetest2` teardown failures.
*   **`red-team-reviewer`**: An adversarial agent that prevents the orchestrator from making categorical claims without absolute proof.

## Pillar 3: Historical Context & Local Memory
To triage effectively, agents need a baseline. Analyzing a single run in isolation often leads to false positives. 

*   **Local Synthesis Database:** After triaging a run (whether it passed or failed), the orchestrator saves a highly compressed, synthesized JSON summary of the run's key metrics, exit codes, and failure signatures to a local directory (e.g., `~/.k8s-triage-history/`).
*   **Automated Baselining:** When analyzing a new failure, the agent queries this local history to mathematically prove deltas (e.g., "The local history shows successful runs average 400 LIST calls; this failed run had 581, representing a 45% abnormal surge").
*   **Trend Analysis:** By storing historical signatures, the agent can instantly tell the engineer if the current failure is a known, repeating flake or a novel hard regression.

## Pillar 4: Engineer-Driven Local Execution (Zero-Infrastructure)
The core of this architecture is the execution model. It runs entirely on the performance engineer's local machine, requiring zero integration with Prow or GitHub webhooks.

1.  **Manual Trigger:** An engineer notices a 5k-node test failure on the Perfdash dashboard.
2.  **Local Execution:** The engineer opens their terminal and executes the local master orchestrator (e.g., `gemini -f orchestrator-prompt.md`).
3.  **Zero-Memory Streams:** The local orchestrator uses the engineer's existing credentials (`gcloud auth`) to stream data. Crucially, it uses Unix pipes (`gcloud storage cat ... | grep`) to pull *only* the matching error signatures down to the local `/tmp/k8s-triage/` directory. This avoids downloading 55GB of logs.
4.  **Local Delegation & History Lookup:** The orchestrator queries the local history database (Pillar 3) to establish a baseline, then delegates the filtered data to the specialized agents (Pillar 2).
5.  **Final Output:** A detailed, red-team-verified `journal.md` is generated directly on the engineer's filesystem, ready to be copy-pasted into a GitHub Issue or PR.

---

## Advantages of the Local-First Approach

1.  **Zero CI Friction:** Requires no approval from SIG-Testing, no custom Prow plugins, and no dedicated Kubernetes orchestration clusters.
2.  **Historical Intelligence:** Local storage of compressed run data gives the agent superhuman memory for spotting flakes and establishing mathematical baselines without re-downloading old GCS artifacts.
3.  **Immediate Adoption:** Engineers can install the `.skill` files and start using the agent today.
4.  **Security by Default:** Because it runs locally using the engineer's own credentials, there is no "Confused Deputy" risk associated with bots automatically executing code from PRs in the cloud.