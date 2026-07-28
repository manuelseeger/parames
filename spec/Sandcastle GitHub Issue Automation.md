# Sandcastle GitHub Issue Automation

## Status

Proposed.

## Summary

Build an unattended automation workflow in which a trusted GitHub feature request is selected by Sandcastle, decomposed into an implementation plan, implemented in isolated branches by one or more Claude Code agents, reviewed, deterministically verified, integrated, and submitted as a pull request against `main`.

The automation must never merge the final pull request. A human reviews and approves the pull request before merging it to `main`.

The workflow will use:

- Sandcastle as the orchestration library
- Claude Code as the coding-agent harness
- A Claude Pro subscription through `CLAUDE_CODE_OAUTH_TOKEN`
- Docker as the Sandcastle sandbox provider
- GitHub Issues as the work queue
- GitHub pull requests as the delivery and approval boundary
- A local machine for initial development and validation
- A headless VM for eventual unattended operation

## Goals

1. A maintainer can create a GitHub feature request and explicitly authorize Sandcastle to process it.
2. A scheduled unattended runner can discover and claim the issue.
3. A planner can analyze the feature and produce a dependency-aware task graph.
4. Independent tasks can be implemented concurrently in isolated worktrees and containers.
5. Each implementation can be reviewed and corrected by a separate agent.
6. Tests and other verification are run by the orchestrator, not trusted solely from agent claims.
7. Completed task branches are integrated into one feature branch.
8. A final review and full verification run occur against the integrated feature.
9. The feature branch is pushed and submitted as a pull request against `main`.
10. The root issue remains open until the human-approved pull request is merged.
11. The workflow can recover safely from interruption without duplicating work or pull requests.
12. The final merge to `main` always requires human approval.

## Non-goals

1. Automatically merging pull requests into `main`.
2. Allowing arbitrary public issue authors to trigger code execution.
3. Treating an agent's statement that tests passed as sufficient verification.
4. Giving implementation agents unrestricted control over repository administration.
5. Building a general-purpose hosted issue automation platform.
6. Guaranteeing unlimited Claude usage; Claude Pro subscription limits still apply.

## Feasibility

This is a supported and appropriate use case for Sandcastle, with custom orchestration around its existing primitives.

The generated `parallel-planner-with-review` template already supports:

| Requirement | Existing support |
|---|---|
| Read labeled GitHub issues | Yes, through `gh issue list` in a prompt |
| Structured planning | Yes, through `Output.object()` and a schema |
| Dependency analysis | Yes, in the generated planner prompt |
| Parallel implementation | Yes, using separate branches/worktrees and `Promise.allSettled()` |
| Repeated implementation turns | Yes, using `maxIterations` |
| Per-branch review | Yes, by running a reviewer in the same reusable sandbox |
| Isolated execution | Yes, through the Docker sandbox provider |
| Branch reuse | Yes, through deterministic branch names |
| Session capture and resume | Yes, for supported agent providers |
| Merge conflict resolution | Yes, through a merger agent |
| Pull request creation | Not built into the current template, but can be added with `git push` and `gh pr create` |
| Polling GitHub unattended | Requires a scheduler or service wrapper |
| One feature issue decomposed into parallel tasks | Requires a custom planner schema and DAG scheduler |
| Crash-safe claiming and retries | Requires labels, deterministic identifiers, and startup reconciliation |

Sandcastle is a TypeScript orchestration library rather than a complete hosted GitHub bot. The intended implementation is to customize `.sandcastle/main.mts` and its prompt files while retaining Sandcastle's sandbox, worktree, agent, logging, and session facilities.

## Current template gaps

The generated workflow must not be deployed unattended without addressing these gaps.

### Unsafe final merge target

The current final merger uses the Docker provider's default `head` branch strategy. A bind-mount provider using `head` can modify the host's checked-out branch directly.

The unattended workflow must instead create a dedicated feature integration branch and must never merge task branches into `main`.

### Premature issue closure

The generated `merge-prompt.md` closes issues immediately after merging implementation branches. This bypasses human review.

The new workflow must not close the root issue or any included sub-issue during automation. The pull request body should contain a closing keyword for the root and every included open sub-issue completed by the run, allowing GitHub to close them only when the human-approved pull request is merged.

