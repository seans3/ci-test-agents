# Kubernetes Scalability Triage Journal

**Build ID:** `2066566728590036992`
**Status:** `FAILURE`
**Completion Time:** Monday, June 15, 2026, at 08:26:25 PM UTC

## Executive Summary
The 5k-node scalability test failed due to an API Responsiveness SLO breach (p99 `LIST pods` latency hit 41.48s, limit 30s). While initial data strongly indicates a "Thundering Herd" of reconnecting clients issuing massive `LIST` requests, our root cause investigation reveals a classic "Observer Effect" triggered by a scaling cliff. Temporal `.pprof` analysis strongly indicates the API Server was heavily bottlenecked by the Go Runtime's internal block profiler (`runtime.saveblockevent` and `runtime.fpTracebackPartialExpand`). Crucially, verification of the cluster setup logs shows this profiling was active in *both* the passing baseline and the failed run. The failure likely occurred because a 30% surge in traffic (The Thundering Herd) pushed the volume of blocked channels past a tipping point, causing the profiler's global mutex (`runtime.lock2`) to lock the CPU. Culprit pinpointing suggests the traffic surge was introduced by **PR #139720** and **PR #139719**, which refactored the API Server `WatchCache`. This appears to be a consistent regression; the subsequent build (`2067291549904932864`) also failed with the exact same signature.

**Classification:** Outcome B (Code Regression). Recommending review/revert of the `WatchCache` refactoring PRs that triggered the initial watch disconnects.

**Key Visual Evidence (The Thundering Herd & CPU Lockup):**
![Dimension 1: Concurrency Surge](./visualizations/dim1_concurrency.png)
![Dimension 2: API Server CPU Saturation](./visualizations/dim2_cpu.png)

## Environment Constraints (Control Plane Characteristics)
This specific 5k-node scalability benchmark does not use an HA control plane; it tests the absolute vertical scaling limits of a single, monolithic control-plane node. The physical hardware limits of this node dictate the absolute ceiling for the saturation metrics analyzed below.

| Characteristic | Specification |
| :--- | :--- |
| **Node Name** | `control-plane-us-east1-b-dj79` |
| **Machine Type** | `n2-standard-64` (Typical for 5k scale) |
| **Total CPU Cores** | 64 Cores |
| **Memory Limit** | 256 GB (API Server `cgroup` limit ~64 GB) |
| **Storage** | Local NVMe SSD (`etcd` WAL) |

---

## Triage Narrative & Findings

### 1. Initial Triage: Ground Truth vs. Symptoms
Initial triage began by filtering the raw logs. We explicitly checked `artifacts/junit.xml` to establish ground truth rather than relying on the `build-log.txt` exit code. 

The `junit.xml` confirmed two failures related to the `APIResponsivenessPrometheus` measurement. 
*   **Exact Signature:** `[got: &{Resource:pods Subresource: Verb:LIST Scope:cluster Latency:perc50: 983.769633ms, perc90: 21.020833333s, perc99: 41.487499999s Count:581 SlowCount:15}; expected perc99 <= 30s`
*   This strongly suggests a primary performance regression, allowing us to likely rule out spurious infrastructure teardown deadlocks.

### 2. Metric Anomaly: Call Volume & Baseline Delta
Reviewing the `artifacts/metrics/APIResponsivenessPrometheus_load_overall.json`, we noted that the volume of `LIST pods` requests at the cluster scope is `Count: 581`. 

**Baseline Comparison (Contextual Delta):**
To assess whether this volume is anomalous, we fetched the same metric from a known-good baseline run (Build ID: `2065841946538020864`).
*   **Baseline Run:** `Count: 444`, `SlowCount: 3`
*   **Failed Run:** `Count: 581`, `SlowCount: 15`

This represents a delta of **137 additional `LIST pods` requests** over the baseline. While it does not represent the entire 5,000-node cluster disconnecting, this ~30% abnormal surge in massive `LIST` requests strongly suggests a partial "Thundering Herd" phenomenon occurred, which was enough to contribute to a 5x increase in requests violating the SLO budget.

*(See **Dimension 1: Concurrency Surge** graph in the Executive Summary above).*

### 3. Digging Past the Mechanical Symptom (The Five Whys)
At a 5,000-node scale, a cluster-scoped `LIST pods` request is massive. However, we must determine *why* the API server failed to process them. 

