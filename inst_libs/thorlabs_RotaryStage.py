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

        # 7) Travel limits as configured in the controller, used to wrap/validate targets.
        try:
            limits = self._device.AdvancedMotorLimits
            self.min_pos = float(str(limits.LengthMinimum))
            self.max_pos = float(str(limits.LengthMaximum))
            print(f"[Kinesis] Travel {self.min_pos} .. {self.max_pos} deg")
        except Exception as exc:
            self.min_pos = self.max_pos = None
            print(f"[Kinesis] Warning: travel limits unreadable ({exc}); targets wrapped modulo 360.")

    # ---------- Basic operations ----------
    def home(self, timeout_ms: int = 60000):
        """Home the stage (blocking until done or timeout)."""
        # The controller keeps the homed flag while it stays powered, so a reconnect after the
        # Python side was closed does not need the full homing move again. It is cleared by a
        # power cycle or a limit/error condition, in which case this falls through and homes.
        if self.is_homed():
            print("[Kinesis] Axis already homed, skipping homing move.")
            return
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

    def travel_limits(self) -> tuple[float | None, float | None]:
        """Return (min, max) travel in degrees, or (None, None) if the controller did not report it."""
        return self.min_pos, self.max_pos

    def resolve_target(self, pos_deg: float) -> float:
        """Map a requested angle onto the axis travel.

        A rotation stage is circular, so 367 deg and 7 deg are the same optical configuration -
        but Kinesis rejects anything outside the configured travel with a bare
        "Cannot move to requested position". Targets outside a full-turn travel are therefore
        wrapped into it; on an axis whose travel is not a full turn there is nothing sensible to
        wrap to, so the target is rejected here with a message that names the limits.
        """
        target = float(pos_deg)
        lo, hi = self.min_pos, self.max_pos
        if lo is None or hi is None:
            wrapped = target % 360.0
        else:
            if lo <= target <= hi:
                return target
            span = hi - lo
            if abs(span - 360.0) > 1e-6:
                raise ValueError(
                    f"Target {target} deg is outside the travel range {lo} .. {hi} deg."
                )
            wrapped = lo + (target - lo) % span
        if wrapped != target:
            print(f"[Kinesis] {target} deg wrapped to {wrapped} deg (full-turn axis).")
        return wrapped

    def move_to(self, pos_mm: float, timeout_ms: int = 60000):
        """Absolute move to pos_mm (Decimal for real units)."""
        self._device.MoveTo(Decimal(self.resolve_target(pos_mm)), timeout_ms)

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
        """True when the controller reports the axis as homed.

        Kinesis keeps this on the status object (`Status.IsHomed`), not on the device itself;
        some builds instead expose a `NeedsHoming` flag. Anything unexpected is reported as
        "not homed" so the caller performs the homing move rather than skipping it.
        """
        try:
            return bool(self._device.Status.IsHomed)
        except Exception:
            pass
        try:
            return not bool(self._device.NeedsHoming)
        except Exception:
            pass
        return False

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

