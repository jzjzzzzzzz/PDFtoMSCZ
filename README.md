# AutoTranspose: PDF to MuseScore Converter
 
AutoTranspose is a Python tool that converts PDF sheet music into editable MuseScore (.mscz) files. It integrates Audiveris for Optical Music Recognition (OMR) and MuseScore 4 for final score conversion.

The project is designed to simplify the digitization of printed sheet music and make it ready for editing, playback, and transposition.

## Features

- Convert PDF sheet music into MusicXML using Audiveris
- Automatically detect exported MusicXML (.mxl/.xml) files
- Convert MusicXML into MuseScore (.mscz) format
- Simple and guided workflow
- Automatic output directory handling
- Cross-step automation between OMR and notation software

## Workflow

PDF → Audiveris (OMR) → MusicXML (.mxl/.xml) → MuseScore → MSCZ

## Requirements

### Software Dependencies

You must install the following software manually:

- Audiveris (Optical Music Recognition)
  https://audiveris.github.io/
  License: AGPL-3.0

- MuseScore 4 (Music Notation Software)
  https://musescore.org/
  License: GPL-3.0

Note: These applications are not included in this repository.

### Python Requirements

- Python 3.8 or higher
- Uses only standard libraries:
  - subprocess
  - pathlib
  - sys
  - time

## Installation

1. Clone the repository

```bash
git clone https://github.com/jzjzzzzzzz/PDFtoMSCZ.git
cd AutoTranspose
