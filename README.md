# Git Addline Toolkit

Windows-only Git line tracking UI for any Git repository.

- Monthly progress dashboard for committed and uncommitted added lines
- Commit memo tab with GitHub Desktop-friendly summary/description copy
- Git grass tab based on daily added lines
- Theme support
- 1-minute auto refresh
- Installer build flow with tests and smoke verification

Current app version is managed by [VERSION](/c:/Users/groun/Documents/git-repositories/PROJECT-MA/tools/Git-Addline-Toolkit/VERSION).

## Main Features

- Track a target line goal for the current month
- Show committed totals, branch-only additions, uncommitted additions, and progress bars
- Show a daily additions graph for 7 to 180 days
- Edit a raw memo block that is auto-parsed into `Title / DONE / TODO`
- Copy memo output into GitHub Desktop `Summary` / `Description`
- Show a yearly Git grass view with theme-aware colors
- Filter by user
  The selector merges obvious duplicates such as primary email and GitHub noreply variants when they resolve to the same handle.
- Switch UI themes
  Built-in themes currently include `Forest`, `Cream`, `Slate`, `Dark`, `VS`, `Neon`, `Cherry`, `Discord`, and `MC`.

## End-user Install

공유할 때는 소스 폴더가 아니라 설치 파일을 보내는 방식이 기준입니다.

1. `exe_maker\build_installer.bat`로 `exe_maker\dist\LineTrackerSetup.exe`를 만듭니다.
2. 설치 파일을 전달합니다.
3. 받은 사용자는 설치 후 실행합니다.
4. UI에서 `리포 경로`를 지정하고 `리포 선택` 후 `새로고침`을 누릅니다.

설치본 기준:

- Python은 필요 없습니다.
- Git은 필요합니다.
- `vendor\PortableGit\cmd\git.exe`를 넣고 빌드하면 Git도 함께 번들됩니다.
- 기본 설치 경로는 `%LocalAppData%\Programs\LineTracker`입니다.
- 설정과 캐시는 `%LocalAppData%\LineTracker`에 저장됩니다.

업데이트:

- 기존 사용자는 새 설치 파일을 다시 실행하면 같은 위치에 덮어써서 업데이트할 수 있습니다.
- 설정과 캐시는 유지됩니다.

언인스톨:

- Windows 앱 목록 또는 제어판에서 제거할 수 있습니다.
- 앱 제거 후에도 `%LocalAppData%\LineTracker` 아래 설정/캐시는 남을 수 있습니다.

## Source Run Requirements

- Windows
- Python 3.10+
- Git in PATH, 또는 `LINE_TRACKER_GIT` / 번들 `PortableGit`

## Source Quick Start

1. [line_tracker_ui_click.vbs](/c:/Users/groun/Documents/git-repositories/PROJECT-MA/tools/Git-Addline-Toolkit/line_tracker_ui_click.vbs)를 실행합니다.
2. UI에서 `리포 경로`를 설정합니다.
3. `리포 선택`을 누릅니다.
4. `새로고침`을 누릅니다.

선택한 리포 경로와 UI 설정은 다음 실행 때 복원됩니다.

## What Runs What

- [line_tracker_ui_click.vbs](/c:/Users/groun/Documents/git-repositories/PROJECT-MA/tools/Git-Addline-Toolkit/line_tracker_ui_click.vbs)
  Source 실행용 런처입니다. `pythonw`가 있으면 콘솔 없이 실행합니다.
- [app/line_tracker_ui.pyw](/c:/Users/groun/Documents/git-repositories/PROJECT-MA/tools/Git-Addline-Toolkit/app/line_tracker_ui.pyw)
  GUI 진입점입니다.
- [app/line_tracker_ui.py](/c:/Users/groun/Documents/git-repositories/PROJECT-MA/tools/Git-Addline-Toolkit/app/line_tracker_ui.py)
  메인 UI 셸입니다.
- [app/line_tracker.py](/c:/Users/groun/Documents/git-repositories/PROJECT-MA/tools/Git-Addline-Toolkit/app/line_tracker.py)
  Git 집계 엔진과 CLI입니다.
- [exe_maker/dist/LineTrackerSetup.exe](/c:/Users/groun/Documents/git-repositories/PROJECT-MA/tools/Git-Addline-Toolkit/exe_maker/dist/LineTrackerSetup.exe)
  공유용 설치 파일입니다.

내부 상태 파일:

- `%LocalAppData%\LineTracker\line_tracker_ui_settings.json`
- `%LocalAppData%\LineTracker\line_tracker_cache.json`

## UI Overview

### Dashboard

