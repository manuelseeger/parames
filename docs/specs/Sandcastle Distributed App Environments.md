# Full Distributed Application Environments per Sandcastle

## Executive summary

There is no mature, pure-Python equivalent to Aspire that provides the same combination of application modeling, service lifecycle, networking, health checks, observability, and developer dashboard.

For Sandcastle, the best direction is:

> **Use Docker Compose as the environment specification and add a host-controlled, Compose-backed Sandcastle provider.**

Each Sandcastle would receive:

- Its existing isolated Git worktree and agent container.
- A uniquely named Compose project.
- Dedicated application, MongoDB, Redis, scheduler, and other service containers.
- Private networks and per-castle volumes.
- Automatic startup and cleanup.
- A narrow `castle app start|stop|restart|status|logs|reset` command for the agent.

The Docker daemon should remain controlled by the Sandcastle host process. Do **not** give agents unrestricted access to `/var/run/docker.sock`.

True Docker-in-Docker is feasible, but it should not be the default. A microVM-backed provider is the strongest long-term option for agents that genuinely need unrestricted Docker or Testcontainers.

## 1. Current situation

Parames already has most of the required topology in `deployment/docker-compose.yaml`:

- `api`
- `scheduler`
- `mongo`

Sandcastle currently uses `@ai-hero/sandcastle` 0.12.0. Its Docker provider creates one agent container and bind-mounts the issue worktree into it.

Useful existing Sandcastle capabilities include:

- Per-branch worktrees.
- Reusable sandboxes.
- Host and sandbox setup hooks.
- Custom sandbox providers.
- Additional Docker mounts, networks, groups, and devices.
- Guaranteed agent-container cleanup through `sandbox.close()`.
- Preservation of dirty worktrees.

However, it does not currently have a multi-service sandbox abstraction.

This is also an acknowledged upstream gap:

