# Testing

Instructions on how to confirm that the current development state is correct and can be considered complete: 

## General 

For local testing start the API on port 7000

Always run all local code with PARAMES_DEV_MODE=true

PARAMES_DEV_MODE=true uv run uvicorn parames.api:app --host 0.0.0.0 --port 7000


## Unit testing
- All unit tests pass
- Use: pytest, pytest-mock
- Use the AAA (Arrange, Act, Assert) pattern
- Use the naming convention: `test_method_name_scenario_to_be_tested_expected_behavior`
- Test files go into tests/
  - `test_*.py` - unit tests
  - `tests/integration/test_*.py` - integration tests

## Frontend testing

Use the playwright skill for testing the frontend in the browser.
