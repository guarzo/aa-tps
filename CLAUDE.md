# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AA-TPS (Alliance Auth - Total Participation Statistics) is a Django plugin for Alliance Auth that automatically tracks and visualizes PvP activity for EVE Online players. It pulls killmail data from ZKillboard, enriches it via ESI, and presents statistics through an interactive dashboard.

## Common Commands

### Running Tests
```bash
# Run all tests
python runtests.py aatps

# Run with verbose output
python runtests.py aatps -v 2

# Run with coverage
coverage run runtests.py aatps -v 2
coverage report

# Run across all Python versions
tox -v
```

### Linting and Code Quality
```bash
# Run all pre-commit hooks
make pre-commit-checks

# Or run pre-commit directly
pre-commit run --all-files
```

### Manual Data Operations
```bash
# Trigger killmail pull manually (useful for testing)
python manage.py aa_tps_pull --verbose

# Force run (clears stale lock)
python manage.py aa_tps_pull --force

# Setup periodic Celery tasks
python manage.py aa_tps_setup
```

### Building
```bash
make build_test  # Create distribution package
```

## Architecture

### Data Flow
```
ZKillboard API → Celery Task (hourly) → ESI API (enrichment) → Database → API Views → Chart.js Dashboard
```

### Core Models (`aatps/models.py`)
- **MonthlyKillmail**: Stores killmail data (victim, ship, location, ISK value, zkill hash)
- **KillmailParticipant**: Links authenticated Alliance Auth users to their participation in killmails (attacker or victim)

### Key Components
- **tasks.py**: Celery tasks for data collection (`pull_monthly_killmails`) and cleanup (`cleanup_old_killmails`)
- **views.py**: Dashboard view and 8 JSON API endpoints for stats, leaderboards, activity charts
- **esi.py**: ESI API client helpers using django-esi's OpenAPI client
- **auth_hooks.py**: Alliance Auth integration (menu hook, URL registration)

### API Endpoints (all under `/aatps/`)
| Endpoint | Purpose |
|----------|---------|
| `api/stats/` | Overall kills, losses, efficiency, active pilots |
| `api/activity/` | Daily kill/loss counts for charts |
| `api/leaderboard/` | Server-side DataTables for pilot rankings |
| `api/top-kills/` | Top 10 most valuable killmails |
| `api/ship-stats/` | Ship class breakdown |
| `api/my-stats/` | Personal pilot statistics |
| `api/recent-kills/` | Recent activity feed |

### Frontend
- **dashboard.html**: Main template with Chart.js visualizations
- **dashboard.js**: ~725 lines handling API calls, chart rendering, DataTables, month navigation

## Code Style

- **Line length**: 120 characters (Black)
- **Python**: 3.10+ syntax (pyupgrade enforced)
- **Django**: 4.2+ patterns (django-upgrade enforced)
- **Imports**: isort with Black compatibility

## Test Structure

Tests use Django's test framework with Factory Boy for fixtures:
- `tests/test_aatps.py`: Core task and API functionality
- `tests/test_views.py`: View and endpoint tests
- `tests/test_utils.py`: Utility function tests
- `tests/factories.py`: Test data factories

Test settings are in `testauth/settings/local.py`.

## Configuration Settings

Configurable in Alliance Auth's `local.py`:
```python
AA_TPS_RETENTION_MONTHS = 12      # How long to keep data
AA_TPS_SHOW_PERSONAL_STATS = True # Enable personal stats tab
```

## Key Patterns

- **Distributed locking**: Tasks use Django cache locks to prevent concurrent runs
- **Rate limiting**: 500ms minimum between ZKillboard requests; ESI backoff on 429s
- **Deduplication**: Killmails tracked by ID; participants have unique constraint on (killmail, character)
- **Read-only admin**: Both models are read-only in Django admin to prevent data corruption
