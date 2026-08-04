#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass

LANG_OPTIONS = {"한국어": "ko", "English": "en"}
LANG_DISPLAY = {"ko": "한국어", "en": "English"}
TEXT = {
    "ko": {
        "window_title": "Line Tracker",
        "lang_label": "언어",
        "theme_label": "테마",
        "theme_forest": "포레스트",
        "theme_cream": "크림",
        "theme_slate": "슬레이트",
        "theme_dark": "다크",
        "theme_harddark": "하드다크",
        "theme_vs": "VS",
        "theme_neon": "네온",
        "theme_cherry": "체리",
        "theme_discord": "디스코드",
        "theme_mc": "MC",
        "theme_cyberpunk": "사이버펑크",
        "repo_label": "리포 경로",
        "repo_select": "리포 선택",
        "graph_title": "일별 활동 그래프",
        "graph_period": "기간",
        "graph_settings": "그래프 설정",
        "graph_settings_title": "그래프 설정",
        "graph_metrics": "표시 항목",
        "graph_show_additions": "추가줄",
        "graph_show_deletions": "제거줄",
        "graph_show_commits": "커밋",
        "graph_curve": "곡선화",
        "graph_apply": "적용",
        "graph_series_additions": "추가줄",
        "graph_series_deletions": "제거줄",
        "graph_series_commits": "커밋",
        "commit_history_section": "작업 전적",
        "commit_history_empty": "표시할 커밋이 없습니다.",
        "graph_summary_item": "{label} 평균 {avg} | 최대 {max}",
        "graph_summary_empty": "표시할 그래프 항목을 선택하세요.",
        "tab_activity": "활동",
        "tab_schedule": "일정",
        "tab_grass": "Git 잔디",
        "tab_history": "이력",
        "schedule_title": "일정 계획",
        "schedule_select": "MD 선택",
        "schedule_reload": "다시 읽기",
        "schedule_open_location": "파일 위치 열기",
        "schedule_no_file": "일정 MD가 연결되지 않음",
        "schedule_unconfigured_title": "일정 파일을 연결하세요",
        "schedule_unconfigured_hint": "리포지토리의 일정 MD를 선택하면 날짜와 상태별로 정리해 표시합니다.",
        "schedule_empty_title": "표시할 일정이 없습니다.",
        "schedule_empty_hint": "파일은 정상적으로 불러왔지만 인식된 일정 항목이 없습니다.",
        "schedule_error_title": "일정 파일을 불러오지 못했습니다.",
        "schedule_summary_total": "전체",
        "schedule_summary_active": "미완료",
        "schedule_summary_done": "완료",
        "schedule_group_overdue": "{date} · 지연",
        "schedule_group_today": "오늘 · {date}",
        "schedule_group_date": "{date}",
        "schedule_group_unscheduled": "백로그",
        "schedule_group_completed": "완료",
        "schedule_status_planned": "예정",
        "schedule_status_in_progress": "진행",
        "schedule_status_review": "검수",
        "schedule_status_next": "다음",
        "schedule_status_hold": "보류",
        "schedule_status_done": "완료",
        "schedule_status_overdue": "지연",
        "grass_hint": "칸 하나가 하루입니다. 진할수록 그날 추가한 줄 수가 많고, 테두리는 오늘입니다.",
        "grass_summary": "활동 {active}일 | 총 {total}줄 | 평균 {avg}줄/활동일",
        "grass_empty": "표시할 기록이 없습니다.",
        "grass_day_mon": "월",
        "grass_day_wed": "수",
        "grass_day_fri": "금",
        "grass_legend_zero": "0줄",
        "grass_legend_range": "{start}~{end}줄",
        "grass_legend_open": "{start}줄+",
        "grass_uncommitted_legend": "오늘",
        "settings": "설정",
        "settings_general_tab": "일반",
        "settings_repo_tab": "리포지토리",
        "settings_tracking_tab": "추적",
        "settings_schedule_tab": "일정",
        "schedule_path_label": "일정 MD 경로",
        "schedule_path_hint": "리포 내부 파일은 상대 경로로 저장되어 다른 컴퓨터에서도 그대로 사용할 수 있습니다.",
        "schedule_path_apply": "경로 적용",
        "schedule_dialog_title": "일정 MD 선택",
        "schedule_error_missing": "일정 MD 파일이 존재하지 않습니다.",
        "schedule_error_extension": "Markdown 파일(.md)을 선택하세요.",
        "schedule_error_open_location": "일정 파일 위치를 열지 못했습니다.",
        "custom_date": "커스텀 날짜 사용",
        "apply_date": "날짜 적용",
        "goal_label": "목표 줄수",
        "apply_goal": "목표 적용",
        "author_label": "유저 선택",
        "apply_author": "유저 적용",
        "author_auto": "자동(내 계정)",
        "author_all": "전체",
        "auto_refresh": "1분마다 자동 업데이트",
        "progress": "진행률",
        "overall_progress": "전체 진행률",
        "daily_progress": "일일 진행률",
        "progress_goal_reached": "목표 달성",
        "current_changes": "현재 변경",
        "daily_stats_section": "일일 통계",
        "branch_stats_section": "브랜치 통계",
        "overall_stats_section": "전체 통계",
        "user_stats_section": "유저 통계",
        "refresh": "새로고침",
        "copy": "복사",
        "cancel": "취소",
        "compact_restore": "복원",
        "compact_title": "축소 모드",
        "compact_mode_to_strip": "최소화",
        "compact_mode_to_card": "카드",
        "compact_opacity": "투명도",
        "compact_opacity_value": "{value}",
        "compact_today_progress": "오늘 진행",
        "compact_progress_complete": "오늘 목표 달성",
        "compact_progress_value_text": "{percent}% ({done}/{target})",
        "compact_progress_inline_complete": "달성",
        "compact_progress_inline_text": "{percent}% · {done}/{target}",
        "compact_progress_remaining": "{remaining}줄 남음",
        "compact_progress_over": "목표 초과 +{extra}줄",
        "compact_delta": "추가줄",
        "compact_clock": "날짜 및 시간",
        "compact_datetime_text": "{date} | {time}",
        "compact_refresh_short": "새로고침",
        "compact_restore_short": "복원",
        "loading": "새로고침 중...",
        "loading_detail": "사용자 정보를 불러오는 중...",
        "status_updated": "업데이트: {time}",
        "status_auto_suffix": " (자동 1분 ON)",
        "status_clipboard": "클립보드에 복사됨",
        "status_summary_copied": "커밋 제목이 클립보드에 복사됨",
        "status_description_copied": "커밋 설명이 클립보드에 복사됨",
        "status_error": "오류 발생",
        "status_auto_off": "자동 업데이트 OFF",
        "status_repo_needed": "리포 경로를 선택한 뒤 새로고침하세요.",
        "error_date_format": "날짜 형식은 YYYY-MM-DD 로 입력하세요.",
        "error_goal": "목표 줄수는 1 이상의 정수로 입력하세요.",
        "error_repo_missing": "리포 경로가 존재하지 않습니다.",
        "error_repo_invalid": "유효한 Git 리포가 아닙니다.",
        "error_need_title": "제목을 입력하세요.",
        "repo_not_selected": "리포 미선택",
        "today_label": "오늘 날짜",
        "days_left_label": "남은 날짜({month})",
        "day_suffix": "일",
        "daily_required_label": "일일 필요 추가줄",
        "after_commit_prefix": "커밋 후",
        "after_commit_daily_label": "커밋 후 일일 필요 추가줄",
        "per_day_suffix": "줄/일",
        "current_uncommitted_label": "현재 추가줄(미커밋)",
        "lines_suffix": "줄",
        "branch_only_label": "현재 브랜치 단독 추가줄(커밋)",
        "branch_active_days_label": "브랜치 작업일 수",
        "user_total_label": "유저 누적 추가줄",
        "user_active_days_label": "유저 작업일 수",
        "share_label": "내 추가줄 비중(전체 대비)",
        "progress_breakdown": "메인 {main} + 브랜치 {branch} + 미커밋 {uncommitted}",
        "graph_summary": "최근 {days}일 평균 {avg}줄/일 | 최대 {max}줄",
        "graph_scale_adaptive": "적응형 축",
        "repo_dialog_title": "리포 선택",
        "setup_title": "환경 점검",
        "git_missing": "Git을 찾을 수 없습니다.\nGit for Windows를 설치하거나, 설치본에 PortableGit을 함께 포함하세요.\n지금 다운로드 페이지를 여시겠습니까?",
        "project_total_label": "프로젝트 전체 코드줄 수",
        "project_language_breakdown": "언어별 코드 구성",
    },
    "en": {
        "window_title": "Line Tracker",
        "lang_label": "Language",
        "theme_label": "Theme",
        "theme_forest": "Forest",
        "theme_cream": "Cream",
        "theme_slate": "Slate",
        "theme_dark": "Dark",
        "theme_harddark": "Hard Dark",
        "theme_vs": "VS",
        "theme_neon": "Neon",
        "theme_cherry": "Cherry",
        "theme_discord": "Discord",
        "theme_mc": "MC",
        "theme_cyberpunk": "Cyberpunk",
        "repo_label": "Repository",
        "repo_select": "Browse",
        "graph_title": "Daily Activity Graph",
        "graph_period": "Range",
        "graph_settings": "Graph Settings",
        "graph_settings_title": "Graph Settings",
        "graph_metrics": "Series",
        "graph_show_additions": "Additions",
        "graph_show_deletions": "Deletions",
        "graph_show_commits": "Commits",
        "graph_curve": "Smoothing",
        "graph_apply": "Apply",
        "graph_series_additions": "Additions",
        "graph_series_deletions": "Deletions",
        "graph_series_commits": "Commits",
        "commit_history_section": "Work History",
        "commit_history_empty": "No commits to display.",
        "graph_summary_item": "{label} avg {avg} | max {max}",
        "graph_summary_empty": "Select at least one graph series.",
        "tab_activity": "Activity",
        "tab_schedule": "Schedule",
        "tab_grass": "Git Grass",
        "tab_history": "History",
        "schedule_title": "Schedule Plan",
        "schedule_select": "Select MD",
        "schedule_reload": "Reload",
        "schedule_open_location": "Open File Location",
        "schedule_no_file": "No schedule MD connected",
        "schedule_unconfigured_title": "Connect a schedule file",
        "schedule_unconfigured_hint": "Select a repository schedule MD to organize it by date and status.",
        "schedule_empty_title": "No schedule items to display",
        "schedule_empty_hint": "The file loaded successfully, but no schedule items were recognized.",
        "schedule_error_title": "Could not load the schedule file",
        "schedule_summary_total": "Total",
        "schedule_summary_active": "Open",
        "schedule_summary_done": "Done",
        "schedule_group_overdue": "{date} · Overdue",
        "schedule_group_today": "Today · {date}",
        "schedule_group_date": "{date}",
        "schedule_group_unscheduled": "Backlog",
        "schedule_group_completed": "Completed",
        "schedule_status_planned": "Planned",
        "schedule_status_in_progress": "Active",
        "schedule_status_review": "Review",
        "schedule_status_next": "Next",
        "schedule_status_hold": "Hold",
        "schedule_status_done": "Done",
        "schedule_status_overdue": "Overdue",
        "grass_hint": "Each cell is a day. Darker cells mean more added lines, and the outline marks today.",
        "grass_summary": "{active} active days | {total} total lines | {avg} avg lines/active day",
        "grass_empty": "No history to display.",
        "grass_day_mon": "Mon",
        "grass_day_wed": "Wed",
        "grass_day_fri": "Fri",
        "grass_legend_zero": "0 lines",
        "grass_legend_range": "{start}-{end} lines",
        "grass_legend_open": "{start}+ lines",
        "grass_uncommitted_legend": "Today",
        "settings": "Settings",
        "settings_general_tab": "General",
        "settings_repo_tab": "Repository",
        "settings_tracking_tab": "Tracking",
        "settings_schedule_tab": "Schedule",
        "schedule_path_label": "Schedule MD Path",
        "schedule_path_hint": "Files inside the repository are saved as relative paths for portability.",
        "schedule_path_apply": "Apply Path",
        "schedule_dialog_title": "Select Schedule MD",
        "schedule_error_missing": "The schedule MD file does not exist.",
        "schedule_error_extension": "Select a Markdown (.md) file.",
        "schedule_error_open_location": "Could not open the schedule file location.",
        "custom_date": "Use Custom Date",
        "apply_date": "Apply Date",
        "goal_label": "Goal Lines",
        "apply_goal": "Apply Goal",
        "author_label": "User",
        "apply_author": "Apply User",
        "author_auto": "Auto (me)",
        "author_all": "All",
        "auto_refresh": "Auto refresh (1 min)",
        "progress": "Progress",
        "overall_progress": "Overall Progress",
        "daily_progress": "Daily Progress",
        "progress_goal_reached": "Goal reached",
        "current_changes": "Current Changes",
        "daily_stats_section": "Daily Stats",
        "branch_stats_section": "Branch Stats",
        "overall_stats_section": "Overall Stats",
        "user_stats_section": "User Stats",
        "refresh": "Refresh",
        "copy": "Copy",
        "cancel": "Cancel",
        "compact_restore": "Restore",
        "compact_title": "Compact Mode",
        "compact_mode_to_strip": "Minimize",
        "compact_mode_to_card": "Card",
        "compact_opacity": "Opacity",
        "compact_opacity_value": "{value}",
        "compact_today_progress": "Today's Status",
        "compact_progress_complete": "Goal complete today",
        "compact_progress_value_text": "{percent}% ({done}/{target})",
        "compact_progress_inline_complete": "Done",
        "compact_progress_inline_text": "{percent}% · {done}/{target}",
        "compact_progress_remaining": "{remaining} lines left",
        "compact_progress_over": "Exceeded by +{extra} lines",
        "compact_delta": "Delta",
        "compact_clock": "Date & Time",
        "compact_datetime_text": "{date} | {time}",
        "compact_refresh_short": "Refresh",
        "compact_restore_short": "Restore",
        "loading": "Refreshing...",
        "loading_detail": "Loading user information...",
        "status_updated": "Updated: {time}",
        "status_auto_suffix": " (auto 1 min ON)",
        "status_clipboard": "Copied to clipboard",
        "status_summary_copied": "Commit summary copied to clipboard",
        "status_description_copied": "Commit description copied to clipboard",
        "status_error": "Error",
        "status_auto_off": "Auto refresh OFF",
        "status_repo_needed": "Choose a repository path, then refresh.",
        "error_date_format": "Date must be YYYY-MM-DD.",
        "error_goal": "Goal lines must be a positive integer.",
        "error_repo_missing": "Repository path does not exist.",
        "error_repo_invalid": "Not a valid Git repository.",
        "error_need_title": "Please enter a title.",
        "repo_not_selected": "No repository selected",
        "today_label": "Today",
        "days_left_label": "Days left ({month})",
        "day_suffix": " days",
        "daily_required_label": "Daily required additions",
        "after_commit_prefix": "After commit",
        "after_commit_daily_label": "Daily required (after commit)",
        "per_day_suffix": " lines/day",
        "current_uncommitted_label": "Current additions (uncommitted)",
        "lines_suffix": " lines",
        "branch_only_label": "Current branch additions (committed)",
        "branch_active_days_label": "Branch active days",
        "user_total_label": "User total additions",
        "user_active_days_label": "User active days",
        "share_label": "My additions share",
        "project_total_label": "Project total code lines",
        "project_language_breakdown": "Code by language",
        "progress_breakdown": "Main {main} + Branch {branch} + Uncommitted {uncommitted}",
        "graph_summary": "Last {days} days avg {avg} lines/day | max {max} lines",
        "graph_scale_adaptive": "Adaptive scale",
        "repo_dialog_title": "Select Repository",
        "setup_title": "Environment Check",
        "git_missing": "Git was not found.\nInstall Git for Windows or bundle PortableGit with the app.\nOpen the download page now?",
    },
}

