# Aspire MicroVM Sandcastle Spike

**Date:** 2026-07-29  
**Ticket:** #11  
**Decision:** **Adopt with conditions**

## Executive summary

Docker Sandboxes (`sbx`) is the best fit for one complete Aspire development environment per Sandcastle issue. A live prototype ran Paramés' TypeScript AppHost, API, MongoDB, optional scheduler, coding agent, Git synchronization, and a private Docker Engine inside genuine microVMs. The host Docker socket was never mounted or copied.

Two 4-CPU/8-GiB castles ran concurrently. They had different boot IDs and Docker daemon IDs, disjoint Docker objects, separate Aspire control planes and credentials, and separate MongoDB data. Removing castle A left castle B healthy. A warm cached VM accepted commands in about 4 seconds; the earlier cold custom-template run accepted commands in 25 seconds. During the concurrent uncached application build, API health took 133 and 146 seconds.

Adoption should initially be limited to Docker-heavy or higher-risk implementation/review jobs. The planner should stay on the existing lightweight provider. Production use is conditional on supported Linux/CI hosts with KVM or nested virtualization, a versioned template build, one provider scope per castle, stale-resource reconciliation, and explicit endpoint-forwarding UX.

Per the issue's 2026-07-29 scope update, Aspire MCP and Redis experiments were discontinued and are not part of this decision.

## Tested stack

| Component | Version/evidence |
|---|---|
| Docker Sandboxes | `v0.37.0`, commit `8b65b864b0d49c29f05a55170d6b5eea4c0d11e7` |
| Sandcastle | `@ai-hero/sandcastle 0.12.0` |
| Template | `docker.io/library/parames-sbx:dev` |
| Template digest/size | `sha256:6f00c1a58a878656e3c133f1ed8a80657daa11db0ef75d198e7c2585702890cd`; 1,407,486,132 bytes (~1.31 GiB, reported as ~1.41 GB) |
| Template base | `docker.io/docker/sandbox-templates:claude-code-docker` |
| Guest kernel | `7.0.12` |
| Guest Docker Engine | `29.6.1` |
| Aspire CLI | `13.4.6` |
| Node.js | `22.22.1` |
| Python / uv | `3.13.14` / `0.12.0` |
| Git / GitHub CLI | `2.53.0` / `2.46.0` |
| Coding agent in image | Claude Code `2.1.195` |
| Test host | Omarchy 3.8 / Arch Linux x86-64, kernel `7.0.3-arch1-2`, 8 CPUs, 31 GiB RAM, KVM |

Arch is outside Docker's documented Linux support matrix. Docker documents Ubuntu 24.04+ with KVM, macOS 14+ on Apple silicon, and Windows 11 with Windows Hypervisor Platform. The official distro-neutral Linux archive worked on this host and `sbx diagnose` passed all nine checks, but production should use a documented platform.

## Reproduction

### Install and validate sbx

Install the official v0.37.0 archive, authenticate, select the desired network policy, and verify the host:

```bash
sbx version
sbx diagnose
```

The archive used in this spike had published SHA-256:

```text
770abf7f91b13aba86cc7bb7d548b8e07c812d5a109321905e7b7da0ad07d998
```

### Build the versioned template

```bash
docker build -f .sandcastle/Dockerfile.sbx -t parames-sbx:dev .
docker image save parames-sbx:dev -o /tmp/parames-sbx-dev.tar
sbx template load /tmp/parames-sbx-dev.tar
sbx template ls
```

The image contains tools and package caches, never project source or long-lived secrets. It pre-restores the Aspire 13.4.6 NuGet closure because Balanced policy denied runtime access to `api.nuget.org` during the first run.

### Provider checks

```bash
npm run sandcastle:provider:test
npm --prefix aspire run build
npm --prefix aspire run lint
git diff --check
```

The retained provider is deliberately not selected in `.sandcastle/main.mts`.

### Manual equivalent of the isolated transfer

