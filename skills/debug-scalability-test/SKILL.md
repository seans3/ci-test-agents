---
name: debug-scalability-test
description: Coordinator skill for managing the scalability debugging process. Use this skill when investigating scalability test failures to fan out tasks to multiple sub-skills (like artifact retrieval, triage, and pinpointing) and merge their results.
---

# Debug Scalability Test

## Overview

This is a coordinator skill designed to orchestrate the end-to-end debugging process for scalability test failures. It acts as the "Master Orchestrator" or "Mapper," fanning out tasks to specialized sub-agents and combining their findings into a cohesive report.

## Workflow

1. **Information Gathering:** Use foundational skills (e.g., artifact retrieval) to fetch test data.
2. **Triage:** Delegate to triage skills to determine if the issue is a flake or regression.
3. **Pinpointing:** Delegate to pinpointing skills to find the culprit if a regression is identified.
4. **Verification:** Delegate to verification skills to test the suspected fix.
5. **Reporting:** Synthesize all findings into a final markdown journal or report.
