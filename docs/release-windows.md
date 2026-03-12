# Windows Installer Release Notes

## What ships

The Windows installer is built in two stages:

1. PyInstaller creates `dist/SubVela/` using `subvela.spec`.
2. Inno Setup packages that folder into a single installer executable.

The PyInstaller payload currently includes:
- `SubVela.exe`
- `ffmpeg.exe`
- `ffprobe.exe`
- `libmpv-2.dll`
- application assets, including `assets/favicon.ico`

## Build command

Run the installer build script from PowerShell:

```powershell
.\installer\build-installer.ps1 -AppVersion 0.1.0
```

If `dist/SubVela/` is already current, you can skip the PyInstaller step:

```powershell
.\installer\build-installer.ps1 -AppVersion 0.1.0 -SkipPyInstaller
```

The installer output is written to `dist/installer/`.

## Inno Setup requirement

The build script looks for `ISCC.exe` in one of these default locations:
- `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`
- `C:\Program Files\Inno Setup 6\ISCC.exe`

If Inno Setup is not installed, install Inno Setup 6 before running the script.

## Legal checklist for public download

1. Ship `licenses/THIRD_PARTY_NOTICES.txt` with the installed app.
2. Keep the bundled FFmpeg/FFprobe names unchanged.
3. Add a notice on the website download page that the installer includes FFmpeg under GPLv3 and link to the corresponding source reference.
4. Keep the current `libmpv-2.dll` provenance recorded as the Shinchiro mpv-winbuild-cmake 20260304 release, and update `licenses/THIRD_PARTY_NOTICES.txt` if the binary changes.
5. If you later add an EULA, do not prohibit reverse engineering needed to exercise third-party license rights.

## Suggested website download notice

Use wording close to this next to the download button:

```text
This Windows download includes FFmpeg, licensed under GPLv3. Corresponding FFmpeg source for the bundled build is available from https://www.gyan.dev/ffmpeg/builds/ and https://github.com/FFmpeg/FFmpeg/commit/894da5ca7d.
```

## Recommended next release step

Before publishing to a public website, sign the installer executable so Windows SmartScreen warnings are reduced for new users.