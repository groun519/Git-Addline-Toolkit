# Git Addline Toolkit

Windows-only line tracking UI for Git repos.  
Shows daily/total progress, committed vs uncommitted additions, and a 1-minute auto refresh option.  
Designed to live under a repo (e.g. `PROJECT-MA/tools/Git-Addline-Toolkit`), but can target any Git repo via the UI.

## End-user Install

다른 사용자에게 공유할 때는 소스 폴더가 아니라 설치 파일을 보내는 방식이 기준입니다.

1. `build_installer.bat`로 `dist\LineTrackerSetup.exe`를 만듭니다.
2. 그 설치 파일을 상대방에게 전달합니다.
3. 상대방은 설치 후 시작 메뉴나 바탕화면 아이콘으로 실행합니다.
4. UI에서 `리포 경로`를 설정하고 `리포 선택` -> `새로고침`을 누릅니다.

설치본 기준:
- Python은 필요 없습니다.
- Git은 필요합니다.
- 단, `vendor\PortableGit\cmd\git.exe`를 넣고 빌드하면 Git도 함께 번들됩니다.
- PortableGit 번들 위치 설명은 `vendor\PortableGit\README.md`에 정리돼 있습니다.
- 기본 설치 경로는 `%LocalAppData%\Programs\LineTracker`라서 관리자 권한 없이 설치됩니다.

## Source Run Requirements

- Windows
- Python 3.x in PATH
- Git in PATH, 또는 `LINE_TRACKER_GIT`/번들 `PortableGit`

## Source Quick Start

1. Open `line_tracker_ui_click.vbs` (double click).
2. In the UI, set `리포 경로` to the repo you want to track.
3. Click `리포 선택` (or press Enter in the path field).
4. Click `새로고침`.

The selected repo path is saved and restored on next launch.

## What Runs What

- `line_tracker_ui_click.vbs`  
  Source 실행용 런처입니다. `pythonw`가 있으면 콘솔 없이 실행하고, 없으면 `python`을 사용합니다.

- `dist\LineTrackerSetup.exe`  
  공유용 설치 파일입니다. 설치 후에는 번들 EXE로 실행되며 Python이 필요 없습니다.

Internal state files are stored in `%LocalAppData%\LineTracker`:

- `app/line_tracker_ui.py` (UI)
- `app/line_tracker.py` (metrics engine)
- `%LocalAppData%\LineTracker\line_tracker_ui_settings.json` (saved UI settings)
- `%LocalAppData%\LineTracker\line_tracker_cache.json` (computed caches)

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
- `유저 선택`: Filters by user (auto, all, or specific).
- `리포 경로`: Target repo to track.
- `1분마다 자동 업데이트`: Periodic refresh.

### Commit Memo

Simple local memo area:
- Edit one raw text block.
- The first line becomes `Title`.
- Remaining lines are parsed into `DONE` / `TODO`.
- Items can be moved between `DONE` and `TODO` with buttons in the preview.

Behavior:
- Memo text is saved automatically into settings.
- Empty state starts with a `Title / DONE / TODO` template.
- `제목 복사` / `설명 복사`로 GitHub Desktop의 `Summary` / `Description` 칸에 붙여넣을 수 있습니다.

## Selecting a Repo

Because this toolkit itself is a Git repo, you must point the tracker at the actual project repo.

Steps:
1. Set `리포 경로` to the project folder (e.g. `C:\Users\groun\Documents\git-repositories\PROJECT-MA`).
2. Click `리포 선택`.
3. Refresh.

The repo path is stored in `%LocalAppData%\LineTracker\line_tracker_ui_settings.json` under `repo_path`.

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
  - Make sure Git is available and the repo has commits.
- Installed app says Git is missing:
  - Install Git for Windows, or rebuild the installer with `vendor\PortableGit` bundled.
- Slow refresh:
  - Large repos with many commits can take time. Use auto refresh sparingly.

## Notes

- Uncommitted changes include untracked text files.
- Rename handling is disabled to match GitHub-style stats.
- Works best when launched from `line_tracker_ui_click.vbs`.
# 배포(설치 파일) 만들기

윈도우에서 설치 후 사용이 편한 방식은 `PyInstaller + Inno Setup` 조합입니다.

## 준비물
- Python 3.10+
- Inno Setup (iscc.exe가 PATH에 있어야 함)

## 선택사항: Git까지 같이 번들하기
- `vendor\PortableGit\cmd\git.exe`가 있으면 빌드 스크립트가 자동으로 설치본에 포함합니다.
- 이 경우 설치받는 사용자는 Git을 따로 설치하지 않아도 됩니다.
- 저장소에는 `vendor\PortableGit\README.md`만 추적되고, 실제 PortableGit 파일은 Git에서 제외됩니다.

## 빌드
1. `build_installer.bat` 실행
2. 스크립트가 `python -m unittest discover -s tests -v`를 먼저 실행
3. 테스트 통과 후 GUI 앱과 `LineTrackerCli.exe`를 함께 빌드
4. 설치 파일을 빌드
5. 이어서 `smoke_test_installer.bat`로 무소음 설치 + 설치본 CLI 실행 검증
6. 모든 단계 통과 후 `dist\LineTrackerSetup.exe` 사용

스모크 검증을 건너뛰고 싶으면:

```bat
set LINE_TRACKER_SKIP_SMOKE=1
build_installer.bat
```

## 결과
- 설치 후 시작메뉴/바탕화면 아이콘 제공
- 설치 폴더에 `setup\setup_check.bat` 포함
- 번들 `PortableGit`가 있으면 설치 직후 바로 실행 가능
