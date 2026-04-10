import subprocess
from pathlib import Path
import sys
import time

# Path configuration
PDF_FILE = Path(r"C:\Users\DELL\PycharmProjects\AutoTranspose\test.pdf")
AUDIVERIS_EXE = Path(r"C:\Program Files\Audiveris\Audiveris.exe")
MUSESCORE_EXE = Path(r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe")
OUTPUT_DIR = Path(r"C:\Users\DELL\PycharmProjects\AutoTranspose\output")

# Check if required files exist
def check_exists(path, name):
    if not path.exists():
        print(f"Error: {name} not found at {path}")
        sys.exit(1)
    print(f"{name} found at {path}")

check_exists(PDF_FILE, "PDF file")
check_exists(AUDIVERIS_EXE, "Audiveris executable")
check_exists(MUSESCORE_EXE, "MuseScore executable")

# Create the output directory if it does not exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Step 1: Launch Audiveris GUI with the PDF file
print("\nLaunching Audiveris...")
subprocess.Popen([str(AUDIVERIS_EXE), str(PDF_FILE)])

print("""
Please complete the following steps in Audiveris:

1. Click: Run → Run All
2. After processing is complete, click: Export → MusicXML
3. Save the MusicXML (.mxl) file to the following directory:
   C:\\Users\\DELL\\PycharmProjects\\AutoTranspose\\output
4. Close the Audiveris window after saving the file
""")

# Step 2: Wait for the MusicXML/MXL file to be generated
print("Waiting for the MusicXML/MXL file to be generated...")

score_file = None
while score_file is None:
    candidates = (
        list(OUTPUT_DIR.rglob("*.mxl")) +
        list(OUTPUT_DIR.rglob("*.musicxml")) +
        list(OUTPUT_DIR.rglob("*.xml"))
    )
    if candidates:
        # Select the most recently created file
        score_file = max(candidates, key=lambda p: p.stat().st_mtime)
    else:
        time.sleep(5)

print(f"Score file detected: {score_file}")

# Step 3: Convert the file to MSCZ using MuseScore
mscz_file = OUTPUT_DIR / (score_file.stem + ".mscz")

print("\nConverting to MSCZ using MuseScore...")

try:
    subprocess.run(
        [
            str(MUSESCORE_EXE),
            str(score_file),
            "-o",
            str(mscz_file)
        ],
        check=True
    )
except subprocess.CalledProcessError as e:
    print("MuseScore conversion failed.")
    print(e)
    sys.exit(1)

# Completion message
print("\nConversion completed successfully.")
print(f"MSCZ file location: {mscz_file}")