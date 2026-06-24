---
name: debug-scalability-test
description: Coordinator skill for managing the 5k-node Kubernetes scalability debugging process. Use this skill when investigating scalability test failures to fan out tasks to multiple sub-agents (infra-expert, control-plane-expert, metrics-expert) and synthesize their results into a final triage journal.
---

# Debug Scalability Test

## Overview

This is the primary coordinator skill designed to orchestrate the end-to-end debugging process for the `ci-kubernetes-e2e-gce-scale-performance-5000` test suite. It acts as the "Master Orchestrator" or "Mapper," fanning out triage tasks to specialized sub-agents and synthesizing their findings into a cohesive, data-backed bug report.

## Orchestration Workflow

### 1. State Polling & Artifact Filtration
Before invoking sub-agents, the orchestrator must poll the GCS bucket to determine the run state and filter the massive logs into a local `/tmp/k8s-triage/[BUILD_ID]/` directory.
*(See `cl2-artifacts-reference` skill for the exact structure and filtration commands).*

### 2. Delegating to Domain Experts (The "Reducers")
Based on the filtered evidence, delegate analysis to the appropriate specialized sub-agents. **CRITICAL:** A single run may have multiple failures (e.g., a core test failure followed by a teardown deadlock). You MUST invoke ALL relevant sub-agents if multiple filters match.

*   **`metrics-expert`**: Invoke this agent if `test-results.txt` shows test failures AND `filtered-metrics.json` shows SLO breaches (>1000ms latency).
    *   *Prompt Example:* "Analyze the test failures in `/tmp/.../test-results.txt` and the metric anomalies in `/tmp/.../filtered-metrics.json`. Correlate latency spikes with request volumes."
*   **`control-plane-expert`**: Invoke this agent if `filtered-api.txt` contains `context deadline exceeded`, `HTTP 429`, or Go panics.
    *   *Prompt Example:* "Analyze the API server errors in `/tmp/.../filtered-api.txt` and identify the source of the dropped requests or saturation."
*   **`infra-expert`**: Invoke this agent if `build-tail.txt` contains an infrastructure teardown error (`exit status`, `googleapi: Error 400`, or `resourceInUseByAnotherResource`).
    *   *Prompt Example:* "Analyze the infrastructure teardown failure in `/tmp/.../build-tail.txt`. Determine if this is a spurious lock contention or a primary failure."

### 3. Red-Team Review
Before saving the final journal, you MUST pass your drafted triage report to the **`red-team-reviewer`** sub-agent.
*   The `red-team-reviewer` acts as an adversarial, highly skeptical performance engineer. Its purpose is to find logical gaps, confounding variables, missing baselines, or unproven categorical statements.
*   **Mandatory Saturation Challenge**: Instruct the reviewer to aggressively attack any claims of "resource saturation" (e.g., CPU, Disk IO). It must demand proof from absolute utilization metrics to ensure the system wasn't actually suffering from scheduler starvation (high run-queue, idle cores) instead of true saturation.
*   **Tone & Timeline Audit**: Instruct the reviewer to aggressively reject any journal using absolute, categorical language (e.g., "proves", "definitively"). It must also reject any journal that blames a PR for a failure if that failure signature existed *before* the PR was merged.
*   You must address all flaws identified by the reviewer, which may require fetching additional metrics to strengthen your evidence.

### 4. Mandatory Dashboard Generation
Before finalizing the journal, you MUST extract the TSDB metrics and generate visual graphs:
*   You must query the true metrics from the `prometheus_snapshot.tar` or JSON files. Do NOT use fake fallback data.
*   Render the visualizations to explicitly prove your mechanical bottleneck (e.g., plot `go_sched_goroutines_runnable` vs CPU utilization to prove starvation).

### 5. Journaling and Synthesis
After passing the red-team review and generating the dashboard, save the final, synthesized root-cause report to `./triage-journals/[BUILD_ID]/journal.md`. Embedded visualizations are MANDATORY.

**Mandatory Journal Format:**
*   **Header**: Build ID, Status, and human-readable Completion Time (converted from Unix timestamp).
*   **Executive Summary**: A brief (1-3 sentence) summary stating the identified root cause.
*   **Triage Narrative**: A step-by-step narrative explaining the reasoning (e.g., "Because the junit.xml showed 2 failures, it indicated the teardown timeout was a secondary symptom...").
*   **Supporting Evidence**: Include exact file paths, literal log entries, and specific metric values. *Rule:* If you claim a resource was saturated, you MUST provide the specific metric values that support it.
*   **Tone and Language**: You MUST avoid categorical, absolute language (e.g., "mathematically proves", "definitively", "fully verified"). Always use circumspect, qualified language (e.g., "strongly suggests", "indicates", "highly probable") to acknowledge the possibility of confounding variables.
