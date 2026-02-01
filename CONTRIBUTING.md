# Contributing to Hipster Timer Backend

**[한국어 버전](CONTRIBUTING.ko.md)**

Thank you for your interest in contributing to Hipster Timer Backend. This document describes the contribution process and guidelines.

## Table of Contents

- [Before You Start](#before-you-start)
- [Development Environment](#development-environment)
- [Coding Standards](#coding-standards)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)
- [Review Process](#review-process)

---

## Before You Start

### Check Existing Issues

Before starting work, check if there's already an issue or PR for your intended change:

1. Search [existing issues](https://github.com/onprem-hipster-timer/backend/issues)
2. Search [existing pull requests](https://github.com/onprem-hipster-timer/backend/pulls)

If none exists, create an issue first to discuss the change.

### Issue First Policy

**All non-trivial changes require an issue first.**

- Bug fixes: Create a bug report issue
- New features: Create a feature request issue
- Documentation: Small fixes can go directly to PR

This ensures your work aligns with project direction and prevents duplicate effort.

---

## Development Environment

### Prerequisites

- Python 3.11 or higher
- Git
- Docker (optional, for PostgreSQL testing)

### Setup

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/backend.git
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install development dependencies
pip install -r requirements-dev.txt

# Copy environment file
cp .env.example .env
```

### Running Tests

**All code changes must pass tests.**

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/domain/schedule/test_service.py

# Run E2E tests only
pytest -m e2e
```

### Running the Server

```bash
uvicorn app.main:app --port 2614 --reload
```

---

## Coding Standards

### Python Style

This project follows **PEP 8** with the following specifics:

- Line length: 120 characters maximum
- Use type hints for all function parameters and return values
- Use `"""docstrings"""` for all public functions, classes, and modules

### Type Hints

```python
# Good
def create_schedule(self, data: ScheduleCreate) -> Schedule:
    """Create a new schedule."""
    ...

# Bad
def create_schedule(self, data):
    ...
```

### Docstrings

Use Korean or English, but be consistent within a file:

```python
def validate_parent(self, parent_id: UUID, child_id: UUID | None = None) -> None:
    """
    부모 Todo 유효성 검증
    
    비즈니스 규칙:
    - 부모가 존재해야 함
    - 자기 자신을 부모로 설정 불가
    - 순환 참조 생성 불가
    
    :param parent_id: 부모 Todo ID
    :param child_id: 자식 Todo ID (update 시 검증용)
    :raises TodoInvalidParentError: 부모가 존재하지 않을 때
    :raises TodoSelfReferenceError: 자기 참조 시도 시
    :raises TodoCycleError: 순환 참조 생성 시
    """
```

### Architecture Principles

1. **Layered Architecture**: Router → Service → Domain → Data
2. **Domain Exceptions**: Use `DomainException` subclasses, not HTTP exceptions in services
3. **UTC Storage**: All datetimes stored as UTC naive in database
4. **Owner Isolation**: All resources filtered by `owner_id`

### File Naming

| Type | Pattern | Example |
|------|---------|---------|
| Router | `app/api/v1/{domain}.py` | `schedules.py` |
| Service | `app/domain/{domain}/service.py` | `service.py` |
| Schema | `app/domain/{domain}/schema/dto.py` | `dto.py` |
| Model | `app/models/{domain}.py` | `schedule.py` |
| Test | `tests/domain/{domain}/test_*.py` | `test_service.py` |

---

## Commit Guidelines

### Commit Message Format

Follow the conventional commit format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Code style (formatting, no logic change) |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test` | Adding or updating tests |
| `chore` | Build process, dependencies, etc. |

### Examples

```
feat(schedule): add RRULE exception date handling

Implement exception date handling for recurring schedules.
Users can now skip or modify specific occurrences.

- Add ScheduleException model
- Update expand_recurrence to filter exceptions
- Add exception CRUD endpoints

Closes #42
```

```
fix(todo): prevent circular reference in parent assignment

The previous implementation allowed A→B→A cycles.
Now validates ancestor chain before setting parent.

Fixes #87
```

### Commit Principles

1. **Atomic commits**: Each commit should be a single logical change
2. **Buildable**: Each commit should pass all tests
3. **Descriptive**: Subject line should describe what, body explains why
4. **Reference issues**: Use `Closes #N` or `Fixes #N` in footer

---

## Pull Request Process

### Before Submitting

- [ ] All tests pass (`pytest`)
- [ ] Code follows style guidelines
- [ ] New code has appropriate tests
- [ ] Documentation updated if needed
- [ ] Commit messages follow guidelines
- [ ] Rebased on latest `main`

### PR Title Format

Same as commit message subject:

```
feat(timer): add pause/resume WebSocket support
fix(auth): handle expired JWKS cache gracefully
docs: update installation guide for Windows
```

### PR Description

Use the PR template. Include:

1. **Summary**: What this PR does
2. **Related Issue**: Link to issue (`Closes #N`)
3. **Changes**: List of changes made
4. **Test Plan**: How to verify the changes

### Size Matters

- Keep PRs focused and reasonably sized
- Large changes should be split into logical, reviewable chunks
- If a PR grows too large, discuss splitting it

---

## Review Process

### What Reviewers Look For

1. **Correctness**: Does the code do what it claims?
2. **Tests**: Are edge cases covered?
3. **Architecture**: Does it follow project patterns?
4. **Performance**: Any obvious performance issues?
5. **Security**: Any security concerns?

### Responding to Reviews

- Address all comments before requesting re-review
- Explain your reasoning if you disagree
- Mark conversations as resolved after addressing

### Review Timeline

- Maintainers aim to provide initial review within 3-5 business days
- Complex PRs may take longer
- Ping in the PR if no response after a week

---

## Getting Help

- **Questions**: Open a [Discussion](https://github.com/onprem-hipster-timer/backend/discussions)
- **Bugs**: Create an [Issue](https://github.com/onprem-hipster-timer/backend/issues)
- **Security**: See [SECURITY.md](SECURITY.md)

---

*Good code comes from good reviews. Thank you for contributing.*
