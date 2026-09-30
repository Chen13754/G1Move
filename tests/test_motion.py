import math
import threading
import unittest
from unittest.mock import patch

from g1_move import BusyError, G1Move, MotionConfig, MotionError


def nonzero(command):
    return any((command.vx, command.vy, command.omega))


class MotionTests(unittest.TestCase):
    def make_robot(self, config=None):
        robot = G1Move(config=config, mock_realtime=False)
        self.addCleanup(robot.close)
        return robot

    def test_all_six_directions_and_calibration(self):
        config = MotionConfig(
            linear_speed_mps=0.25, angular_speed_deg_s=30, pause_s=0,
            move_time_factors={"forward": 1.1, "backward": 1.2, "left": 1.3, "right": 1.4},
            turn_time_factors={"left": 1.5, "right": 1.6},
        )
        robot = self.make_robot(config)
        actions = [
            ("move", "forward", 1, (0.25, 0, 0), 4.4),
            ("move", "backward", 1, (-0.25, 0, 0), 4.8),
            ("move", "left", 1, (0, 0.25, 0), 5.2),
            ("move", "right", 1, (0, -0.25, 0), 5.6),
            ("turn", "left", 90, (0, 0, math.pi / 6), 4.5),
            ("turn", "right", 90, (0, 0, -math.pi / 6), 4.8),
        ]
        for kind, direction, value, velocity, duration in actions:
            with self.subTest(kind=kind, direction=direction):
                result = getattr(robot, kind)(direction, value)
                command = robot._backend.commands[-2]
                for actual, expected in zip((command.vx, command.vy, command.omega), velocity):
                    self.assertAlmostEqual(actual, expected)
                self.assertAlmostEqual(command.duration, duration)
                self.assertAlmostEqual(result.duration_s, duration)
                self.assertEqual((result.kind, result.direction, result.value, result.status),
                                 (kind, direction, value, "completed"))
                self.assertEqual(result.unit, "m" if kind == "move" else "deg")
                self.assertFalse(nonzero(robot._backend.commands[-1]))

    def test_entire_sequence_validated_before_moving(self):
        invalid_actions = [("turn", "forward", 90), ("move", "left", 0),
                           ("move", "forward", float("nan")), ("move", "left", True),
                           ("move", "forward"), {"kind": "turn"}]
        for invalid in invalid_actions:
            with self.subTest(action=invalid):
                robot = self.make_robot()
                with self.assertRaises(ValueError):
                    robot.run_sequence([("move", "forward", 1), invalid])
                self.assertFalse(any(map(nonzero, robot._backend.commands)))

    def test_sequence_order_and_stops_between_actions(self):
        robot = self.make_robot()
        results = robot.run_sequence([("move", "left", .5), ("turn", "right", 90),
                                      ("move", "forward", 1)])
        self.assertEqual([result.direction for result in results], ["left", "right", "forward"])
        self.assertEqual([nonzero(command) for command in robot._backend.commands],
                         [False, True, False, True, False, True, False])

    def test_rpc_latency_is_subtracted_from_action_wait(self):
        robot = self.make_robot(MotionConfig(pause_s=0.3))
        with patch("g1_move.motion.time.monotonic", side_effect=[100.0, 100.2]), \
             patch.object(robot, "_wait", return_value=False) as wait:
            robot.move("forward", 1)
        self.assertAlmostEqual(wait.call_args_list[0].args[0], 4.8)
        self.assertAlmostEqual(wait.call_args_list[1].args[0], 0.3)

    def test_sdk_error_stops_sequence_without_retry(self):
        robot = self.make_robot()
        original = robot._backend.set_velocity
        calls = []

        def send(vx, vy, omega, duration):
            calls.append((vx, vy, omega, duration))
            if omega:
                raise MotionError("rejected")
            original(vx, vy, omega, duration)

        with patch.object(robot._backend, "set_velocity", side_effect=send):
            with self.assertRaisesRegex(MotionError, "rejected"):
                robot.run_sequence([("move", "left", .5), ("turn", "right", 90),
                                    ("move", "forward", 1)])
        self.assertEqual(sum(bool(command[2]) for command in calls), 1)
        self.assertFalse(any(command[0] for command in calls))
        self.assertEqual(calls[-1][:3], (0, 0, 0))

    def test_keyboard_interrupt_during_action_sends_zero(self):
        robot = self.make_robot()
        with patch.object(robot, "_wait", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                robot.move("forward", 1)
        self.assertEqual([nonzero(c) for c in robot._backend.commands], [False, True, False])

    def test_stop_failure_is_reported_without_starting_next_action(self):
        robot = self.make_robot()
        with patch.object(robot._backend, "set_velocity",
                          side_effect=[None, MotionError("stop rejected")]) as send:
            with self.assertRaisesRegex(MotionError, "stop rejected"):
                robot.run_sequence([("move", "forward", 1), ("turn", "left", 90)])
        self.assertEqual(send.call_count, 2)

    def test_thread_stop_cancels_sequence_and_busy_is_reported(self):
        robot = G1Move()
        self.addCleanup(robot.close)
        started = threading.Event()
        outcome = []
        errors = []
        original = robot._backend.set_velocity

        def send(vx, vy, omega, duration):
            original(vx, vy, omega, duration)
            if vx:
                started.set()

        def run():
            try:
                outcome.extend(robot.run_sequence([("move", "forward", 100), ("turn", "left", 90)]))
            except BaseException as exc:
                errors.append(exc)

        with patch.object(robot._backend, "set_velocity", side_effect=send):
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            try:
                self.assertTrue(started.wait(2), "worker did not start the action")
                with self.assertRaises(BusyError):
                    robot.turn("right", 90)
            finally:
                robot.stop()
                worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual([result.status for result in outcome], ["stopped"])
        self.assertEqual(sum(map(nonzero, robot._backend.commands)), 1)

    def test_stop_during_pause_does_not_start_next_action(self):
        robot = G1Move(config=MotionConfig(pause_s=100))
        self.addCleanup(robot.close)
        paused = threading.Event()
        original_wait = robot._wait
        wait_count = 0
        outcome = []

        def wait(duration):
            nonlocal wait_count
            wait_count += 1
            if wait_count == 1:
                return False
            paused.set()
            return original_wait(duration)

        with patch.object(robot, "_wait", side_effect=wait):
            worker = threading.Thread(target=lambda: outcome.extend(robot.run_sequence(
                [("move", "left", .5), ("turn", "right", 90)])), daemon=True)
            worker.start()
            try:
                self.assertTrue(paused.wait(2))
            finally:
                robot.stop()
                worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual([result.status for result in outcome], ["stopped"])
        self.assertEqual(sum(map(nonzero, robot._backend.commands)), 1)

    def test_close_is_idempotent_and_closed_instance_rejects_motion(self):
        robot = self.make_robot()
        robot.close()
        count = len(robot._backend.commands)
        robot.close()
        self.assertEqual(len(robot._backend.commands), count)
        with self.assertRaises(MotionError):
            robot.move("forward", 1)
        self.assertFalse(any(map(nonzero, robot._backend.commands)))

    def test_failed_close_can_be_explicitly_retried_with_close_or_stop(self):
        for retry_method in ("close", "stop"):
            with self.subTest(retry_method=retry_method):
                robot = self.make_robot()
                with patch.object(robot._backend, "set_velocity",
                                  side_effect=[MotionError("zero rejected"), None]) as send:
                    with self.assertRaisesRegex(MotionError, "zero rejected"):
                        robot.close()
                    with self.assertRaises(MotionError):
                        robot.move("forward", 1)
                    getattr(robot, retry_method)()
                    self.assertEqual(send.call_count, 2)
                    for call in send.call_args_list:
                        self.assertEqual(call.args[:3], (0, 0, 0))
                    robot.close()
                    self.assertEqual(send.call_count, 2)

    def test_stop_racing_with_registration_is_not_cleared_before_first_send(self):
        robot = self.make_robot()
        acquired = threading.Event()
        release_registration = threading.Event()
        stop_entered = threading.Event()
        stop_finished = threading.Event()
        original_lock = robot._action_lock
        original_run = robot._run
        outcomes = []
        errors = []

        class RegistrationGate:
            def acquire(self, blocking=True):
                result = original_lock.acquire(blocking=blocking)
                acquired.set()
                if not release_registration.wait(2):
                    raise AssertionError("registration gate timed out")
                return result

            def release(self):
                original_lock.release()

        def run_after_stop(action):
            if not stop_finished.wait(2):
                raise AssertionError("stop did not finish before dispatch")
            return original_run(action)

        def execute():
            try:
                outcomes.append(robot.move("forward", 1))
            except BaseException as exc:
                errors.append(exc)

        def stop():
            stop_entered.set()
            try:
                robot.stop()
            except BaseException as exc:
                errors.append(exc)
            finally:
                stop_finished.set()

        with patch.object(robot, "_action_lock", RegistrationGate()), \
             patch.object(robot, "_run", side_effect=run_after_stop):
            worker = threading.Thread(target=execute, daemon=True)
            stopper = threading.Thread(target=stop, daemon=True)
            worker.start()
            try:
                self.assertTrue(acquired.wait(2))
                stopper.start()
                self.assertTrue(stop_entered.wait(2))
                # A non-atomic implementation lets stop finish inside the registration
                # gap and subsequently erases it. Correct locking defers stop until
                # registration finishes, then this test gates dispatch behind stop.
                stop_finished.wait(0.05)
            finally:
                release_registration.set()
                worker.join(2)
                if stopper.ident is not None:
                    stopper.join(2)
        self.assertFalse(worker.is_alive())
        self.assertFalse(stopper.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual([result.status for result in outcomes], ["stopped"])
        self.assertFalse(any(map(nonzero, robot._backend.commands)))


if __name__ == "__main__":
    unittest.main()
