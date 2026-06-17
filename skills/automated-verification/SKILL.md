---
name: automated-verification
description: Triggers rollback testing in sandboxes to verify culprit removal fixes failures. Use this skill to automatically validate if reverting a suspected change resolves the test failure.
---

# Automated Verification

## Overview

This skill automatically triggers rollback testing in isolated sandboxes to verify if the removal or reversion of a suspected culprit actually resolves the test failure.

## Verification Workflow

1. **Identify Suspect:** Receive the suspected culprit PR or commit.
2. **Prepare Sandbox:** Provision an isolated environment or trigger a targeted CI job.
3. **Apply Reversion:** Revert the suspected change or apply a known fix.
4. **Execute Test:** Run the failing test suite against the modified codebase.
5. **Validate Outcome:** Compare the results against the baseline failure to confirm resolution.
