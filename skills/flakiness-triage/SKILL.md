---
name: flakiness-triage
description: Determines if a test failure is transient or a genuine code regression. Use this skill to analyze failure signatures and infrastructure logs to differentiate between flakes and real issues.
---

# Flakiness Triage

## Overview

This skill determines whether a test failure is a transient infrastructure "flake" or a genuine code regression. Differentiating these is critical for routing the issue correctly and preventing wasted debugging effort on infrastructure glitches.

## Triage Process

1. **Symptom vs. Root Cause:** Look beyond the final exit code. Check `junit.xml` or core workload statuses.
2. **Infrastructure Context:** Analyze provisioning and teardown logs to identify spurious errors (e.g., GCE lock contention).
3. **Historical Comparison:** Check if the failure signature has occurred sporadically in the past or if it represents a hard break.
4. **Classification:** Classify the failure as `FLAKE`, `INFRA_ISSUE`, or `CODE_REGRESSION`.
