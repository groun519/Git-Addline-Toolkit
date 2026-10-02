# UI capture

The capture tool renders Line Tracker on an isolated Windows Desktop. It does not
activate the window, add a taskbar entry, move the pointer, or save UI settings.

```powershell
python -m pip install -r devtools/requirements.txt
python devtools/capture_qt_ui.py --repo . --surface activity
python devtools/capture_qt_ui.py --repo . --surface settings-tracking --theme harddark
python devtools/capture_qt_ui.py --repo . --surface schedule-open
python devtools/capture_qt_ui.py --repo . --surface overlay-strip
```

Images are written below `build/ui-captures` by default.
