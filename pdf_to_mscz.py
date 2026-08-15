#!/usr/bin/env python3
"""Convert a PDF score to MusicXML with Audiveris, then to MSCZ with MuseScore."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


Snapshot = Dict[Path, Tuple[int, int]]
MUSICXML_SUFFIXES = {".mxl", ".musicxml", ".xml"}
OCR_LANGUAGE_CONSTANT = "org.audiveris.omr.text.Language.defaultSpecification"
LANGUAGE_SPEC_PATTERN = re.compile(r"^[A-Za-z0-9_]+(?:\+[A-Za-z0-9_]+)*$")


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


def build_audiveris_command(
    audiveris: Path,
    pdf: Path,
    output_dir: Path,
    languages: Optional[str] = None,
    sheets: Sequence[str] = (),
    force: bool = False,
    save_omr: bool = True,
) -> List[str]:
    """Build the non-interactive Audiveris transcription command."""
    command = [
        str(audiveris),
        "-batch",
        "-transcribe",
        "-export",
    ]
    if save_omr:
        command.append("-save")
    if force:
        command.append("-force")
    if languages:
        command.extend(["-constant", f"{OCR_LANGUAGE_CONSTANT}={languages}"])
    if sheets:
        command.extend(["-sheets", *sheets])
    command.extend(["-output", str(output_dir), "--", str(pdf)])
    return command


def build_musescore_command(musescore: Path, musicxml: Path, output: Path) -> List[str]:
    """Build the MuseScore conversion command."""
    return [str(musescore), str(musicxml), "-o", str(output)]


def _run(
    command: Sequence[str],
    label: str,
    timeout: Optional[float] = None,
    dry_run: bool = False,
) -> None:
    print(f"\n[{label}] {shlex.join(command)}")
    if dry_run:
        return
    try:
        subprocess.run(command, check=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise PipelineError(f"{label} executable could not be launched: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise PipelineError(f"{label} failed with exit code {exc.returncode}") from exc
    except subprocess.TimeoutExpired as exc:
        raise PipelineError(f"{label} timed out after {timeout:g} seconds") from exc


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


def normalize_sheets(values: Sequence[str]) -> List[str]:
    """Validate and normalize Audiveris sheet selectors into ascending ranges."""
    selectors: List[str] = []
    for value in values:
        selectors.extend(part.strip() for part in value.split(",") if part.strip())

    previous_end = 0
    for selector in selectors:
        match = re.fullmatch(r"([1-9]\d*)(?:-([1-9]\d*))?", selector)
        if not match:
            raise PipelineError(
                f"Invalid sheet selector '{selector}'; use values such as 1 4-6"
            )
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if end < start or start <= previous_end:
            raise PipelineError("Sheet selectors must be non-overlapping and strictly increasing")
        previous_end = end
    return selectors


def _language_spec(value: str) -> str:
    value = value.strip()
    if not LANGUAGE_SPEC_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "use plus-separated Tesseract language codes, for example eng+deu"
        )
    return value


def _positive_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be a number") from exc
    if timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be greater than zero")
    return timeout


def _signature(path: Path) -> Optional[Tuple[int, int]]:
    if not path.is_file():
        return None
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def _existing_results(output_dir: Path, input_stem: str) -> List[Path]:
    return sorted(
        (
            path
            for path in output_dir.rglob("*.mscz")
            if path.is_file() and _is_export_for(path, input_stem)
        ),
        key=lambda item: item.name.casefold(),
    )


def convert_pdf(
    pdf: Path,
    output_dir: Path,
    audiveris: Path,
    musescore: Path,
    overwrite: bool = False,
    languages: Optional[str] = None,
    sheets: Sequence[str] = (),
    force: bool = False,
    save_omr: bool = True,
    timeout: Optional[float] = None,
    dry_run: bool = False,
) -> List[Path]:
    """Run the complete OMR and MuseScore conversion pipeline for one PDF."""
    pdf = pdf.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if not pdf.is_file():
        raise PipelineError(f"Input PDF not found: {pdf}")
    if pdf.suffix.casefold() != ".pdf":
        raise PipelineError(f"Input must be a PDF file: {pdf}")

    if not overwrite:
        existing = _existing_results(output_dir, pdf.stem) if output_dir.exists() else []
        if existing:
            raise PipelineError(f"Output already exists (use --overwrite): {existing[0]}")

    output_dir.mkdir(parents=True, exist_ok=True)
    before = _snapshot_musicxml(output_dir)
    audiveris_command = build_audiveris_command(
        audiveris,
        pdf,
        output_dir,
        languages=languages,
        sheets=sheets,
        force=force,
        save_omr=save_omr,
    )
    _run(audiveris_command, "Audiveris OCR", timeout=timeout, dry_run=dry_run)

    if dry_run:
        expected_musicxml = output_dir / f"{pdf.stem}.mxl"
        expected_mscz = expected_musicxml.with_suffix(".mscz")
        _run(
            build_musescore_command(musescore, expected_musicxml, expected_mscz),
            "MuseScore conversion",
            timeout=timeout,
            dry_run=True,
        )
        return [expected_mscz]

    exports = find_new_exports(output_dir, pdf.stem, before)
    if not exports:
        raise PipelineError(
            "Audiveris completed but did not create a new MusicXML export in "
            f"{output_dir}"
        )

    results: List[Path] = []
    for musicxml in exports:
        target = musicxml.with_suffix(".mscz")
        previous_signature = _signature(target)
        _run(
            build_musescore_command(musescore, musicxml, target),
            "MuseScore conversion",
            timeout=timeout,
        )
        if _signature(target) is None:
            raise PipelineError(f"MuseScore reported success but did not create: {target}")
        if previous_signature is not None and _signature(target) == previous_signature:
            raise PipelineError(f"MuseScore did not update the existing output: {target}")
        results.append(target)
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert a PDF music score to editable MSCZ using Audiveris OMR and MuseScore."
    )
    parser.add_argument("inputs", type=Path, nargs="+", help="one or more PDF scores")
    parser.add_argument(
        "-o", "--output-dir", type=Path, default=Path("output"), help="output directory"
    )
    parser.add_argument("--audiveris", help="Audiveris executable path")
    parser.add_argument("--musescore", help="MuseScore executable path")
    parser.add_argument(
        "--overwrite", action="store_true", help="replace an existing MSCZ output"
    )
    parser.add_argument(
        "--languages",
        type=_language_spec,
        metavar="CODES",
        help="OCR languages, such as eng or eng+deu (defaults to Audiveris settings)",
    )
    parser.add_argument(
        "--sheets",
        nargs="+",
        default=(),
        metavar="N[-M]",
        help="only process selected sheets, for example --sheets 1 4-6",
    )
    parser.add_argument("--force", action="store_true", help="force Audiveris reprocessing")
    parser.add_argument(
        "--no-save-omr",
        action="store_true",
        help="do not retain Audiveris .omr project files",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_timeout,
        metavar="SECONDS",
        help="maximum time allowed for each external command",
    )
    parser.add_argument(
        "--keep-going", action="store_true", help="continue after a failed input PDF"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="show commands without running them"
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        sheets = normalize_sheets(args.sheets)
        audiveris = resolve_executable(
            "audiveris", args.audiveris, "AUDIVERIS_PATH", ("audiveris", "Audiveris")
        )
        musescore = resolve_executable(
            "musescore",
            args.musescore,
            "MUSESCORE_PATH",
            ("mscore", "musescore", "MuseScore4"),
        )
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    outputs: List[Path] = []
    failures: List[Tuple[Path, str]] = []
    multiple_inputs = len(args.inputs) > 1
    for input_path in args.inputs:
        job_output_dir = (
            args.output_dir / input_path.stem if multiple_inputs else args.output_dir
        )
        try:
            outputs.extend(
                convert_pdf(
                    input_path,
                    job_output_dir,
                    audiveris,
                    musescore,
                    overwrite=args.overwrite,
                    languages=args.languages,
                    sheets=sheets,
                    force=args.force,
                    save_omr=not args.no_save_omr,
                    timeout=args.timeout,
                    dry_run=args.dry_run,
                )
            )
        except PipelineError as exc:
            failures.append((input_path, str(exc)))
            print(f"error: {input_path}: {exc}", file=sys.stderr)
            if not args.keep_going:
                return 1

    heading = "Commands validated; expected outputs:" if args.dry_run else "Conversion complete:"
    print(f"\n{heading}")
    for output in outputs:
        print(f"  {output}")
    if failures:
        print(f"\n{len(failures)} of {len(args.inputs)} input(s) failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
