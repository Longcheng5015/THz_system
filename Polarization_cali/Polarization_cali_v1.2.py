#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Polarization & Power Calibration Program v1.2
This module provides a PySide6 GUI for automated polarization and power calibration.
Connected instruments:
  - 3 x Thorlabs KCube DC Servo Rotary Stages (Stage 1: 1/2 HWP, Stage 2: Polarizer, Stage 3: Aux)
  - Detector: 1 x Thorlabs PM100D Power Meter, or 1 x Stanford SR830 lock-in reading a fast detector
    (APD / PMT / balanced detector channel) at the laser's 1 kHz trigger

Version: v1.2
"""

import sys
import time
import traceback
from pathlib import Path
import numpy as np
import scipy.io as sio
import h5py
import pyvisa

# Path injection for inst_libs and func_cores
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
if str(parent_dir / "inst_libs") not in sys.path:
    sys.path.append(str(parent_dir / "inst_libs"))
if str(parent_dir / "func_cores") not in sys.path:
    sys.path.append(str(parent_dir / "func_cores"))
if str(parent_dir / "OPTP_System") not in sys.path:
    sys.path.append(str(parent_dir / "OPTP_System"))

try:
    from proj_tools import ProjectTools
    ProjectTools.inject_inst_libs(__file__)
    ProjectTools.inject_inst_libs(__file__, libs_dir_name="func_cores")
except Exception:
    pass

import pyqtgraph as pg
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QFileDialog, QLabel
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QThread, Signal, Slot, Qt, QTimer, QEvent
from PySide6.QtGui import QIcon

from MyWidget import LedIndicator
from thorlabs_PM100D import PM100D
from stanford_SR830 import SR830
from thorlabs_RotaryStage import RotaryStage
from scan_func_core import DataProcess, ScanPlanner
from inst_tools import InstrumentTools


class PowerMeterReader:
    """Detector = PM100D: absolute power in mW."""
    name, quantity, unit = "PM100D", "Power", "mW"

    def __init__(self, pm: PM100D):
        self.inst = pm

    def read(self) -> float:
        return self.inst.measure_power() * 1000.0  # W to mW


class LockinReader:
    """Detector = SR830 lock-in at the laser trigger: R (independent of the phase) in mV, proportional to the power."""
    name, quantity, unit = "Lock-in R", "Signal", "mV"

    def __init__(self, lockin: SR830, full_scale_v: float):
        self.inst = lockin
        self.full_scale = full_scale_v * 1000.0  # mV, the sensitivity chosen when the reader was made
        self.log = None                           # set by the scan worker: warns once if a reading exceeds the full scale
        self._warned = False

    def read(self) -> float:
        value = self.inst.get_r() * 1000.0  # V to mV
        if value > self.full_scale and self.log and not self._warned:
            self._warned = True
            self.log(f"Warning: lock-in R = {value:.4f} mV is above the sensitivity full scale ({self.full_scale:g} mV); "
                     f"readings may be clipped. Choose a less sensitive range.")
        return value


def list_lockin_resources() -> list:
    """VISA resources an SR830 can be on: GPIB and serial ports (both quick to list, unlike a full VISA scan)."""
    rm = pyvisa.ResourceManager()
    return [res for query in ("GPIB?*::INSTR", "ASRL?*::INSTR") for res in rm.list_resources(query)]


STABILITY_TIMEOUT_S = 60.0  # a measurement that has not settled after this long is recorded with Stable = False


def check_power_stability(detector, window_s: float, tolerance_mw: float, interval_s: float, tolerance_pct: float = 0.0,
                           stop_flag_check=None, logger=None) -> tuple[float, bool]:
    """
    Function to check if the detector reading (PowerMeterReader: mW, LockinReader: mV) is stable.
    Reads it every interval_s (Refresh) and looks at the last n = ceil(window_s / interval_s) + 1 readings, which cover
    at least window_s (Stable Window). Stable as soon as max - min of these n readings <= max(tolerance_mw,
    tolerance_pct % of their mean): the absolute value (in the detector's unit) is the floor at low power, the percentage
    follows the power. Returns their mean. Right after a stage move the readings still change, so the window does not pass
    until the detector has settled: no separate wait is needed. max - min also catches a slow drift in one direction.
    After STABILITY_TIMEOUT_S without that it gives up and returns the mean of the last n readings with is_stable False.
    A stop request returns the last reading with is_stable False.

    Returns:
        (reading, is_stable)
    """
    if detector is None:
        return 0.0, True

    n = max(2, int(np.ceil(window_s / interval_s - 1e-9)) + 1)  # 1e-9: 1.1 / 0.1 = 11.000000000000002
    t0 = time.monotonic()
    readings = []

    while True:
        t_read = time.monotonic()
        readings.append(detector.read())
        window = readings[-n:]

        if len(readings) >= n:
            mean = float(np.mean(window))
            spread = max(window) - min(window)
            tol = max(tolerance_mw, tolerance_pct / 100.0 * abs(mean))
            if logger:
                u = detector.unit
                logger(f"[Power Stability] {t_read - t0:.1f} s: {readings[-1]:.4f} {u} | "
                       f"last {n} readings: max - min {spread:.4f} {u} "
                       f"(Tol: {tol:.4f} {u} = max({tolerance_mw:g} {u}, {tolerance_pct:g} %))")
            if spread <= tol:
                return mean, True

        if time.monotonic() - t0 >= STABILITY_TIMEOUT_S:
            return float(np.mean(window)), False  # timed out: not stable

        # next reading interval_s after the start of this one (right away if the read took longer),
        # waiting in short steps, so a stop request (Stop, Exit) is seen within 0.1 s
        deadline = t_read + interval_s
        while True:
            if stop_flag_check and stop_flag_check():
                return readings[-1], False
            left = deadline - time.monotonic()
            if left <= 0:
                break
            time.sleep(min(0.1, left))


# Polarization mode, Model Tracking (Option C)
MT_MAX_STEP_DEG = 3.0            # largest single Stage 1 correction
MT_MAX_CORRECTIONS = 5           # corrections per Stage 2 angle after the first (predicted) measurement
MT_TARGET_RANGE = (0.05, 0.90)   # Target Power must lie at B + 5 % .. 90 % of A
MT_MIN_COARSE_POINTS = 5         # coarse scan: at least 5 points over one full 90° period of Stage 1

# hover text of the Polarization mode and of the Model Tracking option
POLAR_MODEL_TRACKING_TIP = (
    "<b>Model Tracking (Option C, default)</b><br>"
    "Laser → Stage 1 (half-wave plate, θ1) → Stage 2 (polarizer, θ2) → detector: P ≈ A·cos²(2θ1 − θ2 − φ) + B "
    "(P in mW with the PM100D, in mV with the lock-in).<ol>"
    "<li><b>Coarse scan</b> at the first Stage 2 angle: Stage 1 scans its Start / Step / Step NO. range "
    "(one full 90° period, at least 5 points) and P = A·cos²(2(θ1 − θ0)) + B is fitted (linear least squares).</li>"
    "<li><b>Check</b>: the target must lie between B + 5 % of A and B + 90 % of A, otherwise the scan stops "
    "(near the maximum the curve is flat and may not reach the target at every Stage 2 angle).</li>"
    "<li><b>Start</b> on the falling slope (power decreasing as θ1 increases), at the solution nearest the middle of the coarse range, "
    "and stay on that slope so the result is continuous.</li>"
    "<li><b>Every Stage 2 angle</b>: predict Stage 1 (the previous solution, then a straight line through the last two), "
    "measure, and correct with the model: Δθ1 = (x<sub>target</sub> − x<sub>measured</sub>) / 2, x = arccos √((P − B) / A), "
    "at most 3° per step.</li>"
    "<li><b>Accept</b> when |P − target| ≤ Target Tol and the reading is stable (Stability Tol). "
    "At most 6 measurements per angle; otherwise the closest one is recorded with Stable = False and the scan goes on.</li></ol>"
    "Every correction uses the measured power, so laser drift and model error are corrected. "
    "Usually 1-2 measurements per Stage 2 angle. The coarse scan and A, B, θ0 are saved with the data (.mat / .h5)."
)


class CalibrationAbort(Exception):
    """A scan that cannot go on for a reason the user can fix (message is shown as is)."""


def fit_hwp_model(theta1_deg, power_mw) -> tuple[float, float, float, float]:
    """Fit P = A*cos^2(2*(theta1 - theta0)) + B to a Stage 1 (half-wave plate) scan.

    cos^2(2x) = (1 + cos 4x) / 2, so P = c0 + c1*cos(4*theta1) + c2*sin(4*theta1) is linear in c0, c1, c2:
    a least-squares solve that needs no start values and cannot fail to converge.
    Returns (A, B, theta0_deg, rms_mw).
    """
    t = np.radians(np.asarray(theta1_deg, dtype=float))
    p = np.asarray(power_mw, dtype=float)
    m = np.column_stack([np.ones_like(t), np.cos(4 * t), np.sin(4 * t)])
    c, *_ = np.linalg.lstsq(m, p, rcond=None)
    amp = 2.0 * float(np.hypot(c[1], c[2]))
    theta0 = float(np.degrees(np.arctan2(c[2], c[1]) / 4.0))
    rms = float(np.sqrt(np.mean((m @ c - p) ** 2)))
    return amp, float(c[0]) - amp / 2.0, theta0, rms


def hwp_phase_deg(power_mw: float, amp: float, offset: float) -> float:
    """Phase x = 2*(theta1 - theta0) in degrees (0..90) at which the model gives power_mw (clamped to the model's range)."""
    r = min(max((power_mw - offset) / amp, 0.0), 1.0)
    return float(np.degrees(np.arccos(np.sqrt(r))))


class CalibrationWorker(QThread):
    """Worker thread executing the calibration scan logic without blocking UI."""

    # Signals
    sig_log = Signal(str)
    sig_progress = Signal(int)
    sig_point_done = Signal(dict)
    sig_model = Signal(dict)  # Model Tracking: coarse scan data and fitted model, saved with the points
    sig_scan_log = Signal(str)  # key events for the ScanLog box and file (tab 2)
    sig_finished = Signal(str, str)  # status ("finished" / "stopped" / "aborted" / "error"), message

    def __init__(self, detector, stage1_inst, stage2_inst, stage3_inst, config: dict):
        super().__init__()
        self.detector = detector  # PowerMeterReader / LockinReader, or None
        if isinstance(detector, LockinReader):
            detector.log = self.scan_event  # full-scale warning is a key event
        self.stage1_inst = stage1_inst
        self.stage2_inst = stage2_inst
        self.stage3_inst = stage3_inst
        self.config = config
        self._is_stopped = False

    def stop(self):
        self._is_stopped = True

    def scan_event(self, message: str):
        """A key event: shown in the log box and written to the ScanLog."""
        self.sig_log.emit(message)
        self.sig_scan_log.emit(message)

    def measure(self, where: str, logger=None) -> tuple[float, bool]:
        """check_power_stability with this scan's settings; a reading that does not settle is a ScanLog event."""
        reading, stable = check_power_stability(self.detector, self.config["stable_window"], self.config["stability_tol"],
                                                self.config["sample_interval"], self.config["stability_tol_pct"],
                                                stop_flag_check=lambda: self._is_stopped, logger=logger)
        if not stable and not self._is_stopped and self.detector is not None:
            self.scan_event(f"Not stable within {STABILITY_TIMEOUT_S:g} s at {where} "
                            f"(mean of the last {self.config['stable_window']:g} s: {reading:.4f} {self.config['signal_unit']})")
        return reading, stable

    def run(self):
        try:
            scan_mode = self.config["scan_mode"]
            polar_algo = self.config["polar_algo"]
            target_power = self.config["target_power"]
            target_tol = self.config["target_tol"]        # |P - target| that counts as reached (Polarization mode)
            unit = self.config["signal_unit"]             # mW (PM100D) or mV (lock-in); target and tolerances are in it

            stage1_cfg = self.config["stage1"]
            stage2_cfg = self.config["stage2"]
            stage3_cfg = self.config["stage3"]

            def build_seq(cfg):
                if not cfg["enabled"]:
                    return []
                start = cfg["start"]
                step = cfg["step"]
                no = cfg["no"]
                if no <= 0:
                    return []
                return [round(start + i * step, 2) for i in range(no)]

            s1_seq = build_seq(stage1_cfg) if stage1_cfg["enabled"] else [None]
            s2_seq = build_seq(stage2_cfg) if stage2_cfg["enabled"] else [None]
            s3_seq = build_seq(stage3_cfg) if stage3_cfg["enabled"] else [None]

            self.sig_log.emit(f"=== Starting Scan | Mode: {scan_mode} | Polar Algo: {polar_algo} ===")
            self.sig_log.emit(f"Sequence Lengths -> Stage1: {len(s1_seq)}, Stage2: {len(s2_seq)}, Stage3: {len(s3_seq)}")

            recorded_data = []
            total_points = len(s1_seq)
            point_count = 0

            # ----------------------------------------------------
            # MODE 1: Power mode
            # ----------------------------------------------------
            if scan_mode.lower().startswith("power"):
                # Stage 2 and Stage 3 stay at their Start angle, only Stage 1 scans.
                # A Stage 2/3 that is not enabled or not connected is not moved and is recorded as NaN.
                fixed_s2 = stage2_cfg["start"] if (stage2_cfg["enabled"] and self.stage2_inst) else np.nan
                fixed_s3 = stage3_cfg["start"] if (stage3_cfg["enabled"] and self.stage3_inst) else np.nan
                if not np.isnan(fixed_s2):
                    self.sig_log.emit(f"Moving Stage 2 to {fixed_s2}° (fixed during the scan)...")
                    self.stage2_inst.move_to(fixed_s2)
                if not np.isnan(fixed_s3):
                    self.sig_log.emit(f"Moving Stage 3 to {fixed_s3}° (fixed during the scan)...")
                    self.stage3_inst.move_to(fixed_s3)
                self.scan_event(f"Power mode: Stage 2 = {fixed_s2}°, Stage 3 = {fixed_s3}° (NaN = not enabled or not connected)")

                total_points = len(s1_seq)

                for angle1 in s1_seq:
                    if self._is_stopped:
                        break

                    moved = False
                    if self.stage1_inst and angle1 is not None:
                        self.sig_log.emit(f"Moving Stage 1 to {angle1}°...")
                        self.stage1_inst.move_to(angle1)
                        moved = True

                    power_mw, stable = self.measure(f"Stage 1 = {angle1}°",
                                                    logger=lambda msg: self.sig_log.emit(msg) if moved else None)

                    s1_pos = angle1 if stage1_cfg["enabled"] else np.nan
                    s2_pos = fixed_s2
                    s3_pos = fixed_s3

                    pt = {
                        "point_idx": point_count,
                        "stage1": s1_pos,
                        "stage2": s2_pos,
                        "stage3": s3_pos,
                        "power_mw": power_mw,
                        "target_power_mw": target_power,
                        "stable": stable
                    }
                    recorded_data.append(pt)

                    point_count += 1
                    prog = int((point_count / total_points) * 100)
                    self.sig_progress.emit(prog)
                    self.sig_point_done.emit(pt)

            # ----------------------------------------------------
            # MODE 2: Polarization mode, Model Tracking (Option C)
            # ----------------------------------------------------
            elif scan_mode.lower().startswith("polar") and "Model" in polar_algo:
                fixed_s3 = s3_seq[0] if (stage3_cfg["enabled"] and len(s3_seq) > 0) else None
                if self.stage3_inst and fixed_s3 is not None:
                    self.stage3_inst.move_to(fixed_s3)
                s3_pos = fixed_s3 if stage3_cfg["enabled"] else np.nan
                recorded_data = self.run_model_tracking(s1_seq, s2_seq, s3_pos, target_power, target_tol)

            # ----------------------------------------------------
            # MODE 2: Polarization mode, Sequential Step (A) / Binary Search (B)
            # ----------------------------------------------------
            elif scan_mode.lower().startswith("polar"):
                fixed_s3 = s3_seq[0] if (stage3_cfg["enabled"] and len(s3_seq) > 0) else None
                if self.stage3_inst and fixed_s3 is not None:
                    self.stage3_inst.move_to(fixed_s3)

                total_points = len(s2_seq)

                for idx2, angle2 in enumerate(s2_seq):
                    if self._is_stopped:
                        break

                    if self.stage2_inst and angle2 is not None:
                        self.sig_log.emit(f"Stage 2 -> {angle2}° | Searching Stage 1 for target {target_power} {unit}...")
                        self.stage2_inst.move_to(angle2)

                    matched = False
                    matched_s1_pos = np.nan
                    final_power_mw = 0.0

                    # Option A: Sequential Step Search
                    if "Sequential" in polar_algo or "A" in polar_algo:
                        for angle1 in s1_seq:
                            if self._is_stopped:
                                break

                            if self.stage1_inst and angle1 is not None:
                                self.stage1_inst.move_to(angle1)

                            power_mw, stable = self.measure(f"Stage 2 = {angle2}°, Stage 1 = {angle1}°")

                            if abs(power_mw - target_power) <= target_tol and stable:
                                matched = True
                                matched_s1_pos = angle1
                                final_power_mw = power_mw
                                self.sig_log.emit(f"Matched Target Power! Stage 1: {angle1}°, Power: {power_mw:.4f} {unit}")
                                break

                    # Option B: Binary Search
                    else:
                        if stage1_cfg["enabled"] and len(s1_seq) >= 2:
                            low_ang = stage1_cfg["start"]
                            high_ang = round(stage1_cfg["start"] + (stage1_cfg["no"] - 1) * stage1_cfg["step"], 2)
                            max_biter = 10

                            for _ in range(max_biter):
                                if self._is_stopped:
                                    break

                                mid_ang = round((low_ang + high_ang) / 2.0, 2)
                                if self.stage1_inst:
                                    self.stage1_inst.move_to(mid_ang)

                                power_mw, stable = self.measure(f"Stage 2 = {angle2}°, Stage 1 = {mid_ang}°")

                                if abs(power_mw - target_power) <= target_tol and stable:
                                    matched = True
                                    matched_s1_pos = mid_ang
                                    final_power_mw = power_mw
                                    self.sig_log.emit(f"Binary Search Matched! Stage 1: {mid_ang}°, Power: {power_mw:.4f} {unit}")
                                    break
                                elif power_mw < target_power:
                                    low_ang = mid_ang
                                else:
                                    high_ang = mid_ang

                    if not matched:
                        final_power_mw = power_mw if 'power_mw' in locals() else 0.0
                        self.scan_event(f"Warning: Target power not matched within tolerance for Stage 2 = {angle2}°")

                    s1_pos = matched_s1_pos if stage1_cfg["enabled"] else np.nan
                    s2_pos = angle2 if stage2_cfg["enabled"] else np.nan
                    s3_pos = fixed_s3 if stage3_cfg["enabled"] else np.nan

                    pt = {
                        "point_idx": point_count,
                        "stage1": s1_pos,
                        "stage2": s2_pos,
                        "stage3": s3_pos,
                        "power_mw": final_power_mw,
                        "target_power_mw": target_power,
                        "stable": matched
                    }
                    recorded_data.append(pt)

                    point_count += 1
                    prog = int((point_count / total_points) * 100)
                    self.sig_progress.emit(prog)
                    self.sig_point_done.emit(pt)

            if self._is_stopped:
                self.sig_finished.emit("stopped", "Calibration scan stopped by user.")
            else:
                self.sig_finished.emit("finished", f"Calibration complete. Total points: {len(recorded_data)}")

        except CalibrationAbort as exc:
            self.sig_finished.emit("aborted", f"✗ {exc}")
        except Exception as exc:
            err_msg = f"Calibration Worker Error: {exc}\n{traceback.format_exc()}"
            self.sig_finished.emit("error", err_msg)

    def run_model_tracking(self, s1_seq, s2_seq, s3_pos, target_power, target_tol) -> list:
        """Polarization mode, Model Tracking (Option C): for every Stage 2 angle find the Stage 1 angle that gives
        target_power. The steps are listed in the Polarization tooltip (POLAR_MODEL_TRACKING_TIP)."""
        unit = self.config["signal_unit"]
        recorded = []

        # 1) coarse scan of Stage 1 at the first Stage 2 angle, fit P = A*cos^2(2*(theta1 - theta0)) + B
        self.sig_log.emit(f"Stage 2 -> {s2_seq[0]}° | Coarse scan of Stage 1: {s1_seq[0]}° .. {s1_seq[-1]}°, {len(s1_seq)} points")
        self.stage2_inst.move_to(s2_seq[0])
        coarse_power = []
        for angle1 in s1_seq:
            self.stage1_inst.move_to(angle1)
            power_mw, _ = self.measure(f"coarse scan, Stage 1 = {angle1}°")
            if self._is_stopped:
                return recorded
            coarse_power.append(power_mw)
            self.sig_log.emit(f"Coarse scan: Stage 1 = {angle1}° -> {power_mw:.4f} {unit}")
        amp, offset, theta0, rms = fit_hwp_model(s1_seq, coarse_power)
        self.sig_model.emit({"coarse_stage1_deg": list(s1_seq), "coarse_reading": coarse_power,
                             "A": amp, "B": offset, "theta0_deg": theta0, "rms": rms})
        self.scan_event(f"Model: P = {amp:.4f} {unit} · cos²(2(θ1 − {theta0:.2f}°)) + {offset:.4f} {unit}, fit RMS {rms:.4f} {unit}")

        # 2) the target must be reachable with margin: near the maximum the curve is flat and may not reach it at every Stage 2 angle
        low, high = offset + MT_TARGET_RANGE[0] * amp, offset + MT_TARGET_RANGE[1] * amp
        if not low <= target_power <= high:
            raise CalibrationAbort(f"Target {target_power} {unit} is outside {low:.4f} .. {high:.4f} {unit} "
                                   f"(B + 5 % .. 90 % of A from the coarse scan). Scan stopped; choose a target in this range.")

        # 3) start on the falling slope (power decreasing as theta1 increases), at the solution nearest the middle of the coarse range
        x_target = hwp_phase_deg(target_power, amp, offset)
        first = theta0 + x_target / 2.0
        first += 90.0 * round(((s1_seq[0] + s1_seq[-1]) / 2.0 - first) / 90.0)
        self.scan_event(f"Target {target_power} {unit}: tracking the falling slope, starting at Stage 1 = {first:.2f}°")

        # 4) every Stage 2 angle: predict Stage 1, measure, correct with the model until within target_tol
        solved = []  # (stage2, stage1) of each finished angle
        for angle2 in s2_seq:
            if self._is_stopped:
                break
            if not solved:
                angle1 = first
            elif len(solved) == 1 or solved[-1][0] == solved[-2][0]:
                angle1 = solved[-1][1]
            else:  # straight line through the last two solutions; learns the sign and size of d(theta1)/d(theta2)
                (a2, a1), (b2, b1) = solved[-1], solved[-2]
                angle1 = a1 + (a1 - b1) * (angle2 - a2) / (a2 - b2)
            self.stage2_inst.move_to(angle2)

            matched, result, n_meas = False, None, 0
            for n_meas in range(1, MT_MAX_CORRECTIONS + 2):
                angle1 = round(angle1, 2)
                self.stage1_inst.move_to(angle1)
                power_mw, stable = self.measure(f"Stage 2 = {angle2}°, Stage 1 = {angle1:.2f}°")
                if self._is_stopped:
                    break
                self.sig_log.emit(f"Stage 2 = {angle2}°: Stage 1 = {angle1:.2f}° -> {power_mw:.4f} {unit} "
                                  f"(target {target_power} ± {target_tol} {unit}, measurement {n_meas})")
                if result is None or abs(power_mw - target_power) < abs(result[1] - target_power):
                    result = (angle1, power_mw)
                if abs(power_mw - target_power) <= target_tol and stable:
                    matched, result = True, (angle1, power_mw)
                    break
                step = (x_target - hwp_phase_deg(power_mw, amp, offset)) / 2.0
                angle1 += max(-MT_MAX_STEP_DEG, min(MT_MAX_STEP_DEG, step))
            if self._is_stopped:
                break  # an unfinished angle is not recorded

            if matched:
                self.sig_log.emit(f"Matched: Stage 2 = {angle2}°, Stage 1 = {result[0]:.2f}°, P = {result[1]:.4f} {unit}")
            else:
                self.scan_event(f"Warning: Stage 2 = {angle2}°: target not reached in {n_meas} measurements; "
                                  f"closest {result[1]:.4f} {unit} at Stage 1 = {result[0]:.2f}° recorded as not matched")
            solved.append((angle2, result[0]))
            pt = {
                "point_idx": len(recorded),
                "stage1": result[0],
                "stage2": angle2,
                "stage3": s3_pos,
                "power_mw": result[1],
                "target_power_mw": target_power,
                "stable": matched,
                "measurements": n_meas,
            }
            recorded.append(pt)
            self.sig_progress.emit(int(len(recorded) / len(s2_seq) * 100))
            self.sig_point_done.emit(pt)
        return recorded


class PolarizationCaliApp(QMainWindow):
    """Main window class for Polarization & Power Calibration System v1.2."""

    def __init__(self):
        super().__init__()

        # Load UI
        uiLoader = QUiLoader()
        uiLoader.registerCustomWidget(pg.PlotWidget)
        uiLoader.registerCustomWidget(LedIndicator)
        ui_path = Path(__file__).parent / "Polarization_cali_v1.2.ui"
        self.ui = uiLoader.load(str(ui_path))
        self.ui.installEventFilter(self)  # window close (Exit, title-bar X, Alt+F4) asks first: see eventFilter
        
        # Add a global stylesheet for button press/hover feedback
        self.ui.setStyleSheet("""
            QPushButton {
                padding: 5px;
                border: 1px solid #a0a0a0;
                border-radius: 3px;
                background-color: #f0f0f0;
            }
            QPushButton:hover {
                background-color: #e5f1fb;
                border: 1px solid #0078d7;
            }
            QPushButton:pressed {
                background-color: #cce4f7;
                border: 1px solid #005499;
            }
        """)

        # Instrument objects
        self.pm_inst = None       # detector option PM100D
        self.lockin_inst = None   # detector option Lock-in (SR830)
        self.stage1_inst = None
        self.stage2_inst = None
        self.stage3_inst = None

        # Data buffers for live plotting
        self.recorded_points = []
        self.x_data = []
        self.y_data = []
        self.coarse_model = None  # Model Tracking: coarse scan + fitted model of the last scan

        # Thread reference
        self.worker = None

        # Setup UI features
        self.setup_ui_events()
        self.setup_chart()
        self.setup_tooltips()
        self.on_detector_changed()  # settings, units and labels of the selected detector

        self.ui.show()
        self.log("Polarization & Power Calibration System v1.2 initialized.")
        self.log("Ready. Select hardware options and click 'Conn. Inst.' to start.")

    def setup_tooltips(self):
        """Set hover tooltips for scan modes as required by prompt."""
        mode_tooltips = {
            "Power": "Power mode: Stage 2 and Stage 3 stay at their Start angle, scan Stage 1. Wait for optical power stability at each Stage 1 angle, then record Stage 1/2/3 positions and power. A Stage 2/3 that is not enabled or not connected is recorded as NaN.",
            "Polarization": ("<b>Polarization mode</b>: for every Stage 2 (polarizer) angle, find the Stage 1 angle that gives "
                             "the target reading and record both. Needs Stage 1, Stage 2 and the Detector (PM100D or lock-in) "
                             "enabled and connected. "
                             "The search is chosen in Polar Search Algo.<br><br>" + POLAR_MODEL_TRACKING_TIP)
        }
        self.ui.combo_scan_mode.setItemData(0, mode_tooltips["Power"], Qt.ToolTipRole)
        self.ui.combo_scan_mode.setItemData(1, mode_tooltips["Polarization"], Qt.ToolTipRole)
        self.ui.combo_scan_mode.setToolTip(mode_tooltips["Power"])
        self.ui.combo_scan_mode.currentIndexChanged.connect(self.on_mode_changed)

        algo_tooltips = [
            POLAR_MODEL_TRACKING_TIP,
            "<b>Sequential Step (Option A)</b>: for each Stage 2 angle, step Stage 1 from Start through its range and stop at the "
            "first angle within Target Tol. The result can only be one of the Stage 1 steps.",
            "<b>Binary Search (Option B)</b>: halve the Stage 1 range (at most 10 measurements). Works only if the power rises "
            "with the Stage 1 angle over the whole range (at most 45° wide).",
        ]
        for i, tip in enumerate(algo_tooltips):
            self.ui.combo_polar_search.setItemData(i, tip, Qt.ToolTipRole)
        self.ui.combo_polar_search.setToolTip(algo_tooltips[0])
        self.ui.combo_polar_search.currentIndexChanged.connect(
            lambda i: self.ui.combo_polar_search.setToolTip(self.ui.combo_polar_search.itemData(i, Qt.ToolTipRole)))

    def on_mode_changed(self, index: int):
        mode = self.ui.combo_scan_mode.currentText()
        tt = self.ui.combo_scan_mode.itemData(index, Qt.ToolTipRole)
        if tt:
            self.ui.combo_scan_mode.setToolTip(tt)
        self.log(f"Scan mode selected: {mode}")

    def setup_chart(self):
        """Configure pyqtgraph chart axis and curves."""
        chart = self.ui.powerChart
        chart.setBackground("w")
        plot_item = chart.getPlotItem()
        plot_item.setLabel("left", "Measured Power (mW)", color="black")
        plot_item.setLabel("bottom", "Point Index / Angle", color="black")
        plot_item.showGrid(x=True, y=True, alpha=0.3)
        self.curve = plot_item.plot(pen=pg.mkPen(color="b", width=2), symbol="o", symbolSize=6, symbolBrush="b")

    def setup_ui_events(self):
        """Connect UI signals to handler slots."""
        self.ui.btn_connect_all.clicked.connect(self.connect_all_devices)
        self.ui.btn_disconnect_all.clicked.connect(self.disconnect_selected_devices)
        self.ui.btn_exit.clicked.connect(self.exit_app)
        self.ui.btn_scan_devices.clicked.connect(self.scan_devices)

        self.ui.btn_home_stage1.clicked.connect(lambda: self.home_stage(1))
        self.ui.btn_home_stage2.clicked.connect(lambda: self.home_stage(2))
        self.ui.btn_home_stage3.clicked.connect(lambda: self.home_stage(3))

        # Manual movement controls
        self.ui.btn_stage1_goto.clicked.connect(lambda: self.manual_goto(1))
        self.ui.btn_stage2_goto.clicked.connect(lambda: self.manual_goto(2))
        self.ui.btn_stage3_goto.clicked.connect(lambda: self.manual_goto(3))

        self.ui.btn_stage1_step_plus.clicked.connect(lambda: self.manual_step(1, 1))
        self.ui.btn_stage1_step_minus.clicked.connect(lambda: self.manual_step(1, -1))
        self.ui.btn_stage2_step_plus.clicked.connect(lambda: self.manual_step(2, 1))
        self.ui.btn_stage2_step_minus.clicked.connect(lambda: self.manual_step(2, -1))
        self.ui.btn_stage3_step_plus.clicked.connect(lambda: self.manual_step(3, 1))
        self.ui.btn_stage3_step_minus.clicked.connect(lambda: self.manual_step(3, -1))

        self.ui.btn_start_scan.clicked.connect(self.start_calibration)
        self.ui.btn_stop_scan.clicked.connect(self.stop_calibration)
        self.ui.btn_browse_dir.clicked.connect(self.browse_save_dir)

        # Save path: cali_data/<Month>/<Month>_<dd> of today (as OPTP), until Browse picks a folder; populate default serials
        self.is_custom_save_path = False
        self.setup_data_folder()
        self.init_device_defaults()

        # Setup continuous monitoring timer for idle state
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self.update_monitor)
        self.monitor_timer.start(self.ui.spin_pm_refresh.value())  # update every Refresh (ms)

        # Detector row (tab 1): PM100D or lock-in; refresh sets the monitor interval
        self.ui.combo_detector.currentIndexChanged.connect(self.on_detector_changed)
        self.ui.chk_detector_enable.toggled.connect(self.on_detector_changed)  # unchecked: readout back to "--"
        self.ui.spin_pm_refresh.editingFinished.connect(lambda: self.monitor_timer.setInterval(self.ui.spin_pm_refresh.value()))
        # PM100D settings: wavelength and range are sent to the meter
        self.ui.spin_pm_wavelength.editingFinished.connect(self.set_pm_wavelength)
        self.ui.combo_pm_range.currentIndexChanged.connect(self.set_pm_range)
        # Lock-in settings (labels and defaults as OPTP): read back on connect, applied at once when changed
        self.ui.combo_lockin_sens.addItems(SR830.get_sensitivity_labels())
        self.ui.combo_lockin_sens.setCurrentIndex(23)  # 100 mV
        self.ui.combo_lockin_tc.addItems(SR830.get_time_constant_labels())
        self.ui.combo_lockin_tc.setCurrentIndex(8)  # 100 ms
        self.ui.combo_lockin_sens.currentIndexChanged.connect(lambda: self.apply_lockin_setting("sens"))
        self.ui.combo_lockin_tc.currentIndexChanged.connect(lambda: self.apply_lockin_setting("tc"))

        # Dynamically add a big readout label to the detector row
        self.lbl_current_power = QLabel("Power: -- mW")
        self.lbl_current_power.setStyleSheet("font-size: 16px; font-weight: bold; color: #d32f2f;")
        if hasattr(self.ui, 'layout_detector'):
            self.ui.layout_detector.addWidget(self.lbl_current_power)
            self.ui.layout_detector.addSpacing(40)  # keep the readout a little away from the right edge

    @Slot()
    def update_monitor(self):
        """Continuously update power and positions when idle."""
        if getattr(self, 'worker', None) is not None and self.worker.isRunning():
            return
            
        status_parts = []
        reader = self.active_reader()
        if reader is not None:
            try:
                p = reader.read()
                power_text = f"{reader.quantity}: {p:.4f} {reader.unit}"
                status_parts.append(power_text)
                if isinstance(reader, LockinReader):  # helps choosing the sensitivity
                    power_text += f" ({p / reader.full_scale * 100:.0f} % FS)"
                if hasattr(self, 'lbl_current_power'):
                    self.lbl_current_power.setText(power_text)
            except Exception:
                pass
                
        for idx, stage in enumerate([getattr(self, 'stage1_inst', None), 
                                     getattr(self, 'stage2_inst', None), 
                                     getattr(self, 'stage3_inst', None)], 1):
            if stage is not None:
                try:
                    pos = stage.position()
                    getattr(self.ui, f"lbl_stage{idx}_pos").setText(f"Pos: {pos:.2f} °")
                    status_parts.append(f"Stg{idx}: {pos:.2f}°")
                except Exception:
                    pass
                    
        if status_parts:
            self.statusBar().showMessage(" | ".join(status_parts))

    def init_device_defaults(self):
        """Populate default VISA resource and stage serials matching OPTP v1.7."""
        if self.ui.combo_pm100d_res.count() == 0:
            self.ui.combo_pm100d_res.addItem("USB0::0x1313::0x8078::P0020951::INSTR")
        if self.ui.combo_lockin_res.count() == 0:
            self.ui.combo_lockin_res.addItem("GPIB0::2::INSTR")  # OPTP's Lock-in 1 default

        optp_serials = {
            1: "27004364",
            2: "27255894",
            3: "27255894",
        }
        combo_map = {
            1: self.ui.combo_stage1_serial,
            2: self.ui.combo_stage2_serial,
            3: self.ui.combo_stage3_serial,
        }
        for s_idx, combo in combo_map.items():
            if combo.count() == 0:
                combo.addItem(optp_serials[s_idx])

    @Slot()
    def scan_devices(self):
        """Offer the PM100D / lock-in resources and Kinesis serials visible to this PC in the drop-down lists, keeping the entered values."""
        scans = (
            ("PM100D (USB)", PM100D.list_resources, [self.ui.combo_pm100d_res]),
            ("Lock-in (GPIB / serial)", list_lockin_resources, [self.ui.combo_lockin_res]),
            ("Kinesis", InstrumentTools.list_kinesis_serials,
             [self.ui.combo_stage1_serial, self.ui.combo_stage2_serial, self.ui.combo_stage3_serial]),
        )
        for label, scan, combos in scans:
            try:
                found = list(scan())
            except Exception as exc:
                self.log(f"✗ {label} device scan failed: {exc}")
                continue
            self.log(f"{label} devices found: {found if found else 'none'}")
            for combo in combos:
                current = combo.currentText()
                combo.clear()
                combo.addItems(found)
                combo.setCurrentText(current)  # the scan only offers choices, it never changes the setting

    def load_pm_settings(self, pm):
        """PM100D settings on connect: the wavelength box (default 800 nm, limited to the sensor) is sent to the
        meter; the power range box offers the sensor's ranges and shows the meter's current range setting."""
        wl_min = float(pm.query("SENS:CORR:WAV? MIN"))
        wl_max = float(pm.query("SENS:CORR:WAV? MAX"))
        self.ui.spin_pm_wavelength.setRange(round(wl_min), round(wl_max))  # clamps the box value into the sensor's limits
        pm.set_wavelength_nm(self.ui.spin_pm_wavelength.value())
        self.ui.spin_pm_wavelength.setValue(round(pm.get_wavelength_nm()))  # what the meter accepted
        self.show_pm_ranges(pm)

    def probe_pm_ranges(self, pm) -> list:
        """The meter's real power ranges (W), lowest first, walked on the meter and its range setting restored.

        They depend on the sensor and the wavelength and are not exact decades (S302C at 800 nm: 3.695 mW,
        34.99 mW, 347.9 mW, 3.477 W), so they cannot be derived from the lowest one: from the lowest range,
        ask for just above the current range until the meter stops moving up.
        """
        auto = pm.get_power_auto_range()
        current = pm.get_power_range_upper()
        ranges = []
        try:
            pm.set_power_auto_range(False)
            pm.write("SENS:POW:RANG:UPP MIN")
            upper = pm.get_power_range_upper()
            for _ in range(12):
                ranges.append(upper)
                pm.set_power_range_upper(upper * 1.01)  # above the top range the meter refuses and keeps it
                following = pm.get_power_range_upper()
                if following <= upper * 1.0001:
                    break
                upper = following
        finally:
            if auto:
                pm.set_power_auto_range(True)
            else:
                pm.set_power_range_upper(current * 0.999)  # see set_pm_range: the read-back value is rounded
            for _ in range(20):  # clear the 'Data out of range' left by the step above the top range
                if pm.get_error()[0] == 0:
                    break
        return ranges

    def show_pm_ranges(self, pm):
        """Offer the meter's real ranges at the current wavelength in the Power range box and show its setting."""
        try:
            ranges = self.probe_pm_ranges(pm)
        except Exception as exc:  # the meter stays usable on Auto; no reason to refuse the connection
            ranges = []
            self.log(f"Warning: could not read the PM100D ranges ({type(exc).__name__}: {exc}); only Auto is offered.")
        box = self.ui.combo_pm_range
        box.blockSignals(True)  # only showing the meter's state; nothing is sent back
        box.clear()
        box.addItem("Auto", None)
        for r in ranges:
            box.addItem(f"{r * 1e3:.4g} mW" if r < 1 else f"{r:.4g} W", r)
        if not ranges or pm.get_power_auto_range():
            box.setCurrentIndex(0)
        else:
            current = pm.get_power_range_upper()
            box.setCurrentIndex(1 + min(range(len(ranges)), key=lambda i: abs(ranges[i] - current)))
        box.blockSignals(False)

    @Slot(int)
    def set_pm_range(self, index: int):
        """Power range box: Auto, or one fixed range (the meter then stops switching ranges)."""
        if self.pm_inst is None or index < 0:
            return
        upper = self.ui.combo_pm_range.itemData(index)
        try:
            if upper is None:
                self.pm_inst.set_power_auto_range(True)
            else:
                self.pm_inst.set_power_auto_range(False)
                # The meter reports a range rounded to 7 digits, which can lie just above the range itself and
                # would select the next one up; 0.1 % below it is inside this range and far above the one below.
                self.pm_inst.set_power_range_upper(upper * 0.999)
            auto = self.pm_inst.get_power_auto_range()
            actual = self.pm_inst.get_power_range_upper()
        except Exception as exc:
            self.log(f"✗ Setting the PM100D range failed: {exc}")
            return
        self.log("PM100D range: Auto." if auto else f"PM100D range fixed at {actual * 1e3:.4g} mW.")

    @Slot()
    def set_pm_wavelength(self):
        """Send the wavelength box to the meter, show the value it accepted and the ranges at that wavelength."""
        if self.pm_inst is None:
            return
        try:
            self.pm_inst.set_wavelength_nm(self.ui.spin_pm_wavelength.value())
            accepted = self.pm_inst.get_wavelength_nm()
            self.show_pm_ranges(self.pm_inst)  # the ranges move with the wavelength
        except Exception as exc:
            self.log(f"✗ Setting the PM100D wavelength failed: {exc}")
            return
        self.ui.spin_pm_wavelength.setValue(round(accepted))
        self.log(f"PM100D wavelength set to {accepted:g} nm.")

    # ---------- detector: PM100D or lock-in ----------
    def selected_detector(self) -> str:
        """'PM100D' or 'Lock-in', as chosen in the detector row."""
        return self.ui.combo_detector.currentText()

    def active_reader(self):
        """Reader of the selected detector if Detector is checked and it is connected (PowerMeterReader / LockinReader),
        else None. Unchecked means not read, by the monitor or a scan, even while connected."""
        if not self.ui.chk_detector_enable.isChecked():
            return None
        if self.selected_detector() == "PM100D":
            return PowerMeterReader(self.pm_inst) if self.pm_inst is not None else None
        if self.lockin_inst is None:
            return None
        return LockinReader(self.lockin_inst, SR830._SENS_VALUES_V[self.ui.combo_lockin_sens.currentIndex()])

    def detector_units(self) -> tuple[str, str]:
        """(quantity, unit) of the selected detector: ('Power', 'mW') or ('Signal', 'mV')."""
        reader = PowerMeterReader if self.selected_detector() == "PM100D" else LockinReader
        return reader.quantity, reader.unit

    @Slot()
    def on_detector_changed(self, *_):
        """Show the selected detector's settings and use its unit for the readout, the chart, the target and the tolerances."""
        is_pm = self.selected_detector() == "PM100D"
        self.ui.widget_pm_settings.setVisible(is_pm)
        self.ui.widget_lockin_settings.setVisible(not is_pm)
        quantity, unit = self.detector_units()
        self.ui.lbl_target_power.setText(f"Target {quantity} ({unit}):")
        self.ui.lbl_stability_tol.setText(f"Stability Tol ({unit}):")
        self.ui.lbl_target_tol.setText(f"Target Tol ({unit}):")
        self.ui.powerChart.getPlotItem().setLabel("left", f"Measured {quantity} ({unit})", color="black")
        self.lbl_current_power.setText(f"{quantity}: -- {unit}")
        self.update_detector_led()

    def update_detector_led(self):
        """The detector LED shows whether the selected detector is connected (checked or not, like the stage LEDs)."""
        inst = self.pm_inst if self.selected_detector() == "PM100D" else self.lockin_inst
        self.ui.led_detector.status = inst is not None

    def set_detector_controls_enabled(self, enabled: bool):
        """During a scan the worker reads the detector: no detector switch and no setting sent to it from the GUI."""
        for name in ("combo_detector", "spin_pm_wavelength", "combo_pm_range", "combo_lockin_sens", "combo_lockin_tc"):
            getattr(self.ui, name).setEnabled(enabled)

    def refresh_lockin_settings(self, lockin: SR830):
        """Show the lock-in's sensitivity and time constant in the boxes, without sending anything back."""
        for box, getter in ((self.ui.combo_lockin_sens, lockin.get_sensitivity_index),
                            (self.ui.combo_lockin_tc, lockin.get_time_constant_index)):
            box.blockSignals(True)
            box.setCurrentIndex(getter())
            box.blockSignals(False)

    def apply_lockin_setting(self, which: str):
        """Sensitivity / time constant box changed: apply it to the lock-in at once."""
        if self.lockin_inst is None:
            return  # not connected: on connect the boxes take the lock-in's own settings
        box, name = ((self.ui.combo_lockin_sens, "sensitivity") if which == "sens" else (self.ui.combo_lockin_tc, "time constant"))
        try:
            if which == "sens":
                self.lockin_inst.set_sensitivity(box.currentIndex())
            else:
                self.lockin_inst.set_time_constant(box.currentIndex())
        except Exception as exc:
            self.log(f"✗ Setting the lock-in {name} failed: {exc}")
            return
        self.log(f"Lock-in {name} set to {box.currentText()}.")

    def log(self, message: str):
        """Append log message to log box and print."""
        timestamp = time.strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        self.ui.txt_log.append(log_line)
        print(log_line)

    @Slot()
    def connect_all_devices(self):
        """Connect all checked/enabled devices in sequence using OPTP v1.7 guarded enable & cleanup flow."""
        self.log("=== Connecting Enabled Devices ===")

        # 1. Connect the selected detector if Detector is checked: PM100D ...
        if self.ui.chk_detector_enable.isChecked() and self.selected_detector() == "PM100D":
            if self.pm_inst is not None:
                self.log("PM100D is already connected.")
            else:
                res = self.ui.combo_pm100d_res.currentText().strip()
                if res:
                    pm_temp = None
                    try:
                        pm_temp = PM100D(
                            res,
                            timeout_ms=10000,
                            query_delay_s=0.1,
                            retry_count=2,
                            retry_delay_s=0.2,
                        )
                        pm_temp.open()
                        idn = pm_temp.idn()
                        self.load_pm_settings(pm_temp)  # PM100D settings: wavelength box -> meter, meter's range -> box
                        self.pm_inst = pm_temp
                        self.log(f"✓ PM100D connected: {idn} ({self.ui.spin_pm_wavelength.value()} nm)")
                    except Exception as exc:
                        if pm_temp is not None:
                            try:
                                pm_temp.close()
                            except Exception:
                                pass
                        self.pm_inst = None
                        self.log(f"✗ Failed to connect PM100D: {exc}")

        # ... or the lock-in (SR830, connected as in OPTP; reference and settings are read, not changed)
        elif self.ui.chk_detector_enable.isChecked():
            if self.lockin_inst is not None:
                self.log("Lock-in is already connected.")
            else:
                res = self.ui.combo_lockin_res.currentText().strip()
                if res:
                    li_temp = None
                    try:
                        li_temp = SR830(res)
                        error_msg = li_temp.open()
                        if error_msg:
                            raise RuntimeError(error_msg)
                        idn = li_temp.idn()
                        self.refresh_lockin_settings(li_temp)  # sensitivity / time constant boxes show the lock-in's settings
                        ref_external = li_temp.get_ref_mode() == 0
                        ref_freq = li_temp.get_ref_freq()
                        self.lockin_inst = li_temp
                        self.log(f"✓ Lock-in connected: {idn} (reference {'external' if ref_external else 'INTERNAL'}, "
                                 f"{ref_freq:g} Hz; sensitivity {self.ui.combo_lockin_sens.currentText()}, "
                                 f"time constant {self.ui.combo_lockin_tc.currentText()})")
                        if not ref_external:
                            self.log("Warning: the lock-in reference is internal, so it is not locked to the laser. Connect the "
                                     "1 kHz laser trigger to REF IN and set the reference source to External on the lock-in.")
                    except Exception as exc:
                        if li_temp is not None:
                            try:
                                li_temp.close()
                            except Exception:
                                pass
                        self.lockin_inst = None
                        self.log(f"✗ Failed to connect lock-in: {exc}")
        self.update_detector_led()

        # 2. Connect Stage 1 if checked
        if self.ui.chk_stage1_enable.isChecked():
            if self.stage1_inst is not None:
                self.log("Stage 1 is already connected.")
            else:
                sn = self.ui.combo_stage1_serial.currentText().strip()
                if sn:
                    stg_temp = None
                    try:
                        stg_temp = RotaryStage(controller_serial=sn, poll_ms=250)
                        self.stage1_inst = stg_temp
                        self.ui.lbl_stage1_pos.setText(f"Pos: {stg_temp.position():.2f} °")
                        self.ui.led_stage1.status = True
                        self.log(f"✓ Stage 1 connected (Serial: {sn})")
                    except Exception as exc:
                        if stg_temp is not None:
                            try:
                                stg_temp.close()
                            except Exception:
                                pass
                        self.stage1_inst = None
                        self.ui.led_stage1.status = False
                        self.log(f"✗ Failed to connect Stage 1: {exc}")

        # 3. Connect Stage 2 if checked
        if self.ui.chk_stage2_enable.isChecked():
            if self.stage2_inst is not None:
                self.log("Stage 2 is already connected.")
            else:
                sn = self.ui.combo_stage2_serial.currentText().strip()
                if sn:
                    stg_temp = None
                    try:
                        stg_temp = RotaryStage(controller_serial=sn, poll_ms=250)
                        self.stage2_inst = stg_temp
                        self.ui.lbl_stage2_pos.setText(f"Pos: {stg_temp.position():.2f} °")
                        self.ui.led_stage2.status = True
                        self.log(f"✓ Stage 2 connected (Serial: {sn})")
                    except Exception as exc:
                        if stg_temp is not None:
                            try:
                                stg_temp.close()
                            except Exception:
                                pass
                        self.stage2_inst = None
                        self.ui.led_stage2.status = False
                        self.log(f"✗ Failed to connect Stage 2: {exc}")

        # 4. Connect Stage 3 if checked
        if self.ui.chk_stage3_enable.isChecked():
            if self.stage3_inst is not None:
                self.log("Stage 3 is already connected.")
            else:
                sn = self.ui.combo_stage3_serial.currentText().strip()
                if sn:
                    stg_temp = None
                    try:
                        stg_temp = RotaryStage(controller_serial=sn, poll_ms=250)
                        self.stage3_inst = stg_temp
                        self.ui.lbl_stage3_pos.setText(f"Pos: {stg_temp.position():.2f} °")
                        self.ui.led_stage3.status = True
                        self.log(f"✓ Stage 3 connected (Serial: {sn})")
                    except Exception as exc:
                        if stg_temp is not None:
                            try:
                                stg_temp.close()
                            except Exception:
                                pass
                        self.stage3_inst = None
                        self.ui.led_stage3.status = False
                        self.log(f"✗ Failed to connect Stage 3: {exc}")

        QApplication.processEvents()

    @Slot()
    def disconnect_selected_devices(self):
        """Close sessions only for instruments whose enable checkboxes are checked."""
        self.log("=== Disconnecting Selected Devices ===")
        # Check Detector: close both detector options that are connected
        if self.ui.chk_detector_enable.isChecked():
            for attr, name in (("pm_inst", "PM100D"), ("lockin_inst", "lock-in")):
                inst = getattr(self, attr)
                if inst:
                    try:
                        inst.close()
                    except Exception:
                        pass
                    setattr(self, attr, None)
                    self.log(f"Disconnected {name}")
            self.update_detector_led()

        # Check Stage 1
        if self.ui.chk_stage1_enable.isChecked() and self.stage1_inst:
            try:
                self.stage1_inst.close()
            except Exception:
                pass
            self.stage1_inst = None
            self.ui.led_stage1.status = False
            self.log("Disconnected Stage 1")

        # Check Stage 2
        if self.ui.chk_stage2_enable.isChecked() and self.stage2_inst:
            try:
                self.stage2_inst.close()
            except Exception:
                pass
            self.stage2_inst = None
            self.ui.led_stage2.status = False
            self.log("Disconnected Stage 2")

        # Check Stage 3
        if self.ui.chk_stage3_enable.isChecked() and self.stage3_inst:
            try:
                self.stage3_inst.close()
            except Exception:
                pass
            self.stage3_inst = None
            self.ui.led_stage3.status = False
            self.log("Disconnected Stage 3")

        QApplication.processEvents()

    def disconnect_all_devices(self):
        """Close sessions for all connected instruments unconditionally (used on application exit)."""
        if self.pm_inst:
            try:
                self.pm_inst.close()
            except Exception:
                pass
            self.pm_inst = None

        if self.lockin_inst:
            try:
                self.lockin_inst.close()
            except Exception:
                pass
            self.lockin_inst = None

        for stg_attr in [self.stage1_inst, self.stage2_inst, self.stage3_inst]:
            if stg_attr:
                try:
                    stg_attr.close()
                except Exception:
                    pass

        self.stage1_inst = None
        self.stage2_inst = None
        self.stage3_inst = None

    @Slot()
    def exit_app(self):
        """Trigger window close on self.ui, which goes through eventFilter: confirmation and cleanup."""
        self.ui.close()

    def eventFilter(self, obj, event):
        """Ask before the window closes (Exit button, title-bar X, Alt+F4), as OPTP.

        The window is created by QUiLoader, so a Python closeEvent assigned to it is never called;
        the close is caught here instead. A close event starts out accepted, so keeping the window open
        needs event.ignore() as well as returning True.
        """
        if obj is self.ui and event.type() == QEvent.Close:
            if self.confirm_exit():
                return False  # let the window close
            event.ignore()
            return True
        return False  # not super().eventFilter(): at interpreter shutdown this object may already be deleted

    def confirm_exit(self) -> bool:
        """Confirm exit; then stop a running scan (its data is saved) and close all instruments. True = exit."""
        scanning = self.worker is not None and self.worker.isRunning()
        text = "Exit the program and close all instruments?"
        if scanning:
            text = "A scan is running. It will be stopped and the data measured so far saved.\n\n" + text
        reply = QMessageBox.question(self.ui, "Confirm Exit", text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            if scanning:
                self.stop_calibration()
                self.worker.wait()  # the worker sees the stop within 0.1 s, or after the current stage move
                QApplication.processEvents()  # deliver its last signals, so the stopped scan is saved

            has_connected_devices = any([
                self.pm_inst is not None,
                self.lockin_inst is not None,
                self.stage1_inst is not None,
                self.stage2_inst is not None,
                self.stage3_inst is not None
            ])

            if has_connected_devices:
                self.log("Disconnecting active hardware devices before exit...")
                self.disconnect_all_devices()

            QApplication.quit()
            return True
        self.log("Exit cancelled.")
        return False

    def home_stage(self, stage_idx: int):
        stage_map = {1: self.stage1_inst, 2: self.stage2_inst, 3: self.stage3_inst}
        stage_obj = stage_map[stage_idx]

        if not stage_obj:
            QMessageBox.warning(self, "Warning", f"Stage {stage_idx} is not connected.")
            return

        try:
            self.log(f"Homing Stage {stage_idx}...")
            stage_obj.home()
            self.log(f"Stage {stage_idx} homed successfully.")
        except Exception as exc:
            self.log(f"Homing error on Stage {stage_idx}: {exc}")

    def manual_goto(self, stage_idx: int):
        stage_map = {1: self.stage1_inst, 2: self.stage2_inst, 3: self.stage3_inst}
        spin_map = {1: self.ui.spin_stage1_goto, 2: self.ui.spin_stage2_goto, 3: self.ui.spin_stage3_goto}
        lbl_map = {1: self.ui.lbl_stage1_pos, 2: self.ui.lbl_stage2_pos, 3: self.ui.lbl_stage3_pos}

        stage_obj = stage_map[stage_idx]
        if not stage_obj:
            QMessageBox.warning(self, "Warning", f"Stage {stage_idx} is not connected.")
            return

        target_angle = spin_map[stage_idx].value()
        try:
            self.log(f"Moving Stage {stage_idx} to {target_angle:.2f}°...")
            stage_obj.move_to(target_angle)
            pos = stage_obj.position()
            lbl_map[stage_idx].setText(f"Pos: {pos:.2f} °")
            self.log(f"Stage {stage_idx} arrived at {pos:.2f}°")
        except Exception as exc:
            self.log(f"Move error on Stage {stage_idx}: {exc}")

    def manual_step(self, stage_idx: int, direction: int):
        stage_map = {1: self.stage1_inst, 2: self.stage2_inst, 3: self.stage3_inst}
        spin_map = {1: self.ui.spin_stage1_rel, 2: self.ui.spin_stage2_rel, 3: self.ui.spin_stage3_rel}
        lbl_map = {1: self.ui.lbl_stage1_pos, 2: self.ui.lbl_stage2_pos, 3: self.ui.lbl_stage3_pos}

        stage_obj = stage_map[stage_idx]
        if not stage_obj:
            QMessageBox.warning(self, "Warning", f"Stage {stage_idx} is not connected.")
            return

        rel_val = spin_map[stage_idx].value() * direction
        try:
            curr = stage_obj.position()
            target = curr + rel_val
            self.log(f"Stepping Stage {stage_idx} by {rel_val:+.2f}° (to {target:.2f}°)...")
            stage_obj.move_to(target)
            pos = stage_obj.position()
            lbl_map[stage_idx].setText(f"Pos: {pos:.2f} °")
        except Exception as exc:
            self.log(f"Relative move error on Stage {stage_idx}: {exc}")

    def setup_data_folder(self) -> str:
        """Create cali_data/<Month>/<Month>_<dd> for today (same layout as OPTP_Data) and show it as the save directory."""
        month_name = time.strftime("%B")  # full month name
        day_dir = Path(__file__).parent / "cali_data" / month_name / f"{month_name}_{time.strftime('%d')}"
        day_dir.mkdir(parents=True, exist_ok=True)
        self.ui.line_save_dir.setText(str(day_dir))
        return str(day_dir)

    @Slot()
    def browse_save_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if folder:
            self.ui.line_save_dir.setText(folder)
            self.is_custom_save_path = True  # from now on scans save here instead of the dated folder

    # ---------- ScanLog (tab 2): test conditions and key events, also appended to ScanLog_YYYY-MM-DD.txt (as OPTP) ----------
    def start_scan_log(self, reader):
        """Open a new block in the day's scan log and write the scan's test conditions (GUI thread only).

        Only stages that are enabled and connected are listed. Point-by-point readings are not logged.
        """
        ui = self.ui
        self._scan_log_start = time.time()
        self._scan_log_ended = False
        save_dir = Path(ui.line_save_dir.text().strip())
        self._scan_log_path = save_dir / f"ScanLog_{time.strftime('%Y-%m-%d')}.txt"
        mode = ui.combo_scan_mode.currentText()
        polar = mode.lower().startswith("polar")
        model_tracking = polar and "Model" in ui.combo_polar_search.currentText()
        unit = self.detector_units()[1]

        lines = ["", "=" * 72, f"Scan started {time.strftime('%Y-%m-%d %H:%M:%S')}", "-" * 72,
                 f"Mode        : {mode}" + (f", {ui.combo_polar_search.currentText()}" if polar else ""),
                 f"Save folder : {save_dir}"]
        if isinstance(reader, PowerMeterReader):
            lines.append(f"Detector    : PM100D, {ui.spin_pm_wavelength.value()} nm, range {ui.combo_pm_range.currentText()}")
        elif isinstance(reader, LockinReader):
            lines.append(f"Detector    : Lock-in R ({ui.combo_lockin_res.currentText()}), sensitivity "
                         f"{ui.combo_lockin_sens.currentText()}, time constant {ui.combo_lockin_tc.currentText()}")
        else:
            lines.append("Detector    : none (readings recorded as 0)")
        if polar:
            lines.append(f"Target      : {ui.spin_target_power.value():g} {unit}, Target Tol {ui.spin_target_tol.value():g} {unit}")
        lines.append(f"Stability   : Tol {ui.spin_stability_tol.value():g} {unit} or {ui.spin_stability_tol_pct.value():g} % "
                     f"of the reading, whichever is larger (max - min), Stable Window "
                     f"{ui.spin_stable_window.value():g} s, a reading every {ui.spin_pm_refresh.value()} ms (Refresh), "
                     f"at most {STABILITY_TIMEOUT_S:g} s per measurement")
        for n in (1, 2, 3):
            if not (getattr(ui, f"chk_stage{n}_enable").isChecked() and getattr(self, f"stage{n}_inst") is not None):
                continue
            start = getattr(ui, f"spin_stage{n}_start").value()
            if n == 3 or (n == 2 and not polar):  # Stage 3 always, Stage 2 in Power mode: fixed at Start
                lines.append(f"Stage {n}     : fixed at {start:g} deg")
            else:
                lines.append(f"Stage {n}     : start {start:g} deg, step {getattr(ui, f'spin_stage{n}_step').value():g} deg "
                             f"x {getattr(ui, f'spin_stage{n}_no').value()}" + (" (coarse scan)" if n == 1 and model_tracking else ""))
        lines.append("-" * 72)
        self.append_scan_log("\n".join(lines))

    @Slot(str)
    def scan_log_event(self, message: str):
        """Log one timestamped key event (the scan thread sends them through sig_scan_log)."""
        self.append_scan_log(f"[{time.strftime('%H:%M:%S')}] {message}")

    def append_scan_log(self, text: str):
        """Show text in the ScanLog box and append it to the day's log file (GUI thread only)."""
        self.ui.txt_scan_log.appendPlainText(text)
        path = getattr(self, "_scan_log_path", None)
        if not path:
            return
        try:
            with open(path, "a", encoding="utf-8") as f:  # opened per write, so every line is on disk at once
                f.write(text + "\n")
        except OSError as exc:
            self.log(f"Warning: could not write scan log {path}: {exc}")

    def end_scan_log(self, result: str):
        """Close the current scan block with how it ended and how long it took. Only the first call counts."""
        if getattr(self, "_scan_log_ended", True):
            return
        self._scan_log_ended = True
        elapsed = int(time.time() - self._scan_log_start)
        hours, rest = divmod(elapsed, 3600)
        self.scan_log_event(f"{result} (duration {hours}:{rest // 60:02d}:{rest % 60:02d})")

    def scan_start_problem(self) -> str | None:
        """Why the selected scan cannot start, or None if it can.

        Power mode scans Stage 1. Polarization mode moves Stage 2 and searches Stage 1 with the PM100D;
        Model Tracking also needs a coarse scan over a full 90° period of Stage 1 to fit its model.
        """
        mode = self.ui.combo_scan_mode.currentText()
        required = [("Stage 1", self.ui.chk_stage1_enable, self.stage1_inst)]
        if mode.lower().startswith("polar"):
            required += [("Stage 2", self.ui.chk_stage2_enable, self.stage2_inst),
                         (f"the Detector ({self.selected_detector()})", self.ui.chk_detector_enable, self.active_reader())]
        for name, chk, inst in required:
            if not chk.isChecked():
                return f"{mode} mode needs {name}, but {name} is not enabled. Check '{chk.text()}' and connect it first. Scan not started."
            if inst is None:
                return f"{mode} mode needs {name}, but {name} is not connected. Click 'Conn. Inst.' first. Scan not started."

        if mode.lower().startswith("polar") and "Model" in self.ui.combo_polar_search.currentText():
            no = self.ui.spin_stage1_no.value()
            span = abs(self.ui.spin_stage1_step.value()) * (no - 1)
            if no < MT_MIN_COARSE_POINTS or span < 90.0:
                return (f"Model Tracking fits its model to a Stage 1 coarse scan, which must cover a full 90° period with at least "
                        f"{MT_MIN_COARSE_POINTS} points (|Step| × (Step NO. − 1) ≥ 90°); now {span:g}° with {no} points. Scan not started.")
        return None

    @Slot()
    def start_calibration(self):
        """Build configuration and start worker thread."""
        msg = self.scan_start_problem()
        if msg:
            self.log(f"✗ {msg}")
            QMessageBox.warning(self.ui, "Cannot Start Scan", msg)
            return

        # update the dated data folder (the date may have changed) unless Browse picked a folder
        if not self.is_custom_save_path:
            self.setup_data_folder()

        config = {
            "signal_unit": self.detector_units()[1],
            "scan_mode": self.ui.combo_scan_mode.currentText(),
            "polar_algo": self.ui.combo_polar_search.currentText(),
            "target_power": self.ui.spin_target_power.value(),
            "stability_tol": self.ui.spin_stability_tol.value(),
            "stability_tol_pct": self.ui.spin_stability_tol_pct.value(),  # % of the reading; the larger of the two counts
            "target_tol": self.ui.spin_target_tol.value(),
            "stable_window": self.ui.spin_stable_window.value(),
            "sample_interval": self.ui.spin_pm_refresh.value() / 1000.0,  # Refresh (ms): stability check reads this often
            "stage1": {
                "enabled": self.ui.chk_stage1_enable.isChecked(),
                "start": self.ui.spin_stage1_start.value(),
                "step": self.ui.spin_stage1_step.value(),
                "no": self.ui.spin_stage1_no.value(),
            },
            "stage2": {
                "enabled": self.ui.chk_stage2_enable.isChecked(),
                "start": self.ui.spin_stage2_start.value(),
                "step": self.ui.spin_stage2_step.value(),
                "no": self.ui.spin_stage2_no.value(),
            },
            "stage3": {
                "enabled": self.ui.chk_stage3_enable.isChecked(),
                "start": self.ui.spin_stage3_start.value(),
                "step": self.ui.spin_stage3_step.value(),
                "no": self.ui.spin_stage3_no.value(),
            },
        }

        # Clear chart & data
        self.coarse_model = None  # set by Model Tracking (sig_model)
        reader = self.active_reader()
        quantity, unit = self.detector_units()
        self.scan_detector = (reader.name if reader else "none", quantity, unit)  # what the saved readings are
        self.recorded_points.clear()
        self.x_data.clear()
        self.y_data.clear()
        self.curve.setData([], [])
        self.ui.progress_bar.setValue(0)
        self.start_scan_log(reader)  # test conditions go into the ScanLog box and the day's log file

        # Launch worker
        self.worker = CalibrationWorker(
            detector=reader,
            stage1_inst=self.stage1_inst,
            stage2_inst=self.stage2_inst,
            stage3_inst=self.stage3_inst,
            config=config
        )

        self.worker.sig_log.connect(self.log)
        self.worker.sig_progress.connect(self.ui.progress_bar.setValue)
        self.worker.sig_point_done.connect(self.on_point_recorded)
        self.worker.sig_model.connect(self.on_model_ready)
        self.worker.sig_scan_log.connect(self.scan_log_event)
        self.worker.sig_finished.connect(self.on_scan_finished)

        self.ui.btn_start_scan.setEnabled(False)
        self.ui.btn_stop_scan.setEnabled(True)
        self.set_detector_controls_enabled(False)  # the scan thread owns the detector until the scan ends
        self.worker.start()

    @Slot()
    def stop_calibration(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.log("Stopping scan request sent...")

    @Slot(dict)
    def on_point_recorded(self, pt: dict):
        self.recorded_points.append(pt)

        # Update position displays
        if not np.isnan(pt["stage1"]):
            self.ui.lbl_stage1_pos.setText(f"Pos: {pt['stage1']:.2f} °")
        else:
            self.ui.lbl_stage1_pos.setText("Pos: -- °")

        if not np.isnan(pt["stage2"]):
            self.ui.lbl_stage2_pos.setText(f"Pos: {pt['stage2']:.2f} °")
        else:
            self.ui.lbl_stage2_pos.setText("Pos: -- °")

        if not np.isnan(pt["stage3"]):
            self.ui.lbl_stage3_pos.setText(f"Pos: {pt['stage3']:.2f} °")
        else:
            self.ui.lbl_stage3_pos.setText("Pos: -- °")

        # Plot live curve
        self.x_data.append(pt["point_idx"])
        self.y_data.append(pt["power_mw"])
        self.curve.setData(self.x_data, self.y_data)

    @Slot(dict)
    def on_model_ready(self, model: dict):
        """Model Tracking: keep the coarse scan and fitted model, saved with the points."""
        self.coarse_model = model

    @Slot(str, str)
    def on_scan_finished(self, status: str, msg: str):
        """status: finished / stopped / aborted / error. Whatever was measured is saved in every case."""
        self.ui.btn_start_scan.setEnabled(True)
        self.ui.btn_stop_scan.setEnabled(False)
        self.set_detector_controls_enabled(True)
        self.log(msg)

        n = len(self.recorded_points)
        if n > 0 or self.coarse_model:  # an aborted Model Tracking scan still has its coarse scan
            name = self.save_data("" if status == "finished" else "_stopped" if status == "stopped" else "_aborted")
            self.scan_log_event(f"Data files: {name}.mat / .csv / .h5")
        not_ok = sum(1 for p in self.recorded_points if not p["stable"])
        if status == "finished":
            result = f"Scan finished: {n} points, {not_ok} with Stable = False"
        elif status == "stopped":
            result = f"Scan stopped by user after {n} points"
        elif status == "aborted":
            result = f"Scan aborted: {msg.lstrip('✗ ')}"
        else:
            result = f"Scan error: {msg.splitlines()[0]}"
        self.end_scan_log(result)

    def save_data(self, suffix: str = "") -> str:
        """Save recorded calibration data to MAT, CSV, and HDF5 (.h5) files; return their common name.

        suffix marks an incomplete scan: "_stopped" (Stop) or "_aborted" (abort or error).
        """
        save_dir = Path(self.ui.line_save_dir.text().strip())
        prefix = self.ui.line_file_prefix.text().strip() or "pol_cali"
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        save_dir.mkdir(parents=True, exist_ok=True)
        name = f"{prefix}_{timestamp}{suffix}"
        mat_file = save_dir / f"{name}.mat"
        csv_file = save_dir / f"{name}.csv"
        h5_file = save_dir / f"{name}.h5"

        pts = self.recorded_points
        stage1_arr = np.array([p["stage1"] for p in pts], dtype=float)
        stage2_arr = np.array([p["stage2"] for p in pts], dtype=float)
        stage3_arr = np.array([p["stage3"] for p in pts], dtype=float)
        power_arr = np.array([p["power_mw"] for p in pts], dtype=float)  # detector reading, in `unit`
        # power measurements per point (Model Tracking only, NaN otherwise)
        meas_arr = np.array([p.get("measurements", np.nan) for p in pts], dtype=float)
        model = self.coarse_model  # Model Tracking: coarse scan of Stage 1 and the fitted A, B, theta0
        detector, quantity, unit = self.scan_detector
        reading_key = f"{quantity.lower()}_{unit}"  # power_mW (PM100D) or signal_mV (lock-in R)

        # 1. Save MAT file (np.nan for missing/disabled stage)
        mat_dict = {
            "stage1_deg": stage1_arr,
            "stage2_deg": stage2_arr,
            "stage3_deg": stage3_arr,
            reading_key: power_arr,
            "measurements": meas_arr,
            "detector": detector,
        }
        if model:
            mat_dict.update({
                "coarse_stage1_deg": np.array(model["coarse_stage1_deg"], dtype=float),
                f"coarse_{reading_key}": np.array(model["coarse_reading"], dtype=float),
                f"model_A_{unit}": model["A"],
                f"model_B_{unit}": model["B"],
                "model_theta0_deg": model["theta0_deg"],
                f"model_rms_{unit}": model["rms"],
            })
        sio.savemat(str(mat_file), mat_dict)
        self.log(f"Saved calibration data to MAT: {mat_file}")

        # 2. Save CSV file (blank for missing/disabled stage; Measurements last, so readers of the first columns are unaffected)
        with open(csv_file, "w", encoding="utf-8") as f:
            f.write(f"Point_Idx,Stage1_deg,Stage2_deg,Stage3_deg,{quantity}_{unit},Stable,Measurements\n")
            for p, n in zip(pts, meas_arr):
                s1 = f"{p['stage1']:.2f}" if not np.isnan(p['stage1']) else ""
                s2 = f"{p['stage2']:.2f}" if not np.isnan(p['stage2']) else ""
                s3 = f"{p['stage3']:.2f}" if not np.isnan(p['stage3']) else ""
                meas = f"{int(n)}" if not np.isnan(n) else ""
                f.write(f"{p['point_idx']},{s1},{s2},{s3},{p['power_mw']:.4f},{p['stable']},{meas}\n")
        self.log(f"Saved calibration data to CSV: {csv_file}")

        # 3. Save HDF5 (.h5) file (np.nan for missing/disabled stage; model scalars as attributes, the fit tool reads every dataset with [:])
        with h5py.File(str(h5_file), "w") as hf:
            hf.create_dataset("stage1_deg", data=stage1_arr)
            hf.create_dataset("stage2_deg", data=stage2_arr)
            hf.create_dataset("stage3_deg", data=stage3_arr)
            hf.create_dataset(reading_key, data=power_arr)
            hf.create_dataset("measurements", data=meas_arr)
            hf.attrs["detector"] = detector
            if model:
                hf.create_dataset("coarse_stage1_deg", data=np.array(model["coarse_stage1_deg"], dtype=float))
                hf.create_dataset(f"coarse_{reading_key}", data=np.array(model["coarse_reading"], dtype=float))
                hf.attrs[f"model_A_{unit}"] = model["A"]
                hf.attrs[f"model_B_{unit}"] = model["B"]
                hf.attrs["model_theta0_deg"] = model["theta0_deg"]
                hf.attrs[f"model_rms_{unit}"] = model["rms"]
        self.log(f"Saved calibration data to HDF5: {h5_file}")
        return name


def main():
    if sys.platform == "win32":  # own taskbar entry, so the taskbar shows this program's icon instead of python.exe's
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GUI_pyqt.PolarizationCali")
        except Exception:
            pass
    app = QApplication(sys.argv)
    # logo: polarizer / wave plate in a rotation mount (pol_cali_icon.svg; the .ico holds 16..256 px, 16/24 px simplified)
    app.setWindowIcon(QIcon(str(Path(__file__).with_name("pol_cali_icon.ico"))))
    window = PolarizationCaliApp()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
