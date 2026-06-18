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
Before running the visualization script, you must curate the extracted TSDB metrics, `.pprof` data, and baseline deltas into a run-specific `metrics.json` file located in the specific triage journal directory (e.g., `triage-journals/[BUILD_ID]/metrics.json`). DO NOT use a global or mock data file.
*   **Format:** The JSON must match the exact schema defined in `plans/visualization-plan.md`. 
*   **Time-Alignment:** Ensure all metrics are zero-indexed relative to the failure event (`T=0`).

## 2. Execute the Dashboard Script
Invoke the `scripts/generate_dashboard.py` script.
*   **DO** pass the run-specific JSON payload file as the first argument.
*   **DO** pass the desired output directory (e.g., `triage-journals/[BUILD_ID]/visualizations`) as the second argument.
*   *Example Command:* `.venv/bin/python3 scripts/generate_dashboard.py triage-journals/12345/metrics.json triage-journals/12345/visualizations`

## 3. Embed in the Newspaper Layout
Once the script successfully generates the 5 `.png` dimensions, you must embed them directly into the final `journal.md` report.
*   **DO NOT** dump all the images at the end of the report.
*   **DO Elevate Core Evidence:** Identify the 1-2 most informative graphs that definitively prove the root cause (e.g., the Concurrency Surge and CPU Saturation graphs for an overload failure). Embed these directly into the **Executive Summary** at the very top of the file so they are visible immediately "above the fold."
*   **DO** intersperse the remaining graphs. Place them immediately after discussing the relevant metric or hypothesis in the deep-dive sections. Use cross-references if a graph was already shown in the Executive Summary.
*   **DO** use standard Markdown image tags: `![Dimension 1: Concurrency Surge](./visualizations/dim1_concurrency.png)`.
