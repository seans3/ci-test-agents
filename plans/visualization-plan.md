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

## 3. Required Visualizations (The Newspaper Layout)

To ensure the failure is immediately understandable to Kubernetes engineers who may lack deep expertise in specific subsystems (e.g., APF, scale testing), while still providing the rigorous telemetry required by domain experts, the visual dashboard is structured in a "Newspaper Layout". It begins with cross-subsystem context mapping and progressively discloses deep, expert-level telemetry.

**Dynamic Layout Prioritization:** The agent MUST dynamically alter the vertical order of the visualizations based on the primary failure mode it identifies. Do not force an engineer to scroll past 5 API Server charts if the cluster died due to a network partition. 
*   *If `INFRA_FLAKE` / Network Partition:* Elevate the Node Readiness Heatmap (4.2) to the top of Tier 1.
*   *If Component Crash:* Elevate the Event Scatter-Plot (4.1) showing the panic/OOMkill to the top.
*   *If Control-Plane Overload:* Use the default layout, leading with Concurrency and CPU Saturation.

### Tier 1: Cross-Subsystem Context
**Target Audience:** General Kubernetes engineers, contributors outside the failing subsystem.
**Goal:** Answer "What broke and what is the blast radius?" in 30 seconds by visually bridging subsystem silos.

#### 3.1. The Environment Constraints (Control Plane Characteristics)
*   **Format:** A stylized Markdown Table or Infobox.
*   **Content:** Explicitly details the physical hardware limits of the single, monolithic control plane node hosting the test. It includes `Machine Type` (e.g., n2-standard-64), `Total CPU Cores`, `Total Memory (GB)`, and `Disk Type` (e.g., Local NVMe). 
*   **Goal:** Before an engineer looks at a graph showing "60 cores utilized", they must know the physical ceiling. This grounds the saturation metrics in physical reality.

#### 3.2. The Narrative Timeline
*   **Format:** A chronological Markdown timeline with timestamps.
*   **Content:** Translates the event into a subsystem narrative (e.g., "T-1m: Control-plane drops `WATCH` connections. T=0: Controllers reconnect and issue unpaginated `LIST pods` (ResourceVersion=''). T+1m: API Server CPU saturates converting objects to JSON. APF queues fill. Latency breaches SLO.").

#### 3.3. The "Blast Radius" Topology
*   **Format:** 3-Box System Diagram (e.g., Mermaid.js graph).
*   **Content:** `[Controllers]` ➡️ `[kube-apiserver]` ➡️ `[etcd]`. 
*   **Indicator:** Color-coded states and arrows. `[Controllers]` emits a massive red arrow labeled `LIST pods` indicating a traffic surge. `[kube-apiserver]` flashes red indicating CPU lockup. `[etcd]` remains green, communicating that the storage layer is healthy.

#### 3.4. Demystifying APF (Queuing Diagram)
*   **Format:** Sankey Diagram.
*   **Content:** Visually maps API Priority and Fairness (APF) flow. Shows total `apiserver_request_total` entering specific `FlowSchemas`/`PriorityLevels` (e.g., `workload-high`, `catch-all`). Shows the split between `Executing`, `Queued`, and `Rejected(Concurrency-Limit)`, explaining exactly where requests were dropped.

---

### Tier 2: Deep-Dive Telemetry
**Target Audience:** Core Kubernetes maintainers, SIG-Scalability engineers.
**Goal:** Provide the exact `.pprof`, Prometheus, and `etcd` metric traces required to write the code fix.

**Layout Rule (Multi-Panel Grid):** Do NOT overlay all dimensions onto a single, unreadable "spaghetti graph." The following time-series dimensions (3.5, 3.6, 3.8, 3.9) MUST be rendered as multiple distinct charts arranged in a vertical stack (a Trellis layout) sharing a synchronized X-axis. This allows an engineer to scroll down and visually correlate a spike in concurrency with a spike in CPU lock contention at the exact same vertical slice in time.

#### 3.5. Dimension 1: Concurrency Surge (The Ghost Overlay)
**Goal:** Visually correlate the traffic anomaly against a known-good run.
*   **Format:** Dual-Axis Line Chart.
*   **X-Axis:** Relative Time (`T-5m` to `T+5m`).
*   **Y-Axis 1:** Inflight Requests (`concurrency_inflight`). Plot `failed_run` (Solid Red) over `baseline_run` (Dashed Gray "Ghost" line).
*   **Y-Axis 2:** APF Queued Requests (`apf_queued`).

