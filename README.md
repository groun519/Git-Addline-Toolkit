# Git Addline Toolkit

Windows-only line tracking UI for Git repos.  
Shows daily/total progress, committed vs uncommitted additions, and a 1-minute auto refresh option.  
Designed to live under a repo (e.g. `PROJECT-MA/tools/Git-Addline-Toolkit`), but can target any Git repo via the UI.

## Requirements

- Windows
- Python 3.x in PATH
- Git in PATH

## Quick Start

1. Open `line_tracker_ui_click.vbs` (double click).
2. In the UI, set `리포 경로` to the repo you want to track.
3. Click `리포 선택` (or press Enter in the path field).
4. Click `새로고침`.

The selected repo path is saved and restored on next launch.

## What Runs What

- `line_tracker_ui_click.vbs`  
  Launches the UI with `pythonw` (no console). If `pythonw` is missing, it uses `python`.

Internal files are in `app/`:

- `app/line_tracker_ui.py` (UI)
- `app/line_tracker.py` (metrics engine)
- `app/line_tracker_ui_settings.json` (saved UI settings)
- `app/line_tracker_cache.json` (computed caches)

## UI Overview

### Main Cards

- Today Date / Days Left: Based on current date or custom date.
- Daily Required Lines: Remaining goal divided by remaining days.
- Branch/Uncommitted stats: Committed additions per branch and uncommitted changes.
- Current Changes: Two mini boxes show `+` (green) and `-` (red).
- Progress Bars: Overall and daily progress with percentages.

### Graph

- Shows daily committed additions for the selected period (7~180 days).
- Shows average and max for the period.

### Settings

- `날짜 커스텀`: Use a fixed date (for retro checks).
- `목표 줄수`: Total goal line count.
- `저자 선택`: Filters by author (auto, all, or specific).
- `리포 경로`: Target repo to track.
- `1분마다 자동 업데이트`: Periodic refresh.
- `일일 목표 달성 알림`: Windows toast when today target is reached.

### Commit Memo

Simple local memo area:
- Title
- DONE list
- TODO list

Buttons:
- `메모 저장`: Save the memo into settings.
- `커밋`: Create a commit with the memo as the message.
  - Optional `자동 스테이지(git add -A)`

## Selecting a Repo

Because this toolkit itself is a Git repo, you must point the tracker at the actual project repo.

Steps:
1. Set `리포 경로` to the project folder (e.g. `C:\Users\groun\Documents\git-repositories\PROJECT-MA`).
2. Click `리포 선택`.
3. Refresh.

The repo path is stored in `app/line_tracker_ui_settings.json` under `repo_path`.

## Command Line (Optional)

You can run the CLI directly:

```bat
python app\line_tracker.py --repo C:\path\to\repo
```

The UI uses the same engine under the hood.

## Troubleshooting

- UI shows the toolkit repo instead of your project:
  - Set `리포 경로` and click `리포 선택`, then refresh.
- No output / zero lines:
  - Make sure Git is in PATH and the repo has commits.
- Slow refresh:
  - Large repos with many commits can take time. Use auto refresh sparingly.

## Notes

- Uncommitted changes include untracked text files.
- Rename handling is disabled to match GitHub-style stats.
- Works best when launched from `line_tracker_ui_click.vbs`.
