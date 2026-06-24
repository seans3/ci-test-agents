# Post-Mortem: GCE 5k-Node Scale Performance SLO Breaches (April - June 2026)

**Job:** `ci-kubernetes-e2e-gce-scale-performance-5000`
**Window:** 2026-04-15 to 2026-06-21

## Executive Summary
Between April and June 2026, the 5k-node scalability job intermittently failed the `APIResponsivenessPrometheusSimple` SLO for cluster-wide pod `LIST` requests. The p99 latency spiked to 35-58 seconds (well above the 30-s limit) on failing runs.

Initial triage incorrectly attributed this to CPU saturation and a "Thundering Herd" of `LIST` requests. However, deep runtime analysis revealed that the apiserver was actually severely underutilized (~80 of 96 cores idle). The true root cause was a **Go Scheduler Wakeup Storm** driven by massive endpointslice watch fan-out, which paralyzed the Go runtime's global scheduler lock.

## Root Cause: The Wakeup Storm
At the 5k-node scale, every endpointslice change wakes up ~5,300 clients (one `kube-proxy` per node + `coredns` pods). During a run, approximately 261,000 endpointslice changes trigger **680 million goroutine wakeups** (77% of all watch wakeups on the apiserver).

Because the Go runtime must wake parked OS threads and pair them with idle cores through a single global scheduler lock, the lock became the system bottleneck. Up to 2,200 goroutines would pile up in the run queue, waiting for a core, while actual CPU utilization remained below 20%.

### The Victim: `LIST pods`
The `LIST pods` request was not the cause of the load; it was merely the victim. A cluster-wide `LIST` takes about 10 seconds of actual work. However, because it gets pushed off the CPU hundreds of times while waiting in the massive scheduler queue, that 10 seconds of real work stretches to 40-50+ seconds, breaching the SLO.

## The Feedback Loop
While all runs experience the scheduler storm, pass/fail is determined by how long the run stays in the slow state. 
When the apiserver slows down:
1. The Controller Manager creates pods much slower (48-73/s vs 94-164/s).
2. The `clusterloader2` framework waits much longer for all deployments to come up before beginning teardown.
3. The teardown phase (which would delete the objects and clear the watch traffic) is delayed by ~30 minutes.
4. Because the slow state drags out, the controller writes smaller endpoint batches, manufacturing even more watch traffic.

Failing runs are simply those trapped in this self-sustaining positive feedback loop for an extended period.

## Aggravating Factor: `CL2_REALISTIC_POD`
The failures were exacerbated by the introduction of `CL2_REALISTIC_POD` on April 27. While it did not increase pod payload size significantly, it added init containers and sidecars. This caused pods to flip ready/not-ready more often, driving total endpointslice changes from ~64k to 90-125k per run, feeding more wakeups into the already strained Go scheduler.
