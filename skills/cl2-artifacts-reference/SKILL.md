---
name: cl2-artifacts-reference
description: Guide for navigating and understanding CI artifacts produced by ClusterLoader2 and the Kubernetes scale performance test suite. Use this when you need to locate logs, metrics, profiles, or understand the GCS bucket directory structure to debug test failures.
---

# ClusterLoader2 Artifacts Reference

## Overview

This skill provides a definitive reference for navigating the directory structure and understanding the specific CI artifacts produced by `ci-kubernetes-e2e-gce-scale-performance-5000` (ClusterLoader2). 

Because the test artifacts can exceed 55 GB per run, agents MUST understand this structure to surgically target, filter, and stream specific files without overwhelming the context window or system memory.

## Remote GCS Artifact Topology

The root artifact bucket is typically `gs://kubernetes-ci-logs/logs/ci-kubernetes-e2e-gce-scale-performance-5000/`.

Inside the root bucket, you will find:
*   `latest-build.txt`: Contains the single newest 64-bit Build ID. Used to find the directory for the latest run.

Inside a specific `[Build_ID_Directory]/`:

### 1. Root Level Metadata
*   `started.json`: Contains the Git commit SHA, node versions, and Unix initialization time.
*   `finished.json`: Contains the completion payload (`{"result": "SUCCESS"}` or `"FAILURE"`, `"passed": true/false`), metadata, and exit timestamp.
*   `clone-log.txt` & `clone-records.json`: Git synchronization telemetry showing which commits were checked out before the test started.
*   `build-log.txt`: The Prow execution stdout. Critical for infrastructure provisioning (`kubetest2`/`kops` up) and teardown logs (`kops` down). Often exits with `255` on infrastructure deadlocks.

### 2. Metrics Directory (`artifacts/metrics/`)
Contains structured JSON summaries emitted by ClusterLoader2.
*   `APIResponsivenessPrometheus_load_overall.json` (and other `APIResponsivenessPrometheus_*.json`): Key files for APF (API Priority & Fairness) and SLO tracking. Look here for 99th percentile latencies `> 1000ms`.
*   `PodStartupLatency_*.json`: Measures the time from pod creation to running state.
*   `ResourceUsageSummary_*.json`: Node-level CPU and memory consumption percentiles over the duration of the test.
*   `MetricsForE2E_*.json`: Contains raw Prometheus snapshots. **CRITICAL:** These are "instant vector snapshots" (single data points containing cumulative counters at the end of the test). They CANNOT be used to generate time-series graphs. Use them only to compare lifetime totals (e.g., `go_cpu_classes_gc_total_cpu_seconds_total` vs `process_cpu_seconds_total`).

### 3. Control Plane Artifacts (`artifacts/control-plane-*/`)
Contains control-plane engine runtime components and plain-text logs.
*   `kube-apiserver.log` (and `.log.1`, `.log.2` etc.): API Server logs. Look for `context deadline exceeded`, `HTTP 429` (Too Many Requests), `LIST.*pods`, or APF dropped requests.
*   `etcd.log`: Storage backend latency records. Look for `apply request took too long` or `sync duration` warnings which indicate disk IOPS starvation.
*   `kube-scheduler.log`: Pod placement timeline events. Look for `failed to schedule` or `backoff` events.
*   `*.pprof` (e.g., `kube-apiserver.cpu.pprof`, `etcd.heap.pprof`): Go profiling artifacts generated every 5 minutes during the test. Essential for proving CPU saturation or memory leaks.

### 4. Special Artifacts
*   `artifacts/junit.xml`: The official test results. Always check this first to differentiate between a core test failure and a spurious infrastructure teardown crash.
*   `artifacts/prometheus_snapshot.tar`: The full Prometheus time-series database (TSDB). Required if you need to generate a time-series graph showing the correlation of metrics over time.

## Local Filtered Data Convention

To prevent memory exhaustion, the Triage Orchestrator streams and filters the massive GCS files into a local temporary directory: `/tmp/k8s-triage/[BUILD_ID]/`. When debugging, agents should expect to find concentrated data here:

*   `build-tail.txt`: The last ~200 lines of `build-log.txt`.
*   `test-results.txt`: The extracted `<testsuite>` and `<failure>` blocks from `junit.xml`.
*   `filtered-api.txt`: Error and warning lines (e.g., `LEVEL=ERROR`, `context deadline exceeded`, `HTTP 429`, panics) filtered from `kube-apiserver.log`.
*   `filtered-metrics.json`: Extracted anomalies from the overall metrics files.

## Workflow Rules

1.  **Never Read Raw Logs Directly:** Never attempt to read `kube-apiserver.log` or `build-log.txt` entirely into memory. Rely on the local `/tmp/k8s-triage/` filtered files, or use zero-memory streams (`gcloud storage cat ... | grep ...`).
2.  **Establish Ground Truth:** Always consult `junit.xml` (or `test-results.txt`) to determine the *actual* outcome of the workload before assuming a `build-log.txt` teardown failure is the root cause.
3.  **Cross-Reference:** If you see an error in `filtered-api.txt`, correlate it with the metric summaries in `artifacts/metrics/` to prove systemic saturation.
