# PDFtoMSCZ

[![tests](https://github.com/jzjzzzzzzz/PDFtoMSCZ/actions/workflows/tests.yml/badge.svg)](https://github.com/jzjzzzzzzz/PDFtoMSCZ/actions/workflows/tests.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![MIT license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Convert PDF sheet music into editable MuseScore (`.mscz`) files with a fully automated, local pipeline:

```text
PDF → Audiveris OMR → MusicXML → MuseScore → MSCZ
```

No score or document is uploaded to a cloud service. The Python package has no runtime Python dependencies.

## Highlights

- Runs Audiveris in non-interactive batch mode—no manual export/wait loop.
- Finds Audiveris and MuseScore on `PATH` and in common Windows, macOS, and Linux locations.
- Supports explicit executable paths through CLI options or environment variables.
- Accepts multiple PDFs and isolates their output folders.
- Selects OCR languages and page ranges from the command line.
- Keeps Audiveris `.omr` projects by default so recognition can be reviewed and corrected.
- Detects every fresh MusicXML export, including multi-movement scores.
- Protects existing `.mscz` files unless `--overwrite` is supplied.
- Provides timeouts, continue-on-error processing, and a safe dry-run mode.
- Includes cross-platform CI and standard-library unit tests.

## Requirements

- Python 3.9 or newer
- [Audiveris](https://audiveris.github.io/audiveris/_pages/tutorials/install/binaries/) 5.x
- [MuseScore Studio](https://musescore.org/en/download) 4.x

Audiveris uses Tesseract for text found in a score. Install the required OCR language data from **Tools → Languages** in Audiveris before using `--languages`. See the [Audiveris OCR language guide](https://audiveris.github.io/audiveris/_pages/guides/main/languages/).

## Install

```bash
git clone https://github.com/jzjzzzzzzz/PDFtoMSCZ.git
cd PDFtoMSCZ
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e .
```

This installs the `pdf-to-mscz` command. You can also run `python PDFtoMSCZ.py` directly without installing the package.

## Quick start

```bash
pdf-to-mscz score.pdf
```

Generated files are written to `output/`:

```text
output/
├── score.omr   # editable Audiveris project
├── score.mxl   # compressed MusicXML interchange file
└── score.mscz  # final MuseScore file
```

Audiveris may emit more than one MusicXML file for a multi-movement book. Each fresh export is converted to its own `.mscz` file.

## Useful examples

Choose only the OCR languages present in the score:

```bash
pdf-to-mscz score.pdf --languages eng+deu
```

Process selected pages and replace previous results:

```bash
pdf-to-mscz score.pdf --sheets 1 4-6 --force --overwrite
```

Convert several PDFs. Each input is placed in a separate subfolder of `converted/`:

```bash
pdf-to-mscz first.pdf second.pdf -o converted --keep-going
```

Preview both external commands without launching them:

```bash
pdf-to-mscz score.pdf --dry-run
```

Set a five-minute limit for each Audiveris or MuseScore process:

```bash
pdf-to-mscz score.pdf --timeout 300
```

## Tool discovery

Discovery order is:

1. `--audiveris` / `--musescore`
2. `AUDIVERIS_PATH` / `MUSESCORE_PATH`
3. Executables available on `PATH`
4. Common platform-specific installation locations

Examples:

```bash
export AUDIVERIS_PATH="/opt/audiveris/bin/Audiveris"
export MUSESCORE_PATH="/Applications/MuseScore 4.app/Contents/MacOS/mscore"
pdf-to-mscz score.pdf
```

```powershell
$env:AUDIVERIS_PATH = "C:\Program Files\Audiveris\Audiveris.exe"
$env:MUSESCORE_PATH = "C:\Program Files\MuseScore 4\bin\MuseScore4.exe"
pdf-to-mscz score.pdf
```

## Command reference

```text
usage: pdf-to-mscz [-h] [-o OUTPUT_DIR] [--audiveris PATH]
                   [--musescore PATH] [--overwrite] [--languages CODES]
                   [--sheets N[-M] ...] [--force] [--no-save-omr]
                   [--timeout SECONDS] [--keep-going] [--dry-run]
                   PDF [PDF ...]
```

| Option | Purpose |
| --- | --- |
| `-o`, `--output-dir` | Select the output root; defaults to `output`. |
| `--audiveris`, `--musescore` | Supply an executable path explicitly. |
| `--languages eng+deu` | Set a focused, plus-separated Tesseract language specification. |
| `--sheets 1 4-6` | Process an ascending selection of pages. |
| `--force` | Ask Audiveris to redo transcription steps. |
| `--no-save-omr` | Skip the reusable Audiveris project file. |
| `--overwrite` | Permit replacement of existing MSCZ results. |
| `--timeout 300` | Limit each external command in seconds. |
| `--keep-going` | Continue with later PDFs if one conversion fails. |
| `--dry-run` | Validate inputs and print commands without executing them. |

## Improving recognition quality

- Start with a straight, high-resolution scan with strong contrast and little page shadow.
- Specify only the text languages that actually appear in the score; extra languages slow OCR and can increase false matches.
- Keep the `.omr` file, open it in Audiveris, and proofread the recognized rhythm, accidentals, voices, and text before relying on the result.
- Use a page subset while tuning a difficult scan, then run the complete book after the settings look right.

OMR is probabilistic, so complex engraving, handwriting, skewed photos, and damaged pages normally need manual correction.

## Development

The test suite uses fake external-process behavior; Audiveris and MuseScore are not required to run it.

```bash
python -m unittest discover -s tests -v
python -m compileall -q PDFtoMXCZ.py PDFtoMSCZ.py pdf_to_mscz.py
```

`PDFtoMXCZ.py` remains as a backward-compatible wrapper for the original misspelled filename.
