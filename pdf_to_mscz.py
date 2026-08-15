#!/usr/bin/env python3
"""Convert a PDF score to MusicXML with Audiveris, then to MSCZ with MuseScore."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


Snapshot = Dict[Path, Tuple[int, int]]
MUSICXML_SUFFIXES = {".mxl", ".musicxml", ".xml"}


class PipelineError(RuntimeError):
    """A user-facing conversion error."""


def _known_tool_paths(tool: str) -> Iterable[Path]:
    """Yield conventional installation locations for a supported tool."""
    if tool == "audiveris":
        yield Path("/Applications/Audiveris.app/Contents/MacOS/Audiveris")
        yield Path("/opt/audiveris/bin/Audiveris")
        if os.environ.get("ProgramFiles"):
            yield Path(os.environ["ProgramFiles"]) / "Audiveris" / "Audiveris.exe"
        applications = Path("/Applications")
        if applications.is_dir():
            yield from applications.glob("Audiveris*.app/Contents/MacOS/Audiveris")
    elif tool == "musescore":
        yield Path("/Applications/MuseScore 4.app/Contents/MacOS/mscore")
        yield Path("/Applications/MuseScore Studio 4.app/Contents/MacOS/mscore")
        if os.environ.get("ProgramFiles"):
            yield Path(os.environ["ProgramFiles"]) / "MuseScore 4" / "bin" / "MuseScore4.exe"


def resolve_executable(
    tool: str,
    explicit: Optional[str],
    env_name: str,
    command_names: Sequence[str],
) -> Path:
    """Resolve a tool from a CLI option, environment variable, PATH, or known location."""
    requested = explicit or os.environ.get(env_name)
    if requested:
        requested_path = Path(requested).expanduser()
        found = shutil.which(str(requested_path))
        if found:
            return Path(found).resolve()
        if requested_path.is_file():
            return requested_path.resolve()
        raise PipelineError(
            f"{tool} executable not found: {requested}. "
            f"Check the path supplied by --{tool} or {env_name}."
        )

    for command in command_names:
        found = shutil.which(command)
        if found:
            return Path(found).resolve()

    for candidate in _known_tool_paths(tool):
        if candidate.is_file():
            return candidate.resolve()

    raise PipelineError(
        f"Could not find {tool}. Install it, put it on PATH, or set {env_name}."
    )


def build_audiveris_command(audiveris: Path, pdf: Path, output_dir: Path) -> List[str]:
    """Build the non-interactive Audiveris transcription command."""
    return [
        str(audiveris),
        "-batch",
        "-transcribe",
        "-export",
        "-save",
        "-output",
        str(output_dir),
        "--",
        str(pdf),
    ]


def build_musescore_command(musescore: Path, musicxml: Path, output: Path) -> List[str]:
    """Build the MuseScore conversion command."""
    return [str(musescore), str(musicxml), "-o", str(output)]


def _run(command: Sequence[str], label: str) -> None:
    print(f"\n[{label}] {' '.join(command)}")
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise PipelineError(f"{label} executable could not be launched: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise PipelineError(f"{label} failed with exit code {exc.returncode}") from exc


def _snapshot_musicxml(output_dir: Path) -> Snapshot:
    snapshot: Snapshot = {}
    if not output_dir.exists():
        return snapshot
    for path in output_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in MUSICXML_SUFFIXES:
            stat = path.stat()
            snapshot[path.resolve()] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def _is_export_for(path: Path, input_stem: str) -> bool:
    stem = path.stem.casefold()
    expected = input_stem.casefold()
    return stem == expected or stem.startswith(expected + ".mvt") or stem == expected + ".opus"


def find_new_exports(output_dir: Path, input_stem: str, before: Snapshot) -> List[Path]:
    """Return MusicXML files created or changed by the current Audiveris run."""
    exports: List[Path] = []
    for path in output_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in MUSICXML_SUFFIXES:
            continue
        if not _is_export_for(path, input_stem):
            continue
        stat = path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        if before.get(path.resolve()) != signature:
            exports.append(path.resolve())
    return sorted(exports, key=lambda item: item.name.casefold())


def convert_pdf(
    pdf: Path,
    output_dir: Path,
    audiveris: Path,
    musescore: Path,
    overwrite: bool = False,
) -> List[Path]:
    """Run the complete OMR and MuseScore conversion pipeline for one PDF."""
    pdf = pdf.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if not pdf.is_file():
        raise PipelineError(f"Input PDF not found: {pdf}")
    if pdf.suffix.casefold() != ".pdf":
        raise PipelineError(f"Input must be a PDF file: {pdf}")

    output_dir.mkdir(parents=True, exist_ok=True)
    before = _snapshot_musicxml(output_dir)
    _run(build_audiveris_command(audiveris, pdf, output_dir), "Audiveris OCR")

    exports = find_new_exports(output_dir, pdf.stem, before)
    if not exports:
        raise PipelineError(
            "Audiveris completed but did not create a new MusicXML export in "
            f"{output_dir}"
        )

    results: List[Path] = []
    for musicxml in exports:
        target = musicxml.with_suffix(".mscz")
        if target.exists() and not overwrite:
            raise PipelineError(f"Output already exists (use --overwrite): {target}")
        _run(build_musescore_command(musescore, musicxml, target), "MuseScore conversion")
        if not target.is_file():
            raise PipelineError(f"MuseScore reported success but did not create: {target}")
        results.append(target)
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert a PDF music score to editable MSCZ using Audiveris OMR and MuseScore."
    )
    parser.add_argument("input", type=Path, help="PDF score to recognize")
    parser.add_argument(
        "-o", "--output-dir", type=Path, default=Path("output"), help="output directory"
    )
    parser.add_argument("--audiveris", help="Audiveris executable path")
    parser.add_argument("--musescore", help="MuseScore executable path")
    parser.add_argument(
        "--overwrite", action="store_true", help="replace an existing MSCZ output"
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        audiveris = resolve_executable(
            "audiveris", args.audiveris, "AUDIVERIS_PATH", ("audiveris", "Audiveris")
        )
        musescore = resolve_executable(
            "musescore",
            args.musescore,
            "MUSESCORE_PATH",
            ("mscore", "musescore", "MuseScore4"),
        )
        outputs = convert_pdf(
            args.input, args.output_dir, audiveris, musescore, overwrite=args.overwrite
        )
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print("\nConversion complete:")
    for output in outputs:
        print(f"  {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
