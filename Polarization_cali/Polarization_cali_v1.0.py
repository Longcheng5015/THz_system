#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Polarization & Power Calibration Program v1.0
This module provides a PySide6 GUI for automated polarization and power calibration.
Connected instruments:
  - 3 x Thorlabs KCube DC Servo Rotary Stages (Stage 1: 1/2 HWP, Stage 2: Polarizer, Stage 3: Aux)
  - 1 x Thorlabs PM100D Power Meter

Version: v1.0
"""

import sys
import os
import time
import traceback
from pathlib import Path
import numpy as np
import scipy.io as sio
import h5py

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
    QApplication, QMainWindow, QMessageBox, QFileDialog
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QThread, Signal, Slot, Qt

from MyWidget import LedIndicator
from thorlabs_PM100D import PM100D
from thorlabs_RotaryStage import RotaryStage
from scan_func_core import DataProcess, ScanPlanner



def check_power_stability(pm_inst: PM100D, wait_time_s: float, tolerance_mw: float,
                           stop_flag_check=None, logger=None, pm_enabled: bool = True) -> tuple[float, bool]:
    """
    Function to check if optical power measured by PM100D is stable.
    Reads power at wait_time_s intervals until 3 CONSECUTIVE intervals have absolute changes <= tolerance_mw.
    Requires 4 consecutive power samples P0, P1, P2, P3 such that |P1-P0|<=tol, |P2-P1|<=tol, and |P3-P2|<=tol.

    Returns:
        (stable_power_mw, is_stable)
    """
    if pm_inst is None:
        return 0.0, True

    readings = []

    # Read 1st sample
    p0 = pm_inst.measure_power() * 1000.0  # W to mW
    readings.append(p0)
    time.sleep(wait_time_s)

    max_attempts = 45  # Safety timeout fallback
    attempt = 0

    while attempt < max_attempts:
        if stop_flag_check and stop_flag_check():
            return readings[-1], False

        p_curr = pm_inst.measure_power() * 1000.0
        readings.append(p_curr)

        if len(readings) >= 4:
            d1 = abs(readings[-1] - readings[-2])
            d2 = abs(readings[-2] - readings[-3])
            d3 = abs(readings[-3] - readings[-4])

            if logger:
                logger(f"[Power Stability] Sample: {p_curr:.4f} mW | Diffs: [{d1:.4f}, {d2:.4f}, {d3:.4f}] mW (Tol: {tolerance_mw:.4f} mW)")

            if d1 <= tolerance_mw and d2 <= tolerance_mw and d3 <= tolerance_mw:
                return p_curr, True

        attempt += 1
        time.sleep(wait_time_s)

    return readings[-1], True


class CalibrationWorker(QThread):
    """Worker thread executing the calibration scan logic without blocking UI."""

    # Signals
    sig_log = Signal(str)
    sig_progress = Signal(int)
    sig_point_done = Signal(dict)
    sig_finished = Signal(bool, str)

    def __init__(self, pm_inst, stage1_inst, stage2_inst, stage3_inst, config: dict):
        super().__init__()
        self.pm_inst = pm_inst
        self.stage1_inst = stage1_inst
        self.stage2_inst = stage2_inst
        self.stage3_inst = stage3_inst
        self.config = config
        self._is_stopped = False

    def stop(self):
        self._is_stopped = True

    def run(self):
        try:
            scan_mode = self.config["scan_mode"]
            polar_algo = self.config["polar_algo"]
            wait_time = self.config["wait_time"]
            target_power = self.config["target_power"]
            tolerance = self.config["tolerance"]

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

            pm_enabled = self.config.get("pm100d_enabled", True)

            # ----------------------------------------------------
            # MODE 1: Power mode
            # ----------------------------------------------------
            if scan_mode.lower().startswith("power"):
                fixed_s2 = s2_seq[0] if (stage2_cfg["enabled"] and len(s2_seq) > 0) else None
                fixed_s3 = s3_seq[0] if (stage3_cfg["enabled"] and len(s3_seq) > 0) else None

                if self.stage2_inst and fixed_s2 is not None:
                    self.stage2_inst.move_to(fixed_s2)
                if self.stage3_inst and fixed_s3 is not None:
                    self.stage3_inst.move_to(fixed_s3)

                for idx1, angle1 in enumerate(s1_seq):
                    if self._is_stopped:
                        break

                    if self.stage1_inst and angle1 is not None:
                        self.sig_log.emit(f"Moving Stage 1 to {angle1}°...")
                        self.stage1_inst.move_to(angle1)

                    power_mw, stable = check_power_stability(
                        self.pm_inst, wait_time, tolerance,
                        stop_flag_check=lambda: self._is_stopped,
                        logger=lambda msg: self.sig_log.emit(msg),
                        pm_enabled=pm_enabled
                    )

                    s1_pos = angle1 if stage1_cfg["enabled"] else np.nan
                    s2_pos = fixed_s2 if stage2_cfg["enabled"] else np.nan
                    s3_pos = fixed_s3 if stage3_cfg["enabled"] else np.nan

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
            # MODE 2: Polarization mode
            # ----------------------------------------------------
            elif scan_mode.lower().startswith("polar"):
                fixed_s3 = s3_seq[0] if (stage3_cfg["enabled"] and len(s3_seq) > 0) else None
                if self.stage3_inst and fixed_s3 is not None:
                    self.stage3_inst.move_to(fixed_s3)

                for idx1, angle1 in enumerate(s1_seq):
                    if self._is_stopped:
                        break

                    if self.stage1_inst and angle1 is not None:
                        self.sig_log.emit(f"Stage 1 -> {angle1}° | Searching Stage 2 for target power {target_power} mW...")
                        self.stage1_inst.move_to(angle1)

                    matched = False
                    matched_s2_pos = np.nan
                    final_power_mw = 0.0

                    # Option A: Sequential Step Search (Option A)
                    if "Sequential" in polar_algo or "A" in polar_algo:
                        for angle2 in s2_seq:
                            if self._is_stopped:
                                break

                            if self.stage2_inst and angle2 is not None:
                                self.stage2_inst.move_to(angle2)

                            power_mw, stable = check_power_stability(
                                self.pm_inst, wait_time, tolerance,
                                stop_flag_check=lambda: self._is_stopped,
                                pm_enabled=pm_enabled
                            )

                            if abs(power_mw - target_power) <= tolerance and stable:
                                matched = True
                                matched_s2_pos = angle2
                                final_power_mw = power_mw
                                self.sig_log.emit(f"Matched Target Power! Stage 2: {angle2}°, Power: {power_mw:.4f} mW")
                                break

                    # Option B: Binary Search (Option B)
                    else:
                        if stage2_cfg["enabled"] and len(s2_seq) >= 2:
                            low_ang = stage2_cfg["start"]
                            high_ang = round(stage2_cfg["start"] + (stage2_cfg["no"] - 1) * stage2_cfg["step"], 2)
                            max_biter = 10

                            for _ in range(max_biter):
                                if self._is_stopped:
                                    break

                                mid_ang = round((low_ang + high_ang) / 2.0, 2)
                                if self.stage2_inst:
                                    self.stage2_inst.move_to(mid_ang)

                                power_mw, stable = check_power_stability(
                                    self.pm_inst, wait_time, tolerance,
                                    stop_flag_check=lambda: self._is_stopped,
                                    pm_enabled=pm_enabled
                                )

                                if abs(power_mw - target_power) <= tolerance and stable:
                                    matched = True
                                    matched_s2_pos = mid_ang
                                    final_power_mw = power_mw
                                    self.sig_log.emit(f"Binary Search Matched! Stage 2: {mid_ang}°, Power: {power_mw:.4f} mW")
                                    break
                                elif power_mw < target_power:
                                    low_ang = mid_ang
                                else:
                                    high_ang = mid_ang

                    if not matched:
                        final_power_mw = power_mw if 'power_mw' in locals() else 0.0
                        self.sig_log.emit(f"Warning: Target power not matched within tolerance for Stage 1 = {angle1}°")

                    s1_pos = angle1 if stage1_cfg["enabled"] else np.nan
                    s2_pos = matched_s2_pos if stage2_cfg["enabled"] else np.nan
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
                self.sig_finished.emit(False, "Calibration scan stopped by user.")
            else:
                self.sig_finished.emit(True, f"Calibration complete. Total points: {len(recorded_data)}")

        except Exception as exc:
            err_msg = f"Calibration Worker Error: {exc}\n{traceback.format_exc()}"
            self.sig_finished.emit(False, err_msg)


class PolarizationCaliApp(QMainWindow):
    """Main window class for Polarization & Power Calibration System v1.0."""

    def __init__(self):
        super().__init__()

        # Load UI
        uiLoader = QUiLoader()
        uiLoader.registerCustomWidget(pg.PlotWidget)
        uiLoader.registerCustomWidget(LedIndicator)
        ui_path = Path(__file__).parent / "Polarization_cali_v1.0.ui"
        self.ui = uiLoader.load(str(ui_path))
        self.ui.closeEvent = self.on_ui_close_event

        # Instrument objects
        self.pm_inst = None
        self.stage1_inst = None
        self.stage2_inst = None
        self.stage3_inst = None

        # Data buffers for live plotting
        self.recorded_points = []
        self.x_data = []
        self.y_data = []

        # Thread reference
        self.worker = None

        # Setup UI features
        self.setup_ui_events()
        self.setup_chart()
        self.setup_tooltips()

        self.ui.show()
        self.log("Polarization & Power Calibration System v1.0 initialized.")
        self.log("Ready. Select hardware options and click 'Connect Enabled Devices' to start.")

    def setup_tooltips(self):
        """Set hover tooltips for scan modes as required by prompt."""
        mode_tooltips = {
            "Power": "Power mode: Fix Stage 2 angle, scan Stage 1. Wait for optical power stability at each Stage 1 angle, then record Stage 1/2/3 positions and power.",
            "Polarization": "Polarization mode: Read target power, scan Stage 2 according to Stage 1/2 settings until optical power reaches target within tolerance and stabilizes, then record positions and power."
        }
        self.ui.combo_scan_mode.setItemData(0, mode_tooltips["Power"], Qt.ToolTipRole)
        self.ui.combo_scan_mode.setItemData(1, mode_tooltips["Polarization"], Qt.ToolTipRole)
        self.ui.combo_scan_mode.setToolTip(mode_tooltips["Power"])
        self.ui.combo_scan_mode.currentIndexChanged.connect(self.on_mode_changed)

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
        self.ui.btn_disconnect_all.clicked.connect(self.disconnect_all_devices)
        self.ui.btn_exit.clicked.connect(self.exit_app)

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

        # Set default save path and populate default serials
        default_save_path = str(Path(__file__).parent / "cali_data")
        os.makedirs(default_save_path, exist_ok=True)
        self.ui.line_save_dir.setText(default_save_path)
        self.init_device_defaults()

    def init_device_defaults(self):
        """Populate default VISA resource and stage serials matching OPTP v1.7."""
        if self.ui.combo_pm100d_res.count() == 0:
            self.ui.combo_pm100d_res.addItem("USB0::0x1313::0x8078::P0000000::INSTR")

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

        # 1. Connect PM100D if checked
        if self.ui.chk_pm100d_enable.isChecked():
            if self.pm_inst is not None:
                self.log("PM100D is already connected.")
            else:
                res = self.ui.combo_pm100d_res.currentText().strip()
                if res:
                    pm_temp = None
                    try:
                        pm_temp = PM100D(res)
                        pm_temp.open()
                        idn = pm_temp.idn()
                        self.pm_inst = pm_temp
                        self.ui.led_pm100d.status = True
                        self.log(f"✓ PM100D connected: {idn}")
                    except Exception as exc:
                        if pm_temp is not None:
                            try:
                                pm_temp.close()
                            except Exception:
                                pass
                        self.pm_inst = None
                        self.ui.led_pm100d.status = False
                        self.log(f"✗ Failed to connect PM100D: {exc}")

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
                        stg_temp.home(60000)
                        self.stage1_inst = stg_temp
                        self.ui.lbl_stage1_pos.setText(f"Pos: {stg_temp.position():.2f} °")
                        self.ui.led_stage1.status = True
                        self.log(f"✓ Stage 1 connected & homed (Serial: {sn})")
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
                        stg_temp.home(60000)
                        self.stage2_inst = stg_temp
                        self.ui.lbl_stage2_pos.setText(f"Pos: {stg_temp.position():.2f} °")
                        self.ui.led_stage2.status = True
                        self.log(f"✓ Stage 2 connected & homed (Serial: {sn})")
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
                        stg_temp.home(60000)
                        self.stage3_inst = stg_temp
                        self.ui.lbl_stage3_pos.setText(f"Pos: {stg_temp.position():.2f} °")
                        self.ui.led_stage3.status = True
                        self.log(f"✓ Stage 3 connected & homed (Serial: {sn})")
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
    def disconnect_all_devices(self):
        """Close sessions for all connected instruments and reset LEDs."""
        has_connected_devices = any([
            self.pm_inst is not None,
            self.stage1_inst is not None,
            self.stage2_inst is not None,
            self.stage3_inst is not None
        ])

        if not has_connected_devices:
            self.log("No devices currently connected.")
            return

        self.log("=== Disconnecting All Devices ===")
        if self.pm_inst:
            try:
                self.pm_inst.close()
            except Exception:
                pass
            self.pm_inst = None
            self.ui.led_pm100d.status = False
            self.log("Disconnected PM100D")

        for idx, (stg_attr, led) in enumerate([
            (self.stage1_inst, self.ui.led_stage1),
            (self.stage2_inst, self.ui.led_stage2),
            (self.stage3_inst, self.ui.led_stage3),
        ], start=1):
            if stg_attr:
                try:
                    stg_attr.close()
                except Exception:
                    pass
                led.status = False
                self.log(f"Disconnected Stage {idx}")

        self.stage1_inst = None
        self.stage2_inst = None
        self.stage3_inst = None
        QApplication.processEvents()

    @Slot()
    def exit_app(self):
        """Trigger window close on self.ui, which invokes on_ui_close_event confirmation and cleanup."""
        self.ui.close()

    def on_ui_close_event(self, event):
        """Handle window close event on self.ui to confirm exit and disconnect active devices."""
        reply = QMessageBox.question(
            self.ui,
            "Confirm Exit",
            "Are you sure you want to exit the application?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self.worker and self.worker.isRunning():
                self.stop_calibration()

            has_connected_devices = any([
                self.pm_inst is not None,
                self.stage1_inst is not None,
                self.stage2_inst is not None,
                self.stage3_inst is not None
            ])

            if has_connected_devices:
                self.log("Disconnecting active hardware devices before exit...")
                self.disconnect_all_devices()

            event.accept()
            QApplication.quit()
        else:
            event.ignore()

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

    @Slot()
    def browse_save_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if folder:
            self.ui.line_save_dir.setText(folder)

    @Slot()
    def start_calibration(self):
        """Build configuration and start worker thread."""
        config = {
            "pm100d_enabled": self.ui.chk_pm100d_enable.isChecked(),
            "scan_mode": self.ui.combo_scan_mode.currentText(),
            "polar_algo": self.ui.combo_polar_search.currentText(),
            "target_power": self.ui.spin_target_power.value(),
            "tolerance": self.ui.spin_power_tol.value(),
            "wait_time": self.ui.spin_wait_time.value(),
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
        self.recorded_points.clear()
        self.x_data.clear()
        self.y_data.clear()
        self.curve.setData([], [])
        self.ui.progress_bar.setValue(0)

        # Launch worker
        self.worker = CalibrationWorker(
            pm_inst=self.pm_inst,
            stage1_inst=self.stage1_inst,
            stage2_inst=self.stage2_inst,
            stage3_inst=self.stage3_inst,
            config=config
        )

        self.worker.sig_log.connect(self.log)
        self.worker.sig_progress.connect(self.ui.progress_bar.setValue)
        self.worker.sig_point_done.connect(self.on_point_recorded)
        self.worker.sig_finished.connect(self.on_scan_finished)

        self.ui.btn_start_scan.setEnabled(False)
        self.ui.btn_stop_scan.setEnabled(True)
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

    @Slot(bool, str)
    def on_scan_finished(self, success: bool, msg: str):
        self.ui.btn_start_scan.setEnabled(True)
        self.ui.btn_stop_scan.setEnabled(False)
        self.log(msg)

        if success and len(self.recorded_points) > 0:
            self.save_data()

    def save_data(self):
        """Save recorded calibration data to MAT, CSV, and HDF5 (.h5) files."""
        save_dir = Path(self.ui.line_save_dir.text().strip())
        prefix = self.ui.line_file_prefix.text().strip() or "pol_cali"
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        save_dir.mkdir(parents=True, exist_ok=True)
        mat_file = save_dir / f"{prefix}_{timestamp}.mat"
        csv_file = save_dir / f"{prefix}_{timestamp}.csv"
        h5_file = save_dir / f"{prefix}_{timestamp}.h5"

        pts = self.recorded_points
        stage1_arr = np.array([p["stage1"] for p in pts], dtype=float)
        stage2_arr = np.array([p["stage2"] for p in pts], dtype=float)
        stage3_arr = np.array([p["stage3"] for p in pts], dtype=float)
        power_arr = np.array([p["power_mw"] for p in pts], dtype=float)

        # 1. Save MAT file (np.nan for missing/disabled stage)
        mat_dict = {
            "stage1_deg": stage1_arr,
            "stage2_deg": stage2_arr,
            "stage3_deg": stage3_arr,
            "power_mW": power_arr,
        }
        sio.savemat(str(mat_file), mat_dict)
        self.log(f"Saved calibration data to MAT: {mat_file}")

        # 2. Save CSV file (blank for missing/disabled stage)
        with open(csv_file, "w", encoding="utf-8") as f:
            f.write("Point_Idx,Stage1_deg,Stage2_deg,Stage3_deg,Power_mW,Stable\n")
            for p in pts:
                s1 = f"{p['stage1']:.2f}" if not np.isnan(p['stage1']) else ""
                s2 = f"{p['stage2']:.2f}" if not np.isnan(p['stage2']) else ""
                s3 = f"{p['stage3']:.2f}" if not np.isnan(p['stage3']) else ""
                f.write(f"{p['point_idx']},{s1},{s2},{s3},{p['power_mw']:.4f},{p['stable']}\n")
        self.log(f"Saved calibration data to CSV: {csv_file}")

        # 3. Save HDF5 (.h5) file (np.nan for missing/disabled stage)
        with h5py.File(str(h5_file), "w") as hf:
            hf.create_dataset("stage1_deg", data=stage1_arr)
            hf.create_dataset("stage2_deg", data=stage2_arr)
            hf.create_dataset("stage3_deg", data=stage3_arr)
            hf.create_dataset("power_mW", data=power_arr)
        self.log(f"Saved calibration data to HDF5: {h5_file}")


def main():
    app = QApplication(sys.argv)
    window = PolarizationCaliApp()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
