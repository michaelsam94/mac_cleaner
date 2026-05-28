# Mac Cleaner CLI — Design Spec

**Date:** 2026-05-28  
**Level:** Aggressive (C)

## Goal

CLI tool for macOS that scans and cleans user/system caches, logs, dev tool artifacts, and app caches to reclaim maximum disk space safely.

## CLI

```bash
mac-cleaner scan                          # show reclaimable space (default)
mac-cleaner clean                         # dry-run deletion preview
mac-cleaner clean --execute               # delete with confirmation
mac-cleaner clean --execute -y            # delete without prompts
mac-cleaner clean --category xcode,brew   # subset of categories
```

## Categories

| ID | Targets | Sudo |
|----|---------|------|
| user-caches | ~/Library/Caches | No |
| user-logs | ~/Library/Logs | No |
| system-caches | /Library/Caches | Yes |
| system-logs | /private/var/log (old/rotated) | Yes |
| temp | /tmp, user temp in /var/folders | Partial |
| trash | ~/.Trash | No |
| ds-store | .DS_Store under $HOME | No |
| homebrew | brew cleanup -s --prune=all | No |
| npm/pip/yarn/cargo/gem | package manager caches | No |
| xcode | DerivedData, Archives, old DeviceSupport | No |
| simulator | CoreSimulator caches | No |
| docker | docker system prune -af --volumes | No |
| browsers | Safari, Chrome, Firefox, Edge | No |
| mail | Mail envelope/cache files | No |
| snapshots | Local TM snapshots via tmutil | Yes |
| dev-caches | Gradle, Maven, CocoaPods, Flutter | No |
| app-caches | Slack, Discord, Spotify, Zoom | No |

## Architecture

Python 3.10+, Click, Rich. Modular `Cleaner` ABC per category group. Shared scanner (du), executor (delete/sudo), reporter (Rich tables).

## Safety

- Dry-run unless `--execute`
- Confirm before sudo (unless `-y`)
- Skip missing paths, log failures, continue
- No symlinks followed outside target
- Exit 1 on partial failure