FONT_TITLE = ("Bahnschrift", 18, "bold")
FONT_VERSION = ("Bahnschrift", 9)
FONT_SUBTITLE = ("Bahnschrift", 10)
FONT_BODY = ("Bahnschrift", 10)
FONT_SECTION = ("Bahnschrift", 11, "bold")
FONT_COMPACT_VALUE = ("Bahnschrift", 14, "bold")
FONT_COMPACT_TOOL = ("Bahnschrift", 9)
FONT_COMPACT_CLOCK = ("Bahnschrift", 11)
FONT_TILE_LABEL = ("Bahnschrift", 9)
FONT_TILE_VALUE = ("Bahnschrift", 12, "bold")
FONT_CHIP = ("Bahnschrift", 9)
FONT_COMPACT_META = ("Bahnschrift", 10)
FONT_COMPACT_BAR_VALUE = ("Bahnschrift", 9, "bold")
FONT_MONO = ("Cascadia Mono", 10)

@dataclass(frozen=True)
class LayoutMetrics:
    header_gap: int
    header_group_gap: int
    header_subtitle_gap: int
    section_gap: int
    section_title_gap: int
    meta_gap: int
    chip_pad_x: int
    chip_pad_y: int
    chip_gap: int
    tile_pad_x: int
    tile_pad_y: int
    tile_gap_x: int
    tile_gap_y: int
    tile_value_gap: int
    card_pad_x: int
    card_pad_y: int
    card_inner_gap: int
    progress_block_gap: int
    note_tab_gap: int
    footer_gap: int
    control_small_gap: int
    control_large_gap: int
    panel_gap_x: int


