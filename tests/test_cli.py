import json
import io
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def run_cli(self, *args, input=None):
        return subprocess.run([sys.executable, "-m", "g1_move", *args], cwd=ROOT,
                              input=input, text=True, capture_output=True, timeout=5)

    def test_single_mock_command_outputs_result(self):
        result = self.run_cli("--mock-fast", "move", "forward", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {
            "kind": "move", "direction": "forward", "value": 1.0,
            "unit": "m", "duration_s": 6.024096385542169, "status": "completed",
        })

    def test_dds_domain_option_is_forwarded(self):
        from g1_move.cli import main

        for option, expected in (([], 0), (["--dds-domain", "1"], 1)):
            with self.subTest(expected=expected):
                output, errors = io.StringIO(), io.StringIO()
                with redirect_stdout(output), redirect_stderr(errors), patch("g1_move.cli.G1Move") as robot:
                    self.assertEqual(main(["--backend", "unitree", "--interface", "lo", *option, "stop"]), 0)
                self.assertEqual(robot.call_args.kwargs["dds_domain"], expected)
                self.assertEqual(robot.call_args.kwargs["interface"], "lo")
                self.assertEqual(json.loads(output.getvalue()), {"status": "stop_requested"})

    def test_invalid_dds_domains_never_initialize_sdk(self):
        for domain in ("-1", "1.5", "true"):
            with self.subTest(domain=domain):
                result = self.run_cli("--backend", "unitree", "--interface", "fake0",
                                      "--dds-domain", domain, "stop")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("dds", json.loads(result.stderr)["error"])
                self.assertNotIn("SDK is unavailable", result.stderr)

    def test_example_sequence_is_executable(self):
        result = self.run_cli("--config", "config.json", "--mock-fast",
                              "sequence", "examples/sequence.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([action["direction"] for action in json.loads(result.stdout)],
                         ["left", "right", "forward"])

    def test_interactive_shell_continues_after_input_error(self):
        result = self.run_cli("--mock-fast", "shell", input=(
            "move left 0.5\nturn up 90\nturn right 90\nstop\nquit\n"))
        self.assertEqual(result.returncode, 0, result.stderr)
        outputs = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([line["status"] for line in outputs],
                         ["completed", "completed", "stop_requested"])
        self.assertEqual(outputs[1]["direction"], "right")
        self.assertIn("error", json.loads(result.stderr))

    def test_invalid_input_does_not_attempt_real_connection(self):
        result = self.run_cli("--backend", "unitree", "--interface", "fake0",
                              "move", "left", "nan")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads(result.stderr)["error_type"], "ValueError")
        self.assertNotIn("SDK is unavailable", result.stderr)

    def test_invalid_later_sequence_action_is_checked_before_connection(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory).resolve() / "invalid.json"
            path.write_text(json.dumps([["move", "left", 1], ["turn", "left", False]]),
                            encoding="utf-8")
            result = self.run_cli("--backend", "unitree", "--interface", "fake0",
                                  "sequence", str(path))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("sequence action 2", json.loads(result.stderr)["error"])

    def test_real_backend_rejects_fast_flag(self):
        result = self.run_cli("--backend", "unitree", "--interface", "fake0",
                              "--mock-fast", "move", "left", "1")
        self.assertEqual(result.returncode, 2)
        self.assertIn("only available", json.loads(result.stderr)["error"])

    def test_basic_python_example_runs_without_sdk(self):
        result = subprocess.run([sys.executable, "-m", "examples.basic"], cwd=ROOT,
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(len(output), 6)
        self.assertTrue(all(item["status"] == "completed" for item in output))

    def test_sdk_diagnostics_do_not_corrupt_json_stdout(self):
        from g1_move import ActionResult
        from g1_move.cli import main

        class NoisyRobot:
            def __init__(self, **kwargs):
                print("SDK initialization diagnostic")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                print("SDK close diagnostic")

            def move(self, direction, value):
                print("SDK command diagnostic")
                return ActionResult("move", direction, value, "m", 5.0, "completed")

        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors), patch("g1_move.cli.G1Move", NoisyRobot):
            self.assertEqual(main(["--mock-fast", "move", "forward", "1"]), 0)
            self.assertIs(sys.stdout, output)
        self.assertEqual(json.loads(output.getvalue())["status"], "completed")
        self.assertIn("SDK initialization diagnostic", errors.getvalue())
        self.assertIn("SDK command diagnostic", errors.getvalue())
        self.assertIn("SDK close diagnostic", errors.getvalue())

    def test_sequence_requires_numeric_json_values(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory).resolve() / "string_value.json"
            path.write_text('[["move", "left", "1"]]', encoding="utf-8")
            result = self.run_cli("--mock-fast", "sequence", str(path))
        self.assertEqual(result.returncode, 2)
        self.assertIn("JSON number", json.loads(result.stderr)["error"])


if __name__ == "__main__":
    unittest.main()
