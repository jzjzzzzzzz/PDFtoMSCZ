# Changelog

## 0.2.0 - 2026-08-15

- Replaced hard-coded Windows paths with portable executable discovery.
- Replaced the manual Audiveris GUI workflow with batch transcription and export.
- Added a packaged `pdf-to-mscz` command and a correctly named script entry point.
- Added multi-file conversion with isolated outputs and optional continue-on-error behavior.
- Added OCR language, sheet selection, force, timeout, overwrite, OMR retention, and dry-run controls.
- Added fresh-export detection and multi-movement conversion.
- Added actionable subprocess and output validation errors.
- Added unit tests and a Windows/macOS/Linux CI matrix.

## 0.1.0 - 2026-04-10

- Added the initial Windows-only, interactive Audiveris-to-MuseScore workflow.