```bash
mkdir -p /tmp/parames-empty
git bundle create /tmp/parames.bundle --all
sbx create --name parames-test --cpus 4 --memory 8g \
  --no-share-skills --template parames-sbx:dev claude /tmp/parames-empty
sbx cp /tmp/parames.bundle parames-test:/tmp/parames.bundle
sbx exec parames-test sh -lc \
  'git clone /tmp/parames.bundle /home/agent/workspace && cd /home/agent/workspace && git checkout spike-microvm'
sbx exec parames-test sh -lc \
  'cd /home/agent/workspace/aspire && npm ci && aspire restore --non-interactive'
sbx exec parames-test sh -lc \
  'cd /home/agent/workspace/aspire && aspire start --isolated --non-interactive --format Json'
sbx exec parames-test sh -lc \
  'cd /home/agent/workspace/aspire && aspire wait api --status healthy --timeout 600 --non-interactive'
```

A normal Sandcastle coding-agent invocation is a long-running attached `sbx exec`. It keeps the VM running while the agent works. When the final attached session exits, v0.37.0 normally begins a 30-second auto-stop grace period. The source and Git state persist across stop/start, but each implementer or reviewer must start the AppHost it needs.

Cleanup:

```bash
sbx exec parames-test sh -lc 'cd /home/agent/workspace/aspire && aspire stop --non-interactive'
sbx rm --force parames-test
sbx ls
```

## Candidate comparison

| Dimension | Docker Sandboxes | Vercel Sandbox | Daytona VM class | Incus VM | Kata / raw Firecracker |
|---|---|---|---|---|---|
| Isolation | Dedicated microVM, kernel, filesystem, network | Firecracker microVM | Qualifies only with explicit VM class | Full QEMU VM | Correct primitive, awkward/incomplete platform |
| Private Docker | Built-in guest Docker Engine in `-docker` template | Privileged guest processes can run Docker; must validate image | Documented `docker-dind` snapshot inside VM; must validate | Install Docker in VM | Nested daemon and lifecycle must be built |
| Host socket | Not required; proven absent | Not required | Not required in VM mode | Not required | Reject any design that bind-mounts it |
| Local / CI | Local-first; CI needs KVM/nested virtualization | Hosted, no caller KVM | Hosted | Self-hosted hosts/runners | Significant host/platform work |
| Startup | 25 s cold, ~4 s warm in this test | Provider-dependent; hosted startup | Provider-dependent | Usually slower full VM | Depends on custom manager/snapshots |
| Images/cache | OCI templates, persistent template store, Docker layers inside VM | Custom registry images/snapshots | Snapshots | Images/snapshots | Must design and operate |
| Exec/transfer | CLI streaming exec, `sbx cp`, create/rm | SDK streaming and transfer | SDK streaming and transfer | CLI/REST/guest agent | Must build guest agent and APIs |
| Endpoints | Ephemeral loopback publishing; Aspire needs relay/all-interface binding | Exposed ports | Preview/network endpoints | Proxy devices | Must build networking/forwarding |
| Secrets/egress | Per-process env; governance policy; Balanced blocks raw TCP/UDP/ICMP and denied NuGet in test | SDK env and network policy | Provider env/policy | Operator-owned controls | Operator-owned controls |
| Concurrency | Host-capacity bound; two castles proven | Hobby documentation listed 10; higher paid limits | Account/plan bound | Host-capacity bound | Host-capacity bound |
| Cleanup | `sbx rm --force`; list with `sbx ls`; stopped VM remains discoverable | Installed adapter calls `stop`, not permanent delete | Adapter calls `delete` | Operator reconciliation | Must build reconciliation |
| Platform | Docker-supported OS/hypervisor; Linux KVM | Hosted API | Hosted API | Linux QEMU/KVM | Linux KVM/containerd expertise |
| License/cost | CLI documented free for commercial use; paid governance features; local compute/storage | About $0.128/vCPU-h + $0.0212/GB-h memory, $0.15/GB egress, $0.08/GB-month snapshots | About $0.0504/vCPU-h + $0.0162/GiB-h memory, plus storage | Apache-2.0; operator infrastructure/labor | Kata/Firecracker open source; high engineering/operations cost |
| Sandcastle effort | Small custom isolated provider; best contract fit | Existing provider, but deletion/custom-image gaps | Existing provider, VM selection/version validation needed | New provider and fleet operation | High; effectively building VM management |
| Verdict | **Adopt with conditions** | Hosted fallback | Conditional fallback | Self-hosted fallback | Reject for initial implementation |

