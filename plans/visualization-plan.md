# Plan: 5k-Node Performance Test Visualizations

## 1. Overview
This document outlines the architecture, data curation strategy, and visualization formats required to mechanically diagnose and visually represent failures in 5k-node Kubernetes scalability tests. The goal is to move beyond textual metrics to a multi-dimensional, visually intuitive dashboard that correlates concurrency, hardware saturation, and latency.

## 2. Data Curation & Normalization Pipeline
Before any visualizations can be rendered, raw data from ClusterLoader2 artifacts must be extracted, time-aligned, and normalized into a standard JSON payload format.

### 2.1. Target Data Sources & Ephemeral Querying
*   **Prometheus TSDB:** `artifacts/prometheus_snapshot.tar`
    *   *Note:* Agents cannot read TSDB tarballs directly. The pipeline MUST launch an ephemeral local Prometheus instance, mount the extracted snapshot, and query it via the HTTP API.
*   **Temporal CPU Profiles:** `artifacts/*kube-apiserver_CPUProfile_load*.pprof`

### 2.2. The Normalized Data Format (JSON Matrix)
The data extraction scripts will output a unified JSON matrix. To render comparative "Ghost" overlays, the schema includes both the failed run and the baseline run.

```json
{
  "metadata": {
    "failed_build_id": "2066566728590036992",
    "baseline_build_id": "2065841946538020864",
    "failure_timestamp_utc": "2026-06-15T19:45:10Z"
  },
  "hardware_limits": {
    "kube_apiserver_memory_limit_gb": 64.0
  },
  "time_series_data": [
    {
      "relative_time_seconds": -300,
      "failed_run": {
        "concurrency_inflight": 3450,
        "cpu_total_cores": 58.2,
        "cpu_gc_cores": 14.1,
        "memory_working_set_gb": 42.5,
        "etcd_fsync_buckets": {"0.005": 1200, "0.01": 50, "0.05": 10, "+Inf": 0}
      },
      "baseline_run": {
        "concurrency_inflight": 400,
        "cpu_total_cores": 12.0
      }
    }
  ],
  "pprof_snapshot_t_zero": {
    "runtime.selectgo_cpu_percent": 52.49,
    "runtime.lock2_cpu_percent": 15.89,
    "garbage_collection_cpu_percent": 2.1
  }
}
```

## 3. Required Visualizations

Based on the curated JSON matrix, the following visualizations will be generated via Python scripts (using `matplotlib`/`seaborn`) outputting `.png` files.

### 3.1. Dimension 1: Concurrency Surge (The Ghost Overlay)
**Goal:** Visually prove the traffic anomaly against a known-good run.
*   **Format:** Dual-Line Chart.
*   **X-Axis:** Relative Time (`T-5m` to `T+5m`).
*   **Y-Axis:** Inflight Requests.
*   **Data:** Plot `failed_run.concurrency_inflight` (Solid Red Line) overlaid directly on top of `baseline_run.concurrency_inflight` (Dashed Gray Line).

### 3.2. Dimension 2: CPU Saturation vs. GC (Time-Series)
**Goal:** Track overall CPU saturation and identify if Garbage Collection was spiking over time.
*   **Format:** Stacked Area Chart.
*   **X-Axis:** Relative Time (`T-5m` to `T+5m`).
*   **Y-Axis:** Total CPU Cores.
*   **Strata:** Plot `cpu_total_cores`. Overlay a distinct red stratum representing `cpu_gc_cores` to show the proportion of time spent managing memory.

### 3.3. Dimension 3: The T=0 Bottleneck (Static Profiling)
**Goal:** Detail the exact function locking the CPU at the moment of failure.
*   **Format:** Pie Chart (or embedded Flame Graph).
*   **Data:** Rendered exclusively from `pprof_snapshot_t_zero`. 
*   *Rule:* Do not extrapolate this snapshot across the time-series. It represents the specific CPU breakdown at `T=0`.

### 3.4. Dimension 4: Memory Exhaustion (Working Set vs. Limits)
**Goal:** Identify rapid memory leaks or allocations leading to OOM kills.
*   **Format:** Line Chart with Thresholds.
*   **X-Axis:** Relative Time (`T-5m` to `T+5m`).
*   **Y-Axis:** Memory Usage in GB (`memory_working_set_gb`).
*   **Overlay:** A dashed red horizontal line drawn at `hardware_limits.kube_apiserver_memory_limit_gb`.

### 3.5. Dimension 5: Etcd Disk IOPS Heatmap
**Goal:** Rule out or confirm the underlying storage layer as the root bottleneck.
*   **Format:** Distribution Heatmap.
*   **X-Axis:** Relative Time (`T-5m` to `T+5m`).
*   **Y-Axis:** Fsync duration buckets (e.g., 5ms, 10ms, 50ms+).
*   **Color Intensity:** Derived from the counts in `etcd_fsync_buckets`.
*   **Overlay:** A dashed horizontal line at the 50ms critical threshold.