### Incorrect project verification

The generated prompts run `npm run typecheck` and `npm run test`. Parames is a Python project managed with `uv`.

The workflow must use project-specific verification with `PARAMES_DEV_MODE=true`, including at minimum:

```bash
PARAMES_DEV_MODE=true uv sync
PARAMES_DEV_MODE=true uv run pytest
```

Features involving the web UI must also use the repository's Playwright skill and run the API locally on port `7000`.


## Issue authorization and state model

### Trigger policy

An issue must not be processed merely because it exists or has a generic `enhancement` label. A trusted maintainer must explicitly authorize it.

Required intake labels for a root issue:

- `Sandcastle`
- `sandcastle:queued`

Only trusted maintainers should have permission to add the `Sandcastle` label. Authorizing a root issue implicitly authorizes its existing GitHub sub-issues for the same run; sub-issues do not require Sandcastle labels of their own. Unrelated issues are not included.

### State labels

Use the following state labels:

- `sandcastle:queued` — authorized and waiting
- `sandcastle:in-progress` — claimed by a runner
- `sandcastle:blocked` — requires human clarification or has an open external dependency
- `sandcastle:pr-ready` — implementation completed and a PR awaits review
- `sandcastle:failed` — automation failed and requires inspection or retry

The permanent `Sandcastle` authorization label remains present throughout processing. Workflow state labels are applied only to the root issue; included sub-issues do not receive Sandcastle state labels.

### One root issue per pull request

A root issue is an authorized queued issue selected as the top-level unit of work for a run, even when that issue itself has a GitHub parent. In that case, only the selected issue's descendant subtree is included; its ancestors are context rather than work items. Each orchestration run processes one root issue and its included sub-issues into one pull request. Multiple unrelated queued root issues must not be combined into one PR.

Every included issue in the root's full recursive sub-issue hierarchy is treated as an existing atomic work item rather than being decomposed into newly created issues. The orchestrator refreshes the recursive hierarchy before every dependency wave, before final review, and immediately before marking the pull request ready, automatically adding newly discovered sub-issues to the run. Scope freezes when the pull request is marked ready; later additions require human action or a follow-up run. If an issue is removed before work starts, it is dropped from the run. If work on it has started or been merged, removal blocks the run for maintainer direction; the orchestrator never reverts or discards that work automatically. At each refresh, changed requirements or dependency metadata are re-planned for pending issues. A semantic change to an issue that is running, completed, or merged blocks the run for maintainer review; clearly non-semantic edits may be accepted without reopening work. Closed descendants remain available as planning context but are not scheduled. Dependencies may connect issues at any level of that hierarchy. The dependency graph combines explicit GitHub dependency metadata or references with technical ordering inferred by the planner; explicit edges are authoritative, and inferred edges may add constraints for required APIs, decisions, or conflicting changes. Within one authorized root run, Sandcastle may satisfy a dependency by implementing, verifying, and integrating the prerequisite issue into the root issue branch. An issue outside the selected root hierarchy is never included implicitly and satisfies a dependency only when GitHub reports it closed; code or an unmerged PR alone is insufficient. An open external dependency blocks the run. The root commonly supplies user stories and overall acceptance criteria while its sub-issues carry most implementation work. Only the selected root may be tracking-only. The planner records whether the root has requirements not covered by descendants; if not, it receives final acceptance validation but no dedicated implementation assignment. Every included open descendant is an atomic implementation issue, even when it has descendants of its own. Final feature review may still apply and commit integration fixes or refactoring directly on the root issue branch.

The runner evaluates queued roots in age order. A candidate with an open dependency outside its selected hierarchy is moved to `sandcastle:blocked`, receives a comment identifying the dependency, and is skipped so another eligible root can run. Reconciliation automatically returns it to `sandcastle:queued` when all external dependencies are closed. Priority labels may be introduced later.

### Claiming

The host orchestrator must claim an issue before planning:

1. Confirm it has `Sandcastle` and `sandcastle:queued`.
2. Remove `sandcastle:queued`.
3. Add `sandcastle:in-progress`.
4. Add an issue comment identifying the automation run and start time.

The runner must use a host process lock so only one process can claim work for a repository at a time.

