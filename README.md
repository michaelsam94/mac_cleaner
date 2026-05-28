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
```

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
