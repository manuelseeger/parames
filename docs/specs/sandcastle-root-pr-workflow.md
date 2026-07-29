# Sandcastle root-PR workflow implementation plan

## Goal

Adapt the installed `parallel-planner-with-review` template into a minimal Python/Vite-capable workflow where every root issue owns a published aggregation branch and draft PR. Dependent issue branches are implemented separately and merged into that root branch. Keep Sandcastle-native behavior such as Markdown `!` command expansion; do not reimplement it.

## Scope and terminology

- Only open issues with the `sandcastle` (now lowercase) label are executable graph nodes.
- A **root issue** is a top-level deliverable that is not a dependency/sub-issue of another executable issue.
- A standalone issue is a root with no dependents.
- A **dependent issue** belongs to exactly one root.
- Formal GitHub parents without the `sandcastle` label provide context only.
- Re-plan after every merge round, as the template currently does.
- Assume one serialized invocation against a persistent local/VM checkout.

## Decisions

### Dependency planning

- The planner reasons over the complete currently open labeled issue set, but returns only issues ready in this round.
- Each returned issue includes its root ID/title. Branch names are not agent decisions.
- TypeScript derives every branch as `sandcastle/issue-{id}`.
- A parent is blocked by its sub-issues. Inferred code/API dependencies and likely conflicting work also establish ordering.
- The graph must be a forest. Cycles and dependencies shared by multiple roots are reported as planner errors and skipped; unrelated valid roots continue.
- Planner input includes issue title, body, labels, comments, and immediate formal parent metadata, fetched deterministically with GitHub GraphQL inside Markdown `!` expansion.

Proposed schema:

```ts
const planSchema = z.object({
  issues: z.array(z.object({
    id: z.string().regex(/^\d+$/),
    title: z.string(),
    rootId: z.string().regex(/^\d+$/),
    rootTitle: z.string(),
  })),
  errors: z.array(z.object({
    issueIds: z.array(z.string().regex(/^\d+$/)),
    message: z.string(),
  })),
});
```

### Branches and PRs

- Use `SANDCASTLE_BASE_BRANCH` when set; otherwise detect the repository default branch from GitHub and use `origin/<base>`. Never derive the base from the host's checked-out branch.
- Root and dependent branches both use `sandcastle/issue-{id}`.
- New dependent branches start from the latest local root branch tip. Existing dependent branches are reused unchanged; do not merge newer root changes into them before retrying.
- Dependent branches remain local. Keep merged local branches; clean worktrees may still be removed by Sandcastle.
- Root branches are remotely published. Existing local/remote roots are synchronized only by safe fast-forward; never force-push. Stop only the affected root on divergence.
- To create an immediate draft PR when root equals the default branch, add exactly one deterministic empty commit:
  - Message: `chore: initialize Sandcastle work for #<id>`
  - Author: `Sandcastle <sandcastle@users.noreply.github.com>` using command-scoped Git config.
- Root initialization is idempotent: reuse existing branches and open PRs and never add duplicate initialization commits.
- Draft PR:
  - Base: detected default branch
  - Head: root branch
  - Title: `#<id>: <root title>`
  - Body: short generated notice and `Closes #<id>`
- If an existing PR lacks the exact closure line, append it without replacing human content.
- Existing PR states:
  - Open draft: reuse.
  - Open ready: reuse and never turn back into draft.
  - Closed unmerged: stop that root for manual intervention.
  - Merged: treat as finished.
- If root publication or PR creation fails, skip that root for the round; unrelated roots continue.

All branch publication and PR lifecycle actions belong in TypeScript orchestration, not agent prompts.

### Agent completion and review

- Implementer and reviewer both receive deterministic current-issue and immediate-formal-parent context through Markdown `!` expansion. Include title, body, labels, and comments.
- Agents discover coding/testing policy from repository context (`AGENTS.md`, repository docs) and issue/parent context. Do not hard-code generic npm test commands or `PARAMES_DEV_MODE` in orchestration.
- Configure both runs with `completionSignal: "<promise>COMPLETE</promise>"`.
- An issue may proceed only when both implementer and reviewer explicitly complete.
- Review even if the latest implementer run produced no new commit; retries may already contain valid work.
- A no-diff issue may be accepted as already satisfied when both agents complete.
- Reviewer diff target:
  - Dependent: root branch vs dependent branch.
  - Root: remote default branch vs complete root branch.
- For incomplete work, preserve branch state and leave the issue open. Existing prompt behavior allowing an issue comment should remain.

### Merging and issue lifecycle