## Branch model

For root issue `#42` with sub-issues `#43`, `#44`, and `#45`, use deterministic branch names based on GitHub issue numbers:

```text
main
└── sandcastle/issue-42
    ├── sandcastle/issue-43
    ├── sandcastle/issue-44
    └── sandcastle/issue-45
```

### Root issue branch

The branch `sandcastle/issue-<root-issue-number>` is the run's integration branch and the only branch pushed as the pull request head. It starts from the current `origin/main` when processing begins.

Sub-issue branches are merged into the root issue branch, never directly into `main`.

### Sub-issue branches

Each included open sub-issue uses `sandcastle/issue-<issue-number>`. Existing GitHub issue numbers provide stable identifiers across retries; the planner does not invent task IDs or branch names.

A sub-issue branch is created from the latest root issue branch after all of its dependencies have been merged. Independent issues in the same dependency wave share the same integration base and may run concurrently. Sub-issue branches are pushed after successful implementation and review checkpoints for crash recovery, but they never receive their own pull requests. Deletion requires a separate explicit cleanup policy.

If the root has implementation requirements not covered by sub-issues, root-specific implementation is represented as a node in the dependency graph and runs directly on the root issue branch. Because that branch is also the integration target, root-specific implementation runs exclusively between dependency waves and never concurrently with sub-issue work. Its graph dependencies determine whether it runs before, between, or after sub-issues.

### Final pull request

The final relationship is:

```text
sandcastle/issue-42 -> main
```

Immediately after claiming the root issue, the orchestrator creates and pushes its root issue branch, then finds or creates exactly one draft PR against `main`. It updates that PR throughout the run and marks it ready only after final review and deterministic verification succeed.

## End-to-end workflow

### Phase 0: Host preparation

Before selecting an issue, the host orchestrator must:

1. Acquire an exclusive repository lock.
2. Verify that the automation checkout has no unexpected uncommitted changes.
3. Fetch `origin` and prune deleted references.
4. Check out `main`.
5. Fast-forward to `origin/main` using `git pull --ff-only` or equivalent.
6. Verify Docker and required credentials are available.
7. Reconcile any previously interrupted in-progress issue before claiming new work.

The automation must stop rather than reset or discard unexpected local changes.

### Phase 1: Intake and claim

1. Query GitHub for issues labeled `Sandcastle` and `sandcastle:queued`.
2. Select one root issue according to the queue policy.
3. Claim it using the state transition described above.
4. Create or resume `sandcastle/feature-<issue-number>`.
5. Find or create the corresponding draft PR, if early PR creation is enabled.

### Phase 2: Feature planning

The planner receives:

- Root issue number, title, body, and maintainer comments
- The full ancestor chain as read-only context when the selected root has a GitHub parent, clearly marked as outside run scope
- Relevant repository instructions and specifications
- Current repository tree and recent commits
- Project test and tooling constraints
- The current base commit

It produces structured output validated by a schema.

An example output is:

```json
{
  "summary": "Add configurable wind-alert quiet hours",
  "tasks": [
    {
      "id": "models",
      "title": "Add quiet-hours settings",
      "branch": "sandcastle/feature-42/task-models",
      "dependsOn": [],
      "acceptanceCriteria": [
        "Quiet hours can be configured per alert"
      ],
      "verification": [
        "Run focused settings tests"
      ],
      "browserVerification": false
    },
    {
      "id": "scheduler",
      "title": "Enforce quiet hours when sending alerts",
      "branch": "sandcastle/feature-42/task-scheduler",
      "dependsOn": ["models"],
      "acceptanceCriteria": [
        "Alerts are suppressed during configured quiet hours"
      ],
      "verification": [
        "Run scheduler and notification tests"
      ],
      "browserVerification": false
    }
  ]
}
```

If the dependency graph contains a cycle, including one created by inferred edges, the runner starts no implementation, marks the root `sandcastle:blocked`, and comments with the exact cycle so a maintainer can correct the dependencies or requirements.

The schema must include at least:

- Feature summary
- Task ID
- Task title
- Deterministic branch name
- Dependency task IDs
- Acceptance criteria
- Verification requirements
- Whether browser verification is needed

Planner constraints:

