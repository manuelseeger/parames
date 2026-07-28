# TASK

Merge the following branches into the current integration branch:

{{BRANCHES}}

For each branch:

1. Run `git merge <branch> --no-edit`.
2. Resolve conflicts by checking both implementations against their issue requirements.
3. Run deterministic verification:

   ```bash
   PARAMES_DEV_MODE=true uv sync --locked
   PARAMES_DEV_MODE=true uv run pytest
   ```

4. Fix verification failures before proceeding.

Use conventional commit messages for conflict-resolution or integration commits. Do not close issues, modify issue labels, push to `main`, or merge a pull request.

Issues represented by these branches:

{{ISSUES}}

Once all safe merges and verification are complete, output `<promise>COMPLETE</promise>`.