- `오늘 날짜 / 남은 날짜`
- `일일 필요 추가줄`
- `현재 추가줄(미커밋)`
- `현재 브랜치 단독 추가줄(커밋)`
- `내 추가줄 비중`
- `전체 진행률 / 일일 진행률`
- `현재 변경 + / -`
- `일별 추가줄 그래프`

### Commit Memo Tab

- 원문 텍스트 하나를 자유롭게 편집합니다.
- 첫 줄은 제목, 나머지는 `DONE / TODO`로 자동 분리됩니다.
- 미리보기에서 항목을 `DONE`과 `TODO` 사이로 이동할 수 있습니다.
- `제목 복사` / `설명 복사`로 GitHub Desktop에 붙여넣을 수 있습니다.
- 메모는 자동 저장됩니다.

기본 양식 예시:

```text
[제목 입력]

DONE
-

TODO
-
-
```

### Git Grass Tab

- 현재 연도 전체를 2줄 레이아웃으로 표시합니다.
- 기준은 `일별 추가줄 수`입니다.
- 오늘의 미커밋 추가줄이 있으면 오늘 칸은 파란 계열로 표시됩니다.
- 하단에는 활동일, 총 추가줄, 활동일 기준 평균 줄 수를 보여줍니다.

### User Filter

- `자동(내 계정)`, `전체`, 또는 특정 유저를 선택할 수 있습니다.
- 가능한 경우 같은 계정의 여러 identity를 하나로 합쳐서 보여줍니다.

### Themes

- 상단 `테마` 콤보에서 즉시 전환할 수 있습니다.
- 테마 선택은 설정에 저장됩니다.

## Command Line

CLI도 직접 실행할 수 있습니다.

```bat
python app\line_tracker.py --repo C:\path\to\repo
```

UI는 같은 엔진을 사용합니다.

## Build Installer

윈도우 배포는 `PyInstaller + Inno Setup` 조합을 사용합니다.

### Prerequisites

- Python 3.10+
- Inno Setup

### Optional: Bundle Git

- `vendor\PortableGit\cmd\git.exe`가 있으면 빌드 시 설치본에 포함됩니다.
- 이 경우 설치받는 사용자는 Git을 따로 설치하지 않아도 됩니다.
- 위치 설명은 [vendor/PortableGit/README.md](/c:/Users/groun/Documents/git-repositories/PROJECT-MA/tools/Git-Addline-Toolkit/vendor/PortableGit/README.md)에 있습니다.

### Optional: Custom App Icon

- `assets\line_tracker.ico`를 두면 소스 UI, PyInstaller EXE, 설치파일 아이콘에 같이 사용됩니다.
- 아이콘이 없으면 기존처럼 기본 아이콘으로 빌드됩니다.

### Versioning

- 앱 버전 원본은 [VERSION](/c:/Users/groun/Documents/git-repositories/PROJECT-MA/tools/Git-Addline-Toolkit/VERSION) 한 군데입니다.
- 형식은 `V0.1.000`처럼 사용합니다.
- 빌드 스크립트와 설치 스크립트는 이 값을 같이 사용합니다.

### Build Steps

1. `exe_maker\build_installer.bat` 실행
2. `python -m unittest discover -s tests -t . -v` 실행
3. 테스트 통과 후 GUI 앱과 `LineTrackerCli.exe` 빌드
4. Inno Setup으로 설치 파일 생성
5. `exe_maker\smoke_test_installer.bat`로 무소음 설치 + 설치본 CLI 스모크 검증
6. 최종 결과물은 `exe_maker\dist\LineTrackerSetup.exe`

스모크 검증을 건너뛰고 싶으면:

```bat
set LINE_TRACKER_SKIP_SMOKE=1
exe_maker\build_installer.bat
```

## Troubleshooting

- 설치본에서 Git이 없다고 나옴
  Git for Windows를 설치하거나 `vendor\PortableGit`를 번들해서 다시 빌드하세요.
- 내 프로젝트가 아니라 툴 저장소가 잡힘
  `리포 경로`를 프로젝트 폴더로 바꾸고 `리포 선택` 후 `새로고침` 하세요.
- 0줄만 보임
  Git이 가능한 리포인지, 선택한 유저 필터가 맞는지 확인하세요.
- 새 설치파일로 업데이트하고 싶음
  같은 설치파일을 다시 실행하면 됩니다.

## Notes

- 미커밋 추가줄에는 untracked text file도 포함됩니다.
- rename handling은 GitHub-style 통계에 가깝게 맞추기 위해 꺼져 있습니다.
- 현재 저장소에는 테스트 23개가 포함돼 있습니다.