1. Do not create tasks only to maximize parallelism.
2. Produce one task when the feature is small or tightly coupled.
3. Avoid task boundaries that require concurrent edits to the same central files.
4. Ensure the task graph is acyclic.
5. Ensure all root issue acceptance criteria are assigned to one or more tasks.
6. Do not modify GitHub state from the planner.

### Phase 3: Dependency-wave scheduling

The orchestrator evaluates the task DAG and runs tasks in waves.

A task is runnable when all task IDs in `dependsOn` have been successfully merged into the feature integration branch.

For each wave:

1. Create each task branch from the current feature integration branch.
2. Create an isolated Sandcastle worktree and Docker sandbox.
3. Run up to the configured concurrency limit.
4. Preserve failed task branches and worktrees for diagnosis.
5. Do not begin dependent tasks until required branches are verified and merged.

### Phase 4: Task implementation

Each implementer receives only:

- The root issue context
- Its assigned task
- Its acceptance criteria
- Its dependency context
- Relevant project instructions
- The source and target branch names

The implementer must:

1. Work only on the assigned task.
2. Inspect relevant implementation and test files.
3. Follow `AGENTS.md` and repository skills.
4. Use test-driven development where appropriate.
5. Run focused tests during implementation.
6. Keep secrets out of source, test fixtures, output, and commits.
7. Create one or more conventional commits.
8. Emit `<promise>COMPLETE</promise>` only after meeting its acceptance criteria.
9. Report blockers instead of inventing requirements.

The implementer must not:

- Merge branches
- Push to `main`
- Create or merge the final PR
- Close the root issue
- Change labels
- Work on another task

### Phase 5: Per-task review

If the implementer produced commits, a reviewer runs in the same reusable sandbox and on the same task branch.

The reviewer compares the task branch against its feature integration base and checks:

1. Compliance with the assigned acceptance criteria
2. Correctness and edge cases
3. Test quality and missing coverage
4. Scope discipline
5. Security issues and credential exposure
6. Project conventions and architecture
7. Maintainability and unnecessary complexity
8. Compatibility with dependent or sibling tasks

The reviewer may fix issues directly and commit corrections using conventional commits.

If the implementation is incorrect or incomplete and cannot be safely repaired, the reviewer must fail the task rather than emit completion.

### Phase 6: Deterministic task verification

After agent implementation and review, the orchestrator runs verification commands itself and checks exit codes.

The baseline task gate is:

```bash
PARAMES_DEV_MODE=true uv sync
PARAMES_DEV_MODE=true uv run pytest
```

During early development, focused tests may be run before the complete suite, but a complete suite is required before final PR readiness.

For frontend features:

1. Start the API using:

   ```bash
   PARAMES_DEV_MODE=true uv run uvicorn parames.api:app --host 0.0.0.0 --port 7000
   ```

2. Use the repository's Playwright skill to verify the behavior in a browser.
3. Save relevant browser-test artifacts with the run logs.
4. Stop the API cleanly after verification.

A task may be merged only if required verification commands return zero.

### Phase 7: Issue integration

After a sub-issue passes review and deterministic verification:

1. Merge the sub-issue branch with `--no-ff` and a conventional integration commit such as `chore(sandcastle): integrate issue #43`.
2. Preserve its implementation and review commits rather than squashing.
3. Record the merged issue and commit SHA in run state.
4. Push the updated root issue branch so the draft PR reflects progress.
5. Add one concise comment to the integrated sub-issue linking the root draft PR and naming the integrated commit; do not close it.
6. Refresh the hierarchy and recompute newly unblocked issues.

If merge conflicts occur, run a dedicated integration agent in a sandbox on the feature branch. It receives:

- Conflicting branch names
- Task descriptions
- Conflict details
- Root issue acceptance criteria

The integration agent must resolve conflicts, run relevant tests, and create a conventional conflict-resolution commit when needed.

The orchestrator must then rerun deterministic verification.

### Phase 8: Final feature review

After all included issue work is integrated, fetch `origin/main` and merge its latest tip into the root issue branch with a normal merge commit. Never rebase or force-push. A dedicated integration agent resolves conflicts, and deterministic verification must pass after the merge.

Then run a final reviewer against:

