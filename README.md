# AA-TPS (Alliance Auth - Total Participation Statistics)

[![PyPI - Version](https://img.shields.io/pypi/v/aa-tps?style=for-the-badge)](https://pypi.org/project/aa-tps/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/aa-tps?style=for-the-badge)](https://pypi.org/project/aa-tps/)
[![Python Versions](https://img.shields.io/pypi/pyversions/aa-tps?style=for-the-badge)](https://pypi.org/project/aa-tps/)
[![Django](https://img.shields.io/badge/django-4.2%2B-blue?style=for-the-badge)](https://www.djangoproject.com/)
[![License](https://img.shields.io/badge/license-GPLv3-green?style=for-the-badge)](LICENSE)

> **Zero-configuration PvP activity tracking for your entire Alliance Auth community.**

AA-TPS automatically tracks and visualizes PvP activity for all authenticated users in your Alliance Auth installation. No setup required - just install and go.

## Features

### Automatic Tracking
- **All Users, All the Time** - Automatically tracks every authenticated user's PvP activity
- **Current Month Focus** - Always shows the current month's statistics
- **Smart Data Collection** - Intelligently pulls data by alliance/corp to minimize API calls
- **Historical Access** - Browse previous months' statistics

### Rich Visualizations
- **Daily Activity Charts** - See kills and losses over time with interactive Chart.js graphs
- **Ship Class Breakdown** - Doughnut charts showing what's being flown and destroyed
- **ISK Flow Analysis** - Track ISK destroyed vs lost with area charts
- **Personal Performance** - Individual pilots can see their own stats and ranking

### Leaderboards
- **Organization-wide Rankings** - See who's contributing the most
- **Kill Count & ISK Value** - Multiple ranking metrics
- **Top Performer Badges** - Recognition for top 5 pilots
- **Smart Aggregation** - Alt characters properly grouped under main

### Activity Feed
- **Recent Kills** - Live feed of recent activity
- **Color-coded** - Green for kills, red for losses
- **Direct Links** - One-click access to ZKillboard for details
- **Rich Information** - Ship types, values, participants at a glance

## Screenshots

*Screenshots coming soon*

## Requirements

- **Alliance Auth** >= 4.3.1
- **django-eveuniverse**
- **Python** >= 3.10

## Installation

1. **Activate your virtual environment:**
  ```bash
  source /home/allianceserver/venv/auth/bin/activate
  cd /home/allianceserver/myauth/
  ```

2. **Install the package:**
  ```bash
  pip install aa-tps
  ```

3. **Add to INSTALLED_APPS** in your `local.py`:
  ```python
  INSTALLED_APPS += [
      'eveuniverse',  # if not already added
      'aatps',
  ]
  ```

4. **Run migrations and setup:**
  ```bash
  python manage.py migrate
  python manage.py collectstatic --noinput
  python manage.py aa_tps_setup
  ```

5. **Restart services:**
  ```bash
  sudo supervisorctl restart myauth:
  ```

## Configuration

AA-TPS works out of the box with zero configuration. However, you can customize behavior in your `local.py`:

```python
# How many months of data to retain (default: 12)
AA_TPS_RETENTION_MONTHS = 12

# Enable/disable personal stats tab (default: True)
AA_TPS_SHOW_PERSONAL_STATS = True
```

## Usage

### Automatic Data Collection

AA-TPS automatically pulls killmail data hourly for all authenticated users. The task intelligently:
- Groups characters by alliance/corporation to minimize API calls
- Deduplicates data to avoid redundant requests
- Respects ZKillboard rate limits

### Manual Data Pull

To manually trigger a data pull:

```bash
# Pull current month data
python manage.py aa_tps_pull

# With verbose output
python manage.py aa_tps_pull --verbose
```

### Viewing Statistics

1. Grant users the `aatps.basic_access` permission
2. Users can access the dashboard from the sidebar menu
3. The dashboard shows:
  - Organization-wide statistics for the current month
  - Interactive charts and graphs
  - Leaderboard of top performers
  - Personal statistics (if enabled)
  - Recent activity feed

## Permissions

| Permission | Description |
|------------|-------------|
| `basic_access` | Can view the activity dashboard |

## Data Flow

```
ZKillboard API
  |
[Hourly Celery Task]
  |
ESI API (for full killmail details)
  |
[MonthlyKillmail + KillmailParticipant models]
  |
Dashboard Views
  |
Chart.js Visualizations
```

## API Politeness

AA-TPS is designed with API politeness as a priority:
- Minimum 500ms between ZKillboard requests
- Smart deduplication reduces redundant calls
- Respects rate limit headers
- Uses compression for faster transfers


## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Credits

- Originally based on AA-Campaign by BioBrute
- Built for the Alliance Auth community
- Powered by data from [ZKillboard](https://zkillboard.com)

## Support

- **Issues**: [GitHub Issues](https://github.com/BroodLK/aa-tps/issues)
- **Changelog**: [CHANGELOG.md](CHANGELOG.md)