- Group completed dependents by root.
- Run one merger sandbox/agent per root, with different roots in parallel.
- The merger works directly on the root branch and processes that root's dependent branches sequentially.
- Use normal `git merge <branch> --no-edit`; allow fast-forwards and natural merge commits. Do not force `--no-ff`, squash, or add a synthetic summary commit.
- If an individual merge cannot be resolved, abort that merge, restore a clean root, and continue where safe.
- Merger receives root/dependent issue and immediate-parent context so it can choose relevant validation.
- Configure merger completion signal. Only publish a batch when the merger outputs `COMPLETE` and its root worktree is clean.
- Mechanically verify each dependent branch tip is an ancestor of the root tip. This decides which branches actually merged and allows partial batch success.
- Push the root before closing any dependent issue. A push failure blocks closure.
- After a successful push, orchestration posts a root PR progress comment listing issues merged in that round. Duplicate comments on retries are acceptable for the MVP; comment failure does not block closure.
- Close each verified merged dependent with:

  `Completed by Sandcastle and merged into root PR #<pr-number>.`

- Closing dependencies allows the next planner round to discover newly unblocked work.
- Once the planner returns the root itself as ready, run implementer/reviewer directly on the root branch. This covers acceptance criteria not implemented by its dependents.
- After root completion, push it, mark its PR ready with `gh pr ready`, and remove the root issue's `sandcastle` label. Do not directly close the root issue; `Closes #<root>` in the PR body closes it when the PR merges.
- If a completion run crashes after making the PR ready but before label removal, occasional repeated agent work is acceptable for the MVP.
- New dependencies added after readiness require manual reactivation: add `sandcastle` back to the root and label the new dependent. Reuse the ready PR without reverting it to draft.

### Iteration and scheduling behavior

- Preserve `Promise.allSettled` behavior: failed issue/root pipelines do not cancel unrelated roots.
- Continue iterative planning after rounds that make progress.
- Stop cleanly after a no-progress round or `MAX_ITERATIONS`.
- Leave unfinished root PRs as drafts and print a concise unfinished/error summary. A later scheduled invocation resumes from local branches, remote roots, PRs, and issue state.
- Local and eventual VM execution are assumed to use persistent storage.

### Sandbox environment

Sandcastle uses the Docker Sandboxes template in `.sandcastle/Dockerfile.sbx` for every phase. The template provides a private Docker daemon and the agent toolchain:

- Node 22, Git, curl, jq, GitHub CLI, and Claude Code
- `uv` with Python 3.13
- Aspire and its cached NuGet closure
- No repository source, host worktree, host Docker socket, or long-lived secrets

Use hooks appropriate to each phase:

- Planner: no project dependency install.
- Implement/reviewer/merger sandbox creation: `uv sync --locked`, `npm ci --prefix webapp`, `npm ci --prefix aspire`, and `aspire restore --non-interactive`.
- Implementer and reviewer share one castle, so dependencies install once for that pipeline.
- Root `node_modules` remain host-side Sandcastle orchestration dependencies, not application dependencies.

## Manual steps for the owner

> [!IMPORTANT]
> These steps require the repository owner and must not be guessed or silently performed by the coding agent.

1. **Grant the fine-grained `GH_TOKEN` these repository permissions:**
   - Metadata: read
   - Contents: read/write
   - Issues: read/write
   - Pull requests: read/write
2. Put `GH_TOKEN` and either `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` in `.sandcastle/.env`. Never commit this file.
3. Ensure the `sandcastle` issue label exists.
4. Build and load the microVM template after `Dockerfile.sbx` changes:

   ```bash
   docker build -f .sandcastle/Dockerfile.sbx -t parames-sbx:dev .
   docker image save parames-sbx:dev -o /tmp/parames-sbx-dev.tar
   sbx template load /tmp/parames-sbx-dev.tar
   sbx diagnose
   ```

5. Before the first real backlog run, create or select a small labeled test forest and confirm the inferred root/dependency relationships. Then run:

   ```bash
   npm run sandcastle
   ```

6. Ensure future scheduling never overlaps runs. MVP relies on scheduler serialization rather than an orchestration lock.
7. When late work must re-enter a ready root PR, manually re-add the `sandcastle` label to the root and label the new dependent.

## Proposed implementation sequence

1. **MicroVM template**
   - Build and load `.sandcastle/Dockerfile.sbx` with Python 3.13/`uv`, Aspire, and the agent toolchain.
   - Preserve GitHub CLI, Claude Code, the non-root agent user, and the private Docker daemon.
   - Transfer Git state through the isolated-provider contract and use runtime hooks for project dependencies.
