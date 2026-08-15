from pathlib import Path, PureWindowsPath
import subprocess
import tempfile
import unittest
from unittest import mock

import pdf_to_mscz as pipeline


class CommandBuildingTests(unittest.TestCase):
    def test_audiveris_command_enables_batch_ocr_controls(self):
        audiveris = Path("tools") / "audiveris"
        pdf = Path("scores") / "input score.pdf"
        output = Path("output")
        command = pipeline.build_audiveris_command(
            audiveris,
            pdf,
            output,
            languages="eng+deu",
            sheets=("1", "4-6"),
            force=True,
            save_omr=False,
        )

        self.assertEqual(
            command,
            [
                str(audiveris),
                "-batch",
                "-transcribe",
                "-export",
                "-force",
                "-constant",
                (
                    "org.audiveris.omr.text.Language.defaultSpecification="
                    "eng+deu"
                ),
                "-sheets",
                "1",
                "4-6",
                "-output",
                str(output),
                "--",
                str(pdf),
            ],
        )

    def test_audiveris_command_saves_omr_by_default(self):
        command = pipeline.build_audiveris_command(
            Path("audiveris"), Path("score.pdf"), Path("output")
        )
        self.assertIn("-save", command)
        self.assertLess(command.index("--"), command.index("score.pdf"))

    def test_audiveris_command_preserves_windows_paths(self):
        audiveris = PureWindowsPath(r"C:\Program Files\Audiveris\Audiveris.exe")
        pdf = PureWindowsPath(r"C:\Scores\input score.pdf")
        output = PureWindowsPath(r"C:\Scores\OMR output")

        command = pipeline.build_audiveris_command(audiveris, pdf, output)

        self.assertEqual(command[0], r"C:\Program Files\Audiveris\Audiveris.exe")
        self.assertEqual(command[command.index("-output") + 1], r"C:\Scores\OMR output")
        self.assertEqual(command[-1], r"C:\Scores\input score.pdf")

    def test_musescore_command_uses_output_extension(self):
        self.assertEqual(
            pipeline.build_musescore_command(
                Path("mscore"), Path("score.mxl"), Path("score.mscz")
            ),
            ["mscore", "score.mxl", "-o", "score.mscz"],
        )


class OptionValidationTests(unittest.TestCase):
    def test_normalize_sheets_accepts_spaces_and_commas(self):
        self.assertEqual(
            pipeline.normalize_sheets(("1,3-5", "8")), ["1", "3-5", "8"]
        )

    def test_normalize_sheets_rejects_invalid_or_overlapping_ranges(self):
        for selectors in (("0",), ("5-2",), ("1-3", "3-4"), ("page2",)):
            with self.subTest(selectors=selectors):
                with self.assertRaises(pipeline.PipelineError):
                    pipeline.normalize_sheets(selectors)

    def test_language_option_accepts_tesseract_codes(self):
        self.assertEqual(pipeline._language_spec("eng+chi_sim"), "eng+chi_sim")
        with self.assertRaises(Exception):
            pipeline._language_spec("eng,chi_sim")

    def test_timeout_must_be_positive(self):
        self.assertEqual(pipeline._positive_timeout("2.5"), 2.5)
        for value in ("0", "-1", "never"):
            with self.subTest(value=value):
                with self.assertRaises(Exception):
                    pipeline._positive_timeout(value)


class DiscoveryTests(unittest.TestCase):
    def test_find_new_exports_ignores_stale_and_unrelated_files(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir)
            stale = output / "score.mxl"
            stale.write_bytes(b"old")
            before = pipeline._snapshot_musicxml(output)
            movement = output / "score.mvt1.mxl"
            movement.write_bytes(b"new")
            (output / "another-score.mxl").write_bytes(b"other")

            self.assertEqual(
                pipeline.find_new_exports(output, "score", before),
                [movement.resolve()],
            )


