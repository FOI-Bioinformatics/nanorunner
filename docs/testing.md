# Testing Guide

This document provides a comprehensive guide to NanoRunner's test suite, including how to run tests, understand test categories, and contribute new tests.

## Overview

NanoRunner has a comprehensive test suite designed to validate both individual components and complete workflows:

- **Total Tests**: 524 tests across 31 test files
- **Runtime**: ~100 seconds for complete suite with coverage
- **Coverage**: 97% on core components

## Test Categories

### Unit Tests

Test individual components in isolation with fast execution (<1 second per test).

| Test File | Description |
|-----------|-------------|
| `test_unit_core_components.py` | Core component isolation tests |
| `test_config.py` | Configuration validation and parameter handling |
| `test_detector.py` | File structure detection algorithms |
| `test_timing_models.py` | Timing model implementations and edge cases |
| `test_adapters.py` | Pipeline adapter functionality |
| `test_profiles.py` | Configuration profile system validation |

### Integration Tests

Test component interactions and end-to-end workflows.

| Test File | Description |
|-----------|-------------|
| `test_cli.py` | Core command-line interface functionality |
| `test_cli_enhanced.py` | Enhanced CLI features and monitoring integration |
| `test_simulator.py` | Core simulation functionality and orchestration |
| `test_integration.py` | End-to-end workflow testing |
| `test_timing_integration.py` | Timing model integration with simulation workflow |
| `test_parallel_processing.py` | Parallel processing capabilities and thread safety |
| `test_enhanced_monitoring.py` | Advanced monitoring features and resource tracking |

### Generate Mode Tests

Test read generation functionality.

| Test File | Description |
|-----------|-------------|
| `test_generators.py` | Read generation backends, FASTA parsing, factory pattern |
| `test_generate_integration.py` | End-to-end generate mode (multiplex, singleplex, mixed, timing) |

### Practical Tests

Real-world tests using actual NCBI genome sequences.

| Test File | Description |
|-----------|-------------|
| `test_practical.py` | Tests with real NCBI genomes (Lambda, S. aureus, E. coli) |

Requires the NCBI datasets CLI to be installed. Run with:
```bash
pytest tests/test_practical.py -m practical
```

### Performance Tests

Benchmarks and large dataset handling (marked as `slow`).

| Test File | Description |
|-----------|-------------|
| `test_performance.py` | Large dataset handling and performance benchmarks |

### Edge Case Tests

Error handling, permissions, and boundary conditions.

| Test File | Description |
|-----------|-------------|
| `test_edge_cases.py` | Error handling, permissions, boundary conditions |
| `test_realistic_edge_cases.py` | Mixed file types, permissions, symlinks |
| `test_realistic_long_running.py` | Extended runs, checkpoint/resume, recovery |

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
pytest tests/test_cli.py tests/test_cli_enhanced.py

# Generate mode tests
pytest tests/test_generators.py tests/test_generate_integration.py

# Practical tests (requires NCBI datasets CLI)
pytest tests/test_practical.py -m practical

# Exclude slow tests (for development)
pytest -m "not slow"

# Only slow tests (performance benchmarks)
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
├── test_cli.py                      # CLI interface tests
├── test_cli_enhanced.py             # Enhanced CLI tests
├── test_config.py                   # Configuration tests
├── test_detector.py                 # File detection tests
├── test_simulator.py                # Core simulation tests
├── test_timing_models.py            # Timing model tests
├── test_parallel_processing.py      # Parallel processing tests
├── test_enhanced_monitoring.py      # Monitoring tests
├── test_profiles.py                 # Profile system tests
├── test_adapters.py                 # Pipeline adapter tests
├── test_generators.py               # Read generator tests
├── test_generate_integration.py     # Generate mode integration
├── test_practical.py                # Real genome tests
├── test_integration.py              # End-to-end tests
├── test_timing_integration.py       # Timing integration tests
├── test_edge_cases.py               # Edge case tests
├── test_performance.py              # Performance benchmarks
└── ...
```

### Naming Conventions

- **Test files**: `test_<module>.py` for unit tests, `test_<feature>_integration.py` for integration
- **Test classes**: `Test<ComponentName>` for grouped functionality
- **Test methods**: `test_<functionality>_<scenario>` with descriptive names
- **Fixtures**: `<module>_fixture` or `mock_<component>` for identification

### Markers

Tests use pytest markers for categorization:

```python
@pytest.mark.slow        # Performance tests (>10 seconds)
@pytest.mark.practical   # Tests requiring external tools (NCBI datasets)
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
markers =
    slow: marks tests as slow (may take several seconds)
    practical: marks tests requiring external tools
addopts = --strict-markers
```

### Coverage Configuration

Coverage is configured in `.coveragerc` or `pyproject.toml`:
- Minimum coverage threshold: 90%
- Excludes platform-specific code and import fallbacks

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