```bash
git diff origin/main...sandcastle/feature-<issue-number>
```

The final reviewer checks:

1. Every root issue acceptance criterion is satisfied.
2. Task implementations work together coherently.
3. No task output was lost or contradicted during integration.
4. Full test coverage is adequate.
5. No unrelated changes are present.
6. Documentation and configuration changes are included where needed.
7. Security and secret handling are acceptable.
8. Deployment changes are internally consistent.
9. Versioning requirements are satisfied if the feature is intended to include a version bump.

The final reviewer may make and commit corrections on the feature branch.

### Phase 9: Final verification

Run the complete deterministic verification suite after final review.

At minimum:

```bash
PARAMES_DEV_MODE=true uv sync
PARAMES_DEV_MODE=true uv run pytest
```

Additional project checks should be added as the repository adopts formatting, linting, static typing, frontend testing, or deployment validation tools.

No PR may be marked ready when any required verification command fails.

### Phase 10: Push and pull request

After final verification succeeds, the host orchestrator must:

1. Push `sandcastle/feature-<issue-number>` to `origin`.
2. Find or create a PR targeting `main`.
3. Update the PR title and body with the final result.
4. Mark the PR ready for review if it was created as a draft.
5. Replace `sandcastle:in-progress` with `sandcastle:pr-ready`.
6. Comment on the issue with the PR URL.

The PR body must include:

- `Closes #<issue-number>`
- Feature summary
- Implemented task summary
- Important design decisions
- Tests and browser checks run
- Known limitations or follow-up work
- A reference to Sandcastle logs or run ID where appropriate

The automation must not merge the PR.

### Phase 11: Human approval

A maintainer reviews the pull request, requests changes if needed, and manually approves and merges it.

GitHub closes the root issue through the `Closes #<issue-number>` directive only after the PR is merged.

## Failure handling

### Task failure

When an implementation, review, sandbox, or verification step fails:

1. Preserve the failed sub-issue branch.
2. Finish deterministic verification and integration for successful siblings already running in the same wave.
3. Preserve all branches and any dirty worktree Sandcastle reports.
4. Save logs and session IDs.
5. Stop scheduling new work after the current wave, including otherwise independent work.
6. Mark the root issue `sandcastle:failed` or `sandcastle:blocked` as appropriate.
6. Add a concise issue comment with the failing phase and recovery instructions.
7. Do not close the issue or merge incomplete work into `main`.

Independent completed task branches may remain merged into the feature branch if doing so is safe and recorded. A retry must continue from the recorded state.

### Human clarification

If an existing issue is ambiguous, contradictory, or not atomic enough to implement safely, the planner or implementer must stop rather than guess, split it, or create new issues.

The runner changes the root issue state to `sandcastle:blocked` and asks a focused question in a comment on the specific issue that needs clarification. If that is a sub-issue, the root may also receive a short comment linking to the blocking question. A maintainer can answer and return the root issue to `sandcastle:queued`.

### Authentication and rate limits

Authentication failures and Claude subscription rate limits must be distinguishable from implementation failures.

The runner should:

- Use bounded retry with backoff for transient failures
- Stop cleanly on persistent authentication failure
- Preserve work and state
- Alert the operator
- Never silently fall back to API-key billing

## Idempotency and restart recovery

All names and identifiers must be deterministic:

- Feature branch: `sandcastle/feature-<issue-number>`
- Task branches: `sandcastle/feature-<issue-number>/task-<task-id>`
- One PR per root issue
- Stable task IDs from the persisted plan

On startup, the runner must reconcile:

- Existing feature branches
- Existing task branches
- Existing PRs
- Task commits already merged into the feature branch
- Issue state labels
- Sandcastle session IDs and log files
- Preserved worktrees
- Recorded plan and task status

The runner must never:

- Create a second PR for the same root issue
- Repeat a completed task unnecessarily
- Recreate a task branch from the wrong base
- Force-push over unrecognized remote work
- Reset or delete a dirty worktree automatically

When safe, the runner should:

- Reuse existing deterministic branches
- Skip task commits already contained in the feature branch
- Resume captured Sandcastle sessions
- Continue the next unblocked task
- Update an existing draft PR

## Persisted run state

