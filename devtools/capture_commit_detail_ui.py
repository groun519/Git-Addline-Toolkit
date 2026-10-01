from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget

from hidden_desktop import close_hidden_desktop, create_hidden_desktop
from line_tracker import CommitChangeEntry, get_commit_detail
from line_tracker_theme import get_theme_palette
from line_tracker_ui_resources import TEXT
from qt_app.commit_detail_dialog import CommitDetailDialog
from qt_app.theme import build_stylesheet, build_theme_tokens


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture the commit detail dialog on an isolated desktop.")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--output", type=Path, default=ROOT_DIR / "build" / "ui-captures" / "commit-detail.png")
    parser.add_argument("--theme", default="forest")
    parser.add_argument("--lang", choices=("ko", "en"), default="ko")
    args = parser.parse_args()

    detail = get_commit_detail(args.repo.resolve(), args.commit)
    entry = CommitChangeEntry(
        commit_hash=detail.commit_hash,
        short_hash=detail.short_hash,
        date=detail.authored_at.date() if detail.authored_at is not None else None,
        subject=detail.subject,
        insertions=detail.insertions,
        deletions=detail.deletions,
    )
    translations = TEXT[args.lang]

    def translate(key: str, **kwargs) -> str:
        return translations.get(key, key).format(**kwargs)

    desktop = create_hidden_desktop()
    app: QApplication | None = None
    dialog: CommitDetailDialog | None = None
    try:
        app = QApplication([])
        tokens = build_theme_tokens(get_theme_palette(args.theme))
        parent = QWidget()
        parent.setStyleSheet(build_stylesheet(tokens))
        dialog = CommitDetailDialog(
            parent,
            repo=args.repo.resolve(),
            entry=entry,
            translate=translate,
            tokens=tokens,
        )
        dialog._loading_started = True
        dialog._show_detail(detail)
        dialog.show()

        def capture() -> None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            image = dialog.grab()
            if not image.save(str(args.output.resolve())):
                raise OSError(f"Failed to save capture: {args.output.resolve()}")
            print(f"Captured {image.width()}x{image.height()}: {args.output.resolve()}")
            dialog.close()
            app.quit()

        QTimer.singleShot(300, capture)
        app.exec()
    finally:
        if dialog is not None:
            dialog.close()
        close_hidden_desktop(desktop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
