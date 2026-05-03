# Testing Guide

How to run NanoRunner's test suite, the layout of test categories, and conventions for adding new tests.

## Overview

The test suite covers individual components and end-to-end workflows.

- **Total tests**: 729 tests across 18 test files
- **Runtime**: roughly 45 seconds excluding the `slow` marker
- **Coverage**: 88% overall (the 90% threshold in `pytest.ini` is the target for new code)

## Test Categories

### Unit Tests

Component-level tests, typically under one second each.

| Test File | Description |
|-----------|-------------|
| `test_config.py` | Configuration validation and parameter handling |
| `test_detection.py` | File structure detection (singleplex vs multiplex) |
| `test_timing.py` | Timing model implementations and edge cases |
| `test_adapters.py` | Pipeline adapter functionality |
| `test_profiles.py` | Configuration profile system |
| `test_mocks.py` | Mock community definitions, aliases, organism validation |
| `test_species.py` | Species name resolution (GTDB/NCBI) |
| `test_deps.py` | Dependency checking, install hints, pre-flight validation |
| `test_fastq.py` | FASTQ writing and format handling |
| `test_manifest.py` | Manifest generation and parsing |
| `test_executor.py` | Operation executor (copy/link) |

### Integration Tests

Cross-component and end-to-end workflows.

| Test File | Description |
|-----------|-------------|
| `test_cli.py` | Command-line interface |
| `test_cli_coverage.py` | Additional CLI coverage paths |
| `test_runner.py` | Simulation orchestration |
| `test_integration.py` | End-to-end workflow testing |
| `test_monitoring.py` | Progress monitoring and resource tracking |
| `test_generators.py` | Read generation backends and factory pattern |
| `test_empty_source_exit_code.py` | Exit codes when no input files are present |
| `test_coverage_boost.py` | Targeted coverage gap fillers |

## Running Tests

### Basic Commands

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run quick summary
pytest -q

# Run with coverage
pytest --cov=nanopore_simulator --cov-report=term-missing
```

### By Category

```bash
# Unit tests only
pytest tests/test_unit_core_components.py tests/test_config.py tests/test_detector.py

# CLI tests
pytest tests/test_cli.py tests/test_cli_coverage.py

# Generate mode tests
pytest tests/test_generators.py

# Exclude slow tests (for development)
pytest -m "not slow"

# Only slow tests
pytest -m "slow"
```

### Coverage Analysis

```bash
# Generate terminal coverage report
pytest --cov=nanopore_simulator --cov-report=term-missing

# Generate HTML coverage report
pytest --cov=nanopore_simulator --cov-report=html
open htmlcov/index.html

# Generate XML report for CI/CD
pytest --cov=nanopore_simulator --cov-report=xml
```

### Debugging Tests

```bash
# Stop on first failure
pytest -x

# Show local variables on failure
pytest -l

# Enter debugger on failure
pytest --pdb

# Verbose with stdout capture disabled
pytest -v -s
```

## Test Organization

### File Structure

```
tests/
├── __init__.py
├── conftest.py                      # Shared fixtures
├── test_adapters.py                 # Pipeline adapter tests
├── test_cli.py                      # CLI interface tests
├── test_cli_coverage.py             # Additional CLI coverage
├── test_config.py                   # Configuration tests
├── test_coverage_boost.py           # Targeted coverage fillers
├── test_deps.py                     # Dependency checking and pre-flight
├── test_detection.py                # File structure detection
├── test_empty_source_exit_code.py   # Empty-source exit code behaviour
├── test_executor.py                 # Operation executor (copy/link)
├── test_fastq.py                    # FASTQ writing and format handling
├── test_generators.py               # Read generation backends
├── test_integration.py              # End-to-end tests
├── test_manifest.py                 # Manifest generation and parsing
├── test_mocks.py                    # Mock community definitions
├── test_monitoring.py               # Progress monitoring
├── test_profiles.py                 # Profile system tests
├── test_runner.py                   # Simulation orchestration
├── test_species.py                  # Species name resolution
└── test_timing.py                   # Timing model tests
```

### Naming Conventions

- **Test files**: `test_<module>.py` for unit tests, `test_<feature>_integration.py` for integration
- **Test classes**: `Test<ComponentName>` for grouped functionality
- **Test methods**: `test_<functionality>_<scenario>` with descriptive names
- **Fixtures**: `<module>_fixture` or `mock_<component>` for identification

### Markers

Tests use pytest markers for categorization:

```python
@pytest.mark.slow         # Long-running tests (deselect with -m "not slow")
@pytest.mark.unit         # Component-level tests
@pytest.mark.integration  # Integration tests
```

## Contributing Tests

### When to Add Tests

- New functionality requires tests
- Bug fixes need regression tests
- Coverage gaps need targeted tests

### Test Structure

Follow the Arrange-Act-Assert pattern:

```python
def test_feature_specific_scenario(fixture_name):
    """Test that feature handles specific scenario correctly."""
    # Arrange - set up test conditions
    config = SimulationConfig(interval=1.0)

    # Act - perform the action
    result = feature.method_under_test(config)

    # Assert - verify expected behavior
    assert result.meets_expectations()
```

### Quality Checklist

- [ ] Test has a single, clear responsibility
- [ ] Test name explains what is being tested
- [ ] Docstring explains the test scenario
- [ ] Uses appropriate fixtures
- [ ] Tests both success and failure paths
- [ ] Runs in reasonable time (<1 second for unit tests)
- [ ] Does not depend on other tests
- [ ] Produces consistent results

### Performance Guidelines

- Keep individual unit tests under 1 second
- Use `@pytest.mark.slow` for tests taking >10 seconds
- Optimize test data size for speed
- Mock external dependencies where appropriate

## Configuration

### pytest.ini

```ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    --verbose
    --strict-markers
    --disable-warnings
    --cov=nanopore_simulator
    --cov-report=html
    --cov-report=term-missing
    --cov-report=xml
    --cov-fail-under=90
markers =
    slow: marks tests as slow (deselect with -m "not slow")
    integration: marks tests as integration tests
    unit: marks tests as unit tests
```

### Coverage Configuration

The project sets `--cov-fail-under=90` in `pytest.ini`. Current overall coverage is around 88%, so adding tests should keep new code at or above the threshold to avoid regressions.

## Continuous Integration

### Local Development

```bash
# Quick validation during development
pytest -m "not slow" -q

# Full validation before commits
pytest -v

# With coverage check
pytest --cov=nanopore_simulator --cov-fail-under=90
```

### CI/CD Pipeline

```bash
# Fast CI (exclude slow tests)
pytest -m "not slow" --cov=nanopore_simulator --cov-report=xml

# Comprehensive nightly builds
pytest --cov=nanopore_simulator --cov-report=xml --cov-report=html
```