A container that merely bind-mounts `/var/run/docker.sock` is rejected: possession of that socket is effectively host-root control and does not isolate Docker objects or cleanup.

## Provider design

The proof of concept uses the public `createIsolatedSandboxProvider()` API. It does not fork Sandcastle and does not alter the active Docker provider.

Lifecycle:

1. Generate a unique, prefix-identifiable VM name.
2. Create a fresh empty host directory solely because `sbx create` requires a workspace argument.
3. Create a custom-template VM with no shared skills, 4 CPUs, and 8 GiB.
4. Return `/home/agent/workspace` as `worktreePath`; default pre-sync exec uses existing `/home/agent`.
5. Let Sandcastle create a Git bundle, transfer it through `copyIn`, and clone it inside the guest.
6. Run coding agents with streaming `sbx exec`; pass environment values at execution time.
7. Return session files through `copyFileOut`; Sandcastle exports/fetches guest Git commits through its isolated synchronization path.
8. Stop Aspire when practical and call idempotent `sbx rm --force`.
9. Remove the temporary empty host directory.

`withDockerSbxProvider()` adds a per-castle `finally` boundary. This is needed because Sandcastle 0.12.0 does not call `handle.close()` if isolated Git synchronization fails after provider creation. It closes every handle created in that one provider scope without touching concurrent scopes. A partially successful `sbx create` is also followed by best-effort named removal.

The provider bounds captured output while streaming complete stdout/stderr lines through `onLine`. Environment is supplied to `sbx exec`, not baked into the image. Shared skills are disabled to avoid cross-castle writable state.

### Git and uncommitted state

A bundle-only worktree was cloned in the guest with valid `.git` metadata. A harmless documentation commit was created there, exported as a bundle, fetched, and fast-forwarded onto the host branch. This proved commit recovery; the temporary proof commit/file was removed from the final branch.

Sandcastle remains responsible for branch creation, initial bundle generation, commit collection, session capture, and dirty-worktree policy. Files not represented by Git or configured transfer paths require explicit `copyIn`/`copyFileOut`, as they do for other isolated providers.

## Aspire results

Inside a fresh VM receiving only the Git bundle:

- `npm ci`, `aspire restore`, TypeScript build/lint, and AppHost startup succeeded.
- Aspire created API and MongoDB in the guest daemon.
- `aspire wait api --status healthy` passed.
- `GET /api/healthz` returned `{"status":"ok","version":"0.1.5"}`.
- `GET /` returned HTTP 200 and the Paramés frontend (`<title>Parames`).
- The optional scheduler was explicitly started under `PARAMES_DEV_MODE=1`, reached `running`, and was stopped.
- A temporary API source change was rebuilt/restarted with `aspire resource api restart`, observed in the health response, and reverted. Warm restart-to-health was 13 seconds.

The issue's `/healthz` text is stale; the actual route is `/api/healthz`.

## Concurrency and isolation evidence

Two castles, `parames-castle-a` and `parames-castle-b`, ran simultaneously from separate transferred clones.

| Evidence | Castle A | Castle B |
|---|---|---|
| Boot ID | `671915fd-ffd2-481f-b4fc-c85f71c83baa` | `236966e8-e302-4163-8f31-97f9964e535d` |
| Docker daemon ID | `9afac3c1-175c-462a-86f0-4f67e49eb76e` | `fdc63372-4f98-4108-98b3-00a6efef0100` |
| Aspire network | `aspire-session-network-kuebbrjw-aspire-managed` | `aspire-session-network-hdbntdet-aspire-managed` |
| API VM-loopback endpoint | `localhost:44691` | `localhost:44425` |
| Dashboard VM-loopback endpoint | `localhost:35119` | `localhost:39035` |
| Mongo marker visible | only `castle-a` | only `castle-b` |

