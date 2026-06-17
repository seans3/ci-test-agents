---
name: flakiness-triage
description: Determines if a test failure is transient or a genuine code regression. Use this skill to analyze failure signatures, differentiate between ground truth errors and wrapper symptoms, and classify the failure type.
---

# Flakiness Triage

## Overview

This skill determines whether a test failure is a transient infrastructure "flake" or a genuine code regression. Differentiating these is critical for routing the issue correctly and preventing wasted debugging effort on infrastructure glitches.

## Triage Process

When investigating a test failure, follow these steps to classify the issue:

### 1. Identify Ground Truth vs. Wrapper Symptoms
Wrapper scripts and CI pipelines frequently crash during cleanup operations *after* the core workload has already failed, creating spurious "masking" errors.
*   **Do not rely on the final exit code.** An `exit status 255` in the build log during teardown is often a secondary symptom.
*   **Check the Test Results:** Always inspect the `junit.xml` (or the filtered `test-results.txt`). If the `junit.xml` reports failures, the core workload failed, and any subsequent infrastructure errors (e.g., GCE lock contention) should be treated as secondary.
*   **Check the Metrics:** If the test results indicate success but the job failed, check `filtered-metrics.json` for SLO breaches. A performance regression might cause the test to abort early, leading to spurious infrastructure errors later.

### 2. Analyze Infrastructure Context
If the core workload passed (or never ran) and the failure is entirely within the infrastructure setup/teardown:
*   Examine `build-tail.txt` for provisioning or teardown logs.
*   Look for transient errors like `resourceInUseByAnotherResource` or `googleapi: Error 400` during cluster deletion. These are usually infrastructure flakes or secondary symptoms of earlier failures.

### 3. Historical Comparison
*   Compare the current failure signature against recent test runs. 
*   Does this exact failure occur sporadically (suggesting a flake) or has it consistently failed since a specific build (suggesting a hard break/regression)?

### 4. Classification
Based on the evidence, explicitly classify the failure into one of these categories:
*   **`FLAKE`**: A transient failure not related to code changes (e.g., random network timeout, sporadic API server lag that recovers).
*   **`INFRA_ISSUE`**: A failure in the CI/CD pipeline or cloud provider (e.g., unable to provision machines, GCE API limits exceeded).
*   **`CODE_REGRESSION`**: A genuine failure in the core codebase, such as a new panic, a consistent SLO breach, or a reproducible logic error. 

## Actionable Next Steps
*   If classified as a **`CODE_REGRESSION`**, proceed to precise culprit pinpointing.
*   If classified as a **`FLAKE`** or **`INFRA_ISSUE`**, document the signature and gather relevant infrastructure logs, but do not initiate a deep codebase search for culprits.
