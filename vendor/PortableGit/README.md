Bundled MinGit runtime location.

`exe_maker\build_installer.bat` provisions the pinned 64-bit MinGit release
automatically when `cmd\git.exe` is missing. The download is SHA-256 verified
before extraction.

To refresh the bundled version, update the version, release URL, and SHA-256 in
`exe_maker\ensure_portable_git.ps1`, then rebuild.

The actual MinGit payload is ignored by Git. Only this instruction file is tracked.
