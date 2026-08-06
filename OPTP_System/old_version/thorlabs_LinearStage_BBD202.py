# dds220_stage.py
# Minimal control class: DDS220 + BBD-series (Benchtop Brushless DC) controller
import os
import sys
import time
import clr # clr means pythonnet package

KINESIS_DIR = r"C:\Program Files\Thorlabs\Kinesis"  # Verify your install path
if KINESIS_DIR not in sys.path:
    sys.path.append(KINESIS_DIR)  # add KINESIS_DIR into search_path_list for python_module 

# Load .NET assemblies
clr.AddReference("Thorlabs.MotionControl.DeviceManagerCLI")
clr.AddReference("Thorlabs.MotionControl.GenericMotorCLI")
clr.AddReference("Thorlabs.MotionControl.Benchtop.BrushlessMotorCLI")

from Thorlabs.MotionControl.DeviceManagerCLI import *
from Thorlabs.MotionControl.GenericMotorCLI import *
from Thorlabs.MotionControl.Benchtop.BrushlessMotorCLI import *
from System import Decimal  # necessary for real world units

 # Create a global cache, the same serial share the same controller and reference count
_BBD_DEVICES: dict[str, BenchtopBrushlessMotor] = {}
_BBD_REFCOUNT: dict[str, int] = {}

