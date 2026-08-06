import sys
import time
import clr

KINESIS_DIR = r"C:\Program Files\Thorlabs\Kinesis"
if KINESIS_DIR not in sys.path:
    sys.path.append(KINESIS_DIR)

clr.AddReference("Thorlabs.MotionControl.DeviceManagerCLI")
clr.AddReference("Thorlabs.MotionControl.FilterFlipperCLI")

from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI, SimulationManager, DeviceConfiguration
from Thorlabs.MotionControl.FilterFlipperCLI import FilterFlipper as KinesisFilterFlipper
from Thorlabs.MotionControl.FilterFlipperCLI.Native import FilterFlipperIOSettings


class FilterFlipper:
    """
    MFF01 / MFF101 / MFF102 filter flipper controller (Kinesis).
    - Two discrete positions: 1 and 2.
    - Manual notes: Move/Jog direction uses 1 (clockwise) or 2 (counterclockwise).
    - Status bits: bit1 indicates upright (1) or horizontal (0).
    """

    POSITION_1 = 1
    POSITION_2 = 2
    STATUS_BIT_UPRIGHT = 0x02

    IO_OPERATING_MODES = FilterFlipperIOSettings.FFOperatingModes
    IO_SIGNAL_MODES = FilterFlipperIOSettings.FFSignalModes

    def __init__(self, controller_serial: str, poll_ms: int = 200, use_sim: bool = False):
        self.serial = str(controller_serial)
        self.poll_ms = int(poll_ms)
        self.use_sim = bool(use_sim)
        self._device = None

        if self.use_sim:
            SimulationManager.Instance.InitializeSimulations()

        DeviceManagerCLI.BuildDeviceList()
        self._device = KinesisFilterFlipper.CreateFilterFlipper(self.serial)
        self._device.Connect(self.serial)

        self._device.StartPolling(self.poll_ms)
        time.sleep(self.poll_ms / 1000.0)
        self._device.EnableDevice()
        time.sleep(self.poll_ms / 1000.0)

        try:
            info = self._device.GetDeviceInfo()
            print(f"[Kinesis] {info.Description}")
        except Exception:
            pass

        try:
            config = self._device.GetDeviceConfiguration(
                self.serial, DeviceConfiguration.DeviceSettingsUseOptionType.UseFileSettings
            )
            config.UpdateCurrentConfiguration(
                DeviceConfiguration.DeviceSettingsUseOptionType.UseFileSettings,
                DeviceConfiguration.MergeMode.MergeLoadedSettings,
            )
            self._device.SetSettings(self._device.FilterFlipperDeviceSettings, True, False)
        except Exception:
            pass

        if not self._device.IsSettingsInitialized():
            self._device.WaitForSettingsInitialized(10000)
            if not self._device.IsSettingsInitialized():
                raise RuntimeError("Device settings failed to initialize.")

    # ---------- Basic operations ----------
    def home(self, timeout_ms: int = 60000):
        """Home the flipper (blocking)."""
        print("[Kinesis] Homing...")
        self._device.Home(timeout_ms)
        print("[Kinesis] Homed.")

    def move_to(self, position: int, timeout_ms: int = 10000):
        """Move to position 1 or 2."""
        if position not in (self.POSITION_1, self.POSITION_2):
            raise ValueError("position must be 1 or 2.")
        self._device.SetPosition(int(position), int(timeout_ms))

    def move_jog(self, direction: int, timeout_ms: int = 10000):
        """Move/Jog direction: 1 = clockwise, 2 = counterclockwise."""
        if direction not in (self.POSITION_1, self.POSITION_2):
            raise ValueError("direction must be 1 (clockwise) or 2 (counterclockwise).")
        self.move_to(direction, timeout_ms)

    def toggle(self, timeout_ms: int = 10000) -> int:
        """Toggle between position 1 and 2. Returns the target position."""
        current = self.position()
        target = self.POSITION_2 if current == self.POSITION_1 else self.POSITION_1
        self.move_to(target, timeout_ms)
        return target

    def position(self) -> int:
        """Read current position (1 or 2)."""
        self._device.RequestPosition()
        return int(self._device.Position)

    def get_status_bits(self) -> int:
        """Return status bits; bit1 indicates upright (1) or horizontal (0)."""
        self._device.RequestStatusBits()
        return int(self._device.GetStatusBits())

    def is_upright(self) -> bool:
        """True if the manual's upright position bit is set."""
        return bool(self.get_status_bits() & self.STATUS_BIT_UPRIGHT)

    def enable(self):
        self._device.EnableDevice()

    def disable(self):
        self._device.DisableDevice()

    # ---------- I/O settings ----------
    def get_io_settings(self) -> FilterFlipperIOSettings:
        """Return IO settings (including transition time)."""
        self._device.RequestIOSettings()
        return self._device.GetIOSettings()

    def set_io_settings(self, io_settings: FilterFlipperIOSettings, persist: bool = False):
        """Apply IO settings; set persist=True to store in hardware."""
        self._device.SetIOSettings(io_settings)
        if persist:
            self._device.PersistSettings()

    def get_transition_time(self) -> int:
        """Return transition time in ms (range 300 to 2800)."""
        return int(self.get_io_settings().TransitTime)

    def set_transition_time(self, transit_ms: int, persist: bool = False):
        """Set transition time in ms (range 300 to 2800)."""
        if not 300 <= int(transit_ms) <= 2800:
            raise ValueError("transit_ms must be within 300 to 2800 ms.")
        io_settings = self.get_io_settings()
        io_settings.TransitTime = int(transit_ms)
        self.set_io_settings(io_settings, persist=persist)

    def persist_settings(self):
        """Persist current settings to hardware."""
        self._device.PersistSettings()

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