- [Sandcastle #471 – Add docker-compose sandbox provider](https://github.com/mattpocock/sandcastle/issues/471)
- [Sandcastle PR #580 – dockerCompose() provider](https://github.com/mattpocock/sandcastle/pull/580)
- [Sandcastle #611 – Hardened Docker-in-Docker/Testcontainers](https://github.com/mattpocock/sandcastle/issues/611)
- [Sandcastle #875 – Compose/DinD use case](https://github.com/mattpocock/sandcastle/issues/875)
- [Sandcastle #372 – Docker Sandboxes microVM provider](https://github.com/mattpocock/sandcastle/issues/372)

The Compose PR is currently open, unmerged, and does not yet solve full per-session dependency isolation by itself.

## 2. Python alternatives to Aspire

### 2.1 Dagger with its Python SDK

Dagger is the closest code-first Python option. It models containers, services, files, secrets, caches, and service bindings through a Python API.

#### Advantages

- Python SDK.
- Strong container-oriented dependency graph.
- Services can be bound to other containers by hostname.
- Good caching and reproducibility.
- Suitable for integration tests and CI.
- Could eventually back a custom Sandcastle provider.

#### Disadvantages

- Primarily a pipeline and CI execution engine, not an Aspire-style local application host.
- Services normally live within a Dagger session rather than as a developer-controlled persistent environment.
- No equivalent Aspire dashboard experience by default.
- Adds another engine and abstraction above Docker.
- Sandcastle orchestration is TypeScript, so using the Python SDK would require a Python subprocess or service boundary.

#### Assessment

A credible option if the goal expands into reproducible CI pipelines. It is not the simplest fit for Sandcastle application environments.

Source: [Dagger services](https://docs.dagger.io/getting-started/types/service/)

### 2.2 Testcontainers for Python

Testcontainers can start MongoDB, Redis, and custom containers from Python tests.

#### Advantages

- Excellent integration with pytest.
- Ephemeral dependencies and automatic cleanup.
- Ready-made support for common databases.
- Good for tests that need MongoDB or Redis.

#### Disadvantages

- Test-oriented rather than full application orchestration.
- The environment usually belongs to the test process.
- Not naturally suited to a scheduler and API remaining available throughout a long agent session.
- Requires Docker API access from inside Sandcastle, creating the same Docker socket/DinD question.
- Does not provide a general application dashboard or operational control plane.

#### Assessment

Use for individual integration tests, not as the primary full-castle environment manager.

Source: [Testcontainers for Python](https://testcontainers-python.readthedocs.io/)

### 2.3 Python Docker SDK / Python-on-whales

These provide Python APIs over Docker and Docker Compose.

#### Advantages

- Python-native control.
- Can implement start, stop, status, logs, and cleanup.
- `python-on-whales` exposes Compose fairly directly.
- Straightforward for a small custom orchestrator.

#### Disadvantages

- Building blocks rather than an application-host framework.
- The project would own naming, cleanup, health checks, concurrency, security, and error recovery.
- No Aspire-like dashboard or service-discovery conventions.
- Duplicates behavior already available through the Compose CLI.

#### Assessment

Useful implementation libraries, but they do not justify introducing a Python orchestration layer when Sandcastle itself is TypeScript and Compose already provides the required model.

### 2.4 Tilt

Tilt provides a complete developer environment, watches files, builds images, and manages services. Its Tiltfile uses Starlark, which is Python-like.

#### Advantages

- Strong development loop.
- UI and service status.
- Handles multiple services and live updates.
- Can use Docker Compose as well as Kubernetes.

#### Disadvantages

- Not actually Python.
- Primarily optimized for interactive human development.
- Adds a long-running control plane per host.
- More complexity than needed for agent-owned, short-lived environments.
- Integration and cleanup would still need to be tied to Sandcastle lifecycle.

#### Assessment

Good for a human microservice development platform, but too heavy for the initial Sandcastle solution.

Source: [Tilt](https://docs.tilt.dev/)

### 2.5 Aspire with Python applications

Aspire can include Python applications as resources, but the AppHost/orchestration layer remains based on the Aspire SDK rather than becoming a pure Python application host.

#### Advantages

- Closest to the desired developer experience.
- Excellent service discovery, health, telemetry, and dashboard.
- Python applications can participate in an Aspire application.

#### Disadvantages

- Requires the .NET/Aspire toolchain and an AppHost project.
- Introduces C# orchestration into an otherwise Python/TypeScript repository.
- Does not align naturally with Sandcastle's existing provider lifecycle.
- Compose remains necessary or useful for deployment portability.

#### Assessment

Technically possible, but not a Python alternative and not recommended solely for Sandcastle orchestration.

Source: [Build Aspire apps with Python](https://learn.microsoft.com/en-us/dotnet/aspire/get-started/build-aspire-apps-with-python)

### Python conclusion

There are Python orchestration components, but no clear pure-Python Aspire replacement. For this requirement, **Docker Compose is the best language-neutral application model**.

## 3. Sandcastle implementation alternatives

### Alternative A: Host-controlled Compose project per Sandcastle

Sandcastle creates a unique Compose project alongside each agent container.

Conceptually:

```text
Host Sandcastle process
└── Compose project: sandcastle-issue-42-<id>
    ├── agent
    ├── api
    ├── scheduler       optional profile
    ├── mongo
    └── redis           future optional service
```

Sandcastle executes the agent inside the `agent` service while Compose owns all supporting services.

#### Advantages

- Natural representation of an application composed of arbitrary services.
- Per-project networks, containers, and volumes.
- Works with MongoDB, Redis, queues, browsers, and future services.
- The agent does not need host Docker privileges.
- Compose health checks and `depends_on` can gate readiness.
- Cleanup can be deterministic with `docker compose down -v --remove-orphans`.
- Fits Sandcastle's custom provider interface.
- Matches the direction of upstream Sandcastle issue #471 and PR #580.
- Existing branch, worktree, agent, review, logging, and cleanup behavior can remain.

#### Disadvantages

- Requires a custom provider until upstream support lands.
- Sandcastle's current provider abstraction has only one execution target, so sidecars must be managed internally by the provider.
- Agent-controlled lifecycle requires a small, restricted control mechanism.
- Builds and package caches need care to avoid excessive startup time.
- Compose manifests must avoid shared resource names.

#### Assessment

**Recommended.**

### Alternative B: Docker-outside-of-Docker using the host socket

Mount `/var/run/docker.sock` into the agent and install the Docker CLI/Compose plugin. Sandcastle already exposes the mounts and supplementary groups needed for this.

The agent can then run:

```bash
docker compose up
docker compose down
docker compose logs
```

#### Advantages

- Easiest prototype.
- Excellent agent ergonomics.
- Reuses host image caches.
- Supports Compose and Testcontainers directly.
- Minimal Sandcastle orchestration work.

#### Disadvantages

- Docker documents membership/access to the Docker daemon as effectively granting root-level host privileges.
- An agent could:
  - Mount arbitrary host directories.
  - Access other castles' containers and volumes.
  - Read secrets from unrelated containers.
  - Start privileged containers.
  - Stop or delete host workloads.
- A project-name convention does not enforce authorization.
- A Docker socket proxy usually cannot validate all dangerous request-body options while remaining compatible with Compose and Testcontainers.
- Container isolation is largely defeated.

#### Assessment

Feasible only as an explicitly unsafe mode for fully trusted agents on a disposable machine. It should not be the standard Sandcastle design.

Sources:

- [Docker daemon socket protection](https://docs.docker.com/engine/security/protect-access/)
- [Docker group grants root-level privileges](https://docs.docker.com/engine/install/linux-postinstall/)

### Alternative C: True Docker-in-Docker sidecar

Each castle has a dedicated `docker:dind` service. The agent talks to that daemon through `DOCKER_HOST`.

#### Advantages

- Agents can use normal Docker, Compose, and Testcontainers.
- Docker objects are isolated from the host daemon and other castles.
- Straightforward agent start/stop interface.
- Per-castle image and container namespace.
- Compatible with the proposed Compose-backed Sandcastle provider.

#### Disadvantages

- Standard DinD normally requires a privileged outer container.
- A privileged container has a much larger host attack surface.
- Nested storage and networking are more complex.
- Image caching and disk use are duplicated per castle.
- Worktree bind mounts are tricky because paths are interpreted by the nested daemon.
- More failure modes and slower startup.
- Cleanup must handle both the outer Compose project and inner Docker objects.

#### Assessment

A useful specialized mode for trusted jobs that require Testcontainers or arbitrary Docker. Not the default for normal app/API/database work.

### Alternative D: Rootless nested Docker or Podman

Run a rootless daemon inside each castle.

#### Advantages

- Better security than privileged rootful DinD.
- Dedicated daemon per castle.
- Docker-compatible APIs are possible.
- Podman supports daemonless and rootless operation.

#### Disadvantages

- User namespaces, cgroups, storage drivers, and networking are complicated inside another container.
- Rootless DinD images may still require elevated outer-container configuration.
- Testcontainers and Compose compatibility needs verification.
- Slower and harder to debug.
- Significant portability differences across Linux, Docker Desktop, and CI hosts.

#### Assessment

Worth prototyping if unrestricted per-agent container execution becomes essential, but too complex for the first implementation.

Source: [Docker rootless mode](https://docs.docker.com/engine/security/rootless/)

### Alternative E: MicroVM per Sandcastle

Run each agent in a Firecracker/Kata/Docker Sandbox-style microVM with its own Docker daemon.

#### Advantages

- Strongest isolation.
- Agent can receive unrestricted Docker access inside its VM.
- Best fit for untrusted generated code and Testcontainers.
- No host Docker socket exposure.
- Clean conceptual ownership: one VM equals one castle.

#### Disadvantages

- More infrastructure and startup overhead.
- Sandcastle does not currently ship this provider.
- Local portability is weaker.
- Custom images and cache distribution need additional work.
- Potential dependence on Docker Sandbox, cloud sandbox, or VM-specific tooling.

#### Assessment

Best long-term security architecture for unrestricted agent Docker access. Track upstream Sandcastle #372, but do not block the Compose solution on it.

## 4. Recommended architecture

### 4.1 Compose-backed Sandcastle provider

Implement or adopt a provider with the following responsibilities:

1. Create or receive the existing Sandcastle worktree.
2. Generate a unique castle ID and Compose project name.
3. Start the project with a trusted Compose definition.
4. Wait for required health checks.
5. Execute Sandcastle commands in the designated `agent` service.
6. Expose application service names through the private Compose network.
7. Tear down the entire project when the sandbox closes.
8. Preserve Sandcastle's existing dirty-worktree behavior.

The Sandcastle custom-provider interface is suitable for this: it expects one execution target and leaves provider-specific lifecycle management behind `create()`, `exec()`, and `close()`.

### 4.2 Unique resources

Every castle must receive unique Compose resources:

- Project name: `sandcastle-<issue>-<run-id>`
- Default project network.
- Project-scoped volumes.
- Containers labeled with castle, branch, issue, and creation time.

Avoid explicit globally shared names.

The existing deployment file cannot be used directly for parallel castles because it contains:

- Top-level `name: parames`
- Fixed host port `8090`
- Fixed MongoDB port `27017`
- Explicit network name `parames_network`
- Production-style `restart: unless-stopped`

Those are appropriate deployment choices but cause collisions between concurrent castles. Keep that deployment file unchanged and use a Sandcastle-specific Compose definition or generated override.

### 4.3 Networking and ports

Services should communicate through Compose DNS:

- `mongodb://mongo:27017/parames`
- `http://api:8000`
- Future Redis at `redis://redis:6379`

Do not publish host ports by default. Playwright and the agent can access the API over the internal project network.

For human debugging, optionally allocate random host ports and report them in Sandcastle logs.

### 4.4 Scheduler profile

The scheduler should be optional:

```text
Default: agent + api + mongo
Profile: scheduler
Future profile: redis
```

Running the scheduler automatically can cause unwanted external API calls or Telegram delivery. Castle configuration should enforce development-safe behavior such as `PARAMES_DEV_MODE=1`.

### 4.5 Agent lifecycle commands

Agents should receive a stable command independent of the underlying runtime:

```text
castle app start
castle app stop
castle app restart
castle app status
castle app logs [service]
castle app reset
```

These commands should call a narrow, project-scoped controller owned by Sandcastle. The controller should permit only operations against the current castle and trusted service definitions.

It must not expose the general Docker API.

Important security constraints:

- Do not let the agent select arbitrary Compose files.
- Do not let it add bind mounts, devices, capabilities, or privileged services.
- Keep the trusted topology outside the agent-writable worktree, or snapshot/validate it before starting.
- Allow rebuilding/restarting application services from the worktree without allowing topology escalation.

### 4.6 Cleanup

The provider's `close()` should always run the equivalent of:

```text
docker compose -p <castle> down -v --remove-orphans
```

Cleanup must execute in `finally`, matching current Sandcastle behavior.

Add host-side recovery for interrupted runs:

- Find resources by Sandcastle labels.
- Remove stale projects older than a configured age.
- Never rely solely on agents calling `stop`.

## 5. Preserving existing functionality

The proposal does not require replacing the current workflow.

| Existing behavior | Preservation approach |
|---|---|
| Planner sandbox is lightweight | Do not start the app stack for the planner |
| Issue-specific branches/worktrees | Continue using Sandcastle worktrees |
| Implementer and reviewer share one sandbox | They also share one Compose project |
| Dependency installation hooks | Continue running once in the agent service |
| Parallel issue execution | Unique project names eliminate collisions |
| Root merger sandboxes | Start only the services needed for merge verification |
| Dirty worktree recovery | Leave Sandcastle's worktree cleanup logic unchanged |
| Agent log files | Keep existing Sandcastle logging |
| Application logs | Add `castle app logs`, without replacing agent logs |
| Container cleanup | Provider closes the whole Compose project |
| Existing deployment | Leave `deployment/docker-compose.yaml` intact |

## 6. Suggested adoption path

### Phase 1: Compose environment, harness-owned lifecycle

- Create a Compose-backed custom Sandcastle provider.
- Give every issue pipeline a unique project.
- Start `agent`, `api`, and `mongo`.
- Keep the scheduler optional.
- Automatically clean up on sandbox close.
- Let the agent inspect the app and logs.

This delivers most of the value without Docker access inside the agent.

### Phase 2: Restricted agent controls

- Add the project-scoped `castle app` control command.
- Support start, stop, restart, status, logs, and reset.
- Add health/readiness reporting.
- Add stale-project cleanup.

### Phase 3: General reusable castle topology

Establish conventions reusable by future repositories:

- One `agent` service.
- Arbitrary sidecars.
- Profiles for optional services.
- Standard labels and health checks.
- No fixed ports or resource names.
- Standard environment output for the agent.
- Optional snapshot/seed hooks.

### Phase 4: Strong Docker-capable sandbox

For repositories requiring arbitrary Docker/Testcontainers:

- Prefer a microVM provider.
- Alternatively test rootless Podman/Docker per castle.
- Retain host-socket access only as an explicit unsafe mode.

## 7. Final recommendation

1. **Use Docker Compose, not a Python orchestration framework, as the portable application model.**
2. **Build a host-controlled Compose-backed Sandcastle provider now**, following the general direction of upstream PR #580 but adding unique per-session projects and full dependency cleanup.
3. **Give the agent restricted application lifecycle commands**, not Docker daemon access.
4. **Do not reuse the production Compose file directly**; introduce a castle-specific topology with no global names or fixed ports.
5. **Keep Docker-in-Docker as an optional trusted mode**, primarily for Testcontainers.
6. **Treat a microVM-backed provider as the long-term solution** for unrestricted Docker-capable agents.

This provides the shortest path to full application environments while retaining Sandcastle's current branch, worktree, review, logging, parallelism, and recovery behavior.
