"""Blocking relative moves implemented as timed native velocity commands."""

from dataclasses import dataclass
import math
import threading
import time
import warnings

from .backends import BusyError, MockBackend, MotionError, UnitreeBackend, _validate_dds_domain
from .config import MotionConfig, number


@dataclass(frozen=True)
class ActionResult:
    kind: str
    direction: str
    value: float
    unit: str
    duration_s: float
    status: str


@dataclass(frozen=True)
class _Action:
    kind: str
    direction: str
    value: float
    duration: float
    vx: float
    vy: float
    omega: float


class G1Move:
    def __init__(self, *, backend: str = "mock", interface: str | None = None,
                 config: MotionConfig | None = None, mock_realtime: bool = True,
                 dds_domain: int = 0):
        _validate_dds_domain(dds_domain)
        self.config = MotionConfig() if config is None else config
        if not isinstance(self.config, MotionConfig):
            raise ValueError("config must be a MotionConfig instance")
        if backend not in ("mock", "unitree"):
            raise ValueError("backend must be 'mock' or 'unitree'")
        if not isinstance(mock_realtime, bool):
            raise ValueError("mock_realtime must be a bool")
        if backend == "unitree" and not mock_realtime:
            raise ValueError("mock_realtime=False is only available with backend='mock'")
        self._fast = backend == "mock" and not mock_realtime
        self._cancel = threading.Event()
        self._action_lock = threading.Lock()
        self._send_lock = threading.RLock()
        self._closed = False
        self._close_stop_confirmed = False
        self._backend = (MockBackend() if backend == "mock"
                         else UnitreeBackend(interface, self.config.rpc_timeout_s, dds_domain=dds_domain))
        # Start with zero locomotion; never switch FSM, release the controller, or write joints.
        self._zero()

    def _plan(self, kind, direction, value) -> _Action:
        if kind not in ("move", "turn"):
            raise ValueError("Action kind must be 'move' or 'turn'")
        factors = self.config.move_time_factors if kind == "move" else self.config.turn_time_factors
        if not isinstance(direction, str) or direction not in factors:
            raise ValueError(f"Invalid {kind} direction: {direction!r}; choose {list(factors)}")
        value = number(value, "distance_m" if kind == "move" else "angle_deg")
        speed = self.config.linear_speed_mps if kind == "move" else self.config.angular_speed_deg_s
        duration = number(value / speed * factors[direction], "computed duration_s")
        vx = vy = omega = 0.0
        if kind == "move":
            vx, vy = {"forward": (speed, 0.0), "backward": (-speed, 0.0),
                      "left": (0.0, speed), "right": (0.0, -speed)}[direction]
        else:
            omega = math.radians(speed) * (1 if direction == "left" else -1)
        return _Action(kind, direction, value, duration, vx, vy, omega)

    def move(self, direction: str, distance_m: float) -> ActionResult:
        return self._execute([self._plan("move", direction, distance_m)])[0]

    def turn(self, direction: str, angle_deg: float) -> ActionResult:
        return self._execute([self._plan("turn", direction, angle_deg)])[0]

    def run_sequence(self, actions) -> list[ActionResult]:
        if not isinstance(actions, (list, tuple)) or not actions:
            raise ValueError("actions must be a non-empty list/tuple of (kind, direction, value)")
        planned = []
        for item in actions:
            if not isinstance(item, (list, tuple)) or len(item) != 3:
                raise ValueError("Each action must be (kind, direction, value)")
            planned.append(self._plan(*item))
        return self._execute(planned)

    def _execute(self, actions: list[_Action]) -> list[ActionResult]:
        # Register an action and reset cancellation atomically with stop().
        with self._send_lock:
            if self._closed:
                raise MotionError("G1Move is closed")
            if not self._action_lock.acquire(blocking=False):
                raise BusyError("An action is already running; call stop() to interrupt it")
            self._cancel.clear()
        try:
            results = []
            for action in actions:
                result = self._run(action)
                results.append(result)
                if result.status == "stopped":
                    break
            return results
        finally:
            self._action_lock.release()

    def _wait(self, duration: float) -> bool:
        return self._cancel.is_set() if self._fast else self._cancel.wait(max(0.0, duration))

    def _run(self, action: _Action) -> ActionResult:
        try:
            with self._send_lock:
                if self._cancel.is_set() or self._closed:
                    return self._result(action, "stopped")
                start = time.monotonic()
                self._backend.set_velocity(action.vx, action.vy, action.omega, action.duration)
            self._wait(action.duration - (time.monotonic() - start))
        except BaseException as exc:
            self._cleanup_failure(exc)
            raise
        self._zero()
        try:
            self._wait(self.config.pause_s)
        except BaseException as exc:
            self._cleanup_failure(exc)
            raise
        return self._result(action, "stopped" if self._cancel.is_set() else "completed")

    @staticmethod
    def _result(action: _Action, status: str) -> ActionResult:
        return ActionResult(action.kind, action.direction, action.value,
                            "m" if action.kind == "move" else "deg", action.duration, status)

    def _zero(self):
        with self._send_lock:
            self._backend.set_velocity(0.0, 0.0, 0.0, 1.0)

    def _cleanup_failure(self, original: BaseException):
        try:
            self._zero()
        except Exception as stop_error:
            if isinstance(original, Exception):
                raise MotionError(f"{original}; sending zero velocity also failed: {stop_error}") from original
            warnings.warn(f"Sending zero velocity after interruption failed: {stop_error}", RuntimeWarning)

    def stop(self) -> None:
        """Interrupt the current action/sequence and send zero velocity (not motor power-off)."""
        with self._send_lock:
            self._cancel.set()
            if self._closed and self._close_stop_confirmed:
                raise MotionError("G1Move is closed")
            self._zero()
            if self._closed:
                self._close_stop_confirmed = True

    def close(self) -> None:
        with self._send_lock:
            if self._closed and self._close_stop_confirmed:
                return
            self._closed = True
            self._cancel.set()
            self._zero()
            self._close_stop_confirmed = True

    def __enter__(self) -> "G1Move":
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc is None:
            self.close()
        else:
            try:
                self.close()
            except Exception as stop_error:
                if isinstance(exc, Exception):
                    raise MotionError(f"{exc}; closing with zero velocity also failed: {stop_error}") from exc
                warnings.warn(f"Sending zero velocity on exit failed: {stop_error}", RuntimeWarning)
        return False
