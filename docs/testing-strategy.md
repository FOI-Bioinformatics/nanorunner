# Testing Strategy and Framework

This document outlines the comprehensive testing strategy for NanoRunner, including test organization, coverage goals, and development practices.

## Table of Contents
- [Testing Philosophy](#testing-philosophy)
- [Test Organization](#test-organization)
- [Coverage Strategy](#coverage-strategy)
- [Test Categories](#test-categories)
- [Test Data Management](#test-data-management)
- [Running Tests](#running-tests)
- [Coverage Reports](#coverage-reports)
- [Contributing Tests](#contributing-tests)

## Testing Philosophy

NanoRunner follows a **comprehensive testing strategy** designed to ensure:

1. **Reliability**: All core functionality is thoroughly tested
2. **Maintainability**: Tests serve as living documentation
3. **Performance**: Regular performance regression testing
4. **Integration**: End-to-end pipeline testing
5. **Edge Cases**: Robust error handling and edge case coverage

### Testing Principles

- **Test-Driven Development**: Write tests before or alongside code
- **Behavioral Testing**: Focus on expected behavior, not implementation
- **Realistic Data**: Use representative test data for accurate validation
- **Fast Feedback**: Unit tests run quickly for rapid development cycles
- **Comprehensive Coverage**: Aim for 95%+ code coverage with meaningful tests

## Test Organization

### File Structure
```
tests/
├── __init__.py                    # Test package initialization
├── conftest.py                    # Shared fixtures and configuration
├── fixtures/                     # Reusable test fixtures
│   ├── __init__.py
│   ├── data_fixtures.py          # Test data creation utilities
│   ├── config_fixtures.py        # Configuration fixtures
│   └── monitoring_fixtures.py    # Monitoring test utilities
├── unit/                         # Unit tests by module
│   ├── test_config.py            # Configuration validation tests
│   ├── test_detector.py          # File structure detection tests
│   ├── test_timing.py            # Timing model tests
│   ├── test_monitoring.py        # Monitoring system tests
│   ├── test_adapters.py          # Pipeline adapter tests
│   └── test_simulator.py         # Core simulation tests
├── integration/                  # Integration and end-to-end tests
│   ├── test_cli_integration.py   # CLI interface tests
│   ├── test_pipeline_integration.py # Pipeline integration tests
│   └── test_performance.py       # Performance benchmarks
├── coverage/                     # Coverage-specific tests
│   ├── test_edge_cases.py        # Edge case coverage
│   ├── test_error_handling.py    # Error path coverage
│   └── test_concurrency.py       # Parallel processing coverage
└── data/                         # Test data sets
    ├── realistic/                # Realistic test datasets
    ├── edge_cases/               # Edge case test data
    └── performance/              # Performance testing data
```

### Naming Conventions

- **Test Files**: `test_<module>.py` for unit tests, `test_<feature>_integration.py` for integration
- **Test Classes**: `Test<ModuleName>` for grouped functionality
- **Test Methods**: `test_<functionality>_<scenario>` with descriptive names
- **Fixtures**: `<module>_fixture` or `mock_<component>` for clear identification

## Coverage Strategy

### Coverage Goals

| Module | Target Coverage | Current Coverage | Priority |
|--------|----------------|------------------|----------|
| CLI | 99% | 99% | ✅ Complete |
| Config | 100% | 100% | ✅ Complete |
| Simulator | 95% | 88% | 🔄 Active |
| Monitoring | 95% | 89% | 🔄 Active |
| Adapters | 95% | 94% | 🔄 Active |
| Timing | 98% | 96% | 🔄 Active |
| **Overall** | **95%** | **93%** | 🔄 Active |

### Coverage Analysis

#### Lines Requiring Coverage Priority:
1. **Error Handling Paths**: Exception handling and recovery
2. **Edge Cases**: Boundary conditions and unusual inputs
3. **Concurrency Code**: Thread safety and parallel processing
4. **Interactive Features**: Pause/resume and signal handling

#### Lines Excluded from Coverage:
- **Platform-specific code**: OS-specific implementations
- **Defensive assertions**: Safety checks for impossible conditions
- **Import fallbacks**: Optional dependency handling

## Test Categories

### 1. Unit Tests
**Purpose**: Test individual functions and classes in isolation

**Characteristics**:
- Fast execution (< 1 second per test)
- No external dependencies
- Focused on single responsibility
- High code coverage

**Examples**:
```python
def test_uniform_timing_model():
    """Test uniform timing model generates consistent intervals"""
    model = UniformTimingModel(interval=5.0)
    intervals = [model.next_interval() for _ in range(10)]
    assert all(interval == 5.0 for interval in intervals)

def test_config_validation_negative_interval():
    """Test configuration rejects negative intervals"""
    with pytest.raises(ValueError, match="interval must be non-negative"):
        SimulationConfig(interval=-1.0)
```

### 2. Integration Tests
**Purpose**: Test component interactions and system behavior

**Characteristics**:
- Moderate execution time (1-10 seconds)
- Tests realistic workflows
- Uses temporary file systems
- Validates end-to-end behavior

**Examples**:
```python
@pytest.mark.integration
def test_simulator_with_monitoring():
    """Test complete simulation with monitoring enabled"""
    config = SimulationConfig(source_dir=test_data, target_dir=temp_dir)
    simulator = NanoporeSimulator(config, enable_monitoring=True)
    simulator.run_simulation()
    assert monitoring_metrics_collected()
```

### 3. Performance Tests
**Purpose**: Validate performance characteristics and prevent regressions

**Characteristics**:
- Longer execution time (10+ seconds)
- Tests scalability limits
- Measures resource usage
- Benchmarks against baselines

**Examples**:
```python
@pytest.mark.slow
def test_large_dataset_performance(benchmark):
    """Test performance with 1000+ files"""
    large_dataset = create_test_files(count=1000)
    result = benchmark(simulate_dataset, large_dataset)
    assert result.throughput > 50  # files/second
```

### 4. Coverage Tests
**Purpose**: Specifically target uncovered code paths

**Characteristics**:
- Tests error conditions
- Validates edge cases
- Ensures exception handling
- Covers defensive code

**Examples**:
```python
def test_file_permission_error_handling():
    """Test simulator handles file permission errors gracefully"""
    with patch('pathlib.Path.exists', side_effect=PermissionError):
        with pytest.raises(PermissionError):
            detector.detect_structure(restricted_path)
```

## Test Data Management

### Realistic Test Data

Located in `tests/data/realistic/`:
- **Singleplex**: 3 FASTQ files, 1 POD5 file (small, medium, large sizes)
- **Multiplex**: 3 barcodes with 2-4 files each, unclassified directory
- **Mixed**: Combination of singleplex and multiplex structures

### Edge Case Data

Located in `tests/data/edge_cases/`:
- **Empty directories**: For error condition testing
- **Invalid files**: Malformed FASTQ headers
- **Unicode filenames**: International character testing
- **Large files**: Memory usage testing (symlinked, not committed)

### Performance Data

Located in `tests/data/performance/`:
- **Small dataset**: 10 files for quick tests
- **Medium dataset**: 100 files for integration tests
- **Large dataset**: Generated on-demand for performance tests

### Data Creation Utilities

```python
# tests/fixtures/data_fixtures.py
@pytest.fixture
def realistic_singleplex_data(tmp_path):
    """Create realistic singleplex test data"""
    source_dir = tmp_path / "singleplex"
    source_dir.mkdir()
    
    # Create files with realistic content
    create_fastq_file(source_dir / "sample1.fastq", reads=100)
    create_fastq_file(source_dir / "sample2.fastq.gz", reads=200, compressed=True)
    create_pod5_file(source_dir / "sample1.pod5", signals=1000)
    
    return source_dir

@pytest.fixture
def realistic_multiplex_data(tmp_path):
    """Create realistic multiplex test data"""
    # Implementation for multiplex data creation
    pass
```

## Running Tests

### Basic Test Execution

```bash
# Run all tests
pytest

# Run unit tests only
pytest tests/unit/

# Run with coverage
pytest --cov=nanopore_simulator

# Run specific test file
pytest tests/unit/test_config.py

# Run specific test
pytest tests/unit/test_config.py::TestConfigValidation::test_negative_interval
```

### Test Categories

```bash
# Run fast tests only (default)
pytest -m "not slow"

# Run all tests including slow ones
pytest -m ""

# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run performance tests
pytest -m slow
```

### Parallel Test Execution

```bash
# Run tests in parallel (requires pytest-xdist)
pytest -n auto

# Run with specific worker count
pytest -n 4
```

### Debugging Tests

```bash
# Stop on first failure
pytest -x

# Show local variables on failure
pytest -l

# Enter debugger on failure
pytest --pdb

# Verbose output
pytest -v -s
```

## Coverage Reports

### HTML Reports
```bash
pytest --cov=nanopore_simulator --cov-report=html
# Open htmlcov/index.html in browser
```

### Terminal Reports
```bash
pytest --cov=nanopore_simulator --cov-report=term-missing
```

### XML Reports (for CI/CD)
```bash
pytest --cov=nanopore_simulator --cov-report=xml
```

### Coverage Analysis
```bash
# Detailed coverage analysis
coverage report --show-missing
coverage html

# Coverage diff between branches
coverage xml
diff-cover coverage.xml --compare-branch=main
```

## Contributing Tests

### Test Development Workflow

1. **Identify Test Need**:
   - New functionality requires tests
   - Bug fixes need regression tests
   - Coverage gaps need targeted tests

2. **Choose Test Type**:
   - Unit test for isolated functionality
   - Integration test for component interaction
   - Performance test for scalability concerns

3. **Write Test**:
   - Follow naming conventions
   - Use appropriate fixtures
   - Include descriptive docstrings
   - Test both success and failure cases

4. **Validate Test**:
   - Ensure test passes with correct code
   - Ensure test fails with incorrect code
   - Check coverage improvement
   - Verify test performance

### Test Quality Checklist

- [ ] **Clear Purpose**: Test has a single, clear responsibility
- [ ] **Descriptive Name**: Test name explains what is being tested
- [ ] **Good Documentation**: Docstring explains the test scenario
- [ ] **Appropriate Fixtures**: Uses proper setup and teardown
- [ ] **Error Testing**: Tests both success and failure paths
- [ ] **Performance**: Test runs in reasonable time
- [ ] **Isolation**: Test doesn't depend on other tests
- [ ] **Deterministic**: Test produces consistent results

### Example Test Template

```python
def test_feature_specific_scenario(fixture_name, mock_dependency):
    """Test that feature handles specific scenario correctly.
    
    This test verifies that when the feature encounters a specific
    scenario, it behaves according to the specification.
    
    Args:
        fixture_name: Provides test data setup
        mock_dependency: Mocks external dependency
        
    Asserts:
        Expected behavior occurs
        Error handling works correctly
        State changes are valid
    """
    # Arrange
    setup_test_conditions()
    
    # Act
    result = feature.method_under_test(parameters)
    
    # Assert
    assert result.meets_expectations()
    assert feature.state_is_valid()
    mock_dependency.assert_called_correctly()
```

## Test Maintenance

### Regular Maintenance Tasks

- **Weekly**: Review test failures and flaky tests
- **Monthly**: Analyze coverage reports and identify gaps
- **Quarterly**: Review test performance and optimize slow tests
- **Release**: Comprehensive test suite run with performance benchmarks

### Performance Monitoring

- **Test Execution Time**: Monitor for regressions in test speed
- **Coverage Trends**: Track coverage changes over time
- **Flaky Test Detection**: Identify and fix unreliable tests
- **Resource Usage**: Monitor memory and CPU usage during tests

### Documentation Updates

- Keep test documentation current with code changes
- Update examples when APIs change
- Maintain test data relevance
- Document new testing patterns and utilities