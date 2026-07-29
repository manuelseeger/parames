# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v` — `gh` does this automatically when run inside a clone.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## When a skill says "create a sub-issue"

GitHub's `gh issue create` does not create the parent/child relationship itself. Create the issue, then use the REST API to attach it to its parent.

```sh
child_url="$(gh issue create --title "Child issue title" --body "Child issue body")"
child_number="${child_url##*/}"
child_id="$(gh api "repos/{owner}/{repo}/issues/$child_number" --jq .id)"
gh api --method POST "repos/{owner}/{repo}/issues/<parent-number>/sub_issues" \
  -F sub_issue_id="$child_id"
```

To link an existing issue as a sub-issue, replace `<child-number>` and `<parent-number>` below. The parent is the issue in the API path; the child is supplied as `sub_issue_id`.

```sh
child_id="$(gh api "repos/{owner}/{repo}/issues/<child-number>" --jq .id)"
gh api --method POST "repos/{owner}/{repo}/issues/<parent-number>/sub_issues" \
  -F sub_issue_id="$child_id"
```

Both commands infer the repository from the current checkout. If the child already belongs to a different parent, add `-F replace_parent=true` to move it.

