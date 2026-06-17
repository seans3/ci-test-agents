---
name: graph-image-generation
description: Transforms raw test data into visual graphs or infographics. Use this skill to generate visual representations of performance trends, latency spikes, and anomalies (using Mermaid.js or python) to support claims in the final triage journal.
---

# Graph/Image Generation

## Overview

Textual claims about performance bottlenecks are stronger when backed by visual evidence. This skill dictates how agents should transform raw telemetry (like Prometheus TSDB data or JSON metrics) into embedded graphs within the final `journal.md`.

Because the agent operates in a markdown-centric environment, **Mermaid.js is the preferred medium** for visualization, though Python scripting can be used for complex external artifacts.

## Generation Guidelines

### 1. Data Selection
Select the right data source before visualizing:
*   **Time-Series Correlation:** If you need to show how a metric spiked over time (e.g., CPU vs. Request Volume), you MUST extract data from `artifacts/prometheus_snapshot.tar`.
*   **Distribution/Percentiles:** If you need to show latency distribution (P50 vs P99), use the structured JSON files in `artifacts/metrics/`.

### 2. Preferred Medium: Mermaid.js
Whenever possible, embed graphs directly into the markdown report using Mermaid.js syntax. This ensures the graphs are highly portable and render natively in most markdown viewers.

**Supported Chart Types:**
*   **Pie Charts (`pie`):** Best for showing the breakdown of CPU time (e.g., GC vs. Serialization vs. Network IO) extracted from a `.pprof` file.
*   **XY Charts (`xychart-beta`):** Best for showing simple time-series latency spikes or request volume over time.
*   **Sequence Diagrams (`sequenceDiagram`):** Best for visualizing the timeline of a complex infrastructure teardown deadlock or request flow.

*Rule:* Every Mermaid graph MUST be immediately preceded or followed by an explicit textual explanation of *what* the graph shows and *why* those specific numbers constitute proof of the hypothesis.

### 3. Alternative Medium: Python (matplotlib/seaborn)
If the data is too massive or complex for a simple Mermaid chart (e.g., a scatter plot of 10,000 requests), write and execute a Python script to generate a `.png` file.
*   The script should read the local `/tmp/k8s-triage/` filtered data.
*   The script must save the output image into the `./triage-journals/[BUILD_ID]/` directory.
*   The final `journal.md` must link to the generated image using standard markdown syntax: `![Description of Graph](./graph.png)`.

## Execution

1.  Identify the claim that needs visual proof (e.g., "The API server spent 17% of CPU in garbage collection").
2.  Extract the absolute numbers from the metric artifacts.
3.  Draft the Mermaid syntax or Python script.
4.  If using Mermaid, insert the block directly into the `journal.md` draft.
5.  If using Python, execute the script and verify the image exists before linking it in the draft.
