# Translation Provider Design

Date: 2026-03-11

## Goal

Replace relay-based translation with a local-first provider system that supports:

- Local free translation using a CTranslate2-compatible NLLB model
- Optional user-supplied API keys for Gemini, OpenAI, and Claude
- Lazy imports for cloud SDKs so app startup stays light
- Secure key storage behavior matching the existing transcription settings flow

## Chosen approach

Use a unified translation provider framework.

- `core/translator.py` remains the UI-facing orchestration layer.
- Provider-specific translation logic is split into dedicated modules.
- The app exposes a translation provider selector in Settings.
- The local NLLB model is auto-downloaded on first use and cached locally.
- Cloud providers use built-in default models rather than exposing per-provider model settings.

## Architecture

### Orchestrator

The translation orchestrator is responsible for:

- Selecting the active provider from config and app state
- Loading provider implementations lazily
- Batching subtitle entries
- Normalizing outputs into `{index: translated_text}`
- Reporting progress and errors back to the UI

### Providers

Providers are:

- `local_nllb`
- `gemini`
- `openai`
- `claude`

Each provider implements a common batch translation interface.

### Settings and config

Translation settings mirror the transcription settings pattern:

- Translation provider selector in Settings
- Secure local storage toggle for cloud API keys
- Session-only fallback when local storage is disabled
- Environment variable fallback support

## UX

- Users choose a translation provider in Settings.
- The Transcribe panel keeps the target language dropdown and translate button.
- Local translation downloads the NLLB model on first use, then reuses the cached model.
- Cloud translation uses the configured provider key and built-in default model.

## Cleanup

Remove:

- Cloudflare relay code and docs
- Vercel relay code and docs
- Relay defaults and shared key behavior from translator code

Update:

- README to describe local NLLB and optional cloud providers
- Requirements to include translation dependencies
- Settings and config to support translation provider storage

## Testing

Validate:

- Config and secure key storage behavior for translation providers
- Local provider path can initialize or fail cleanly without breaking the UI
- Existing translation button flow still updates subtitle `translated_text`
- Relay code removal does not break imports or packaging