2. **Deterministic prompt context**
   - Add GraphQL `!` expansions for planner issue/parent input.
   - Add current issue/immediate parent expansions to implement, review, and merge prompts.
   - Do not create a custom prompt preprocessor.
3. **Planner contract**
   - Change schema to ready issues with root metadata plus graph errors.
   - Rewrite only the dependency/root/output portions of `plan-prompt.md`.
   - Log errors and continue valid roots.
4. **Git/GitHub orchestration helpers**
   - Detect/fetch default branch.
   - Derive branch names.
   - Safely initialize/synchronize/push root branches.
   - Idempotently create/reuse draft PRs and ensure closure text.
   - Return the root PR number/state to later lifecycle steps.
5. **Issue execution pipeline**
   - Create dependent branches from root and root sandboxes on root itself.
   - Pass `TASK_ID`, titles, root IDs, branch, and review target.
   - Gate on implementer and reviewer completion signals rather than latest-run commit count.
6. **Per-root merger pipeline**
   - Group completed dependents by root and run mergers in parallel across roots.
   - Gate on merger completion and clean state.
   - Verify ancestry, push successful root updates, post progress comments, and close only verified dependents.
7. **Root completion**
   - Detect ready root entries, implement/review directly on root, push, mark PR ready, and remove the label.
8. **Resumability and summaries**
   - Reuse branches/PRs, stop on no progress, and replace misleading unconditional `All done` output with completed/unfinished/error summaries.
9. **Verification**
   - Build and load the microVM template, then run `sbx diagnose`.
   - Smoke-check `python --version`, `uv --version`, `node --version`, `gh --version`, `aspire --version`, and the private Docker daemon.
   - Run one standalone test issue and one two-level root/dependent test forest.
   - Confirm draft creation, dependency merge/push/comment/closure, root implementation, PR readiness, and label removal.
   - Rerun to verify branches/PRs are reused without duplicate initialization commits.

## Proposed agent prompts

The exact GraphQL shell can be factored into readable `gh api graphql` expressions inside each Markdown `!` block. Do not move expansion into TypeScript. Keep context bounded to 100 labeled issues/comments, matching the current template limit.

### `plan-prompt.md`

```md
# ISSUES

Here are the open issues labeled `sandcastle`, including immediate formal parent metadata:

<issues-json>

!`<gh GraphQL query for the current repository: first 100 OPEN issues with label sandcastle; return number, title, body, labels, first 100 comments, and immediate parent number/title/body>`

</issues-json>

The list is the complete executable scope. Unlabeled parents are context only.

# TASK

Analyze the issues and build a dependency graph.

Issue B is blocked by issue A when:

- A is a formal sub-issue of B and both are executable issues
- B requires code or infrastructure introduced by A
- A and B would modify overlapping files/modules and concurrent work is likely to conflict
- B depends on a decision or API shape established by A

A root issue is a top-level deliverable that is not a dependency or sub-issue of another executable issue. A standalone issue is its own root.

The graph must be a forest: every issue belongs to exactly one root. If a component contains a cycle or a dependency shared by multiple roots, report that component as an error and do not schedule it. Continue scheduling unrelated valid components.

An issue is ready when it has no blocking dependency among the currently open executable issues. Re-evaluate this on every planner run.

For each ready issue, return its ID/title and its root ID/title. Do not choose branch names; orchestration derives them.

# OUTPUT

Always output JSON inside `<plan>` tags:

<plan>
{
  "issues": [
    {"id": "42", "title": "Fix auth", "rootId": "40", "rootTitle": "Add accounts"}
  ],
  "errors": [
    {"issueIds": ["50", "51"], "message": "Dependency cycle: #50 -> #51 -> #50"}
  ]
}
</plan>

Use empty arrays when there is no ready work or no errors.
```

### `implement-prompt.md`

```md
# TASK

Fix issue {{TASK_ID}}: {{ISSUE_TITLE}}

Only work on this issue. Work on branch {{BRANCH}} and make conventional commits.

# ISSUE CONTEXT

The following context is expanded deterministically from GitHub. It contains the issue and its immediate formal parent, when present:

<issue-context>

!`<gh GraphQL query for issue {{TASK_ID}} returning title, body, labels, comments, and immediate parent title/body/labels/comments>`

</issue-context>

# CONTEXT

Root issue: #{{ROOT_ID}} — {{ROOT_TITLE}}
Root branch: {{ROOT_BRANCH}}

Here are the last 10 commits:

<recent-commits>

!`git log -n 10 --format="%H%n%ad%n%B---" --date=short`

</recent-commits>

# EXPLORATION

Explore the repository and relevant tests before changing code. Follow repository instructions, including AGENTS.md and testing documentation. Issue or parent context may specify additional verification.

# EXECUTION

If applicable, use red-green-refactor:

1. RED: write one test
2. GREEN: implement enough to pass
3. Repeat until done
4. Refactor

Choose and run verification appropriate to the issue and repository instructions.

# COMMIT

Make conventional commits. Keep messages concise and include useful task/decision context in the commit body when needed.

# INCOMPLETE WORK

If the task is incomplete, preserve progress and leave a useful issue comment. Do not close the issue and do not output the completion promise.

Only when the issue is semantically complete, output:

<promise>COMPLETE</promise>

# FINAL RULE

ONLY WORK ON THIS SINGLE ISSUE.
```

