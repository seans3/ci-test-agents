---
name: precise-culprit-pinpointing
description: Identifies specific code or configuration changes causing regressions. Use this skill to analyze failure signatures, historical data, and commit change windows to find the root cause of a code regression.
---

# Precise Culprit Pinpointing

## Overview

Once a test failure has been definitively classified as a `CODE_REGRESSION` (using the `flakiness-triage` skill), this skill is used to find the exact commit, PR, or configuration change that introduced the bug. 

It does this by establishing a "suspect window" between the last known good build and the first known bad build, and then cross-referencing the technical failure signature against the code changes within that window.

## Pinpointing Process

### 1. Define the Suspect Window
*   **Last Known Good (LKG):** Identify the most recent build where the test passed successfully.
*   **First Known Bad (FKB):** Identify the oldest build where this exact failure signature first appeared.
*   **Extract Commits:** The suspect window consists of all commits merged between the LKG and the FKB. Use the `clone-records.json` or `started.json` artifacts from those builds to extract the Git SHAs and determine the diff.

### 2. Extract the Failure Signature
Determine the specific technical manifestation of the bug. 
*   Is it an API server Go panic? Extract the stack trace.
*   Is it an APF (API Priority & Fairness) SLO breach? Note the specific resource (e.g., `LIST pods`) that is saturating.
*   Is it a scheduling failure? Note the specific scheduler plugin that is failing.

### 3. Correlate Signatures with Commits
Review the code changes (PR descriptions, file paths, diffs) within the suspect window and correlate them with the failure signature.
*   If the API server is panicking in a specific Go package, look for commits that modified files in that package.
*   If APF latency spiked, look for commits that changed rate limits, caching layers, or introduced new heavy database queries.
*   If a specific test is failing, look for commits that modified the test itself or the feature it exercises.

### 4. Rank Suspects
If multiple commits match the criteria, rank them by probability:
1.  **High Probability:** Commits that directly modified the crashing function, the failing test, or the specific resource limits in question.
2.  **Medium Probability:** Commits that modified the same component/subsystem, even if the exact file wasn't touched.
3.  **Low Probability:** Commits affecting unrelated subsystems (e.g., UI changes, documentation, unrelated components).

### 5. Propose Next Steps
Once the top suspects are identified, recommend a course of action. This usually involves invoking the `automated-verification` skill to test a revert of the suspected commit.