def build_layout_metrics(scale: float) -> LayoutMetrics:
    density = min(max(scale, 0.55), 1.0)
    base = max(3, int(round(4 * density)))
    vertical = max(2, int(round(base * 0.75)))
    return LayoutMetrics(
        header_gap=vertical + 2,
        header_group_gap=base * 2,
        header_subtitle_gap=max(1, vertical - 1),
        section_gap=vertical,
        section_title_gap=max(2, vertical - 1),
        meta_gap=vertical + 2,
        chip_pad_x=base * 2,
        chip_pad_y=max(3, vertical),
        chip_gap=base * 2,
        tile_pad_x=base * 2 + 2,
        tile_pad_y=vertical,
        tile_gap_x=base * 2,
        tile_gap_y=max(2, vertical - 1),
        tile_value_gap=1,
        card_pad_x=base * 3,
        card_pad_y=vertical + 2,
        card_inner_gap=vertical,
        progress_block_gap=vertical + 3,
        note_tab_gap=vertical,
        footer_gap=vertical + 3,
        control_small_gap=max(2, vertical - 1),
        control_large_gap=vertical + 2,
        panel_gap_x=base * 3,
    )


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    cleaned = value.strip().lstrip("#")
    if len(cleaned) != 6:
        raise ValueError(f"Expected #RRGGBB color, got {value!r}")
    return tuple(int(cleaned[index:index + 2], 16) for index in (0, 2, 4))


def blend_hex(base: str, overlay: str, ratio: float) -> str:
    mix_ratio = min(max(ratio, 0.0), 1.0)
    base_rgb = _hex_to_rgb(base)
    overlay_rgb = _hex_to_rgb(overlay)
    blended = tuple(
        round(base_channel + (overlay_channel - base_channel) * mix_ratio)
        for base_channel, overlay_channel in zip(base_rgb, overlay_rgb)
    )
    return "#" + "".join(f"{channel:02x}" for channel in blended)


def contrast_text_color(background: str) -> str:
    red, green, blue = _hex_to_rgb(background)
    luminance = ((red * 299) + (green * 587) + (blue * 114)) / 1000
    return "#10161c" if luminance >= 150 else "#f5f8fb"


def _hex_to_colorref(value: str) -> int:
    red, green, blue = _hex_to_rgb(value)
    return red | (green << 8) | (blue << 16)
