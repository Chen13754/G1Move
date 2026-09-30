"""Only SetVelocity is used; importing this module does not load Unitree DDS."""

from dataclasses import dataclass
import threading


class MotionError(RuntimeError):
    """A command or SDK operation failed; no automatic motion retry occurs."""


class BusyError(MotionError):
    """Another motion or sequence is executing on this instance."""


@dataclass(frozen=True)
class VelocityCommand:
    vx: float
    vy: float
    omega: float
    duration: float


class MockBackend:
    def __init__(self):
        self.commands: list[VelocityCommand] = []

    def set_velocity(self, vx: float, vy: float, omega: float, duration: float):
        self.commands.append(VelocityCommand(vx, vy, omega, duration))


def _validate_dds_domain(dds_domain: int) -> None:
    if isinstance(dds_domain, bool) or not isinstance(dds_domain, int) or dds_domain < 0:
        raise ValueError("dds_domain must be a nonnegative integer, not a bool")


class UnitreeBackend:
    _initialization_lock = threading.Lock()
    _dds_config: tuple[int, str] | None = None

    def __init__(self, interface: str, timeout_s: float, *, dds_domain: int = 0):
        _validate_dds_domain(dds_domain)
        if not isinstance(interface, str) or not interface.strip():
            raise ValueError("unitree backend requires a network interface, e.g. 'eth0'")
        try:
            from unitree_sdk2py.core.channel import ChannelFactoryInitialize
            from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient
        except (ImportError, OSError) as exc:
            raise MotionError("Unitree SDK is unavailable. On Ubuntu, run bash scripts/setup_unitree.sh") from exc
        try:
            with self._initialization_lock:
                dds_config = (dds_domain, interface)
                if self.__class__._dds_config is None:
                    if ChannelFactoryInitialize(dds_domain, interface) is False:
                        raise MotionError("Unitree DDS initialization failed")
                    self.__class__._dds_config = dds_config
                elif self.__class__._dds_config != dds_config:
                    raise MotionError(
                        "Unitree DDS is already initialized with a different domain or interface; "
                        "use a fresh process to change DDS configuration"
                    )
            self._client = LocoClient()
            self._client.SetTimeout(timeout_s)
            self._client.Init()
        except MotionError:
            raise
        except Exception as exc:
            raise MotionError(f"Unitree SDK initialization failed: {exc}") from exc

    def set_velocity(self, vx: float, vy: float, omega: float, duration: float):
        try:
            code = self._client.SetVelocity(vx, vy, omega, duration)
        except Exception as exc:
            raise MotionError(f"SetVelocity RPC failed: {exc}") from exc
        # Do not call Move()/StopMove(): those Python convenience methods discard the code.
        if isinstance(code, bool) or not isinstance(code, int) or code != 0:
            raise MotionError(f"SetVelocity rejected or unconfirmed (SDK code={code!r})")
