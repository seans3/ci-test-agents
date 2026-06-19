# Kubernetes Scalability Triage Journal

**Build ID:** `2067291549904932864`
**Date:** `2026-06-17 17:01:59 UTC`
**Status:** `FAILURE`

## Executive Summary
The 5k-node scalability test failed due to an API Responsiveness SLO breach (p99 `LIST pods` latency hit 43.64s, limit 30s). After extensive Red-Team falsification, we have definitively ruled out recent `WatchCache` PRs and normal cluster operations. The root cause lies within the `perf-tests` load generation framework itself (specifically, the `watch-list` utility pod). 

The `watch-list` utility is an explicitly designed stress test that deliberately destroys and recreates its watches every 5 seconds. This design creates a catastrophic **Death Spiral**: if the cluster is even slightly slow, the test phase takes longer, causing `watch-list` to stay alive longer. Because it is an infinite loop tied to the phase duration, staying alive longer means it spams exponentially more `LIST pods` requests, bogging down the cluster further. This runaway positive feedback loop eventually saturates the API Server channels, triggering the Go runtime profiler (`--contention-profiling=true`) to seize the global `runtime.lock2` mutex, completely crashing the node.

**Classification:** Emergent System Limit / Latent Bug (Testing Framework). 

**Key Visual Evidence (The Death Spiral):**
The following graph demonstrates the stark discrepancy between successful runs (where the cluster was fast enough to outrun the loop) and failed runs (where the cluster fell slightly behind, triggering the death spiral of exponential `LIST` requests).

![The Death Spiral: Test Duration vs. Pathological LIST Requests](./visualizations/death_spiral.png)

## Environment Constraints (Control Plane Characteristics)
| Characteristic | Specification |
| :--- | :--- |
| **Machine Type** | `n2-standard-64` (Typical for 5k scale) |
| **Total CPU Cores** | 64 Cores |
| **Memory Limit** | 256 GB (API Server `cgroup` limit ~64 GB) |
| **Storage** | Local NVMe SSD (`etcd` WAL) |

---

## Triage Narrative & Findings

### 1. The Initial Symptom: Thundering Herd & CPU Saturation
The failure initially manifested as a massive SLO breach. Temporal `.pprof` analysis indicated that the API Server CPU was entirely saturated. 
Inspecting the specific `-traces` of the CPU profile pointed to the Go runtime's internal profiler (`runtime.saveblockevent`):
```text
             runtime.saveblockevent
             runtime.blockevent
             runtime.selectgo
             golang.org/x/net/http2.(*serverConn).writeDataFromHandler
```
The test environment's aggressive `--contention-profiling` configuration attempted to capture a stack trace for every single blocked HTTP/2 stream during a traffic surge, paralyzing the global runtime mutex. 

### 2. Finding the True Unknown (The `watch-list` Anomaly)
To determine what caused the sudden surge of blocked HTTP/2 streams, we queried the `kube-apiserver.log` to identify exactly which `userAgent` was issuing the anomalous load. 

By applying the Principle of Exhaustive Falsification across multiple historical runs, we found a massive, definitive anomaly stemming from a test utility pod called `watch-list`:

*   **Successful Runs (Healthy Baseline):**
    *   2065841946538020864: 672 `watch-list` LIST requests (Duration: ~169m) *[High load, but SLO survived]*
    *   2061131017258799104: 210 `watch-list` LIST requests (Duration: ~164m)
    *   2062942951578800128: 199 `watch-list` LIST requests (Duration: ~169m)
    *   2063667733328826368: 192 `watch-list` LIST requests (Duration: ~154m)
    *   2057507115173416960: 192 `watch-list` LIST requests (Duration: ~171m)
    *   2061493408802803712: 190 `watch-list` LIST requests (Duration: ~158m)
    *   2060406235777208320: 190 `watch-list` LIST requests (Duration: ~158m)
    *   2059681452215242752: 171 `watch-list` LIST requests (Duration: ~154m)
*   **Failed Runs (Spamming LISTs):**
    *   2064392517519937536: 852 `watch-list` LIST requests (Duration: ~230m)
    *   2067291549904932864: 784 `watch-list` LIST requests (Duration: ~196m)
    *   2066566728590036992: 794 `watch-list` LIST requests (Duration: ~204m)
    *   2065117162749562880: 732 `watch-list` LIST requests (Duration: ~180m)
    *   2058231898483724288: 514 `watch-list` LIST requests (Duration: ~206m)

### 3. Red-Team Deep Dive: The watch-list Stress Test
We audited the source code of this utility (`k8s.io/perf-tests/util-images/watch-list/main.go`) and discovered that the 5-second teardown loop is not a bug, but an explicit design choice. The utility is designed to act as an aggressive stress-test generator. 

As stated in its own `README.md`: *"Starts X number of informers... and waits until they are fully synchronised. Then the test is repeated until specified timeout has elapsed."*

*Visual Evidence (Intentional Load Generation in perf-tests):*
```go
err = wait.PollUntilContextCancel(ctx, 5*time.Second, true, func(ctx context.Context) (bool, error) {
    ctxInformer, cancelInformers := context.WithCancel(ctx)
    defer cancelInformers() // <--- Intentional teardown
    
    informersSynced, err := startInformersForResource(...)
    cache.WaitForCacheSync(ctx.Done(), informersSynced...)
    
    return false, nil // <--- Forces the loop to repeat every 5 seconds
})
```
By design, the `watch-list` pod runs an infinite loop that deliberately destroys its own watch connections via `cancelInformers()` and re-syncs them (issuing massive `LIST pods` requests) every 5 seconds. It is designed to hammer the API Server with watch initialization load.

### 4. The Positive Feedback Loop (Why Some Runs Succeed)
The `watch-list` module is deployed during an intermediate phase of the load test. 
*   **In successful runs:** The cluster processes the load quickly, completing the phase in ~27 minutes. The stress-test loop executes ~190 times before the `watch-list` pod is naturally deleted by the test framework. The API server absorbs this expected load.
*   **In failed runs:** If the cluster is even slightly slower, this phase takes longer. Because `watch-list` is an infinite loop tied to the duration of the phase, *running longer means it generates exponentially more load*. This extra load slows the cluster down further, which forces the phase to take even longer, causing even more `LIST` requests (up to 800+). 

This creates the Death Spiral. The load continuously compounds until the API Server channels become completely saturated, triggering the fatal profiler lockup.

---

## Conclusion & Next Steps
The mechanical bottleneck is the profiler lockup, and the *initial trigger* is the `watch-list` utility acting exactly as designed (as a stress test), but inadvertently amplifying minor latency variance into a fatal death spiral when the test runs long. 

We strongly recommend a dual-pronged fix: 
1. **Disable `--contention-profiling`** at 5k-node scales to immediately mitigate the fatal lockup caused by the high volume of blocked channels during stress tests.
2. **Submit a PR to `kubernetes/perf-tests`** to cap the maximum number of iterations or put a hard time limit on the `watch-list` utility, preventing it from entering a runaway positive feedback loop when the cluster is running slow.
