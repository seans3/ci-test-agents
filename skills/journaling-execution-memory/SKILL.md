---
name: journaling-execution-memory
description: Records agent actions, hypotheses, and findings during complex debugging sessions. Use this skill to maintain a strict execution journal, preventing the agent from getting stuck in loops, repeating failed strategies, or losing context over long sessions.
---

# Journaling & Execution Memory

## Overview

Complex software triage (like Kubernetes 5k-node performance debugging) requires multi-step investigations. Agents are susceptible to context-window decay or entering infinite loops when tools repeatedly fail.

This skill dictates how an agent must maintain a persistent, externalized "Execution Memory" to ensure forward progress and where to store the final output.

## Journaling Workflow

When engaged in a complex debugging task, the agent MUST adhere to the following memory practices:

### 1. State the Hypothesis
Before executing a heavy command (e.g., downloading a massive log, executing a Python script, invoking a sub-agent), explicitly write down the hypothesis.
*   *Example:* "Hypothesis: The API server is panicking because the memory limit was exceeded. I will check the `ResourceUsageSummary` metric to prove this."

### 2. Record the Outcome
Immediately after the command completes, log the factual result against the hypothesis.
*   *Example:* "Result: The memory limit was NOT exceeded (Peak was 45%). The hypothesis is invalidated."

### 3. Track Dead Ends (Anti-Looping)
If a specific tool call, search query, or hypothesis fails, explicitly mark it as a `DEAD END`.
*   You MUST review the list of `DEAD ENDs` before formulating a new plan.
*   You MUST NOT execute the exact same tool call or shell command twice if it previously failed, unless you have fundamentally changed the environment or the parameters.

### 4. Synthesize the Triage Journal
When the root cause is found, compile the running execution memory into the final report. The final report must not just state the conclusion; it must narrate the journey:
*   State the initial symptom.
*   List the hypotheses tested.
*   Explain *why* the invalid hypotheses were discarded (using data).
*   Provide the definitive proof for the correct hypothesis.

## File Locations

### Temporary Storage (The Scratchpad)
If the context window is getting full during a long session, the agent should write its running execution memory to a temporary scratchpad file and read it back to re-orient itself:
*   **Path:** `/tmp/k8s-triage/[BUILD_ID]/scratchpad.md`

### Permanent Storage (The Final Journal)
Once the triage is complete and the root cause is found, the final, synthesized narrative MUST be saved to the permanent journal directory within the workspace:
*   **Path:** `./triage-journals/[BUILD_ID]/journal.md`