Each guest had its own `/var/run/docker.sock`; `/host/var/run/docker.sock` was absent. The initially created daemons had no objects. Later container IDs, image build IDs, networks, generated Mongo credentials, API ports, and dashboard tokens differed.

Network namespaces reused overlapping private addresses, which is further evidence that these were not one shared bridge. From A, B's API/dashboard ports were closed; from B, A's ports were closed. Mongo was not exposed on either guest host. No other castle's Docker socket, Aspire control plane, API, or database was reachable through default localhost/network state.

Castle A was stopped and removed. `sbx ls` then listed only B. B immediately passed `aspire wait`, returned healthy, retained only its `castle-b` Mongo marker, and kept both API and Mongo containers running.

## Performance and resources

| Measurement | Result |
|---|---|
| First custom-template provisioning | 24 s |
| First command-ready | 25 s from cold create |
| Warm cached concurrent provisioning | ~4 s for each VM |
| Concurrent AppHost start to API healthy | A 133 s; B 146 s |
| Warm source rebuild/restart to health | 13 s |
| Guest allocation | 4 CPUs, 8 GiB RAM each |
| Guest used memory after startup (`free`) | ~823–840 MiB; ~7.0 GiB available |
| API container memory | ~160 MiB; 0.16–0.18% CPU at sample |
| Mongo container memory | ~181 MiB; 0.32–0.37% CPU at sample |
| Guest Docker images | 1.626 GB across 3 images |
| Build cache | 824.4 MB, 387.7 MB reclaimable |
| Local volumes | ~315 MB |
| Template image | 1,407,486,132 bytes |

The 133/146-second readiness values include simultaneous Docker builds on an eight-core host and are intentionally conservative. Warm image/build-layer reuse should be measured in a later representative workload benchmark rather than inferred from this one run.

## Caching model

- **VM base/toolchain:** versioned OCI template in sbx's template store.
- **Aspire packages:** pinned 13.4.6 CLI and pre-restored NuGet closure in the image. Rebuild when integrations change.
- **Python:** Python 3.13 and uv in the template; project dependencies remain lockfile-driven. A future image may add an uv download cache but must not add a project virtualenv.
- **Node:** Node in the template; `npm ci` remains worktree-local. A controlled npm cache can be layered later.
- **Docker builds:** guest Docker layer cache survives VM auto-stop/restart but is deleted with the VM. Common heavyweight base images may be pre-pulled into a template only after measuring image-size trade-offs.
- **Secrets:** never in image layers or shared caches.

## Endpoint access

Guest-local API/frontend access works directly through URLs from `aspire describe`. `sbx ports` allocates collision-free host ports and binds loopback by default.

A direct publication of the Aspire endpoint proxy failed with connection reset because Aspire's generated proxy listened on VM loopback, while sbx forwarding enters through the VM interface. A temporary guest TCP relay from `0.0.0.0:18000` to `127.0.0.1:44691`, followed by `sbx ports --publish 18000`, exposed A at ephemeral host port `32770`; the host health request succeeded.

Production should provide a small authenticated/explicit relay command or configure Aspire's development proxy to listen on a guest interface. It must publish only on host loopback by default, allocate ephemeral ports, show the mapping, and remove it at close. Dashboard tokens and generated database credentials must not be logged.

## Security, secrets, and egress

- VM, not privileged Docker-in-Docker on the host, is the primary boundary.
- Docker's `-docker` template runs its Docker service inside the microVM; no host daemon socket is involved.
- `--no-share-skills` prevents shared writable agent skills.
- Secrets are injected as command environment values. Use short-lived tokens and provider-specific secret stores where available.
- Balanced policy blocked NuGet and raw TCP/UDP/ICMP behavior is restricted by default. Required package domains should be explicitly allowlisted or resolved during a trusted template build.
- Governance policy, DNS/HTTP allowlists, and audit requirements should be decided before broad rollout.

## Cleanup and failure behavior

