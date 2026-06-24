# Kubernetes Scalability Triage Journal

**Build ID:** `2068741058296025088`
**Date:** `2026-06-21 13:13:30 UTC`
**Status:** `FAILURE`

## Executive Summary
The 5k-node scalability test failed due to an API Responsiveness SLO breach (p99 `LIST pods` latency hit 36.16s, limit 30s). A highly probable root cause appears to be an architectural scale limit regarding how Kubernetes handles endpointslice watch fan-out, which severely impacted the Go scheduler. The data indicates the API Server was likely not CPU-bound; rather, the Go runtime's global scheduler lock was heavily contended by hundreds of millions of goroutine wakeups, leaving many cores idle while requests queued. While PR #36900 (`CL2_REALISTIC_POD`) significantly aggravated the issue, historical data strongly suggests the failures predate this PR, indicating the root cause is likely the emergent system limit combined with a positive feedback loop.

**Classification:** Emergent System Limit (Architectural Scale Limit) / Go Scheduler Starvation

## Empirical Evidence: Go Scheduler Starvation

To gather empirical evidence indicating whether this was Scheduler Starvation rather than CPU Saturation, we queried the TSDB for the absolute CPU utilization and the Go scheduler's run queue depth (`go_sched_goroutines_runnable`).

![Dimension: Go Scheduler Starvation](./visualizations/dim6_starvation.png)

*Visual Evidence:* The graph strongly indicates starvation. The red line shows the Go scheduler run queue increasing to ~2,200 waiting goroutines. Crucially, the blue line indicates the CPU was severely underutilized (only 14-16 active cores out of 96). It is highly probable that the goroutines were waiting in the queue for the runtime's global scheduler lock to pair them with idle cores. 

## Triage Narrative & Mechanical Breakdown

### 1. The Victim: `LIST pods` SLO Breach
The `junit.xml` indicated the failure was a `LIST pods` SLO breach (p99 of 36.16s). A cluster-wide `LIST` returns ~150-230MB and generally requires ~10s of real CPU work. However, because the Go scheduler appeared heavily contended, this request was likely pushed off the CPU hundreds to thousands of times while waiting in the run queue (queue wait `go_sched_latencies_seconds` hit 1060µs on average with tens of ms tail latency). Thus, ~10s of real work appears to have stretched to 36+ seconds.

### 2. The Driver: Endpointslice Fan-out
The massive scheduler queue appears to be driven by overhead: waking parked goroutines for watch events. Every single endpointslice change wakes up 5,317 clients (one `kube-proxy` on every node + CoreDNS pods). Over this run, ~261,000 endpointslice changes translated into ~680 million goroutine wakeups, accounting for 77% of all watch wakeups on the apiserver. 

### 3. The Aggravating Factor: PR #36900 (`CL2_REALISTIC_POD`)
By evaluating historical runs, we discovered that while this architectural bottleneck likely existed previously (with failures predating April 17), it was massively exacerbated by PR #36900 (`CL2_REALISTIC_POD`). While this PR did not increase the overall payload size of pods (~6.5KB before and after), it fundamentally changed their lifecycle by adding 2 init containers and a sidecar. 
*   This likely caused pods to take longer to go ready and flip between ready/not-ready states more frequently.
*   This directly drove up the raw volume of endpointslice changes from a baseline of ~64K to 90-125K per run. 
*   These extra endpointslice changes fed directly into the 5,317x fan-out, generating the 680M wakeups that heavily contended the Go scheduler lock.

### 4. The Vicious Feedback Loop
It appears that every run experiences this slowdown, but failing runs get stuck in a self-sustaining loop. The slow apiserver causes the Controller Manager to create pods slower. This delays the `clusterloader2` teardown phase (the phase that deletes objects and clears watch traffic) by ~30 minutes. Because the watches stay active longer, the slow state sustains itself, heavily contributing to the run failing the SLO. This also likely caused the spurious teardown failure at the end of the run (`googleapi: Error 400`).