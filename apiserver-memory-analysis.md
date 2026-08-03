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
