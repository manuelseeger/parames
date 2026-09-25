# Wind alert system for good paragliding / groundhandling conditions

## Implementing 

Use conventional commit messages
gh cli for remote repo and issues

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
