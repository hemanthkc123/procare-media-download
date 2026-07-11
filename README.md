# Procare Photo Archiver

An automated Python and Playwright script that systematically traverses your Procare Connect gallery and archives your child’s weekly or daily photos into a neatly organized local directory structure.

My child was ending her term at daycare, and I had no way to download her photos. So, I created this utility to download the photos and videos.

------------------------------------------------------------------------

## Directory Structure

``` text
procare_archive/
├── 2025/
│   └── October/
│       └── Oct_27_-_Nov_2/
│           ├── photo_1.jpg
│           └── photo_2.png
└── 2026/
    └── July/
        └── Jul_6_-_Jul_12/
            ├── photo_1.jpg
            └── photo_2.jpg
```

## Setup and Installation

### Prerequisites

Install Python. Using `uv` is recommended for fast package management.

### Project Files

Create a project folder containing:

-   `download.py` --- main application script
-   `config.json` --- navigation rules
-   `.env` --- private credentials
-   `README.md`

### Install Dependencies

``` bash
uv init
uv venv
uv pip install -r requirements.txt
uv run playwright install chromium
```

## Configuration

### Credentials (`.env`)

``` env
PROCARE_EMAIL="your_email@example.com"
PROCARE_PASSWORD="your_secure_password"
```

### Runtime Targets (`config.json`)

Change the configuration when to stop downloading the files

``` json
{
  "view_mode": "Weekly",
  "stop_month": "October",
  "stop_year": "2025"
}
```

## Usage

Run:

``` bash
uv run download.py
```

The script:

1.  Logs into the Procare portal as a parent.
2.  Opens the target gallery.
3.  Switches to weekly or daily view based on the configuration.
4.  Scrolls to load images and downloads them.
5.  Navigates backward through the gallery.
6.  Stops when the configured date boundary is reached.