### `review-prompt.md`

```md
# TASK

Review issue {{TASK_ID}}: {{ISSUE_TITLE}} on branch `{{BRANCH}}`.

# ISSUE CONTEXT

<issue-context>

!`<same deterministic current-issue and immediate-parent GraphQL expansion used by implementer>`

</issue-context>

# CHANGE CONTEXT

## Diff

!`git diff {{TARGET_BRANCH}}...{{BRANCH}}`

## Commits

!`git log {{TARGET_BRANCH}}..{{BRANCH}} --oneline`

# REVIEW PROCESS

1. Understand the issue, parent guidance, diff, and commits.
2. Check correctness, acceptance criteria, edge cases, security, and relevant test coverage.
3. Improve clarity, consistency, and maintainability without unnecessary abstraction.
4. Follow repository instructions and choose issue-appropriate verification.
5. If fixes are needed and can be completed, apply and conventionally commit them.

Do not approve merely because the branch has commits. A no-diff issue may be complete if the target branch already satisfies it.

If the issue cannot be validated as complete, do not output the completion promise. Preserve useful progress and leave a useful issue comment when appropriate.

Only when review is complete and the issue is satisfied, output:

<promise>COMPLETE</promise>
```

### `merge-prompt.md`

```md
# TASK

Merge these dependent branches into root branch `{{ROOT_BRANCH}}`:

{{BRANCHES}}

The sandbox is already on the root branch. Only integrate the listed branches; do not push branches, create/edit PRs, post progress comments, or close issues. Orchestration handles GitHub lifecycle actions.

# ISSUE CONTEXT

Root and dependent issue context, including immediate formal parents:

<issues-context>

!`<gh GraphQL query for root/dependent IDs supplied in {{ISSUE_IDS}}, returning issue and immediate-parent context>`

</issues-context>

# MERGE PROCESS

For each branch:

1. Run `git merge <branch> --no-edit`.
2. Resolve conflicts intelligently from issue and repository context.
3. Choose and run verification appropriate to the integrated work and repository instructions.
4. If an individual merge cannot be completed safely, abort that merge so the root returns to a clean state, then continue with other branches when safe.

Use normal Git merge behavior. Do not squash, force `--no-ff`, or create an extra summary commit.

Before completion, ensure the root worktree is clean and all successful integration work is committed. It is valid for only part of the requested batch to succeed.

Only when this merge attempt and validation are finished, output:

<promise>COMPLETE</promise>
```

## Supplemental information: verified GraphQL query

The following query was verified against issues #5 and #6. It returns open issues carrying the `sandcastle` label together with each issue's labels and comments and its immediate formal parent's labels and comments.

```graphql
query LabeledIssuesWithParents(
  $owner: String!
  $name: String!
  $labels: [String!]
) {
  repository(owner: $owner, name: $name) {
    issues(
      first: 100
      states: OPEN
      labels: $labels
      orderBy: { field: CREATED_AT, direction: ASC }
    ) {
      nodes {
        number
        title
        body
        labels(first: 100) {
          nodes {
            name
          }
        }
        comments(first: 100) {
          nodes {
            body
          }
        }
        parent {
          number
          title
          body
          labels(first: 100) {
            nodes {
              name
            }
          }
          comments(first: 100) {
            nodes {
              body
            }
          }
        }
      }
    }
  }
}
```

Use variables in this shape:

```json
{
  "owner": "<repository-owner>",
  "name": "<repository-name>",
  "labels": ["sandcastle"]
}
```

## Explicitly deferred

Do not add these to the MVP:

- Repository/distributed lock for overlapping scheduled runs
- Publishing incomplete dependent branches for VM-loss recovery
- Automatic pruning of old merged local branches
- Hidden completion markers or transactional crash recovery
- Deduplication of merge-progress PR comments
- MongoDB orchestration inside Sandcastle
- Duplicated coding standards in `.sandcastle/CODING_STANDARDS.md`
