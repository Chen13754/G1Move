import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from g1_move import G1Move, MotionError
from g1_move.backends import UnitreeBackend


class UnitreeBackendTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(spec=["SetTimeout", "Init", "SetVelocity"])
        self.client.SetVelocity.return_value = 0
        self.factory = Mock(return_value=None)
        self.client_class = Mock(return_value=self.client)
        channel = types.ModuleType("unitree_sdk2py.core.channel")
        channel.ChannelFactoryInitialize = self.factory
        loco = types.ModuleType("unitree_sdk2py.g1.loco.g1_loco_client")
        loco.LocoClient = self.client_class
        modules = {name: types.ModuleType(name) for name in (
            "unitree_sdk2py", "unitree_sdk2py.core", "unitree_sdk2py.g1", "unitree_sdk2py.g1.loco")}
        modules.update({channel.__name__: channel, loco.__name__: loco})
        self.modules = patch.dict(sys.modules, modules)
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.dds_config = patch.object(UnitreeBackend, "_dds_config", None)
        self.dds_config.start()
        self.addCleanup(self.dds_config.stop)

    def test_adapter_initializes_sdk_and_only_sends_set_velocity(self):
        with G1Move(backend="unitree", interface="fake0") as robot:
            robot.stop()
        self.factory.assert_called_once_with(0, "fake0")
        self.client.SetTimeout.assert_called_once_with(2.0)
        self.client.Init.assert_called_once_with()
        self.assertEqual([c[0] for c in self.client.method_calls],
                         ["SetTimeout", "Init", "SetVelocity", "SetVelocity", "SetVelocity"])
        for call in self.client.SetVelocity.call_args_list:
            self.assertEqual(call.args, (0.0, 0.0, 0.0, 1.0))

    def test_explicit_simulation_domain_reaches_sdk(self):
        with G1Move(backend="unitree", interface="lo", dds_domain=1):
            pass
        self.factory.assert_called_once_with(1, "lo")
        self.client.SetVelocity.assert_called_with(0.0, 0.0, 0.0, 1.0)

    def test_invalid_domains_are_rejected_before_sdk_initialization(self):
        for domain in (-1, True, False, 1.0, "1", None):
            with self.subTest(domain=repr(domain)):
                with self.assertRaisesRegex(ValueError, "dds_domain"):
                    UnitreeBackend("fake0", 2, dds_domain=domain)
                for backend in ("mock", "unitree"):
                    with self.assertRaisesRegex(ValueError, "dds_domain"):
                        G1Move(backend=backend, interface="fake0", dds_domain=domain)
        self.factory.assert_not_called()
        self.client_class.assert_not_called()

    def test_native_arguments_are_forwarded_without_conversion(self):
        backend = UnitreeBackend("fake0", 1.5)
        backend.set_velocity(0.1, -0.2, 0.3, 4.5)
        self.client.SetVelocity.assert_called_once_with(0.1, -0.2, 0.3, 4.5)

    def test_every_unconfirmed_return_code_is_an_error(self):
        backend = UnitreeBackend("fake0", 2)
        for code in (1, -1, None, False, True, "0", 0.0):
            with self.subTest(code=repr(code)):
                self.client.SetVelocity.return_value = code
                with self.assertRaisesRegex(MotionError, "unconfirmed"):
                    backend.set_velocity(.1, 0, 0, 1)

    def test_rpc_exception_is_reported_once_without_retry(self):
        backend = UnitreeBackend("fake0", 2)
        self.client.SetVelocity.side_effect = TimeoutError("no response")
        with self.assertRaisesRegex(MotionError, "no response"):
            backend.set_velocity(.1, 0, 0, 1)
        self.client.SetVelocity.assert_called_once()

    def test_channel_failure_prevents_creating_client(self):
        self.factory.return_value = False
        with self.assertRaisesRegex(MotionError, "initialization failed"):
            UnitreeBackend("fake0", 2)
        self.client_class.assert_not_called()

    def test_channel_is_shared_but_cannot_silently_change_domain_or_interface(self):
        UnitreeBackend("fake0", 2, dds_domain=1)
        UnitreeBackend("fake0", 2, dds_domain=1)
        self.factory.assert_called_once_with(1, "fake0")
        for domain, interface in ((1, "fake1"), (0, "fake0"), (2, "fake1")):
            with self.subTest(domain=domain, interface=interface):
                with self.assertRaisesRegex(MotionError, "different domain or interface"):
                    UnitreeBackend(interface, 2, dds_domain=domain)
        self.assertEqual(self.client_class.call_count, 2)
        self.factory.assert_called_once_with(1, "fake0")

    def test_failed_channel_initialization_does_not_cache_configuration(self):
        self.factory.side_effect = [False, None]
        with self.assertRaises(MotionError):
            UnitreeBackend("fake0", 2)
        UnitreeBackend("lo", 2, dds_domain=1)
        self.assertEqual(self.factory.call_args_list[-1].args, (1, "lo"))
        self.client_class.assert_called_once()

    def test_missing_interface_and_fast_real_execution_are_rejected(self):
        for interface in (None, "", "   "):
            with self.subTest(interface=interface):
                with self.assertRaises(ValueError):
                    G1Move(backend="unitree", interface=interface)
        with self.assertRaises(ValueError):
            G1Move(backend="unitree", interface="fake0", mock_realtime=False)
        self.factory.assert_not_called()


class ImportIsolationTests(unittest.TestCase):
    def test_mock_import_and_motion_never_import_unitree(self):
        code = """
import importlib.abc
import sys
class BlockUnitree(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith('unitree_sdk2py'):
            raise AssertionError('Mock attempted to import Unitree: ' + fullname)
sys.meta_path.insert(0, BlockUnitree())
from g1_move import G1Move
with G1Move(mock_realtime=False) as robot:
    robot.move('forward', 1)
    robot.turn('left', 90)
assert not any(name.startswith('unitree_sdk2py') for name in sys.modules)
"""
        result = subprocess.run([sys.executable, "-c", code],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
