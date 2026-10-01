from __future__ import annotations

from dataclasses import dataclass

from line_tracker_theme import ThemePalette
from line_tracker_ui_resources import blend_hex, contrast_text_color


PANEL_PADDING = 12
PANEL_SPACING = 8
PANEL_RADIUS = 12
CARD_RADIUS = 9
STAT_CARD_MIN_HEIGHT = 58
LIST_ROW_MIN_HEIGHT = 30


@dataclass(frozen=True)
class QtThemeTokens:
    background: str
    chrome: str
    surface: str
    card: str
    raised: str
    text: str
    muted: str
    faint: str
    border: str
    accent: str
    accent_text: str
    hover: str
    pressed: str
    selection: str
    focus: str
    success: str
    danger: str
    warning: str
    canvas: str
    grid: str


def build_theme_tokens(palette: ThemePalette) -> QtThemeTokens:
    return QtThemeTokens(
        background=palette.app_bg,
        chrome=blend_hex(palette.app_bg, palette.card_bg, 0.35),
        surface=palette.card_bg,
        card=blend_hex(palette.card_bg, palette.app_bg, 0.18),
        raised=blend_hex(palette.card_bg, palette.text, 0.07),
        text=palette.text,
        muted=palette.muted_text,
        faint=blend_hex(palette.muted_text, palette.app_bg, 0.45),
        border=palette.border,
        accent=palette.accent,
        accent_text=contrast_text_color(palette.accent),
        hover=blend_hex(palette.card_bg, palette.text, 0.12),
        pressed=blend_hex(palette.card_bg, palette.text, 0.19),
        selection=blend_hex(palette.card_bg, palette.accent, 0.22),
        focus=blend_hex(palette.accent, palette.text, 0.32),
        success=palette.success,
        danger=palette.danger,
        warning=palette.accent_alt,
        canvas=palette.canvas_bg,
        grid=palette.graph_grid,
    )


