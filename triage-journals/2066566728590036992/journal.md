# Kubernetes Scalability Triage Journal

**Build ID:** `2066566728590036992`
**Status:** `FAILURE`
**Completion Time:** Monday, June 15, 2026, at 08:26:25 PM UTC

## Executive Summary
The 5k-node scalability test failed due to an API Responsiveness SLO breach (p99 `LIST pods` latency hit 41.48s, limit 30s). Data strongly indicates this is associated with a "Thundering Herd" of reconnecting clients issuing unpaginated `LIST` requests. The metrics suggest `etcd` IOPS saturation is unlikely to be the primary cause. Furthermore, temporal `.pprof` analysis indicates the API Server was heavily bottlenecked by channel blocking (`runtime.selectgo`) and lock contention on internal `WATCH` event caches, rather than GC churn. This channel saturation likely contributed to watches dropping, thereby triggering the Thundering Herd.

## Triage Narrative & Findings

### 1. Initial Triage: Ground Truth vs. Symptoms
Initial triage began by filtering the raw logs. We explicitly checked `artifacts/junit.xml` to establish ground truth rather than relying on the `build-log.txt` exit code. 

The `junit.xml` confirmed two failures related to the `APIResponsivenessPrometheus` measurement. 
*   **Exact Signature:** `[got: &{Resource:pods Subresource: Verb:LIST Scope:cluster Latency:perc50: 983.769633ms, perc90: 21.020833333s, perc99: 41.487499999s Count:581 SlowCount:15}; expected perc99 <= 30s`
*   This confirms a primary performance regression, allowing us to rule out spurious infrastructure teardown deadlocks.

### 2. Metric Anomaly: Call Volume & Baseline Delta
Reviewing the `artifacts/metrics/APIResponsivenessPrometheus_load_overall.json`, we noted that the volume of `LIST pods` requests at the cluster scope is `Count: 581`. 

Under normal operation, controllers rely on long-lived `WATCH` connections. A high `LIST` count is the classic signature of a "Thundering Herd"—when watches timeout and drop, controllers reconnect simultaneously and request full state syncs via unpaginated `LIST` calls. 

**Baseline Comparison (Contextual Delta):**
To assess whether this volume is anomalous, we fetched the same metric from a known-good baseline run (Build ID: `2065841946538020864`).
*   **Baseline Run:** `Count: 444`, `SlowCount: 3`
*   **Failed Run:** `Count: 581`, `SlowCount: 15`

This demonstrates a ~30% abnormal surge in massive `LIST pods` requests, strongly suggesting a Thundering Herd phenomenon occurred, contributing to a 5x increase in requests violating the SLO budget.

### 3. Latency vs. Error Budget
The test suite operates on an error budget. An absolute latency value of 41.48s does not automatically fail the test if the total number of slow requests is small (as seen in the baseline's `SlowCount: 3`). 

However, in this run, the `SlowCount` for `LIST pods` reached 15, and for `PATCH deployments` it reached 189. This high volume of slow requests exhausted the allowable error budget. 

### 4. Competing Hypotheses for the Bottleneck
At a 5,000-node scale, a cluster-scoped `LIST pods` request is massive. There are several competing hypotheses for what caused the latency to spike to 41 seconds:

*   **Hypothesis A (Strong Indicator: Lock Contention / Channel Blocking):** We initially hypothesized that massive JSON serialization triggered Garbage Collection (GC) churn. However, temporal `.pprof` analysis (`34.75.75.236_kube-apiserver_CPUProfile_load_2026-06-15T19:44:24Z.pprof`) captured during the latency spike makes the GC churn theory less likely. The profile shows 52.49% of all CPU time was spent in `runtime.selectgo` (200.9s cumulative), accompanied by massive lock contention (`runtime.lock2` at 15.89%). This strongly points to channel saturation as a significant bottleneck. The internal `WATCH` event buffers filled up, causing goroutines attempting to enqueue events (`convertToWatchEvent`) to block on mutexes. This channel blocking likely contributed to client watches timing out and dropping, triggering the Thundering Herd.
*   **Hypothesis B (UNLIKELY): Etcd Saturation.** We hypothesized that the sheer volume of data requested saturated the `etcd` disk IOPS. However, analysis of `EtcdMetrics_load_2026-06-15T19:45:11Z.json` does not support this. Out of ~3.27 million `etcd_disk_wal_fsync_duration_seconds` operations, 3,268,070 completed in under 4ms, and 100% completed in under 64ms. `etcd` was responding extremely fast, suggesting the bottleneck occurred upstream in the API Server.

## Conclusion

The 5k-node performance regression is clearly evident in the metrics. Internal API Server `WATCH` channels became saturated, leading to severe lock contention (`runtime.selectgo` / `runtime.lock2`). This caused watch connections to drop, forcing clients to reconnect and issue massive, unpaginated `LIST pods` requests (a Thundering Herd). This 30% surge in `LIST` volume overwhelmed the API Server, resulting in 41-second P99 latencies that exhausted the SLO error budget.