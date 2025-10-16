# Contributing to NanoRunner

Thank you for your interest in contributing to NanoRunner! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Code Quality](#code-quality)
- [Submitting Changes](#submitting-changes)
- [Release Process](#release-process)

## Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md) to keep our community approachable and respectable.

## Getting Started

### Prerequisites

- Python 3.7 or higher
- Git
- Basic familiarity with nanopore sequencing and bioinformatics pipelines

### Development Setup

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/nanorunner.git
   cd nanorunner
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install development dependencies**
   ```bash
   pip install -e .[dev,test,enhanced]
   ```

4. **Verify installation**
   ```bash
   pytest -v
   nanorunner --version
   ```

## Development Workflow

### Branching Strategy

- `main` - Stable releases only
- `develop` - Integration branch for features (if using)
- `feature/feature-name` - New features
- `fix/bug-name` - Bug fixes
- `docs/documentation-update` - Documentation improvements

### Creating a Feature Branch

```bash
git checkout main
git pull origin main
git checkout -b feature/your-feature-name
```

### Making Changes

1. **Write code** following our style guidelines
2. **Add tests** for new functionality
3. **Update documentation** as needed
4. **Run tests locally** before committing

```bash
# Run tests
pytest -v

# Check formatting
black --check nanopore_simulator/ tests/

# Run linter
flake8 nanopore_simulator/

# Type checking
mypy nanopore_simulator/
```

## Testing

### Test Structure

```
tests/
├── test_unit_core_components.py    # Unit tests (32 tests)
├── test_realistic_scenarios.py     # Integration tests
├── test_realistic_edge_cases.py    # Edge case testing
├── test_realistic_long_running.py  # Long-running scenarios
└── fixtures/                       # Test fixtures and utilities
```

### Running Tests

```bash
# Run all tests
pytest

# Run unit tests only
pytest tests/test_unit_core_components.py

# Run with coverage
pytest --cov=nanopore_simulator --cov-report=html

# Run fast tests (exclude slow markers)
pytest -m "not slow"

# Run specific test
pytest tests/test_unit_core_components.py::TestTimingModels::test_uniform_timing
```

### Writing Tests

All new features must include tests. Follow these guidelines:

1. **Unit tests** for individual components
2. **Integration tests** for complete workflows
3. **Use realistic data** that represents actual use cases
4. **Test edge cases** and error conditions

Example test structure:

```python
def test_feature_name():
    """Test that feature behaves correctly under normal conditions."""
    # Arrange
    config = SimulationConfig(...)

    # Act
    result = feature.execute()

    # Assert
    assert result.is_valid()
```

### Coverage Goals

- **Minimum**: 90% overall coverage
- **Target**: 95% for core modules (config, simulator, timing)
- **Tests must pass**: 100% success rate required

## Code Quality

### Style Guidelines

We follow PEP 8 with some modifications:

- **Line length**: 88 characters (Black default)
- **Formatting**: Use Black for code formatting
- **Imports**: Sort with standard library first, then third-party, then local
- **Docstrings**: Google-style docstrings for all public functions/classes

### Code Formatting

```bash
# Format code
black nanopore_simulator/ tests/

# Check formatting without changes
black --check nanopore_simulator/ tests/
```

### Linting

```bash
# Run flake8
flake8 nanopore_simulator/

# Common issues to avoid:
# - Unused imports
# - Undefined names
# - Line too long (>88 chars)
# - Complexity too high
```

### Type Checking

```bash
# Run mypy
mypy nanopore_simulator/

# All functions should have type hints
def process_file(path: Path, config: SimulationConfig) -> bool:
    ...
```

### Pre-commit Hooks

Install pre-commit hooks to automatically check code quality:

```bash
# Install pre-commit
pip install pre-commit

# Install git hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## Submitting Changes

### Before Submitting

- [ ] All tests pass locally
- [ ] Code is formatted with Black
- [ ] No linting errors from flake8
- [ ] Type hints are present and mypy passes
- [ ] Documentation is updated
- [ ] CHANGELOG.md is updated (for significant changes)

### Pull Request Process

1. **Push your branch**
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create Pull Request** on GitHub
   - Use a clear, descriptive title
   - Reference any related issues
   - Describe the changes and motivation
   - Include screenshots for UI changes

3. **PR Template**
   ```markdown
   ## Description
   Brief description of changes

   ## Type of Change
   - [ ] Bug fix
   - [ ] New feature
   - [ ] Documentation update
   - [ ] Performance improvement

   ## Testing
   - [ ] Unit tests added/updated
   - [ ] Integration tests pass
   - [ ] Manual testing completed

   ## Checklist
   - [ ] Code follows style guidelines
   - [ ] Tests pass locally
   - [ ] Documentation updated
   - [ ] CHANGELOG updated
   ```

4. **Code Review**
   - Address reviewer feedback
   - Keep discussions focused and professional
   - Update your branch as requested

5. **Merge**
   - Maintainers will merge when approved
   - Squash commits for clean history

## Release Process

### Version Numbering

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (x.0.0): Breaking changes
- **MINOR** (1.x.0): New features, backward compatible
- **PATCH** (1.0.x): Bug fixes, backward compatible

### Release Checklist

For maintainers preparing a release:

1. **Update version numbers**
   ```bash
   # Update these files:
   # - nanopore_simulator/__init__.py
   # - pyproject.toml
   # - setup.py
   # - nanopore_simulator/cli/main.py (--version)
   ```

2. **Update CHANGELOG.md**
   ```markdown
   ## [X.Y.Z] - YYYY-MM-DD

   ### Added
   - New features

   ### Changed
   - Modifications

   ### Fixed
   - Bug fixes

   ### Removed
   - Deprecated features
   ```

3. **Run full test suite**
   ```bash
   pytest -v
   pytest --cov=nanopore_simulator --cov-report=html
   ```

4. **Run quality checks**
   ```bash
   black --check nanopore_simulator/ tests/
   flake8 nanopore_simulator/
   mypy nanopore_simulator/
   ```

5. **Create release commit**
   ```bash
   git add .
   git commit -m "Release version X.Y.Z"
   git push origin main
   ```

6. **Create Git tag**
   ```bash
   git tag -a vX.Y.Z -m "Release version X.Y.Z"
   git push origin vX.Y.Z
   ```

7. **Create GitHub Release**
   - Go to GitHub → Releases → Draft a new release
   - Select the tag
   - Copy changelog content
   - Publish release

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/FOI-Bioinformatics/nanorunner/issues)
- **Discussions**: Use GitHub Discussions for questions
- **Email**: bioinformatics@foi.se

## Recognition

Contributors will be recognized in:
- CHANGELOG.md for significant contributions
- GitHub contributors page
- Release notes

Thank you for contributing to NanoRunner!
