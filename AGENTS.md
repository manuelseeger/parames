# Wind alert system for good paragliding / groundhandling conditions

Initial spec: [Initial Wind Alert](./spec/Initial%20Wind%20Alert.md)


# Implementing 

## Python standard

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

## Versioning

After implementing a feature, bump the version. Use your own judgement for major/minor/patch. 

After a version bump, also update the `x-ci-trigger` field in ./deployment/docker-compose.yaml with the new version. 

# Testing

For local testing start the API on port 7000

Use playwright for testing the frontend in the browser.

Always run all local code with PARAMES_DEV_MODE=true

PARAMES_DEV_MODE=true uv run uvicorn parames.api:app --host 0.0.0.0 --port 7000


## Available Skills

The following skills are installed in ~/.claude/skills/:
- playwright-cli: Automate browser interactions, test web pages and work with Playwright tests.

When you encounter a problem that matches a skill, READ the SKILL.md file first before attempting to fix it.