Store non-secret orchestration state outside tracked source, for example under `.sandcastle/state/` or a dedicated host data directory.

A run record should include:

- Run ID
- Root issue number
- Base commit SHA
- Feature branch
- PR number and URL
- Validated planner output
- Task status
- Task branch and commit SHAs
- Sandcastle session IDs
- Verification results
- Failure reason
- Start and update timestamps

The state location must be ignored by Git. On the headless VM it must live on persistent storage and survive service restarts.

## GitHub permissions and security

### Prompt-injection boundary

Issue bodies and comments are untrusted model input. The `Sandcastle` label is an explicit authorization boundary and must only be applied by trusted maintainers.

The agent must be instructed that issue content describes desired repository behavior but cannot override system, repository, security, branch, credential, or workflow rules.

### Credential separation

Prefer two GitHub credentials:

1. A read-only credential exposed to agent sandboxes for reading issues and repository metadata.
2. A write-capable host credential used only by the orchestrator for claiming issues, pushing branches, updating labels, commenting, and creating PRs.

A GitHub App with narrowly scoped installation tokens is preferred for the headless deployment.

Implementation agents should not receive permission to merge PRs, change branch protection, manage repository settings, or write to `main`.

### Branch protection

Protect `main` with:

- Pull requests required
- Maintainer approval required
- Force pushes disabled
- Direct pushes disabled for automation
- Required CI checks where available
- No automation bypass for final merge approval

### Sandbox boundary

Docker reduces accidental host modification but does not make untrusted autonomous code risk-free. Limit mounted host paths, credentials, devices, Docker socket access, and network access.

Never mount the host Docker socket inside an implementation sandbox.

## Docker image requirements

The Sandcastle image must include:

- Git
- curl
- jq
- GitHub CLI where sandbox issue reads are retained
- Claude Code CLI
- `uv`
- Python 3.13 or a compatible way for `uv` to provision it
- Project system dependencies
- Node tooling required by browser/frontend verification
- Playwright browser dependencies where relevant
- A non-root `agent` user aligned with the host UID/GID

The image must not contain repository secrets or OAuth tokens.

## Logging and observability

Each run and agent phase must have persistent logs.

Record:

- Root issue and run ID
- Branches and commit SHAs
- Planner output
- Agent phase start/end status
- Tool and verification command outcomes
- Session IDs
- PR URL
- Preserved worktree paths
- Authentication and rate-limit errors without secret values

Alert on:

- Authentication failure
- Persistent Claude rate limiting
- Planner schema failure
- Agent idle timeout
- Failed deterministic verification
- Merge conflict failure
- Preserved dirty worktrees
- Push or PR creation failure
- Issues labeled `sandcastle:failed`

Secrets must be redacted from logs.

## Scheduling

### Local development

Initially invoke the runner manually with an explicit issue number. Add polling only after the workflow can reliably produce a draft PR.

### Headless VM

Use a `systemd` oneshot service and timer.

The service must:

- Run as a dedicated `sandcastle` Unix user
- Acquire an exclusive `flock`
- Use a predictable `HOME`
- Load credentials from a secret manager or systemd credentials
- Set a maximum runtime
- Preserve logs and orchestration state
- Exit nonzero on an operational failure

The timer should initially poll every 10 to 15 minutes. It may poll more frequently after reliability is established.

A webhook receiver is not required for the first version. Polling is simpler, easier to secure, and sufficient for issue-driven unattended work.

## Local rollout plan

### Stage 1: Prepare and commit Sandcastle configuration

1. Review generated `.sandcastle` files.
2. Switch the Docker image from Pi to Claude Code.
3. Switch all Sandcastle agents to `claudeCode()`.
4. Add `uv`, Python, and project dependencies to the image.
5. Replace npm verification commands with Parames commands.
6. Replace `RALPH:` commit instructions with conventional commits.
7. Fill in `.sandcastle/CODING_STANDARDS.md`.
8. Ensure secrets, `.sandcastle/.env`, logs, worktrees, and state are ignored.
9. Commit the Sandcastle setup so worktrees contain required resources.

Acceptance criteria:

- The Docker image builds locally.
- Claude Code responds non-interactively through the Pro subscription token.
- A sandbox can run `PARAMES_DEV_MODE=true uv run pytest`.

