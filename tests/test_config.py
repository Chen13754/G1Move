import json
import tempfile
import unittest
from pathlib import Path

from g1_move import G1Move, MotionConfig


class ConfigTests(unittest.TestCase):
    def test_positive_settings_reject_nonfinite_zero_negative_bool_and_strings(self):
        for name in ("linear_speed_mps", "angular_speed_deg_s", "rpc_timeout_s"):
            for value in (float("nan"), float("inf"), float("-inf"), 0, -1, True, "0.2"):
                with self.subTest(name=name, value=value):
                    with self.assertRaises(ValueError):
                        MotionConfig(**{name: value})

    def test_pause_allows_zero_but_rejects_invalid_values(self):
        self.assertEqual(MotionConfig(pause_s=0).pause_s, 0)
        for value in (float("nan"), float("inf"), -1, False, "0"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    MotionConfig(pause_s=value)

    def test_factor_directions_must_match_and_factors_must_be_positive(self):
        for field, defaults in (("move_time_factors", dict(MotionConfig().move_time_factors)),
                                ("turn_time_factors", dict(MotionConfig().turn_time_factors))):
            for value in (0, -1, True, float("nan"), float("inf"), "1"):
                with self.subTest(field=field, value=value):
                    factors = dict(defaults, left=value)
                    with self.assertRaises(ValueError):
                        MotionConfig(**{field: factors})
            with self.assertRaises(ValueError):
                MotionConfig(**{field: {**defaults, "lef": 1}})
            with self.assertRaises(ValueError):
                MotionConfig(**{field: {key: value for key, value in defaults.items() if key != "left"}})

    def test_config_loads_defaults_and_utf8_bom_but_rejects_typos(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"linear_speed_mps": .3}), encoding="utf-8-sig")
            loaded = MotionConfig.from_file(path)
            self.assertEqual(loaded.linear_speed_mps, .3)
            self.assertEqual(dict(loaded.move_time_factors), dict(MotionConfig().move_time_factors))
            path.write_text('{"linear_speed_mpss": 0.3}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unknown configuration keys"):
                MotionConfig.from_file(path)
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                MotionConfig.from_file(path)

    def test_config_defensively_copies_calibration_values(self):
        factors = dict(MotionConfig().move_time_factors)
        config = MotionConfig(move_time_factors=factors)
        factors["forward"] = 999
        with G1Move(config=config, mock_realtime=False) as robot:
            self.assertEqual(robot.move("forward", 1).duration_s, 5)

    def test_invalid_distances_and_angles_send_no_motion(self):
        with G1Move(mock_realtime=False) as robot:
            for method in (robot.move, robot.turn):
                for value in (0, -1, float("nan"), float("inf"), True, "1", None):
                    with self.subTest(method=method.__name__, value=value):
                        with self.assertRaises(ValueError):
                            method("left", value)
            self.assertEqual(len(robot._backend.commands), 1)


if __name__ == "__main__":
    unittest.main()
