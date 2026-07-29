# Wind alert system for good paragliding / groundhandling conditions

## Implementing 

Use conventional commit messages

### Python standard

Use: 
- httpx
- rich
- click
- fastapi
- pyodmongo
- pydantic
- pydantic-settings
- aiogram
- pytest    

uv for package managment and running

### Versioning

After implementing a feature, bump the version. Use your own judgement for major/minor/patch. Only do this when asked to commit, don't do it while you are working. 

After a version bump, also update the `x-ci-trigger` field in ./deployment/docker-compose.yaml with the new version. 

## Running

Use aspire to start, stop, inspect, the app and required resources. 

aspire skill for general workflow
aspire-orchestration skill for app lifecycle

Do not run the app directly unless specifically told to. 

## Testing

Observe `./docs/agents/testing-instructions.md`

## Agent skills

### Issue tracker

Issues for this repo are tracked in GitHub Issues for the current repository. See `docs/agents/issue-tracker.md`.

### Triage labels

Label `sandcastle` marks a ticket as implementable by agent without human interaction. 