### Stage 2: Single-task smoke test

Create a small, low-risk issue such as a documentation change or isolated test improvement.

Run manually with:

- Explicit issue number
- One generated task
- Concurrency one
- No automatic PR creation initially

Inspect:

- Planner output
- Worktree isolation
- Agent commits
- Review corrections
- Verification logs
- Final feature branch diff

Acceptance criteria:

- `main` remains unchanged.
- The task branch contains only intended changes.
- Verification succeeds.
- Logs and session data are captured.

### Stage 3: Pull request delivery test

Enable:

- Feature integration branch creation
- Branch push
- Draft PR creation
- `Closes #<issue-number>` in the PR body
- Issue state transition to `sandcastle:pr-ready`

Acceptance criteria:

- Exactly one PR is created.
- The PR targets `main`.
- The issue remains open before merge.
- The automation cannot merge the PR.
- The issue closes only after a maintainer merges the PR.

### Stage 4: Parallel feature test

Create a feature request with two naturally independent workstreams.

Acceptance criteria:

- The planner creates a valid task DAG.
- Independent tasks run in separate worktrees.
- Concurrent tasks do not interfere with each other.
- Both tasks are reviewed and verified.
- Both are integrated into one feature branch.
- One final PR contains the complete feature.

### Stage 5: Dependency-wave test

Create a feature with at least one task dependent on another.

Acceptance criteria:

- The dependent task does not start early.
- It branches from a feature branch containing its dependencies.
- Final verification exercises the integrated behavior.

### Stage 6: Recovery test

Terminate the runner during implementation and restart it.

Acceptance criteria:

- No duplicate PR is created.
- Existing branches are reused safely.
- Completed tasks are not repeated.
- The persisted plan remains stable.
- Work resumes from the correct phase.
- Issue labels remain coherent.

### Stage 7: Local polling test

Run a local scheduled poller for several days.

Acceptance criteria:

- It does nothing when no authorized issue exists.
- It processes only explicitly authorized issues.
- The repository lock prevents overlapping runs.
- Operational failures are visible and recoverable.

## Headless VM rollout plan

1. Provision a dedicated `sandcastle` Unix user.
2. Install Docker, Git, Node.js, GitHub CLI, and required host tooling.
3. Clone a dedicated automation checkout.
4. Configure Git author identity for automation commits.
5. Install the Claude Code OAuth token through a secret manager or systemd credentials.
6. Install narrowly scoped GitHub credentials.
7. Build and smoke-test the Sandcastle Docker image.
8. Copy or initialize persistent orchestration state and log directories.
9. Install the `systemd` oneshot service with locking and runtime limits.
10. Install the polling timer.
11. Run one explicitly selected issue manually on the VM.
12. Enable the timer only after the manual VM run succeeds.
13. Configure alerts for operational and workflow failures.
14. Keep final PR review and merge manual.

## Acceptance criteria

The feature is complete when all of the following are demonstrated:

1. A maintainer creates a GitHub feature request.
2. The maintainer adds `Sandcastle` and `sandcastle:queued`.
3. The unattended runner claims exactly one issue.
4. The planner produces a validated task graph.
5. Independent tasks can run concurrently in isolated sandboxes.
6. Dependent tasks wait for their dependencies.
7. Every task receives implementation, review, and deterministic verification.
8. Task branches are merged only into the feature integration branch.
9. `main` is never directly changed by Sandcastle.
10. Full final verification passes.
11. Exactly one PR is created against `main`.
12. The PR includes `Closes #<issue-number>` and verification details.
13. The issue remains open while the PR awaits review.
14. Sandcastle cannot merge the final PR.
15. A maintainer can review and manually merge the PR.
16. GitHub closes the issue after the PR is merged.
17. Restarting an interrupted run does not duplicate work or PRs.
18. Secrets do not appear in Git, Docker images, or logs.

## Recommended first milestone

Implement the smallest complete delivery path before adding parallel decomposition:

```text
One authorized issue
→ one planned task
→ one isolated implementation branch
→ one reviewer
→ deterministic tests
→ one feature branch
→ one draft PR
→ human review and merge
```

After this path is reliable, add planner-generated task DAGs, dependency waves, and parallel fan-out.
