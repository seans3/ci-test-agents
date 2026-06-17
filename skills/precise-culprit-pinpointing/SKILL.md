---
name: precise-culprit-pinpointing
description: Identifies specific code or configuration changes causing regressions. Use this skill to analyze failure signatures, historical data, and commit change windows to find the root cause of a regression.
---

# Precise Culprit Pinpointing

## Overview

This skill analyzes failure signatures, historical data, and change windows to identify the exact code or configuration changes that introduced a regression.

## Analysis Steps

1. **Define the Window:** Identify the last known good build and the first known bad build.
2. **Retrieve Changes:** Fetch all commits and configuration changes that occurred within that window.
3. **Correlate Signatures:** Match the technical nature of the failure (e.g., an API Server panic) with the files touched in the change window.
4. **Rank Suspects:** Produce a ranked list of likely culprits based on relevance and impact.