Temporal `.pprof` analysis (`34.75.75.236_kube-apiserver_CPUProfile_load_2026-06-15T19:44:24Z.pprof`) captured during the latency spike reveals that 68% of the API Server's CPU was consumed by channel blocking (`runtime.selectgo`) and mutex locks (`runtime.lock2`). 

*(See **Dimension 2: API Server CPU Saturation** graph in the Executive Summary above).*

**Applying the "Five Whys": What was holding the lock, and why did the baseline pass?**
We initially suspected internal Kubernetes channel saturation (e.g., watch caches). However, inspecting the specific `-traces` of the CPU profile points to a highly probable culprit:
```text
    11.17s   runtime.fpTracebackPartialExpand
             runtime.saveblockevent
             runtime.blockevent
             runtime.selectgo
             golang.org/x/net/http2.(*serverConn).writeDataFromHandler
```
The CPU was not locked up executing Kubernetes business logic. It was locked up by the Go runtime's internal profiler (`runtime.saveblockevent`). The test environment's aggressive block-profiling configuration attempted to capture a stack trace for every single one of the thousands of blocked HTTP/2 streams during the traffic surge, paralyzing the global runtime mutex. 

To determine why the baseline run (Build `2065841946538020864`) passed successfully, we explicitly queried the `build-log.txt` for both runs. We verified that `--set spec.kubeAPIServer.enableContentionProfiling=true` was actively configured in **both** clusters. 

Therefore, the test configuration did *not* change. The baseline passed because its slightly lower traffic volume (`Count: 444`) remained just below the threshold required to trigger the profiler's catastrophic snowball effect. When the failed run experienced a 30% traffic surge (`Count: 581`), the volume of blocked channels finally overwhelmed the profiler's lock.

*Visual Evidence (The T=0 Bottleneck - Static CPU Profile):*
![Dimension 3: pprof CPU Profile Snapshot](./visualizations/dim3_pprof_pie.png)

*Visual Evidence (Memory Exhaustion):*
The memory working set spiked as the inflight requests piled up, but it remained well below the critical threshold limit.
![Dimension 4: Memory Exhaustion](./visualizations/dim4_memory.png)

### 4. Evaluating Competing Hypotheses
We investigated whether the sheer volume of data requested saturated the `etcd` disk IOPS, which would cause upstream blocking. However, analysis of `EtcdMetrics_load_2026-06-15T19:45:11Z.json` does not support this. Out of ~3.27 million `etcd_disk_wal_fsync_duration_seconds` operations, 100% completed in under 64ms. `etcd` appears to have been responding extremely fast.

*Visual Evidence (Etcd Disk IOPS / Storage Health):*
The P99 Latency line chart indicates that the vast majority of `etcd` disk syncs occurred in under 5ms, well below the 50ms critical threshold.
![Dimension 5: Etcd Disk IOPS (P99 Latency)](./visualizations/dim5_etcd_p99.png)

---

## Conclusion (Trinary Goal Outcome)

Following the Trinary Goal framework, this failure is classified as **Outcome B: Code Regression**. 

While the direct mechanical cause of the failure appears to be an "Observer Effect" (the profiler locked the CPU), we must consider *why* the traffic surged by 30% to trigger the profiler. 

By defining the strict suspect window between the LKG build (`99dad60c350`) and the failing build (`9d6e94a40d9`), we isolated the commits merged into `kubernetes/kubernetes`. Cross-referencing the failure signature (Watch Cache timeouts leading to a Thundering Herd) against this window revealed two highly suspect, back-to-back refactoring PRs:
*   **PR #139720:** `Encapsulate storage mutations and snapshots inside watchCacheStorage`
*   **PR #139719:** `Refactor watchCache to delegate history operations to watchCacheHistory`

These PRs fundamentally altered the locking and memory delegation semantics of the API Server's internal `WatchCache`. This change in the watch cache likely caused the initial stream disconnects, generating the 30% surge in `LIST pods` requests. The surge then likely triggered the fatal profiling lockup.

**Red-Team Corroboration (The Consistent Break):** To assess if this was a one-off anomaly, we verified the subsequent test run (Build `2067291549904932864`), which just completed. It failed with the exact same signature (p99 Latency: 43.6s, Count: 563). This strongly suggests the master branch is suffering a continuous regression.

**Next Steps:** Recommending an immediate revert or intensive review of PRs #139720 and #139719, followed by an automated Kubemark verification run to confirm the SLO returns to passing metrics.