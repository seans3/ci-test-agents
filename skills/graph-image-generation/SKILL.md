---
name: graph-image-generation
description: Generates the Multi-Panel Trellis visualization dashboard for Kubernetes 5k-node triage journals using the project's Python script.
allowed-tools: Bash
---

# Goal
Transform a curated JSON matrix of Kubernetes metrics into a suite of highly accessible, synchronized `.png` visualizations, and embed them into the final triage report.

# Instructions

Because this repository uses the **Local-First Architecture**, the agent should NOT attempt to generate raw Mermaid.js charts or write its own plotting scripts. You MUST use the pre-built Python visualization tool provided in the repository.

## 1. Prepare the JSON Payload
Before running the visualization script, you must curate the extracted TSDB metrics, `.pprof` data, and baseline deltas into a `mock_data.json` file. 
*   **Format:** The JSON must match the exact schema defined in `plans/visualization-plan.md`. 
*   **Time-Alignment:** Ensure all metrics are zero-indexed relative to the failure event (`T=0`).

## 2. Execute the Dashboard Script
Invoke the `scripts/generate_dashboard.py` script.
*   **DO** pass the JSON payload file as the first argument.
*   **DO** pass the desired output directory (e.g., `triage-journals/[BUILD_ID]/visualizations`) as the second argument.
*   *Example Command:* `python3 scripts/generate_dashboard.py scripts/mock_data.json triage-journals/12345/visualizations`

## 3. Embed in the Newspaper Layout
Once the script successfully generates the 5 `.png` dimensions, you must embed them directly into the final `journal.md` report.
*   **DO NOT** dump all the images at the end of the report.
*   **DO** intersperse them. Place `dim1_concurrency.png` immediately after discussing the traffic anomaly. Place the CPU and Memory graphs immediately after discussing the lock contention or GC churn.
*   **DO** use standard Markdown image tags: `![Dimension 1: Concurrency Surge](./visualizations/dim1_concurrency.png)`.
