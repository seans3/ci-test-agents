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

## 2. Analyze the Metrics (Hypothesis Formation)
Do NOT blindly execute the plotting script yet. First, READ the `metrics.json` file you just generated.
*   **Formulate a Hypothesis:** What do the numbers actually say? Is memory flat? Is etcd latency spiking? Is concurrency anomalous? 
*   **Determine Relevant Dimensions:** Based on your hypothesis, decide which of the 5 visual dimensions are actually relevant to proving your conclusion. You do not need to feature a memory graph if the memory profile is perfectly flat and irrelevant to the failure.

## 3. Execute the Dashboard Script
Invoke the `scripts/generate_dashboard.py` script to generate the suite of visualizations.
*   **DO** pass the run-specific JSON payload file as the first argument.
*   **DO** pass the desired output directory (e.g., `triage-journals/[BUILD_ID]/visualizations`) as the second argument.
*   *Example Command:* `.venv/bin/python3 scripts/generate_dashboard.py triage-journals/12345/metrics.json triage-journals/12345/visualizations`

## 4. Embed in the Newspaper Layout
Once the script successfully generates the `.png` dimensions, you must selectively embed them directly into the final `journal.md` report.
*   **DO NOT** dump all the images at the end of the report.
*   **DO Elevate Core Evidence:** Identify the 1-2 most informative graphs that definitively prove your hypothesis (e.g., the Concurrency Surge and CPU Saturation graphs for an overload failure). Embed these directly into the **Executive Summary** at the very top of the file so they are visible immediately "above the fold."
*   **DO** intersperse the remaining relevant graphs. Place them immediately after discussing the corresponding metric in the deep-dive sections. Ignore graphs that do not contribute to the root cause proof.
