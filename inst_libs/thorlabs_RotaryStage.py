import os
import time
import sys
import clr

KINESIS_DIR = r"C:\Program Files\Thorlabs\Kinesis"
if KINESIS_DIR not in sys.path:
    sys.path.append(KINESIS_DIR)

clr.AddReference("Thorlabs.MotionControl.DeviceManagerCLI")
clr.AddReference("Thorlabs.MotionControl.GenericMotorCLI")
clr.AddReference("Thorlabs.MotionControl.KCube.DCServoCLI")
#clr.AddReference("Thorlabs.MotionControl.KCube.DCServoUI")

from Thorlabs.MotionControl.DeviceManagerCLI import *
from Thorlabs.MotionControl.GenericMotorCLI import *
from Thorlabs.MotionControl.KCube.DCServoCLI import *
from System import Decimal

class RotaryStage:
    """
    KCube DC Servo (KDC101) minimal controller.
    - Pass the controller serial (e.g., '27000001').
    - Units are real-world (mm) per Kinesis stage file.
    - Initialization flow mirrors your DDS220 example.
    """

    def __init__(self, controller_serial: str, poll_ms: int = 200, use_sim: bool = False):
        self.serial = str(controller_serial)
        self.poll_ms = int(poll_ms)
        self._device = None
        self.use_sim = bool(use_sim)

        # Optional: enable simulation mode if desired (matches the example pattern)
        if self.use_sim:
            SimulationManager.Instance.InitializeSimulations()

        # 1) Build device list
        DeviceManagerCLI.BuildDeviceList()

        # 2) Create and connect device
        self._device = KCubeDCServo.CreateKCubeDCServo(self.serial)
        self._device.Connect(self.serial)

        # 3) Start polling and enable device
        self._device.StartPolling(self.poll_ms)
        time.sleep(self.poll_ms / 1000.0)
        self._device.EnableDevice()
        time.sleep(self.poll_ms / 1000.0)

        # 4) (Optional) read device info
        try:
            info = self._device.GetDeviceInfo()
            print(f"[Kinesis] {info.Description}")
        except Exception:
            pass

        # 5) Load configuration & apply settings
        #    For KCube DC Servo, use serial directly.
        mcfg = self._device.LoadMotorConfiguration(self.serial)
        mcfg.UpdateCurrentConfiguration()
        self._device.SetSettings(self._device.MotorDeviceSettings, True, False)

        # 6) Wait for settings to initialize
        if not self._device.IsSettingsInitialized():
            self._device.WaitForSettingsInitialized(10000)  # 10s timeout
            if not self._device.IsSettingsInitialized():
                raise RuntimeError("Device settings failed to initialize.")

    # ---------- Basic operations ----------
    def home(self, timeout_ms: int = 60000):
        """Home the stage (blocking until done or timeout)."""
        print("[Kinesis] Homing...")
        self._device.Home(timeout_ms)
        print("[Kinesis] Homed.")

    def get_homing_params(self):
        """Return homing params object (Velocity, Direction)."""
        return self._device.GetHomingParams()

    def set_homing_params(self, params):
        """Set homing params if you edited them."""
        self._device.SetHomingParams(params)

    def get_velocity(self) -> tuple[float, float]:
        """Return (MaxVelocity_mm_s, Acceleration_mm_s2)."""
        vp = self._device.GetVelocityParams()
        return float(str(vp.MaxVelocity)), float(str(vp.Acceleration))

    def set_velocity(self, vmax_mm_s: float, acc_mm_s2: float):
        """Set velocity parameters using real-world units (mm/s, mm/s^2)."""
        vp = self._device.GetVelocityParams()
        vp.MaxVelocity = Decimal(float(vmax_mm_s))
        vp.Acceleration = Decimal(float(acc_mm_s2))
        self._device.SetVelocityParams(vp)

    def move_to(self, pos_mm: float, timeout_ms: int = 60000):
        """Absolute move to pos_mm (Decimal for real units)."""
        self._device.MoveTo(Decimal(float(pos_mm)), timeout_ms)

    def move_by(self, delta_mm: float, timeout_ms: int = 60000):
        """Relative move by delta_mm (supports direction + timeout overload)."""
        if delta_mm == 0:
            return
        direction = MotorDirection.Forward if delta_mm > 0 else MotorDirection.Backward
        self._device.MoveRelative(direction, Decimal(float(abs(delta_mm))), timeout_ms)

    def stop(self, timeout_ms: int = 10000):
        """Smooth stop."""
        self._device.Stop(timeout_ms)

    def position(self) -> float:
        """Read current position in mm (convert Decimal to float)."""
        return float(str(self._device.Position))

    def is_homed(self) -> bool:
        return bool(self._device.IsHomed)

    def close(self):
        """Stop polling and disconnect."""
        try:
            self._device.StopPolling()
        except Exception:
            pass
        try:
            self._device.Disconnect()
        except Exception:
            pass
        
        if self.use_sim:
            try:
                SimulationManager.Instance.UninitializeSimulations()
            except Exception:
                pass