- **Normal:** `aspire stop`, then `sbx rm --force`; `sbx ls` was empty.
- **One-of-two destruction:** A was removed while B remained healthy.
- **Agent disconnect:** live real-agent tests showed v0.37.0 auto-stop 30 seconds after the last attached session; the next `sbx exec` restarted the VM and retained Git state. Guest processes do not survive this stop.
- **Forced harness/session test:** after terminating the keeper and waiting 42 seconds, one run still showed B as running. It was discoverable and removed with `sbx rm --force`. Auto-stop is therefore a cost optimization, not a cleanup guarantee.
- **Failed provider create:** the retained provider now attempts named `rm --force` even when `sbx create` throws after allocation.
- **Failed Sandcastle synchronization:** the per-castle `withDockerSbxProvider()` scope closes created handles in `finally`, working around Sandcastle 0.12.0's missing close call on sync failure.
- **Failed AppHost:** stop the AppHost if registered, inspect guest Aspire logs, and always remove the VM at provider scope exit.

Manual reconciliation:

```bash
sbx ls
sbx rm --force <project-owned-name>
```

Production should use an invocation-specific name prefix/lease registry and only reap expired resources owned by that invocation or deployment. Host reboot recovery and stronger crash reconciliation were explicitly accepted as post-spike limitations in the ticket update.

After tests, both VMs were removed and `sbx ls` reported no sandboxes. The cached template intentionally remains in the shared template store.

## Limitations and public API findings

1. Sandcastle 0.12.0 omits `close()` when isolated sync fails after `create()`. The retained scoped wrapper solves this for integration without a fork; upstream should add an `ensuring(handle.close)` boundary.
2. The provider uses CLI subprocesses because sbx exposes the needed lifecycle cleanly; a stable SDK would reduce output/schema coupling.
3. Aspire's loopback endpoint proxy needs a relay or listen-address configuration for `sbx ports`.
4. The host must supply KVM/hypervisor support. Ordinary SaaS CI runners generally do not; use nested-virtualization runners or a hosted fallback.
5. Arch worked but is unsupported by Docker's documented matrix and lacked active AppArmor. Use supported hosts for production.
6. VM allocation is materially heavier than the existing planner/container workflow.
7. Template provenance, vulnerability scanning, SBOMs, signing, and patch cadence are not yet automated.
8. No long-lived secret should be supplied through an image build or copied shared state.

## Recommendation and staged plan

**Adopt with conditions.** Docker Sandboxes satisfies the security and functional requirements better than hosted adapters or a self-built VM manager, but it should not immediately replace every sandbox.

1. **Retain the spike assets (this change):** keep the unwired provider, template, tests, and report. Keep current Docker behavior and `deployment/docker-compose.yaml` unchanged.
2. **Integrate implementation/review only:** create one `withDockerSbxProvider()` scope per issue pipeline. Keep the planner on the current lightweight Docker provider. Implementer and reviewer may reuse filesystem/Git state, but each must start its own required Aspire state.
3. **Add lifecycle operations:** invocation lease/prefix, guaranteed outer `finally`, startup/sync timeout handling, stale listing/removal command, and structured sbx diagnostics.
4. **Build a trusted template pipeline:** pin sbx/base/tool versions, produce SBOM/signature, scan, publish by immutable digest, and refresh Aspire/NuGet caches.
5. **Add endpoint UX:** explicit loopback-only ephemeral forwarding with teardown and redacted logs.
6. **Pilot selectively:** use for Docker-heavy, Testcontainers, infrastructure, or high-risk issues; record latency and host saturation. Keep ordinary code-only tickets on the cheaper provider.
7. **CI decision:** provision supported nested-virtualization runners. If that is not economical, implement a Vercel fallback only after changing stop to permanent deletion and validating current custom images/private Docker.
8. **Broaden only after evidence:** establish concurrency quotas, egress policy, secret broker, observability, and per-castle cost/SLOs before making microVMs the default.

Raw Firecracker and Kata should not be pursued for this rollout. Incus remains the fallback only if self-hosting becomes mandatory; Vercel remains the fallback where hosted CI convenience outweighs cost and deletion constraints.
