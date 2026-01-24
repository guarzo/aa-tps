# AA Campaign<a name="aa-campaign"></a>

AA Campaign is a plugin for [Alliance Auth](https://gitlab.com/allianceauth/allianceauth) (AA).

![License](https://img.shields.io/badge/license-GPLv3-green)
![python](https://img.shields.io/badge/python-3.10-informational)
![django](https://img.shields.io/badge/django-4.2-informational)
![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)

______________________________________________________________________

<!-- mdformat-toc start --slug=github --maxlevel=6 --minlevel=1 -->

- [AA Campaign](#aa-campaign)
  - [Features](#features)
  - [Management Commands](#management-commands)
    - [Pull Killmails](#pull-killmails)
    - [Setup Periodic Tasks](#setup-periodic-tasks)
  - [Installation](#installation)
    - [Step 1: Install the Package](#step-1-install-the-package)
    - [Step 2: Configure Alliance Auth](#step-2-configure-alliance-auth)
    - [Step 3: Finalize Installation](#step-3-finalize-installation)
  - [Updating](#updating)
  - [Contribute](#contribute)

<!-- mdformat-toc end -->

______________________________________________________________________

## Features<a name="features"></a>

- Create Z-Kill campaigns based on location (System, Region, Constellation) or global entity-based campaigns.
- Track friendly entities (Characters, Corporations, Alliances) against target entities.
- Automatically pull killmails from ZKillboard hourly.
- Integrated leaderboard and stats page.
- Efficiency calculation and kill/loss tracking.

## Management Commands<a name="management-commands"></a>

### Pull Killmails

Manually trigger a data pull from ZKillboard. By default, this only pulls data for the current day.

```bash
python manage.py aa_campaign_pull --days 30
```

### Setup Periodic Tasks

Automatically setup the hourly background task for pulling data.

```bash
python manage.py aa_campaign_setup
```

## Installation<a name="installation"></a>

### Step 1: Install the Package<a name="step-1-install-the-package"></a>

Install the app from GitHub:

```bash
pip install git+https://github.com/BroodLK/aa-campaign.git
```

### Step 2: Configure Alliance Auth<a name="step-2-configure-alliance-auth"></a>

Add `aacampaign` to your `INSTALLED_APPS` in `local.py`.

### Step 3: Finalize Installation<a name="step-3-finalize-installation"></a>

Run migrations, collect static files, and setup periodic tasks:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py aa_campaign_setup
```

Restart your Alliance Auth services.

## Updating<a name="updating"></a>

To update your installation, run:

```bash
pip install -U git+https://github.com/BroodLK/aa-campaign.git
python manage.py migrate
python manage.py collectstatic --noinput
```

Restart your Alliance Auth services.

## Contribute<a name="contribute"></a>

If you've made a new app for AA, please consider sharing it with the rest of the
community. For any questions on how to share your app, please contact the AA devs on
their Discord. You find the current community creations
[here](https://gitlab.com/allianceauth/community-creations).
