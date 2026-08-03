# kube-apiserver Memory Analysis (GKE Control Plane)

Working notes on memory-saving opportunities for the GKE control plane, based on heap
profile analysis. This is a living document — update as new profiles and findings land.

## Profile Under Analysis

| | |
|---|---|
| File | `control_profile.pb.gz` |
| Binary | `kube-apiserver` (Build ID `a335cc71e9950970181cf0a659e1aa793988a866`) |
| Captured | 2026-07-29 13:02 PDT |
| Default sample type | `inuse_space` |
| Total in-use heap | **253.7 MB** |
| Lifetime allocations (`alloc_space`) | **54.7 GB** |
| Cluster state | **Empty cluster**, ~30 minutes after startup |
| Cluster build | Built at **Kubernetes HEAD** from ~1 week before capture (late July 2026, v1.37 dev cycle) |
| Working Set Memory (avg) | ~615 MB |
| Resident Set Size (avg) | ~680 MB |

## In-Use Heap Breakdown (steady-state footprint)

### 1. Response serialization buffers — ~53 MB (21%)

The largest flat node in the profile is `runtime.(*Allocator).Allocate` (49.2 MB): protobuf
encode buffers for API responses.

Call chain: `WriteObjectNegotiated → SerializeObject → codec.EncodeWithAllocator →
protobuf.(*Serializer).doEncode → Allocator.Allocate`.

Attribution by handler (via `transformResponseObject` callers):

| Handler | In-use |
|---|---|
| `GetResource` | 40.5 MB |
| `UpdateResource` | 7.3 MB |
| `handleList` | 1.1 MB |

40 MB of in-flight serialized **GET** responses is unusually high — points at clients
repeatedly GETting large objects rather than using informers/watches.

### 2. etcd watch decode / watch cache — ~44 MB (17%)

`etcd3.(*watchChan).prepareObjs → runtime.Decode` holds 43.7 MB of decoded objects.
Breakdown by type (via `protobuf.unmarshalToObject` callees):

| Type | In-use | Share of decode |
|---|---|---|
| ConfigMap | 16.2 MB | 41% |
| DaemonSet | 6.0 MB | 15% |
| Pod | 5.0 MB | 13% |
| Node | 3.5 MB | 9% |
| CustomResourceDefinition | 2.5 MB | 6% |
| Deployment | 1.5 MB | 4% |
| Lease | 1.0 MB | 3% |
| Others (StatefulSet, RBAC, EndpointSlice, CSINode, CSR, ReplicaSet) | ~3 MB | 8% |

**ConfigMaps are the standout population** — largest decoded object type by a wide margin.

### 3. OpenAPI machinery — ~54 MB (21%)

Mostly one-time startup cost (visible under `runtime.main` / `app.Run`); scales with the
number of installed APIs and CRDs.

**v2 vs v3 split** (this matters for the lazy-load-v2 PR, see below):

| Component | Path | In-use |
|---|---|---|
| `routes.OpenAPI.InstallV2` subtree (v2 builder + `PruneDefaults`) | **v2** | **16.0 MB** |
| `builder3.BuildOpenAPISpecFromRoutes` | v3 | 21.5 MB |
| apiextensions v3 CRD controller (`openapiv3.Controller` → `BuildOpenAPIV3`) | v3 | 12.0 MB |
| `handler3` cached marshaled v3 specs (`encoding/json.Marshal` via `newOpenAPIV3Group`) | v3 | 11.5 MB |
| `schemamutation.WalkSchema` (via `builder3/util.WrapRefs`) | v3 | 9.0 MB |

Attribution gotcha: the `json.Marshal` (11.5 MB) and `schemamutation` (9 MB) nodes look
v2-ish but are both on the **v3** path. V3 is the bigger half of the OpenAPI bucket.

**Baseline API surface on an empty GKE cluster** (observed via `kubectl`):

