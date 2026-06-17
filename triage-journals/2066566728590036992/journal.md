# Kubernetes Scalability Triage Journal

**Build ID:** `2066566728590036992`
**Status:** `FAILURE`
**Completion Time:** Monday, June 15, 2026, at 08:26:25 PM UTC

## Executive Summary
The 5k-node scalability test failed due to an API Responsiveness SLO breach (p99 `LIST pods` latency hit 41.48s, limit 30s). Data suggests this is caused by a "Thundering Herd" of reconnecting clients issuing unpaginated `LIST` requests, though further `pprof` and baseline metric collection is required to definitively prove the root cause over competing variables like `etcd` IOPS saturation.

## Triage Narrative & Findings

### 1. Initial Triage: Ground Truth vs. Symptoms
Initial triage began by filtering the raw logs. We explicitly checked `artifacts/junit.xml` to establish ground truth rather than relying on the `build-log.txt` exit code. 

The `junit.xml` confirmed two failures related to the `APIResponsivenessPrometheus` measurement. 
*   **Exact Signature:** `[got: &{Resource:pods Subresource: Verb:LIST Scope:cluster Latency:perc50: 983.769633ms, perc90: 21.020833333s, perc99: 41.487499999s Count:581 SlowCount:15}; expected perc99 <= 30s`
*   This confirms a primary performance regression, allowing us to rule out spurious infrastructure teardown deadlocks.

### 2. Metric Anomaly: Call Volume
Reviewing the `artifacts/metrics/APIResponsivenessPrometheus_load_overall.json`, we noted that the volume of `LIST pods` requests at the cluster scope is `Count: 581`. 

Under normal operation, controllers rely on long-lived `WATCH` connections. A high `LIST` count is the classic signature of a "Thundering Herd"—when watches timeout and drop, controllers reconnect simultaneously and request full state syncs via unpaginated `LIST` calls. 

*Note for follow-up:* While 581 appears anomalous, we must pull a baseline run to establish the delta. Absolute numbers without a baseline are insufficient to prove a variance.

### 3. Latency vs. Error Budget
The test suite operates on an error budget. An absolute latency value of 41.48s does not automatically fail the test if the total number of slow requests is small. 

However, in this run, the `SlowCount` for `LIST pods` reached 15, and for `PATCH deployments` it reached 189. This high volume of slow requests exhausted the allowable error budget. 

### 4. Competing Hypotheses for the Bottleneck
At a 5,000-node scale, a cluster-scoped `LIST pods` request is massive. There are several competing hypotheses for what caused the latency to spike to 41 seconds:

*   **Hypothesis A: API Server GC Churn.** The API server must serialize massive protobuf objects from `etcd` into JSON for the client. This extreme memory allocation triggers aggressive Garbage Collection (GC), pausing execution threads and blocking `WATCH` channels, leading to the Thundering Herd.
*   **Hypothesis B: Etcd Saturation.** The sheer volume of data requested saturates the `etcd` disk IOPS or network throughput, causing the initial timeouts before the data even reaches the API server.

## Required Proof (Next Steps for Engineering)

The red-team review correctly identified that we cannot definitively claim "GC churn" as the root cause without absolute proof, as we have not ruled out confounding variables like `etcd` saturation.

Before closing this investigation, the following artifacts **MUST** be fetched and analyzed to mathematically prove the bottleneck:

1.  **Baseline Deltas:** Fetch the `LIST pods` `Count` and `SlowCount` from a known-good baseline run to prove the current numbers are a mathematical anomaly.
2.  **Temporal `.pprof` Snapshots:** Do not rely on cumulative Prometheus metrics. We must fetch the 30-second `kube-apiserver.cpu.pprof` and `kube-apiserver.heap.pprof` artifacts windowed *exactly* over the 40-second latency spike to prove CPU starvation or GC churn.
3.  **Etcd Telemetry:** Query the `artifacts/prometheus_snapshot.tar` TSDB for `etcd_disk_wal_fsync_duration_seconds` to explicitly rule out `etcd` IOPS starvation as the confounding variable. 
