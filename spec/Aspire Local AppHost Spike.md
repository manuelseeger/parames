# Aspire Local AppHost Spike

> Post-spike adoption note: the retained AppHost lives at `aspire/`. The Redis resource and integration described below were spike-only and have been removed from the retained AppHost.

## Recommendation: adopt with conditions

Aspire 13.4.6 successfully modeled and operated the Paramés API, MongoDB, optional scheduler, and Redis sidecar from an isolated TypeScript AppHost. It supplied dynamic endpoints, dependency ordering, health checks, session cleanup, dashboard state/logs, and its official MCP control surface. No custom MCP server is warranted.

Adoption conditions:

1. Use a MongoDB-8-compatible host. This host runs Linux `7.0.3-arch1-2`; MongoDB's [SERVER-121912](https://jira.mongodb.org/browse/SERVER-121912) says every MongoDB 8.0+ version crashes on Linux 6.19+. The spike used the newest compatible official image, `mongo:7.0.39`, only as a host-specific workaround. Production Compose behavior was not changed.
2. Remove generated fixed `profiles` ports from `aspire.config.json` (or have the lifecycle adapter generate unique profile ports). `aspire start --isolated` still collided with the generated `https://127.0.0.1:22102` resource-service port; removing the profile allowed two simultaneous AppHosts with random ports.
3. Fix or explicitly accommodate the current Dockerfile's runtime behavior: it syncs before source is copied, so the editable project is not installed. The spike used `uv run --no-sync` and `PYTHONPATH=/app/src`. Plain `uv run` also attempted a dev sync and failed under Aspire's injected CA environment.

## Versions and setup

| Component | Version |
|---|---|
| Aspire CLI / SDK / MongoDB and Redis integrations | 13.4.6 |
| Node / npm | 25.9.0 / 11.12.1 |
| Docker Engine | 29.4.3 |
| Python / uv | 3.14.4 / 0.11.8 |
| spike MongoDB | 7.0.39 |
| requested MongoDB 8 image tested | 8.2.12 (`mongo:8`) |

The CLI archive was downloaded from the Aspire 13.4.6 GitHub release and SHA-512-verified. Reproduce from a checkout:

```sh
aspire new aspire-ts-empty --name parames-aspire --output aspire
cd aspire
aspire integration add mongodb --version 13.4.6
aspire restore
npm ci
npm run aspire:build && npm run aspire:lint
aspire start --no-build
```

## Resource model and rationale

The spike AppHost used the official MongoDB and Redis integrations and a Dockerfile resource for API and scheduler. The retained `aspire/apphost.mts` uses MongoDB and the Dockerfile resources only. Dockerfile was selected over the Python integration because it exactly exercises the production build, including the built Vite UI and locked deployment dependencies. The Python integration would make local edit/reload simpler, but would test a materially different environment.

* `mongo` has a named `parames` database reference; Aspire injects its connection string into `PARAMES_MONGO_URI`.
* API receives `PARAMES_CONFIG_PATH=/app/config/default.yaml`, `PARAMES_DEV_MODE=1`, connection reference, and dynamic HTTP endpoint. It waits for the seed resource to complete, so a healthy API starts with the default alert definitions present. Its effective health endpoint is **`/api/healthz`**, not `/healthz` as the ticket stated.
* The seed resource runs `parames seed` automatically after MongoDB is healthy; it exits after its idempotent upserts. The API's custom **Paramés seed** command remains available for an explicit repeat.
* Scheduler has the same development-safe environment but `withExplicitStart()`: it cannot start merely by opening the AppHost.
* Redis is unused and `withExplicitStart()`. It is also `excludeFromMcp()`, demonstrating resource-level MCP exclusion.
* No fixed application resource host ports are declared.

## Experiments and results

### Baseline, health, data, and rebuild

```sh
aspire start --no-build --format Json
aspire describe --format Json
curl -fsS http://localhost:<dynamic-port>/api/healthz
# seed through the API image
 docker exec <api-container> sh -lc 'uv run --no-sync python -m parames.cli seed'
curl -fsS http://localhost:<dynamic-port>/api/alert-definitions
```

The API, MongoDB, and `parames` database all reported Healthy. `/api/healthz` returned `{"status":"ok","version":"0.1.5"}`. Seeding upserted `schoenberg`, `mainz_finthen`, and `zurich_bise`; the API returned all three.

A temporary comment was added to `Dockerfile`, the AppHost was stopped and started, then the comment was reverted. The API image source changed from `api:b3e6622f...` to `api:7a53cb4c...`, and its health was Healthy after rebuild.

### Resource controls and optional resources

```sh
aspire resource api restart
aspire resource scheduler start
aspire resource redis start
aspire resource scheduler stop
aspire resource redis stop
```

