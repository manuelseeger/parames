# Testing

Instructions on how to confirm that the current development state is correct and can be considered complete: 

## Unit testing
- All unit tests pass
- Use: pytest, pytest-mock
- Use the AAA (Arrange, Act, Assert) pattern
- Use the naming convention: `test_method_name_scenario_to_be_tested_expected_behavior`
- Test files go into tests/
  - `test_*.py` - unit tests
  - `tests/integration/test_*.py` - integration tests

