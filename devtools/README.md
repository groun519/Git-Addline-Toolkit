# UI capture

The capture tool renders Line Tracker on an isolated Windows Desktop. It does not
activate the window, add a taskbar entry, move the pointer, or save UI settings.

```powershell
python -m pip install -r devtools/requirements.txt
python devtools/capture_ui.py --repo .
python devtools/capture_ui.py --repo . --widget progress_section --theme harddark
python devtools/capture_ui.py --repo . --surface settings-tracking
python devtools/capture_ui.py --repo . --surface main-schedule-sample
python devtools/capture_ui.py --repo . --surface compact-strip
```

Images are written below `build/ui-captures` by default.