class ConversionTests(unittest.TestCase):
    def test_convert_pdf_runs_ocr_then_converts_every_export(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            pdf = root / "my score.pdf"
            pdf.write_bytes(b"%PDF-1.4")
            output = root / "output"

            def fake_run(command, check, timeout):
                self.assertTrue(check)
                if "-transcribe" in command:
                    output.mkdir(parents=True, exist_ok=True)
                    (output / "my score.mxl").write_bytes(b"musicxml")
                    (output / "my score.mvt1.mxl").write_bytes(b"movement")
                else:
                    Path(command[command.index("-o") + 1]).write_bytes(b"mscz")
                return subprocess.CompletedProcess(command, 0)

            with mock.patch.object(pipeline.subprocess, "run", side_effect=fake_run) as run:
                results = pipeline.convert_pdf(
                    pdf,
                    output,
                    Path("audiveris"),
                    Path("mscore"),
                    timeout=10,
                )

            self.assertEqual(run.call_count, 3)
            self.assertEqual(
                results,
                [
                    (output / "my score.mscz").resolve(),
                    (output / "my score.mvt1.mscz").resolve(),
                ],
            )

    def test_convert_pdf_rejects_non_pdf_and_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            text_file = root / "score.png"
            text_file.write_bytes(b"image")
            with self.assertRaisesRegex(pipeline.PipelineError, "must be a PDF"):
                pipeline.convert_pdf(
                    text_file, root / "output", Path("audiveris"), Path("mscore")
                )

            pdf = root / "score.pdf"
            pdf.write_bytes(b"%PDF")
            output = root / "output"
            output.mkdir()
            (output / "score.mscz").write_bytes(b"existing")
            with mock.patch.object(pipeline.subprocess, "run") as run:
                with self.assertRaisesRegex(pipeline.PipelineError, "already exists"):
                    pipeline.convert_pdf(pdf, output, Path("audiveris"), Path("mscore"))
            run.assert_not_called()

    def test_convert_pdf_requires_a_fresh_musicxml_export(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            pdf = root / "score.pdf"
            pdf.write_bytes(b"%PDF")
            with mock.patch.object(pipeline.subprocess, "run"):
                with self.assertRaisesRegex(pipeline.PipelineError, "did not create"):
                    pipeline.convert_pdf(
                        pdf, root / "output", Path("audiveris"), Path("mscore")
                    )

    def test_dry_run_does_not_start_external_programs(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            pdf = root / "score.pdf"
            pdf.write_bytes(b"%PDF")
            with mock.patch.object(pipeline.subprocess, "run") as run:
                results = pipeline.convert_pdf(
                    pdf,
                    root / "output",
                    Path("audiveris"),
                    Path("mscore"),
                    dry_run=True,
                )
            run.assert_not_called()
            self.assertEqual(results[0].name, "score.mscz")

    def test_external_timeout_becomes_pipeline_error(self):
        timeout = subprocess.TimeoutExpired(["audiveris"], 3)
        with mock.patch.object(pipeline.subprocess, "run", side_effect=timeout):
            with self.assertRaisesRegex(pipeline.PipelineError, "timed out after 3"):
                pipeline._run(["audiveris"], "Audiveris OCR", timeout=3)


class ExecutableResolutionTests(unittest.TestCase):
    def test_explicit_executable_takes_priority(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            executable = Path(temporary_dir) / "Audiveris"
            executable.touch()
            resolved = pipeline.resolve_executable(
                "audiveris", str(executable), "AUDIVERIS_PATH", ("audiveris",)
            )
            self.assertEqual(resolved, executable.resolve())

    def test_missing_explicit_executable_has_actionable_error(self):
        with self.assertRaisesRegex(pipeline.PipelineError, "AUDIVERIS_PATH"):
            pipeline.resolve_executable(
                "audiveris", "/missing/audiveris", "AUDIVERIS_PATH", ("audiveris",)
            )


if __name__ == "__main__":
    unittest.main()
