# mac-cleaner

Aggressive macOS CLI tool to scan and clean caches, logs, dev artifacts, and app data to reclaim disk space.

## Install

### Homebrew (recommended)

```bash
brew tap michaelsam94/tap
brew install mac-cleaner
```

### From source

```bash
git clone https://github.com/michaelsam94/mac_cleaner.git
cd mac_cleaner
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

```bash
# Scan all categories (default command)
mac-cleaner
mac-cleaner scan

# Preview what would be deleted (dry-run)
mac-cleaner clean

# Actually delete (prompts for confirmation + sudo when needed)
mac-cleaner clean --execute

# Skip prompts
mac-cleaner clean --execute -y

# Target specific categories
mac-cleaner clean --execute -c xcode -c homebrew -c docker

# List categories
mac-cleaner categories

# Run cleanup every 7 days without manual runs (launchd LaunchAgent)
mac-cleaner schedule install --days 7

# All categories, no prompts — prints sudoers lines to configure once
mac-cleaner schedule install --days 7 --unattended-full

# All categories, admin password dialog each run
mac-cleaner schedule install --days 7 --include-sudo

# Check or remove the schedule
mac-cleaner schedule status
mac-cleaner schedule uninstall

# Scheduled run with specific categories only
mac-cleaner schedule install --days 14 -c homebrew -c xcode
```

Scheduled jobs run `mac-cleaner clean --execute -y` in the background. By default, **sudo categories are skipped** (`system-caches`, `system-logs`, `snapshots`). Use `--include-sudo` for full cleanup with a password dialog each run. Use `--unattended-full` for full cleanup with no dialogs after you add the printed `/etc/sudoers.d/mac-cleaner` rules. Logs: `~/Library/Logs/mac-cleaner-scheduled.log`.

Or without installing:

```bash
python -m mac_cleaner scan
```

## Categories

| Category | What it cleans |
|----------|----------------|
| `user-caches` | `~/Library/Caches` |
| `user-logs` | `~/Library/Logs` |
| `temp` | `/tmp` and user temp folders |
| `trash` | `~/.Trash` |
| `ds-store` | `.DS_Store` files under home |
| `system-caches` | `/Library/Caches` (sudo) |
| `system-logs` | Rotated logs in `/private/var/log` (sudo) |
| `snapshots` | Local Time Machine snapshots (sudo) |
| `homebrew` | Homebrew cache and old versions |
| `npm` / `pip` / `yarn` / `cargo` / `gem` | Package manager caches |
| `xcode` | DerivedData, Archives, DeviceSupport |
| `simulator` | CoreSimulator caches + unavailable sims |
| `docker` | Docker system prune |
| `dev-caches` | Gradle, Maven, CocoaPods, Flutter |
| `browsers` | Safari, Chrome, Firefox, Edge caches |
| `app-caches` | Slack, Discord, Spotify, Zoom |
| `mail` | Mail envelope indexes and caches |

## Safety

- **Dry-run by default** — nothing is deleted unless you pass `--execute`
- **Confirmation prompts** before destructive operations (skip with `-y`)
- **Sudo** only for system caches, system logs, and Time Machine snapshots
- Skips tools that aren't installed (Docker, brew, etc.)

## Requirements

- macOS
- Python 3.10+

## Warning

Aggressive mode deletes real files. Close browsers and Mail before cleaning those categories. Quit Xcode before cleaning DerivedData. Docker prune removes **all** unused images and volumes.

## License

MIT — see [LICENSE](LICENSE).
