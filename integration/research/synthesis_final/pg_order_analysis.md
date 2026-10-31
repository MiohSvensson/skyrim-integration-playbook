READY: final gameplay/compatibility → six-stage Synthesis → fresh PG → new LOD.

This is a source-backed scheduling decision. Runtime output acceptance remains pending.

| Patcher | Reads | Writes | Post-Synthesis PG condition |
|---|---|---|---|
| Disable loading screens (All) | ModKeys, LSCR owner | LSCR conditions | PG emits no LSCR |
| AOS/ISC | Keywords, sound/impact/projectile links, armor armature | Sound/impact/projectile links and ARMA footsteps | Fresh winning-record copy and typed nonmodel equality |
| Missing gender world model | ARMO winning ModKey; ARMA null/empty sex model; templates | Missing male/female ARMA model | Overlapping writer: run it first; preserve populated model and validate fresh PG |
| Experience | RACE health/name/origin | Captured generated INI | PG emits no RACE; retain private sidecar finally-restore protocol |
| Water for ENB | CELL/WRLD water and dependencies | CELL water/env map/flag, WRLD LOD water | PG emits no CELL/WRLD |
| Landscape vertex color | LAND colors/layers; LTEX snow | LAND vertex colors | PG emits no LAND/LTEX/CELL/WRLD |

Do not reuse pre-Synthesis PG plugins or ExpectedSources. Prepare and execute PG against the accepted fresh Synthesis context, install DB outputs after it explicitly, and run the frozen typed verifier. Masters alone do not enforce this order. Preflight NIF snapshots are reusable only for the exact asset path, bytes, provider and reader pins; newly added model uses still require final coverage. Generate LOD last, then repeat final QEX and VFS on the final plugin SHA set.

The opposite order is not asserted equivalent. The AA driver tests winning ARMO ModKey and fills missing model containers; these predicates overlap PG output semantics. Full evidence, source hashes, line ranges and pending gates are in pg_order_analysis.json.