class LinearStage:
    """
    DDS210 linear stage driven by a Benchtop Brushless DC (BBD20x/BBD30x) controller.
    - Pass the controller serial (e.g., '103000001') and the channel index (1/2/3).
    - Units are real-world (mm) per Kinesis stage file.
    - Note: for multiple channels, create multiple LinearStage instances with same serial but different channel.
      To realize it, create a golbal Device instance and get different channels from it if the controller with same serial has been created.
    - Initialization flow mirrors Thorlabs official Pythonnet example .
    """
   
    
    
    def __init__(self, controller_serial: str, channel: int = 1, poll_ms: int = 200, use_sim: bool = False):
        self.serial = str(controller_serial)
        self.channel_index = int(channel)
        self.poll_ms = int(poll_ms)
        self._device = None
        self._chan = None
        self.use_sim = bool(use_sim)    
        
        if self.use_sim:
            try:
                SimulationManager.Instance.UninitializeSimulations()
            except Exception:
                pass

        # ======== 1) Only create/connect device if not already done ========
        global _BBD_DEVICES, _BBD_REFCOUNT
        
        # if use simulation, do the similar cache mechanism
        if self.use_sim:
            DeviceManagerCLI.BuildDeviceList()
            self._device = BenchtopBrushlessMotor.CreateBenchtopBrushlessMotor(self.serial)
            self._device.Connect(self.serial)
            print(f"[Kinesis] (Simulation) Created and connect new BBD device for serial {self.serial}")
        else:
            if self.serial in _BBD_DEVICES:
                # Already exists the same serial device
                self._device = _BBD_DEVICES[self.serial]
                _BBD_REFCOUNT[self.serial] += 1
                print(f"[Kinesis] Reusing existing BBD device for serial {self.serial}, refcount={_BBD_REFCOUNT[self.serial]}")
            else:
                # Create new device if the serial not exists
                # 1) Build device list
                DeviceManagerCLI.BuildDeviceList()
                # 2) Create and connect device, then get channel
                self._device = BenchtopBrushlessMotor.CreateBenchtopBrushlessMotor(self.serial)
                self._device.Connect(self.serial)
                _BBD_DEVICES[self.serial] = self._device
                _BBD_REFCOUNT[self.serial] = 1
                print(f"[Kinesis] Created and connect new BBD device for serial {self.serial}")

        # ======== 2) Get appointed channel from controller ========
        self._chan = self._device.GetChannel(self.channel_index)
        if self._chan is None:
            raise RuntimeError(f"GetChannel({self.channel_index}) returned None. Check controller & channel index.")

        # 3) Start polling and enable device (exactly like the example)
        self._chan.StartPolling(self.poll_ms)
        time.sleep(self.poll_ms / 1000.0)
        self._chan.EnableDevice()
        time.sleep(self.poll_ms / 1000.0)

        # 4) (Optional) read device info
        try:
            info = self._chan.GetDeviceInfo()
            print(f"[Kinesis] {info.Description}")
        except Exception:
            pass

        # 5) Load configuration & apply settings (official flow)
        #    NOTE: Use channel.DeviceID (serial + channel) per example.
        #    Then UpdateCurrentConfiguration() and SetSettings(device_settings, False).
        motor_config = self._chan.LoadMotorConfiguration(self._chan.DeviceID)
        device_settings = self._chan.MotorDeviceSettings

        # Push the current configuration into device_settings object
        motor_config.UpdateCurrentConfiguration()
        self._chan.SetSettings(device_settings, False)

        # 6) Wait for settings to initialize (example suggests assert afterwards)
        if not self._chan.IsSettingsInitialized():
            self._chan.WaitForSettingsInitialized(10000)  # 10s timeout
            if not self._chan.IsSettingsInitialized():
                raise RuntimeError("Channel settings failed to initialize.")

        # Done: the stage is ready

    # ---------- Basic operations ----------
    def home(self, timeout_ms: int = 60000):
        """Home the stage (official example uses 60s timeout)."""
        print("[Kinesis] Homing...")
        self._chan.Home(timeout_ms)
        print("[Kinesis] Homed.")

    def get_homing_params(self):
        """Return homing params object (Velocity, Direction)."""
        return self._chan.GetHomingParams()

    def set_homing_params(self, params):
        """Set homing params if you edited them."""
        self._chan.SetHomingParams(params)

    def get_velocity(self) -> tuple[float, float]:
        """Return (MaxVelocity_mm_s, Acceleration_mm_s2)."""
        vp = self._chan.GetVelocityParams()
        return float(str(vp.MaxVelocity)), float(str(vp.Acceleration))

    def set_velocity(self, vmax_mm_s: float, acc_mm_s2: float):
        """Set velocity parameters using real-world units (mm/s, mm/s^2)."""
        vp = self._chan.GetVelocityParams()  # type: VelocityParameters
        vp.MaxVelocity = Decimal(float(vmax_mm_s))
        vp.Acceleration = Decimal(float(acc_mm_s2))
        self._chan.SetVelocityParams(vp)

    def move_to(self, pos_mm: float, timeout_ms: int = 60000):
        """Absolute move to pos_mm (Decimal for real units)."""
        self._chan.MoveTo(Decimal(float(pos_mm)), timeout_ms)

    def move_by(self, delta_mm: float, timeout_ms: int = 60000):
        """Relative move by delta_mm (Decimal for real units)."""
        if delta_mm == 0:
            return
        direction = MotorDirection.Forward if delta_mm > 0 else MotorDirection.Backward
        self._chan.MoveRelative(direction, Decimal(float(abs(delta_mm))), timeout_ms)

    def stop(self, timeout_ms: int = 10000):
        """Smooth stop."""
        self._chan.Stop(timeout_ms)

    def position(self) -> float:
        """Read current position in mm (convert Decimal to float)."""
        return float(str(self._chan.Position))

    def is_homed(self) -> bool:
        return bool(self._chan.IsHomed)

    def close(self):
        """Stop polling and disconnect.
           use a reference count mechanism to only disconnect when no more users.
        """
        global _BBD_DEVICES, _BBD_REFCOUNT
        
        # Stop polling of current channel
        try:
            self._chan.StopPolling()
        except Exception:
            pass
        
        # Simulation and physical device processing differently
        if self.use_sim:
            try:
                self._device.Disconnect()
            except Exception:
                pass
            
            try:
                SimulationManager.Instance.UninitializeSimulations()
            except Exception:
                pass
            return
        
        # Physical device: decrease reference count and disconnect if no more users
        if self.serial in _BBD_REFCOUNT:
            _BBD_REFCOUNT[self.serial] -= 1
            if _BBD_REFCOUNT[self.serial] <= 0:
                # No more users, disconnect and remove from cache
                dev = _BBD_DEVICES.pop(self.serial, None)
                _BBD_REFCOUNT.pop(self.serial, None)
                if dev is not None:
                    try:
                        dev.Disconnect()
                        print(f"[Kinesis] Disconnected BBD device for serial {self.serial}")
                    except Exception:
                        pass
                    
            


        