- **29 system CRDs** ship with an empty cluster. This is what the CRD-proportional costs
  are paying for at baseline: the apiextensions v3 CRD controller output (12 MB), and
  plausibly much of the compiled-regexp (~8 MB, CRD validation patterns) and CEL
  environment (~8 MB) buckets. "Prune unused CRDs" as an operator lever only applies to
  user-added CRDs on top of these 29 — the baseline is GKE's own.
- **Only one aggregated APIService** beyond the built-ins: the metrics service
  (`metrics.k8s.io`). So the kube-aggregator layer (the `proxyHandler` in every request
  stack trace) is essentially pass-through overhead on an empty cluster, and aggregated
  OpenAPI merging is near its floor — the ~54 MB OpenAPI bucket is almost entirely
  built-in types + the 29 system CRDs.

### 4. Everything else

| Subsystem | In-use |
|---|---|
| Prometheus metrics (histograms, etc.) | ~17 MB (7%) |
| CEL environments (`cel-go`) | ~8 MB |
| Compiled regexps (likely CRD validation patterns) | ~8 MB |
| Webhook authorizer response cache | ~6.5 MB |
| HTTP/2 (hpack) + gRPC buffers, bufio pools | a few MB each |

## Allocation Churn (`alloc_space`, 54.7 GB lifetime)

Top contributors to GC pressure:

| Function | Allocated |
|---|---|
| `prometheus.(*histogram).Write` | 6.3 GB (metrics scraping) |
| `runtime.(*Unknown).Unmarshal` | 4.2 GB |
| `core/v1.(*ConfigMap).Unmarshal` | 3.8 GB |
| `protobuf consumeBytesNoZero` | 3.5 GB |
| `bytes.growSlice` | 3.4 GB |

ConfigMaps are the #1 concrete API type in churn as well as in live watch-cache memory.

## Heap vs. Working Set vs. RSS

Observed: ~250 MB pprof heap, ~615 MB Working Set, ~680 MB RSS. **These numbers are
consistent** — a 2–3× RSS-to-live-heap ratio is the textbook profile for a Go service.
Only a ratio that grows over time would be a red flag.

### Definitions

- **Working Set Memory** (GKE / cadvisor `container_memory_working_set_bytes`): total
  cgroup memory usage minus **inactive** file-backed page cache. Includes anonymous
  memory, kernel memory charged to the cgroup, and *active* page cache. This is the
  operationally important number: kubelet uses it for eviction decisions and it
  approximates what the OOM killer sees.
- **RSS**: depends on the source. The container metric (`container_memory_rss`) is
  anonymous memory only. Process-level RSS (`ps`, `/proc/<pid>/status` VmRSS) is all
  resident physical pages — anonymous *plus* file-backed, including the mapped binary.
  Since observed RSS (680 MB) > Working Set (615 MB), it is almost certainly
  process-level RSS: the kube-apiserver binary is ~150 MB on disk, and its resident text
  pages count toward process RSS but largely fall out of Working Set once inactive.

### Reconciling 250 MB live heap → ~680 MB RSS

pprof `inuse_space` counts only *live heap objects at the last GC*. On top of that:

| Component | Estimate | Notes |
|---|---|---|
| Live heap (pprof) | 250 MB | what the profile measures |
| GC headroom + lazy page return | +200–300 MB | `GOGC=100` lets heap grow to ~2× live before collecting; freed pages returned to OS lazily. **The biggest chunk.** |
| Heap fragmentation | ~10–15% of arena | partially-filled spans |
| Goroutine stacks | +20–60 MB | thousands of goroutines (one-plus per watch connection) |
| Runtime/GC metadata | +10–20 MB | GC bitmaps, span structures (~2–3% of arena) |
| Binary text/data pages | +50–150 MB | process RSS only; also explains RSS > Working Set |

Napkin total: 630–700 MB. Observed 680 MB lands in that band.

### Implications

