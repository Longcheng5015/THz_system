# physik_E861.py
# Minimal control class: PI N-565.360 linear stage + E-861 NEXACT controller (GCS2 via PIPython)
# Exposes the same method names/signatures as thorlabs_LinearStage_BBD202.LinearStage,
# so the GUI code can switch stages by changing only the import and the connection parameters.
import threading
import time

from pipython import GCSDevice, GCSError
from pipython.pitools import waitontarget, waitonreferencing


class LinearStage:
    """
    N-565.360 linear stage driven by an E-861 PiezoWalk controller, connected over USB.
    - Pass the controller serial as printed on the case (e.g. '0119001337') and the GCS axis ID ('1').
    - Units are real-world (mm), matching the stage parameters loaded into the controller (CST).
    - The controller keeps one axis per unit, so one instance owns one controller.
    - All device I/O is serialized by a lock: the GUI reads the position from the main thread while
      the scan thread is moving, and two overlapping GCS requests would desynchronize the replies.
    """

    def __init__(
        self,
        controller_serial: str,
        axis: str = "1",
        devname: str = "E-861",
        servo_on: bool = True,
        reference_if_needed: bool = True,
        reference_timeout_ms: int = 60000,
        move_predelay_s: float = 0.05,
        on_target_tolerance_mm: float = 0.001,
        settle_timeout_ms: int = 1000,
    ):
        self.serial = str(controller_serial)
        self.axis = str(axis)
        self.move_predelay_s = float(move_predelay_s)
        self.on_target_tolerance_mm = float(on_target_tolerance_mm)
        self.settle_timeout_ms = int(settle_timeout_ms)
        self._lock = threading.RLock()
        self._dev = GCSDevice(devname)

        self._dev.ConnectUSB(self.serial)
        print(f"[PI] Connected: {self._dev.qIDN().strip()}")

        if self.axis not in self._dev.axes:
            self._dev.CloseConnection()
            raise RuntimeError(f"Axis {self.axis!r} not available on E-861 {self.serial} (axes: {self._dev.axes}).")

        stage_type = self._dev.qCST()[self.axis]
        self.min_pos = float(self._dev.qTMN()[self.axis])
        self.max_pos = float(self._dev.qTMX()[self.axis])
        print(f"[PI] Axis {self.axis}: {stage_type}, travel {self.min_pos} .. {self.max_pos} mm")

        if servo_on:
            self.ensure_enabled()
        if reference_if_needed:
            self.home(reference_timeout_ms)

    # ---------- Servo state ----------
    def _is_enabled(self) -> bool:
        with self._lock:
            try:
                return bool(self._dev.qSVO()[self.axis])
            except GCSError:
                return False

    def ensure_enabled(self, timeout_ms: int = 5000, poll_interval_ms: int = 100):
        """Switch the servo on; MOV/MVR are rejected while it is off."""
        with self._lock:
            if self._is_enabled():
                return
            self._dev.SVO(self.axis, True)
            deadline = time.time() + max(timeout_ms, 0) / 1000.0
            while time.time() <= deadline:
                if self._is_enabled():
                    return
                time.sleep(max(poll_interval_ms, 10) / 1000.0)
        raise RuntimeError(f"Servo of axis {self.axis} did not switch on within {timeout_ms} ms.")

    # ---------- Basic operations ----------
    def home(self, timeout_ms: int = 60000):
        """Reference the axis (FRF). Already-referenced axes keep their position and are left alone."""
        with self._lock:
            if self._dev.qFRF()[self.axis]:
                print("[PI] Axis already referenced, skipping reference move.")
                return
            print("[PI] Referencing...")
            self._dev.FRF(self.axis)
            waitonreferencing(self._dev, axes=self.axis, timeout=max(timeout_ms, 0) / 1000.0)
            print("[PI] Referenced.")

    def home_with_guard(self, timeout_ms: int = 60000, enable_timeout_ms: int = 5000):
        """Reference with an explicit servo-state guard (same role as the Thorlabs variant)."""
        self.ensure_enabled(timeout_ms=enable_timeout_ms)
        self.home(timeout_ms)

    def travel_limits(self) -> tuple[float, float]:
        """Return (min, max) travel in mm, as reported by the controller on connect."""
        return self.min_pos, self.max_pos

    def get_velocity(self) -> tuple[float, float]:
        """Return (velocity_mm_s, acceleration_mm_s2)."""
        with self._lock:
            return float(self._dev.qVEL()[self.axis]), float(self._dev.qACC()[self.axis])

    def set_velocity(self, vmax_mm_s: float, acc_mm_s2: float):
        """Set closed-loop velocity and acceleration in real-world units (mm/s, mm/s^2)."""
        with self._lock:
            self._dev.VEL(self.axis, float(vmax_mm_s))
            self._dev.ACC(self.axis, float(acc_mm_s2))

    def move_to(self, pos_mm: float, timeout_ms: int = 60000, tolerance_mm: float | None = None):
        """Absolute move to pos_mm, blocking until the axis has really reached the target.

        waitontarget() starts polling qONT right after MOV, and the controller can still report
        the previous move's on-target flag for a few milliseconds, so on its own it can return
        while the axis has not even started moving. move_predelay_s skips that window, and the
        qPOS check afterwards confirms the arrival instead of trusting ONT alone (the ONT window
        is a controller parameter and may be wider than the scan step).
        """
        pos_mm = float(pos_mm)
        if not self.min_pos <= pos_mm <= self.max_pos:
            raise ValueError(
                f"Target {pos_mm} mm is outside the travel range {self.min_pos} .. {self.max_pos} mm."
            )
        tol = self.on_target_tolerance_mm if tolerance_mm is None else float(tolerance_mm)
        with self._lock:
            self._dev.MOV(self.axis, pos_mm)
            time.sleep(max(self.move_predelay_s, 0.0))
            waitontarget(self._dev, axes=self.axis, timeout=max(timeout_ms, 0) / 1000.0)

            deadline = time.time() + max(self.settle_timeout_ms, 0) / 1000.0
            while True:
                actual = float(self._dev.qPOS()[self.axis])
                error_mm = abs(actual - pos_mm)
                if error_mm <= tol:
                    return actual
                if time.time() >= deadline:
                    raise RuntimeError(
                        f"Axis {self.axis} reported on-target at {actual:.5f} mm, "
                        f"{error_mm * 1000:.2f} um away from target {pos_mm:.5f} mm "
                        f"(tolerance {tol * 1000:.2f} um)."
                    )
                time.sleep(0.01)

    def move_by(self, delta_mm: float, timeout_ms: int = 60000, tolerance_mm: float | None = None):
        """Relative move by delta_mm, blocking until the axis is on target."""
        if delta_mm == 0:
            return
        return self.move_to(self.position() + float(delta_mm), timeout_ms, tolerance_mm)

    def stop(self, timeout_ms: int = 10000):
        """Halt the axis smoothly. HLT always leaves error code 10 behind, which qERR clears."""
        with self._lock:
            try:
                self._dev.HLT(self.axis)
            except GCSError:
                pass
            self._dev.qERR()

    def position(self) -> float:
        """Read the current position in mm."""
        with self._lock:
            return float(self._dev.qPOS()[self.axis])

    def is_homed(self) -> bool:
        """True once the axis has been referenced."""
        with self._lock:
            return bool(self._dev.qFRF()[self.axis])

    def close(self):
        """Close the USB connection. The servo is left on so the axis holds its position."""
        with self._lock:
            self._dev.CloseConnection()
            print(f"[PI] E-861 {self.serial} closed.")
