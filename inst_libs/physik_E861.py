# physik_E861.py
# Minimal control class: PI N-565.360 linear stage + E-861 NEXACT controller (GCS2 via PIPython)
# Exposes the same method names/signatures as thorlabs_LinearStage_BBD202.LinearStage,
# so the GUI code can switch stages by changing only the import and the connection parameters.
import threading
import time

from pipython import GCSDevice, GCSError
from pipython.pitools import waitonreferencing


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
        on_target_tolerance_mm: float = 0.00005,
        position_hold_ms: int = 200,
    ):
        self.serial = str(controller_serial)
        self.axis = str(axis)
        self.move_predelay_s = float(move_predelay_s)
        self.on_target_tolerance_mm = float(on_target_tolerance_mm)
        self.position_hold_ms = int(position_hold_ms)
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

        After MOV it polls qONT and qPOS every ~20 ms (instead of pipython's waitontarget):
        - ONT true and |qPOS - target| <= tolerance: arrived.
        - |qPOS - target| <= tolerance for position_hold_ms in a row while ONT stays false:
          also arrived, with a warning. The E-861 only sets ONT after the position has stayed
          within its settle window (+/-5 nm) for 10 ms; at some targets the NEXACT servo keeps
          hunting within about +/-15 nm for seconds (measured 2026-11-09), and waiting for ONT
          there only costs time.
        - Otherwise keep waiting until timeout_ms.
        The tolerance (default 50 nm) must stay below the scan step (1 um), or a move that has not
        started would already count as arrived. move_predelay_s skips the few milliseconds in which
        the controller can still report the previous move's ONT flag.
        """
        pos_mm = float(pos_mm)
        if not self.min_pos <= pos_mm <= self.max_pos:
            raise ValueError(
                f"Target {pos_mm} mm is outside the travel range {self.min_pos} .. {self.max_pos} mm."
            )
        tol = self.on_target_tolerance_mm if tolerance_mm is None else float(tolerance_mm)
        hold_s = max(self.position_hold_ms, 0) / 1000.0
        with self._lock:
            self._dev.MOV(self.axis, pos_mm)
            time.sleep(max(self.move_predelay_s, 0.0))
            self._dev.checkerror()  # as waitontarget() did: report a controller error raised by the move

            t_start = time.time()
            deadline = t_start + max(timeout_ms, 0) / 1000.0
            near_since = None  # first poll of the current run of polls within tolerance
            while True:
                on_target = bool(self._dev.qONT(self.axis)[self.axis])
                actual = float(self._dev.qPOS(self.axis)[self.axis])
                now = time.time()
                if abs(actual - pos_mm) <= tol:
                    if on_target:
                        return actual
                    if near_since is None:
                        near_since = now
                    elif now - near_since >= hold_s:
                        print(
                            f"[PI] Axis {self.axis}: ONT still false after {now - t_start:.2f} s, but the "
                            f"position stayed within {tol * 1e6:.0f} nm of {pos_mm:.4f} mm for "
                            f"{hold_s * 1000:.0f} ms; accepted at {actual:.6f} mm "
                            f"({(actual - pos_mm) * 1e6:+.1f} nm)."
                        )
                        return actual
                else:
                    near_since = None
                if now >= deadline:
                    self._dev.checkerror()  # a controller error (e.g. servo off) explains the timeout best
                    raise RuntimeError(
                        f"Axis {self.axis} did not reach {pos_mm:.5f} mm within {timeout_ms} ms: "
                        f"at {actual:.5f} mm ({(actual - pos_mm) * 1e6:+.1f} nm), ONT {on_target}, "
                        f"tolerance {tol * 1e6:.0f} nm."
                    )
                time.sleep(0.02)

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
