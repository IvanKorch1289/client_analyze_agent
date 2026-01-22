# Contributing to Client Analysis Agent

Thank you for your interest in contributing to Client Analysis Agent! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Pull Request Process](#pull-request-process)
- [Code Style](#code-style)
- [Testing](#testing)
- [Documentation](#documentation)

## Code of Conduct

This project adheres to a code of conduct. By participating, you are expected to:

- Be respectful and inclusive
- Accept constructive criticism gracefully
- Focus on what is best for the community
- Show empathy towards other contributors

## Getting Started

### Prerequisites

- Python 3.12+
- Poetry (dependency management)
- Docker and Docker Compose
- Git

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/client_analyze_agent.git
   cd client_analyze_agent
   ```
3. Add upstream remote:
   ```bash
   git remote add upstream https://github.com/IvanKorch1289/client_analyze_agent.git
   ```

## Development Setup

### 1. Install Dependencies

```bash
# Install Poetry if not already installed
pip install poetry

# Install project dependencies
poetry install

# Activate virtual environment
poetry shell
```

### 2. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your API keys and configuration
# Required: OPENROUTER_API_KEY, DADATA_API_KEY, etc.
```

### 3. Start Services

```bash
# Start all services with Docker Compose
docker-compose up -d

# Or start only dependencies (Tarantool, RabbitMQ)
docker-compose up -d tarantool rabbitmq
```

### 4. Run the Application

```bash
# Run the main application
python run.py

# Or run individual components
python -m app.messaging.worker  # Worker
python -m app.mcp_server.main   # MCP Server
```

## Making Changes

### Branch Naming Convention

- `feature/` - New features (e.g., `feature/add-new-data-source`)
- `fix/` - Bug fixes (e.g., `fix/circuit-breaker-timeout`)
- `docs/` - Documentation changes (e.g., `docs/update-api-reference`)
- `refactor/` - Code refactoring (e.g., `refactor/split-large-module`)
- `test/` - Test additions/changes (e.g., `test/add-integration-tests`)

### Workflow

1. Create a new branch from `main`:
   ```bash
   git checkout main
   git pull upstream main
   git checkout -b feature/your-feature-name
   ```

2. Make your changes following the [Code Style](#code-style) guidelines

3. Write tests for new functionality

4. Run the test suite:
   ```bash
   poetry run pytest
   ```

5. Run linting and type checking:
   ```bash
   poetry run ruff check .
   poetry run pyright
   ```

6. Commit your changes:
   ```bash
   git add .
   git commit -m "feat: add new data source integration"
   ```

### Commit Message Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation only
- `style:` - Formatting, no code change
- `refactor:` - Code restructuring
- `test:` - Adding tests
- `chore:` - Maintenance tasks

Examples:
```
feat: add Spark API integration
fix: resolve circuit breaker race condition
docs: update deployment runbook
refactor: split data_collector into modules
test: add PII protection unit tests
```

## Pull Request Process

### Before Submitting

1. **Update your branch** with the latest changes from upstream:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run all checks**:
   ```bash
   # Linting
   poetry run ruff check .

   # Type checking
   poetry run pyright

   # Tests
   poetry run pytest

   # Security scan
   poetry run bandit -r app
   ```

3. **Update documentation** if needed

### Submitting

1. Push your branch to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

2. Create a Pull Request on GitHub

3. Fill in the PR template with:
   - Description of changes
   - Related issues
   - Testing performed
   - Checklist completion

### Review Process

- PRs require at least one approval
- CI checks must pass
- Address review comments promptly
- Squash commits if requested

## Code Style

### Python Style Guide

We use [Ruff](https://docs.astral.sh/ruff/) for linting with the following rules:

```toml
[tool.ruff.lint]
select = [
  "F",   # pyflakes
  "E",   # pycodestyle
  "I",   # isort
  "B",   # flake8-bugbear
  "C4",  # flake8-comprehensions
]
```

### Key Guidelines

1. **Type Hints**: Use type hints for all function signatures
   ```python
   async def fetch_data(inn: str, timeout: int = 30) -> dict[str, Any]:
       ...
   ```

2. **Docstrings**: Use Google-style docstrings
   ```python
   def calculate_risk(data: dict) -> float:
       """Calculate normalized risk score.

       Args:
           data: Raw data from multiple sources.

       Returns:
           Risk score from 0.0 to 100.0.

       Raises:
           ValueError: If data is incomplete.
       """
   ```

3. **Async/Await**: Use async for I/O operations
   ```python
   # Good
   async def fetch_all():
       results = await asyncio.gather(fetch_a(), fetch_b())

   # Bad - blocking in async context
   async def fetch_all():
       result_a = requests.get(...)  # Don't do this
   ```

4. **Error Handling**: Use specific exceptions
   ```python
   # Good
   except CircuitBreakerOpenError as e:
       logger.warning(f"Circuit open: {e}")

   # Bad
   except Exception:
       pass
   ```

5. **Imports**: Group and sort with isort
   ```python
   # Standard library
   import asyncio
   from typing import Any

   # Third-party
   from fastapi import FastAPI
   from pydantic import BaseModel

   # Local
   from app.services.http_client import resilient_client
   ```

## Testing

### Test Structure

```
tests/
├── unit/           # Unit tests
├── integration/    # Integration tests
├── e2e/            # End-to-end tests
├── performance/    # Performance tests
└── security/       # Security tests
```

### Running Tests

```bash
# All tests
poetry run pytest

# With coverage
poetry run pytest --cov=app --cov-report=html

# Specific test file
poetry run pytest tests/test_risk_calculator.py

# Specific test
poetry run pytest tests/test_api.py::test_health_endpoint

# Skip integration tests
SKIP_INTEGRATION=true poetry run pytest
```

### Writing Tests

```python
import pytest
from app.services.risk_calculator import calculate_risk

@pytest.mark.asyncio
async def test_calculate_risk_high():
    """Test risk calculation for high-risk company."""
    data = {
        "legal_issues": {"court_cases": 15},
        "financial": {"bankruptcy_risk": True},
    }

    score = await calculate_risk(data)

    assert score >= 70.0
    assert score <= 100.0


@pytest.fixture
def mock_http_client(mocker):
    """Mock HTTP client for isolated testing."""
    return mocker.patch("app.services.http_client.resilient_client")
```

## Documentation

### Types of Documentation

1. **Code Documentation**: Docstrings in code
2. **API Documentation**: OpenAPI/Swagger (auto-generated)
3. **User Documentation**: `docs/` directory
4. **Architecture Decisions**: `docs/adr/` (ADRs)

### Updating Documentation

- Update relevant docs when changing functionality
- Add ADR for significant architectural changes
- Keep README.md up to date with new features

### Building Documentation

```bash
# API docs are auto-generated at /docs endpoint
# User docs are in Markdown format in docs/
```

## Questions?

- Open an issue for bugs or feature requests
- Use discussions for questions
- Check existing issues before creating new ones

---

Thank you for contributing to Client Analysis Agent!
