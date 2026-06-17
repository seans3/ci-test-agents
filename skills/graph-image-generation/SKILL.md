---
name: graph-image-generation
description: Transforms raw test data into visual graphs or infographics. Use this skill to generate visual representations of performance trends and anomalies for human consumption.
---

# Graph/Image Generation

## Overview

This skill provides mechanisms to transform raw test data, metrics, and logs into visual graphs or infographics, helping developers quickly comprehend performance trends, latency spikes, and anomalies.

## Usage

1. **Input Data:** Ingest JSON metrics, CSVs, or parsed log data.
2. **Select Plot Type:** Determine the appropriate graph type (e.g., line chart for latency over time, bar chart for resource usage).
3. **Generate Visual:** Invoke rendering tools or libraries (like Python's matplotlib/seaborn or plotting CLI utilities) to output an image or interactive graph.
4. **Export:** Save the output into the project's artifact directory.
