# SubVela

<p align="left">
	<img src="assets/trademark-dark.svg" alt="SubVela wordmark" width="360" />
</p>

Desktop subtitle workflow for generating, translating, styling, and exporting subtitles for video.

SubVela is built for local-first editing: import a video, transcribe speech via `faster-whisper`, review each line, style the subtitles, and export a finished result. Run everything locally with free-to-use Whisper and NLLB models, or bring your own API key for cloud-boosted transcription and translation via Groq, OpenAI, Gemini, or Claude.

![SubVela screenshot](assets/Screenshot%202026-03-11%20010100.png)

## What it does

- Transcribes speech into subtitles with faster-whisper.
- Lets you edit subtitle text and timing in a desktop UI.
- Translates subtitle lines into many target languages.
- Styles subtitle appearance before export.
- Burns subtitles directly into the final video with FFmpeg.

## Current release focus

- Primary supported path: Windows installer.
- Source setup is available for local development and contributor use.
- Translation supports a local free model plus optional cloud providers with your own API keys.

## Install on Windows

Download the latest Windows release from the GitHub Releases page, then run the installer.

The Windows installer bundles the runtime pieces needed for the packaged app, including FFmpeg, FFprobe, and libmpv.

## Quick start

1. Open a video file.
2. Transcribe speech into subtitle lines.
3. Review and edit the generated subtitles.
4. Optionally translate into a second language.
5. Adjust subtitle styling.
6. Export the final video with burned-in subtitles.

## Run from source

SubVela can also be run from source on Windows.

### Prerequisites

- Python 3
- FFmpeg and FFprobe available to the app
- VLC or libmpv runtime available for video playback during development

### Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Optional developer env file:

```powershell
Copy-Item .env.example .env
```

Use `.env` only for your own local development or private internal builds. Do not commit real API keys, and do not ship public installers with embedded provider secrets.

### Translation during local development

- `Local (Free)` downloads a CTranslate2-compatible NLLB model on first use and caches it locally.
- `Gemini`, `OpenAI`, and `Claude` use your own API key entered in Settings.
- Keys can be kept in memory for the current session or stored in your OS credential store.
- Developers can predefine `GROQ_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, and `ANTHROPIC_API_KEY` in a local `.env` file copied from `.env.example`.
- The current local NLLB model sources are tagged `CC-BY-NC-4.0`; review [licenses/THIRD_PARTY_NOTICES.txt](licenses/THIRD_PARTY_NOTICES.txt) before commercial use or redistribution of those downloaded model files.

## Windows packaging

The Windows packaging flow is documented here:

- [docs/release-windows.md](docs/release-windows.md)

## License

SubVela itself is open source, and the core application is MIT licensed.

The Windows installer redistributes third-party components that remain under their own licenses. In particular, the Windows bundle includes FFmpeg and FFprobe, and the bundled FFmpeg build carries GPLv3 obligations in addition to the MIT-licensed core app.

If you create your own installer from source, keep your provider keys outside the public bundle. Use local `.env` files only for private development or private internal distribution.

Third-party bundle notices are documented here:

- [licenses/THIRD_PARTY_NOTICES.txt](licenses/THIRD_PARTY_NOTICES.txt)

The local NLLB translation option also downloads third-party model files on demand. Those NLLB artifacts are not covered by the MIT license for the SubVela application itself.

If you distribute the Windows installer, make sure those bundled notices remain included with the app.

## Project status

SubVela is being prepared for its first public open-source release. Expect some rough edges in packaging, setup, and contributor documentation while the repository is being cleaned up.