#### 3.6. Dimension 2: CPU Saturation vs. GC Breakdown
**Goal:** Track overall CPU saturation and identify if Garbage Collection was spiking.
*   **Format:** Stacked Area Chart.
*   **X-Axis:** Relative Time (`T-5m` to `T+5m`).
*   **Y-Axis:** Total CPU Cores.
*   **Strata:** Plot `cpu_total_cores`. Overlay a distinct red stratum representing `cpu_gc_cores` to explicitly show the proportion of time spent managing memory.

#### 3.7. Dimension 3: The T=0 Bottleneck (Static Profiling)
**Goal:** Detail the exact Go function locking the CPU at the moment of failure.
*   **Format:** Pie Chart (or embedded Flame Graph).
*   **Data:** Rendered exclusively from `pprof_snapshot_t_zero`. 
*   *Rule:* Do not extrapolate this snapshot across the time-series. It represents the specific CPU breakdown at `T=0` (e.g., proving `runtime.selectgo` channel blocking vs. `runtime.gcAssistAlloc`).

#### 3.8. Dimension 4: Memory Exhaustion (Working Set vs. Limits)
**Goal:** Identify rapid memory leaks or allocations leading to OOM kills.
*   **Format:** Line Chart with Thresholds.
*   **X-Axis:** Relative Time (`T-5m` to `T+5m`).
*   **Y-Axis:** Memory Usage in GB (`memory_working_set_gb`).
*   **Overlay:** A dashed red horizontal line drawn at `hardware_limits.kube_apiserver_memory_limit_gb`.

#### 3.9. Dimension 5: Etcd Disk IOPS (P99 Latency)
**Goal:** Rule out or confirm the underlying storage layer as the root bottleneck using an easily readable threshold.
*   **Format:** Line Chart with Thresholds.
*   **X-Axis:** Relative Time (`T-5m` to `T+5m`).
*   **Y-Axis:** Fsync Latency (milliseconds).
*   **Data:** Plot `etcd_fsync_p99_ms` for both the failed run (Solid Red) and baseline run (Dashed Gray).
*   **Overlay:** A dashed horizontal line at the 50ms critical threshold. This visually proves if the disk ever crossed into dangerous territory.

## 4. Visualizing Alternative Failure Modes (Non-Overload Scenarios)
The aforementioned dimensions primarily target saturation and overload. However, 5k-node tests can fail for reasons unrelated to sheer volume. The visualization suite must dynamically adapt to present evidence for these alternative failure modes:

### 4.1. Component Crashes (Panics & OOMKills)
**Scenario:** A component hits a logic bug (Go panic) or memory leak and is killed. The system isn't broadly overloaded; it just crashed.
*   **Format:** Event Scatter-Plot Overlay.
*   **Data Source:** `kube_pod_container_status_restarts_total` and log panic signatures.
*   **Visualization:** Plot discrete events (e.g., container restarts) as highly visible markers (e.g., bright X's) directly on the Tier 1 Narrative Timeline. Embed the exact panic stack trace extracted from the logs as a pop-over or annotation on the event marker.

### 4.2. Infrastructure Flakes & Network Partitions
**Scenario:** The cloud provider drops network traffic, or a batch of nodes suddenly goes `NotReady`. The API server is healthy, but the nodes are unreachable.
*   **Format:** Node Readiness Heatmap.
*   **X-Axis:** Relative Time.
*   **Y-Axis:** Node Batches (e.g., grouped by zone or instance group).
*   **Color Intensity:** Green (Ready) to Red (NotReady/Unknown). 
*   **Goal:** Instantly prove the failure was a localized network/provider partition (e.g., an entire zone goes red simultaneously), exonerating the control-plane software.

### 4.3. Controller Deadlocks & Logic Bugs
**Scenario:** CPU is low, API latency is fast, but the test times out because pods are stuck in `Pending`. A specific controller's sync loop is deadlocked or severely delayed.
*   **Format:** Workqueue Depth & Latency Charts.
*   **Data Source:** `workqueue_depth` and `workqueue_queue_duration_seconds`.
*   **Visualization:** A line chart showing the queue depth of the specific failing controller. 
*   **Goal:** Visually prove that the API was responsive, but a specific internal queue (e.g., `replicaset_controller`) stalled indefinitely, isolating the logic bug.