1. **Every MB of live heap saved is worth ~2 MB of working set** because of the GOGC
   multiplier — the ~50 MB allocator-pool fix and ~16 MB OpenAPI v2 savings are worth
   roughly double at the working-set level. (`GOMEMLIMIT` could trade the headroom for GC
   CPU instead, but that's a blunter instrument.)
2. **The gap can be reconciled precisely** from the apiserver's `/metrics`:
   `go_memstats_heap_inuse_bytes`, `go_memstats_heap_idle_bytes`,
   `go_memstats_heap_released_bytes`, `go_memstats_stack_inuse_bytes`,
   `process_resident_memory_bytes`. Those five account for the gap exactly and separate
   reclaimable GC headroom from truly pinned memory.
3. **The profiled traffic is baseline, not workload.** This is an *empty* cluster 30
   minutes after startup, yet the profile shows 40 MB of in-flight GET-response buffers
   and 3.8 GB of lifetime ConfigMap decode churn. That traffic is GKE system components
   (kube-system agents, monitoring, etc.), which makes the "find the noisy client" step
   both easier (small suspect pool) and more valuable (it's baseline cost on every
   cluster).

## Memory-Saving Opportunities (ranked)

1. **ConfigMap usage audit** — largest watch-cache population (16.2 MB live) *and* 3.8 GB
   of decode churn. Look for very large / very numerous ConfigMaps, and clients GETting
   them in hot loops instead of using informers. The 40 MB of live GET-response encode
   buffers supports this theory. Next step: identify the noisy client via audit logs or
   `apiserver_request_total`.
2. **GET-heavy traffic** — same root cause as (1); fixing the client cuts both memory and
   CPU.
3. **OpenAPI (~54 MB)** — fixed cost that grows with CRD count. See the v2 lazy-load PR
   below; v3 is the bigger pool but is actively used.
4. **Metrics scrape churn** — 6.3 GB allocated lifetime; little live memory, but real GC
   pressure. Scrape interval / cardinality are the knobs.

## Source-Level Root Cause: the Serialization Buffer Pool (Opportunity #1/#2)

Traced in the kubernetes source tree (`~/go/src/k8s.io/kubernetes`, v1.37.0-beta.0-490,
branch `openapi-v2-lazy-build`). The profiled cluster was built at HEAD ~1 week before
capture, so this source tree closely matches the profiled binary — the code-level
attribution here carries little version-skew risk. The 49.2 MB pinned in
`runtime.(*Allocator).Allocate` is explained by three interacting behaviors:

1. **Buffers never shrink and growth overshoots.**
   `staging/src/k8s.io/apimachinery/pkg/runtime/allocator.go` — `Allocator.buf` is reused
   across encodes and only ever grows, with formula `size = 2*cap + n`. An allocator that
   alternates between medium and large objects ratchets upward (e.g. 512 KB cap serving a
   600 KB object → 1.6 MB; next slightly-larger object → 4.9 MB). Capacity converges to a
   multiple of the largest object ever encoded, and there is no shrink/trim path.

2. **Grown allocators are recycled through a global `sync.Pool`.**
   `AllocatorPool` (same file) caches allocators between requests.
   `responsewriters.SerializeObject` (`writers.go:110-117`) gets one per GET/LIST/UPDATE
   response and `Put`s it back after the response — with whatever buffer capacity it
   accumulated. Under constant traffic, pool entries are continuously reused so GC never
   evicts them: **N concurrent encodes of large objects ⇒ N multi-MB buffers pinned
   indefinitely.** This matches the 40.5 MB attributed to `GetResource`: the buffers were
   *allocated* while serving GETs of large objects (ConfigMaps top out at 1 MiB) and are
   now *retained* by the pool. The code comment in `allocator.go` even anticipates this
   ("consider introducing multiple pools for storing buffers of different sizes").

3. **Watch sessions pin an allocator for the whole connection.**
   `endpoints/handlers/watch.go:135-160` — each watch grabs an allocator "for the entire
   watch session", released only when the connection closes. Watches live for
   minutes-to-hours, so every watch on a resource with occasional large objects holds a
   large-capacity buffer the entire time. (Profile shows ~4.6 MB allocated at the watch
   encoders themselves, but watch sessions also hold pool-grown buffers.)

Buffer sizing is exact-fit per object: `protobuf.doEncode` calls
`memAlloc.Allocate(estimatedSize)` for the full serialized object size
(`protobuf.go:212,243,264,513`), so buffer capacity tracks the largest object served.

**Candidate fixes (apiserver-side, complements the client-side ConfigMap audit):**

- **Cap pooled buffer size** — drop (don't `Put`) allocators whose capacity exceeds a
  threshold (e.g. 256 KiB–1 MiB), standard `sync.Pool` hygiene as done in `fmt`/`http2`.
  Cheap, low-risk, directly bounds steady-state pool memory.
- **Fix the growth formula** — `2*cap + n` overshoots badly for large `n`; something like
  `max(2*cap, n)` or rounding `n` up to a size class avoids multi-× overshoot.
- **Trim watch-session allocators** — release or shrink the per-watch buffer after each
  event (or periodically), instead of holding peak capacity for the connection lifetime.
- **Size-classed pools** — the multi-pool idea from the code comment; more invasive,
  probably only worth it if the cap approach measurably regresses CPU.

### Prototype: AllocatorPool buffer-size cap

Implemented on branch `allocator-pool-buffer-cap` in the kubernetes tree (commit
`dc1dccdd4a9`, off master at v1.37 dev). Changes:

- `runtime.PutAllocator()` in `apimachinery/pkg/runtime/allocator.go`: drops buffers
  whose capacity exceeds `maxPooledBufferCapacity` (**512 KiB**) before returning the
  allocator to the pool; the allocator struct itself is still pooled. Encodes larger
  than the cap still work — their buffers just go to the GC instead of the pool.
- All three `AllocatorPool.Put` sites converted: `responsewriters/writers.go`
  (GET/LIST/UPDATE responses) and both watch teardown paths in `handlers/watch.go`.
- Unit tests added (drop-oversized, keep-small, ignore-other-types); apimachinery
  runtime + apiserver endpoints handler package tests pass.

**Estimated savings** (from the 2026-07-29 profile):

| | |
|---|---|
| Currently pinned in `Allocator.Allocate` | 49.2 MB |
| Post-fix worst case (~30 pooled allocators × 512 KiB) | ~15 MB |
| Post-fix realistic idle-cluster retention | ~2–5 MB (+ transient in-flight buffers) |
| **Net live-heap savings** | **~35–45 MB** (~16% of the 254 MB heap) |
| **Working-set savings** (×~2 GOGC multiplier) | **~70–90 MB, i.e. ~11–15% of the 615 MB avg WSS** |

**Integration test** (commit `f8ef802568d`,
`test/integration/apiserver/allocator_pool_test.go`,
`TestAllocatorPoolBufferCapacityBounded`): runs a real apiserver in-process (so the
`AllocatorPool` under test is shared with the serving path), serves protobuf GETs of a
~900 KiB ConfigMap (above the cap) and a 64 KiB ConfigMap (below it), then drains the
pool and inspects retained buffer capacities. Two guards:

- **Invariant:** no drained allocator may retain more than 512 KiB.
- **Positive control:** at least one drained allocator must retain ≥ 64 KiB, proving the
  pool still reuses buffers for sub-cap responses (the invariant can't pass vacuously if
  pooling breaks entirely).

Validated in both directions: PASSes with the fix; with `SerializeObject` temporarily
reverted to the uncapped `Put`, it FAILs on the first round, catching a 931,250-byte
buffer in the pool — the exact pathology from the GKE profile.

Test-design notes worth keeping:

- Protobuf content type is required: `SerializeObject` only uses `AllocatorPool` for
  encoders implementing `EncoderWithAllocator` (protobuf yes, JSON no). A JSON-based test
  would exercise nothing.
- `sync.Pool` contents are cleared by GC — the test disables GC
  (`debug.SetGCPercent(-1)`) between serving and draining to stay deterministic.
- `Allocator.Allocate(0)` exposes the retained buffer capacity from outside the package
  without growing it (`cap(a.Allocate(0))`) — no test-only accessors needed.
- Run with `third_party/etcd` on `PATH`:
  `go test ./test/integration/apiserver/ -run TestAllocatorPoolBufferCapacityBounded`.

Caveats to verify with a before/after profile:

1. **Watch-held buffers are only capped at connection close** — the cap applies at
   `Put`, so a live watch that once encoded a large object keeps its oversized buffer
   until the watch ends. If a meaningful share of the 49 MB is held by open watches
   rather than sitting in the pool, savings phase in over watch-connection lifetimes.
   Follow-up if so: trim the per-watch allocator after each event.
2. **Added GC churn for >512 KiB responses** — each now allocates a fresh buffer.
   Expected to be negligible against the existing 54.7 GB lifetime churn baseline, but
   the encode benchmarks should confirm no CPU regression.
3. The 512 KiB threshold is a first guess (larger than ~99% of API objects, small
   enough to bound the pool at N_concurrent × 512 KiB); tune with benchmark data.

## PR: Lazy-Load the Pre-Built Swagger Doc for OpenAPI v2

**Proposal:** `/openapi/v2` is rarely used; lazy-load its pre-built swagger doc instead of
building/holding it at startup.

**Assessment: worthwhile, with caveats.** Ceiling of the win is **~16 MB (6.3% of heap)**
— the `InstallV2` subtree measured above.

Caveats:

1. **Savings only survive if `/openapi/v2` is never hit.** One request builds and caches
   the spec for the life of the process (plus a first-request latency spike and allocation
   burst). Older kubectl, some client-go discovery paths, and monitoring agents still fall
   back to v2. **Verify with `apiserver_request_total` (or audit logs) for the
   `/openapi/v2` path on representative clusters before banking the savings.** If it gets
   hit even once per pod lifetime, pair lazy-load with an idle TTL that drops the cache.
2. **Invalidation must still work.** The v2 spec is rebuilt on CRD / aggregated-API
   changes; a lazy loader needs correct invalidation, not just build-once. The
   kube-openapi `cached` package models exactly this (lazy + dependency-invalidated) —
   build on it rather than a bespoke `sync.Once`. Also consider whether the change belongs
   upstream (kube-openapi / apiserver) rather than as a GKE carry patch.
3. **It's a ~6% win** — real, but the bigger levers in this profile are the serialization
   buffers and ConfigMap traffic. If the pattern proves out, the v3 side (`handler3`
   cached specs 11.5 MB, CRD v3 controller 12 MB) is a strictly bigger pool, though v3 is
   actively used so the "never requested" assumption won't hold there.

## Reproducing the Analysis

```bash
# Top live consumers
go tool pprof -top -unit=mb control_profile.pb.gz

# Cumulative view (subsystem-level)
go tool pprof -top -cum -unit=mb control_profile.pb.gz

# Churn view
go tool pprof -sample_index=alloc_space -top -unit=mb control_profile.pb.gz

# Trace a node's callers/callees
go tool pprof -peek 'Allocator.*Allocate' -unit=mb control_profile.pb.gz

# Size a subsystem
go tool pprof -top -unit=mb -show_from='kube-openapi' control_profile.pb.gz
```

## Open Questions / Next Steps

- [ ] Identify the client(s) driving GET-heavy ConfigMap traffic (audit logs /
      `apiserver_request_total`).
- [ ] Measure `/openapi/v2` request rate on representative clusters to validate the
      lazy-load PR's assumption.
- [ ] Capture a comparison profile after the v2 lazy-load PR to confirm the ~16 MB delta.
- [ ] Investigate whether large individual ConfigMaps (vs. many small ones) dominate the
      16.2 MB watch-cache population.
- [x] Prototype the AllocatorPool buffer-size cap (branch `allocator-pool-buffer-cap`,
      see "Prototype" section above).
- [ ] Benchmark encode CPU / allocs with the cap in place to confirm no regression, then
      measure heap delta under GET-heavy load (before/after profile).
- [ ] Scrape `/metrics` (`go_memstats_*`, `process_resident_memory_bytes`) alongside the
      next heap profile to reconcile live heap → RSS exactly.