On AppHost startup, the seed container ran after MongoDB, exited 0, and the API only then reached Healthy; its alert-definitions endpoint returned all three seeded entries. The API also exposes a custom **Paramés seed** command for an explicit idempotent repeat. Invoke it with `aspire resource api seed`; it exited 0 and logged all three successful upserts. Scheduler startup logged its configured cron (`*/6`), and confirmed the missing Telegram token without exposing/requiring one; `PARAMES_DEV_MODE=1` was injected. Redis 8.6.5 started and accepted TCP/TLS connections, with no Paramés code coupling.

### MCP

Configured stdio server:

```json
{"mcpServers":{"aspire":{"command":"aspire","args":["agent","mcp"]}}}
```

A standard MCP SDK client connected to `aspire agent mcp`. It successfully used `list_apphosts`, `list_resources`, `list_console_logs`, and `execute_resource_command`.

* `list_resources` reported API/Mongo health, relationships, dynamically allocated endpoints, and environment-variable **names only** (values redacted).
* API and Mongo console logs were readable.
* MCP `stop`, `start`, and `restart` each succeeded for the API, followed by Healthy status.
* Redis did not appear in MCP `list_resources`, proving `excludeFromMcp()`.
* `list_structured_logs` and `list_traces` returned `Resource ... not found`: the Python service emits console logs but has no OpenTelemetry instrumentation/exporter. Thus those diagnostics are not useful without non-production instrumentation/configuration.

### Concurrent worktrees

```sh
git worktree add --detach /tmp/parames-aspire-second HEAD
# copy the isolated spike prototype into that worktree
cd /tmp/parames-aspire-second/aspire
# remove generated fixed profiles from aspire.config.json for dynamic dashboard/service ports
aspire start --isolated --no-build
```

Both AppHosts ran concurrently. API endpoints were independently allocated (`http://localhost:35963` and `http://localhost:46469` in the run); Mongo endpoints were also distinct. Containers and networks had distinct generated names, for example `aspire-session-network-yejqneep-aspire-managed` and `aspire-session-network-wugbeyep-aspire-managed`.

Only the first API was seeded: it returned 3 definitions while the second returned 0. Stopping the first AppHost left the second API Healthy and its MongoDB Running/Healthy. The MCP server discovered the correct AppHost within its working-directory scope; `select_apphost` remains necessary for an agent whose scope contains multiple AppHosts.

Initial `--isolated` failed because template-generated profile ports remained fixed:

```text
Failed to bind to address https://127.0.0.1:22102: address already in use.
```

Removing the profile made `--isolated` choose random dashboard/resource-service ports and succeed.

### Cleanup and failures

* Normal stop removed session-lifetime containers and network.
* Killing the AppHost with `SIGKILL` also removed its session containers and network within 15 seconds; the independent second AppHost stayed healthy.
* `mongo:8` exited code 139 around 30 seconds with `OOMKilled=false`, including when run outside Aspire. `mongo:8.0` explicitly emitted the Linux-6.19 incompatibility error; Jira SERVER-121912 identifies 8.0+ as affected. `mongo:7.0.39` remained running and passed `buildInfo`.
* Changing Mongo to persistent lifetime preserved three seeded definitions across normal AppHost stop/start. The persistent Mongo container and its two anonymous volumes remained after AppHost shutdown. Recovery/cleanup was:

```sh
docker rm -f <persistent-mongo-container>
docker volume rm <data-db-volume> <data-configdb-volume>
```

Session-lifetime cleanup leaves no stale resources; persistent lifetime intentionally requires the above cleanup if data is no longer wanted.

## Security observations

`PARAMES_DEV_MODE=1` is explicit on API and scheduler. No Telegram token is passed. The generated MongoDB credentials appear in local container environment/connection strings and must not be printed in reports or delegated indiscriminately. Aspire MCP redacts environment values in its resource listing, but console logs and lifecycle controls are sensitive; the adapter must authorize callers and scope MCP to the selected AppHost. Redis was excluded from MCP as a proof point.

## Remaining Sandcastle adapter responsibilities

* Create/select a worktree and the corresponding AppHost; remove fixed generated profiles or allocate unique dashboard/resource-service ports.
* Start with `--isolated`, track AppHost PID, dashboard URL/token, worktree, and resource identity.
* Select the intended AppHost before MCP calls and enforce caller authorization/resource allowlists.
* Supply safe configuration/secrets, always force development-safe mode for non-production castles, and prohibit production delivery tokens.
* Select a MongoDB-8-compatible Docker host (or report the kernel blocker), and manage intentional persistent volumes plus explicit cleanup.
* Surface the Dockerfile/Python runtime decision and any telemetry instrumentation needed for traces/structured logs.
* Handle stale-process/container recovery and present concise status/log links to agents.