def build_stylesheet(tokens: QtThemeTokens) -> str:
    return f"""
        QWidget {{
            color: {tokens.text};
            font-family: "Bahnschrift", "Malgun Gothic", "Segoe UI";
            font-size: 12px;
        }}
        QMainWindow, QDialog {{ background: {tokens.background}; }}
        QLabel {{ background: transparent; border: 0; }}

        QFrame#TitleBar {{
            background: {tokens.chrome};
            border: 0;
            border-bottom: 1px solid {tokens.border};
        }}
        QLabel#TitleBarTitle {{ font-weight: 800; font-size: 12px; }}
        QLabel#TitleBarVersion {{ color: {tokens.muted}; font-size: 10px; }}

        QWidget#AppContent {{ background: {tokens.background}; }}
        QFrame#DialogContent {{ background: {tokens.background}; border: 1px solid {tokens.border}; border-top: 0; }}
        QFrame#HeaderAccent {{ background: {tokens.accent}; border: 0; }}
        QLabel#ProjectTitle {{ font-size: 24px; font-weight: 900; }}
        QLabel#ProjectDate {{ color: {tokens.muted}; font-size: 12px; font-weight: 700; }}
        QLabel#ProjectRef {{ color: {tokens.muted}; font-size: 11px; }}
        QLabel#SectionTitle {{ font-size: 14px; font-weight: 900; }}
        QLabel#PanelTitle {{ font-size: 14px; font-weight: 900; }}
        QLabel#MutedLabel {{ color: {tokens.muted}; }}
        QLabel#StatusLabel {{ color: {tokens.muted}; font-size: 11px; }}
        QLabel#DeltaAdd {{ color: {tokens.success}; font-weight: 800; }}
        QLabel#DeltaRemove {{ color: {tokens.danger}; font-weight: 800; }}
        QLabel#CommitCount {{ color: {tokens.muted}; font-weight: 700; }}
        QPushButton#StatsTabButton {{
            min-height: 27px;
            padding: 2px 8px;
            color: {tokens.muted};
            background: {tokens.raised};
            border: 1px solid {tokens.border};
            border-radius: 6px;
            font-weight: 800;
        }}
        QPushButton#StatsTabButton:hover {{ color: {tokens.text}; background: {tokens.hover}; }}
        QPushButton#StatsTabButton:checked {{ color: {tokens.accent_text}; background: {tokens.accent}; border-color: {tokens.accent}; }}

        QFrame#Panel {{
            background: {tokens.surface};
            border: 1px solid {tokens.border};
            border-radius: {PANEL_RADIUS}px;
        }}
        QFrame#WorkspacePage {{ background: {tokens.surface}; border: 0; }}
        QFrame#SummaryStrip {{
            background: {tokens.raised};
            border: 0;
            border-radius: {CARD_RADIUS}px;
        }}
        QLabel#SummaryMetric {{ color: {tokens.muted}; font-weight: 800; }}
        QPushButton#ScheduleFilterButton {{
            min-height: 25px;
            padding: 2px 9px;
            color: {tokens.muted};
            background: transparent;
            border: 0;
            border-radius: 6px;
            font-weight: 800;
        }}
        QPushButton#ScheduleFilterButton:hover {{ color: {tokens.text}; background: {tokens.hover}; }}
        QPushButton#ScheduleFilterButton:checked {{ color: {tokens.accent_text}; background: {tokens.accent}; }}
        QLabel#ScheduleGroup {{ color: {tokens.text}; font-size: 12px; font-weight: 900; padding-top: 6px; }}
        QLabel#EmptyTitle {{ color: {tokens.text}; font-size: 14px; font-weight: 900; }}
        QLabel#ScheduleItemTitle, QLabel#HistorySubject {{ color: {tokens.text}; font-weight: 800; }}
        QLabel#ScheduleItemTitleDone {{ color: {tokens.muted}; font-weight: 700; }}
        QLabel#ScheduleStatus {{ font-size: 10px; font-weight: 900; }}
        QLabel#ExpandableTextLabel {{ color: {tokens.muted}; }}
        QPushButton#InlineButton {{
            min-height: 20px;
            max-height: 20px;
            padding: 0 4px;
            color: {tokens.accent};
            background: transparent;
            border: 0;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 800;
            text-align: left;
        }}
        QPushButton#InlineButton:hover {{ color: {tokens.text}; background: {tokens.hover}; }}
        QFrame#ScheduleCard {{
            background: {tokens.card};
            border: 1px solid {tokens.grid};
            border-radius: {CARD_RADIUS}px;
        }}
        QFrame#ScheduleCard:hover {{ background: {tokens.hover}; border-color: {tokens.focus}; }}
        QPushButton#ScheduleCardAction {{
            min-width: 24px;
            max-width: 24px;
            min-height: 24px;
            max-height: 24px;
            padding: 0;
            background: transparent;
            border: 0;
            border-radius: 6px;
        }}
        QPushButton#ScheduleCardAction:hover {{ background: {tokens.raised}; }}
        QFrame#HistoryRow {{
            background: transparent;
            border: 0;
            border-bottom: 1px solid {tokens.grid};
            border-radius: 0;
        }}
        QFrame#HistoryRow:hover {{ background: {tokens.hover}; }}
        QFrame#HistoryRow:focus {{ background: {tokens.hover}; border-left: 2px solid {tokens.accent}; }}
        QLabel#CommitDetailSubject {{ color: {tokens.text}; font-size: 17px; font-weight: 900; }}
        QFrame#CommitDetailMeta {{
            background: {tokens.raised};
            border: 1px solid {tokens.grid};
            border-radius: {CARD_RADIUS}px;
        }}
        QLabel#CommitDetailField {{ color: {tokens.muted}; font-size: 11px; font-weight: 800; }}
        QLabel#CommitDetailValue {{ color: {tokens.text}; }}
        QFrame#CommitFileRow {{
            background: transparent;
            border: 0;
            border-bottom: 1px solid {tokens.grid};
        }}
        QFrame#CommitFileRow:hover {{ background: {tokens.hover}; }}
        QLabel#CommitFilePath {{ color: {tokens.text}; }}
        QFrame#StatCard {{
            background: {tokens.card};
            border: 1px solid {tokens.grid};
            border-radius: {CARD_RADIUS}px;
        }}
        QFrame#StatAccent {{ background: {tokens.accent}; border: 0; border-radius: 2px; }}
        QLabel#StatLabel {{ color: {tokens.muted}; font-size: 11px; }}
        QLabel#StatValue {{ color: {tokens.text}; font-size: 16px; font-weight: 900; }}

        QFrame#StartupCard {{
            background: {tokens.surface};
            border: 1px solid {tokens.border};
            border-radius: 14px;
        }}
        QLabel#StartupEyebrow {{ color: {tokens.accent}; font-size: 10px; font-weight: 900; }}
        QLabel#StartupHeading {{ color: {tokens.text}; font-size: 20px; font-weight: 900; }}
        QLabel#StartupStatus {{ color: {tokens.muted}; min-height: 32px; }}
        QFrame#StartupPathCard {{
            background: {tokens.card};
            border: 1px solid {tokens.grid};
            border-radius: {CARD_RADIUS}px;
        }}
        QLabel#StartupRepoName {{ color: {tokens.text}; font-weight: 900; }}
        QLabel#StartupRepoPath {{ color: {tokens.muted}; font-size: 10px; }}
        QLabel#StartupProgressValue {{ color: {tokens.text}; min-width: 34px; font-weight: 900; }}
        QProgressBar#StartupProgress {{
            min-height: 8px;
            max-height: 8px;
            border: 0;
            border-radius: 4px;
            background: {tokens.raised};
        }}
        QProgressBar#StartupProgress::chunk {{
            border-radius: 4px;
            background: {tokens.accent};
        }}

        QPushButton {{
            min-height: 34px;
            padding: 0 16px;
            border: 1px solid {tokens.border};
            border-radius: 9px;
            background: {tokens.raised};
            color: {tokens.text};
            font-weight: 700;
        }}
        QPushButton:hover {{ background: {tokens.hover}; border-color: {tokens.focus}; }}
        QPushButton:pressed {{ background: {tokens.pressed}; }}
        QPushButton:disabled {{ color: {tokens.faint}; background: {tokens.card}; border-color: {tokens.border}; }}
        QPushButton#PrimaryButton {{
            color: {tokens.accent_text};
            background: {tokens.accent};
            border-color: {tokens.accent};
        }}
        QPushButton#PrimaryButton:hover {{ background: {blend_hex(tokens.accent, tokens.text, 0.16)}; }}
        QPushButton#PrimaryButton:pressed {{ background: {blend_hex(tokens.accent, tokens.background, 0.22)}; }}
        QPushButton#PrimaryButton:disabled {{
            color: {tokens.faint};
            background: {tokens.card};
            border-color: {tokens.border};
        }}
        QPushButton#IconButton, QPushButton#WindowButton, QPushButton#WindowCloseButton {{
            min-width: 30px;
            max-width: 30px;
            min-height: 30px;
            max-height: 30px;
            padding: 0;
            border: 0;
            border-radius: 8px;
            background: transparent;
        }}
        QPushButton#IconButton:hover, QPushButton#WindowButton:hover {{ background: {tokens.hover}; }}
        QPushButton#WindowCloseButton:hover {{ background: {tokens.danger}; }}

        QLineEdit, QComboBox, QSpinBox {{
            min-height: 34px;
            padding: 0 10px;
            color: {tokens.text};
            background: {tokens.raised};
            border: 1px solid {tokens.border};
            border-radius: 9px;
            selection-background-color: {tokens.selection};
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {tokens.focus}; }}
        QPlainTextEdit {{
            padding: 8px;
            color: {tokens.text};
            background: {tokens.raised};
            border: 1px solid {tokens.border};
            border-radius: 9px;
            selection-color: {tokens.text};
            selection-background-color: {tokens.selection};
        }}
        QPlainTextEdit:focus {{ border-color: {tokens.focus}; }}
        QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDateEdit:disabled {{
            color: {tokens.faint}; background: {tokens.card}; border-color: {tokens.border};
        }}
        QComboBox::drop-down {{
            width: 28px;
            border: 0;
            border-left: 1px solid {tokens.border};
            background: {tokens.card};
        }}
        QComboBox::down-arrow {{ width: 0; height: 0; }}
        QComboBox QAbstractItemView {{
            color: {tokens.text};
            background: {tokens.surface};
            border: 1px solid {tokens.focus};
            selection-color: {tokens.text};
            selection-background-color: {tokens.selection};
            outline: 0;
        }}
        QDateEdit {{
            min-height: 34px;
            padding: 0 10px;
            color: {tokens.text};
            background: {tokens.raised};
            border: 1px solid {tokens.border};
            border-radius: 9px;
            selection-background-color: {tokens.selection};
        }}
        QDateEdit:focus {{ border-color: {tokens.focus}; }}
        QDateEdit::drop-down {{
            width: 28px;
            border: 0;
            border-left: 1px solid {tokens.border};
            background: {tokens.card};
        }}
        QDateEdit::down-arrow {{ width: 0; height: 0; }}

        QCheckBox {{ spacing: 8px; color: {tokens.text}; }}
        QCheckBox::indicator {{
            width: 15px; height: 15px;
            border: 1px solid {tokens.border};
            border-radius: 4px;
            background: {tokens.raised};
        }}
        QCheckBox::indicator:hover {{ border-color: {tokens.focus}; background: {tokens.hover}; }}
        QCheckBox::indicator:checked {{ background: {tokens.accent}; border-color: {tokens.accent}; }}
        QCheckBox::indicator:disabled {{ background: {tokens.card}; border-color: {tokens.border}; }}

        QSlider::groove:horizontal {{ height: 4px; background: {tokens.border}; border-radius: 2px; }}
        QSlider::sub-page:horizontal {{ background: {tokens.accent}; border-radius: 2px; }}
        QSlider::handle:horizontal {{
            width: 13px; margin: -5px 0;
            background: {tokens.text}; border: 2px solid {tokens.accent}; border-radius: 7px;
        }}
        QSlider::groove:vertical {{ width: 3px; background: {tokens.border}; border-radius: 1px; }}
        QSlider::sub-page:vertical {{ background: {tokens.accent}; border-radius: 1px; }}
        QSlider::handle:vertical {{
            height: 9px; margin: 0 -3px;
            background: {tokens.text}; border: 1px solid {tokens.accent}; border-radius: 4px;
        }}

        QTabWidget::pane {{
            background: {tokens.surface};
            border: 1px solid {tokens.border};
            border-radius: {PANEL_RADIUS}px;
            top: -1px;
        }}
        QTabBar::tab {{
            min-width: 96px;
            min-height: 34px;
            padding: 0 12px;
            color: {tokens.muted};
            background: transparent;
            border: 1px solid transparent;
            border-radius: 9px;
        }}
        QTabBar::tab:hover {{ color: {tokens.text}; background: {tokens.hover}; }}
        QTabBar::tab:selected {{ color: {tokens.accent_text}; background: {tokens.accent}; }}
        QTabWidget#WorkspaceTabs::pane {{
            background: {tokens.surface};
            border: 1px solid {tokens.border};
            border-radius: {PANEL_RADIUS}px;
            top: -1px;
        }}
        QTabWidget#WorkspaceTabs QTabBar::tab {{ min-width: 52px; padding: 0 6px; }}

        QScrollArea {{ background: transparent; border: 0; }}
        QScrollArea > QWidget > QWidget {{ background: transparent; }}
        QScrollBar:vertical {{ width: 7px; background: transparent; margin: 2px; }}
        QScrollBar::handle:vertical {{ min-height: 36px; background: {tokens.border}; border-radius: 3px; }}
        QScrollBar::handle:vertical:hover {{ background: {tokens.faint}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ height: 0; background: transparent; }}

        QFrame#OverlayPanel {{
            background: {tokens.surface};
            border: 1px solid {tokens.border};
            border-radius: 10px;
        }}
        QLabel#OverlayTitle {{ font-size: 13px; font-weight: 900; }}
        QLabel#OverlayClock {{ color: {tokens.muted}; font-size: 12px; font-weight: 700; }}
        QPushButton#OverlayTextButton, QPushButton#OverlaySmallButton {{
            min-height: 26px; max-height: 26px;
            min-width: 0;
            padding: 0 9px;
            border: 0;
            border-radius: 6px;
            background: transparent;
            color: {tokens.muted};
        }}
        QPushButton#OverlaySmallButton {{ padding: 0 8px; }}
        QPushButton#OverlayTextButton:hover, QPushButton#OverlaySmallButton:hover {{
            color: {tokens.text}; background: {tokens.hover};
        }}

        QToolTip {{
            color: {tokens.text};
            background: {tokens.surface};
            border: 1px solid {tokens.border};
            border-radius: 6px;
            padding: 6px;
        }}
    """
