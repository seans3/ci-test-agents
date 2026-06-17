---
name: automated-verification
description: Triggers rollback testing in sandboxes to verify if a culprit removal fixes failures. Use this skill to automatically validate if reverting a suspected change resolves the test failure before finalizing the triage report.
---

# Automated Verification

## Overview

After a suspected culprit commit has been identified using the `precise-culprit-pinpointing` skill, the `automated-verification` skill is used to definitively prove the hypothesis. 

It does this by automatically triggering a rollback test (or a targeted CI job) in an isolated sandbox. If reverting the suspected change makes the test pass, the root cause is confirmed.

## Verification Workflow

### 1. Identify Suspect
*   Receive the suspected culprit PR or Git commit SHA.
*   Note the exact test suite or benchmark that is failing.

### 2. Prepare Sandbox
*   Provision an isolated environment or prepare a targeted CI job configuration.
*   Ensure the sandbox environment matches the failing environment as closely as possible (e.g., same Kubernetes version, same cloud provider settings).

### 3. Apply Reversion
*   Check out the codebase at the failing commit (First Known Bad).
*   Apply a `git revert <suspect_commit_sha>` to cleanly roll back the suspected change.
*   Alternatively, apply a known patch or fix if one is already proposed.

### 4. Execute Test
*   Run the specific failing test suite or benchmark against the modified codebase in the sandbox.
*   To save time and resources, execute *only* the tests that are known to fail, rather than the entire test suite.

### 5. Validate Outcome
*   **Resolution Confirmed:** If the test passes after the revert, the suspected commit is definitively the root cause.
*   **Resolution Failed:** If the test still fails, the hypothesis is incorrect. The agent must return to the `precise-culprit-pinpointing` phase to evaluate the next suspect.
*   **New Failure:** If the revert causes compilation errors or new, unrelated test failures, the revert may be fundamentally incompatible. The agent should document this and propose manual engineering review.

## Reporting
Once verification is complete, update the final triage journal with the results of the automated verification, explicitly stating whether the revert successfully resolved the failure.
