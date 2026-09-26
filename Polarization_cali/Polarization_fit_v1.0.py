"""
Polarization & Power Data Fitting & Analysis System v1.0
Author: DeepMind Team
Date: 2026-08-06
Version: v1.0
"""

import sys
import os
import time
import traceback
from pathlib import Path
import numpy as np
import h5py
import pandas as pd
import csv
from scipy.optimize import curve_fit, fsolve

# Path injection for inst_libs and func_cores
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
if str(parent_dir / "inst_libs") not in sys.path:
    sys.path.append(str(parent_dir / "inst_libs"))
if str(parent_dir / "func_cores") not in sys.path:
    sys.path.append(str(parent_dir / "func_cores"))

from scan_data_core import ScanDataCore

import pyqtgraph as pg
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QFileDialog
)
from PySide6.QtCore import Slot, Qt
from PySide6.QtUiTools import QUiLoader


# ============================================================================
# Fitting Model Functions
# ============================================================================

def malus_model(theta_deg, P0, A, theta0_deg):
    """Malus Law Cosine Square Fit: P(theta) = P0 + A * cos^2(2 * (theta - theta0))."""
    rad = np.radians(theta_deg - theta0_deg)
    return P0 + A * (np.cos(2.0 * rad) ** 2)


def sine_model(x, A, w, phi, C):
    """Sine Wave Fit: y = A * sin(w * x + phi) + C."""
    return A * np.sin(w * x + phi) + C


def linear_model(x, a, b):
    """Linear Fit: y = a * x + b."""
    return a * x + b


def poly2_model(x, a, b, c):
    """Polynomial Degree 2 Fit: y = a * x^2 + b * x + c."""
    return a * (x ** 2) + b * x + c


def calculate_r_squared(y_true, y_pred):
    """Calculate Coefficient of Determination (R^2)."""
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        return 1.0
    return 1.0 - (ss_res / ss_tot)


def calculate_rmse(y_true, y_pred):
    """Calculate Root Mean Square Error (RMSE)."""
    return np.sqrt(np.mean((y_true - y_pred) ** 2))


# ============================================================================
# Main Application Class
# ============================================================================

class PolarizationFitApp:
    """Main window class for Polarization & Power Data Fitting Tool v1.0."""

    def __init__(self):
        # Load UI
        uiLoader = QUiLoader()
        uiLoader.registerCustomWidget(pg.PlotWidget)
        ui_path = Path(__file__).parent / "Polarization_fit_v1.0.ui"
        self.ui = uiLoader.load(str(ui_path))
        self.ui.closeEvent = self.on_ui_close_event

        # Data buffers
        self.loaded_data = None
        self.fitted_params = None
        self.current_fit_mode = "Power"
        self.current_formula_name = "Malus"

        # Setup UI events & charts
        self.setup_ui_events()
        self.setup_chart()
        self.setup_tooltips()

        self.ui.show()
        self.log("Polarization & Power Data Fitting Tool v1.0 initialized.")
        self.log("Ready. Browse and load calibration data file (.mat / .csv / .h5) to begin analysis.")

    def setup_tooltips(self):
        """Set hover tooltips for fitting mode selection."""
        self.ui.combo_fit_mode.setItemData(
            0, "Power Mode Fitting: Fits Optical Power vs Stage 1 Angle (Half-Waveplate).", Qt.ToolTipRole
        )
        self.ui.combo_fit_mode.setItemData(
            1, "Polarization Mode Fitting: Fits Stage 2 Angle vs Required Stage 1 Relative Step.", Qt.ToolTipRole
        )

    def setup_chart(self):
        """Configure pyqtgraph chart area."""
        chart = self.ui.powerChart
        chart.setBackground("w")
        plot_item = chart.getPlotItem()
        plot_item.showGrid(x=True, y=True, alpha=0.3)
        plot_item.addLegend()

        # Scatter plot for raw data points
        self.scatter_raw = pg.ScatterPlotItem(
            size=8, pen=pg.mkPen(None), brush=pg.mkBrush(20, 100, 220, 200), name="Raw Data Points"
        )
        plot_item.addItem(self.scatter_raw)

        # Line plot for smooth fitted curve
        self.curve_fit = plot_item.plot(
            pen=pg.mkPen(color="r", width=2.5), name="Fitted Curve"
        )

    def setup_ui_events(self):
        """Connect UI signals to handler slots."""
        self.ui.btn_browse_file.clicked.connect(self.browse_file)
        self.ui.btn_load_data.clicked.connect(self.load_data)
        self.ui.btn_run_fit.clicked.connect(self.run_fitting)
        self.ui.btn_calculate.clicked.connect(self.calculate_prediction)
        self.ui.btn_exit.clicked.connect(self.exit_app)
        self.ui.combo_fit_mode.currentIndexChanged.connect(self.on_fit_mode_changed)

        # Append new interpolation options to formula combo box
        self.ui.combo_formula.addItem("Raw Data Interpolation (Linear)")
        self.ui.combo_formula.addItem("Raw Data Interpolation (Cubic Spline)")

        # Dynamically add an Export CSV button to the UI
        from PySide6.QtWidgets import QPushButton, QHBoxLayout, QInputDialog
        self.btn_export_csv = QPushButton("Export Dense CSV")
        self.btn_export_csv.clicked.connect(self.export_dense_csv)
        
        # We find the parent layout of btn_calculate and add it there
        parent_layout = self.ui.btn_calculate.parentWidget().layout()
        if parent_layout:
            # Find the index of btn_calculate to insert next to it
            idx = parent_layout.indexOf(self.ui.btn_calculate)
            if idx != -1:
                parent_layout.insertWidget(idx + 1, self.btn_export_csv)
            else:
                parent_layout.addWidget(self.btn_export_csv)
            self.btn_export_csv.show()

    def log(self, message: str):
        """Append log trace and formula output to text edit box."""
        timestamp = time.strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        self.ui.txt_formula_log.append(log_line)
        print(log_line)

    @Slot()
    def browse_file(self):
        """Open file dialog to select data file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.ui,
            "Select Calibration Data File",
            str(Path(__file__).parent / "cali_data"),
            "Supported Data Files (*.mat *.csv *.h5);;MAT Files (*.mat);;CSV Files (*.csv);;HDF5 Files (*.h5)"
        )
        if file_path:
            self.ui.line_file_path.setText(file_path)

    @Slot()
    def load_data(self):
        """Parse calibration data file (.mat / .csv / .h5)."""
        filepath = self.ui.line_file_path.text().strip()
        if not filepath or not os.path.exists(filepath):
            QMessageBox.warning(self.ui, "Warning", "Please select a valid existing data file.")
            return

        self.log(f"Loading data file: {filepath}...")
        ext = Path(filepath).suffix.lower()

        try:
            parsed = {}
            if ext == ".mat":
                mat = sio.loadmat(filepath)
                for key in ["stage1", "stage2", "stage3", "power_mw", "target_power_mw", "stable"]:
                    if key in mat:
                        parsed[key] = mat[key].flatten()
            elif ext == ".csv":
                data = ScanDataCore.parse_calibration_file(filepath)
                if data is not None:
                    rot1, rot2, rot3, power = data.T
                    parsed["stage1"] = rot1
                    parsed["stage2"] = rot2
                    parsed["stage3"] = rot3
                    parsed["power_mw"] = power
                else:
                    QMessageBox.warning(self.ui, "Warning", "No valid data found in CSV file.")
                    return
            elif ext in [".h5", ".hdf5"]:
                with h5py.File(filepath, "r") as f:
                    for key in f.keys():
                        parsed[key] = f[key][:]
            else:
                QMessageBox.critical(self.ui, "Error", f"Unsupported file extension: {ext}")
                return

            self.loaded_data = parsed
            num_pts = len(parsed.get("stage1", parsed.get("power_mw", [])))
            self.log(f"Successfully loaded {num_pts} data points from {Path(filepath).name}.")
            self.auto_update_plot_labels()
            self.plot_raw_data()
        except Exception as exc:
            self.log(f"Failed to parse file: {exc}")
            QMessageBox.critical(self.ui, "Parsing Error", f"Failed to parse file:\n{exc}")

    def auto_update_plot_labels(self):
        """Update plot axis labels based on fitting mode."""
        plot_item = self.ui.powerChart.getPlotItem()
        mode_idx = self.ui.combo_fit_mode.currentIndex()
        if mode_idx == 0:
            # Power mode fitting
            plot_item.setLabel("bottom", "Stage 1 Angle (°)", color="black")
            plot_item.setLabel("left", "Measured Power (mW)", color="black")
            self.ui.lbl_calc_in1.setText("Stage 1 Guess/Target (°):")
            self.ui.lbl_calc_in2.setText("Target Power (mW):")
        else:
            # Polarization mode fitting
            plot_item.setLabel("bottom", "Stage 2 Angle (°)", color="black")
            plot_item.setLabel("left", "Required Stage 1 Step (°)", color="black")
            self.ui.lbl_calc_in1.setText("Stage 2 Target Angle (°):")
            self.ui.lbl_calc_in2.setText("Target Stage 1 Step (°):")

    def plot_raw_data(self):
        """Plot raw scatter points on chart."""
        if not self.loaded_data:
            return

        mode_idx = self.ui.combo_fit_mode.currentIndex()
        s1 = self.loaded_data.get("stage1", np.array([]))
        s2 = self.loaded_data.get("stage2", np.array([]))
        power = self.loaded_data.get("power_mw", np.array([]))

        # Filter NaNs
        valid_mask = ~np.isnan(s1) & ~np.isnan(power)

        if mode_idx == 0:
            # Power mode: x = Stage 1 angle, y = Power
            x_vals = s1[valid_mask]
            y_vals = power[valid_mask]
        else:
            # Polarization mode: x = Stage 2 angle, y = Stage 1 angle / step
            valid_mask_p = ~np.isnan(s1) & ~np.isnan(s2)
            x_vals = s2[valid_mask_p]
            y_vals = s1[valid_mask_p]

        if len(x_vals) > 0:
            self.scatter_raw.setData(x_vals, y_vals)
            self.curve_fit.setData([], [])

    @Slot(int)
    def on_fit_mode_changed(self, index: int):
        self.auto_update_plot_labels()
        self.plot_raw_data()

    @Slot()
    def run_fitting(self):
        """Perform non-linear curve fitting on loaded data."""
        if not self.loaded_data:
            QMessageBox.warning(self.ui, "Warning", "Please load a data file first.")
            return

        mode_idx = self.ui.combo_fit_mode.currentIndex()
        formula_idx = self.ui.combo_formula.currentIndex()

        s1 = self.loaded_data.get("stage1", np.array([]))
        s2 = self.loaded_data.get("stage2", np.array([]))
        power = self.loaded_data.get("power_mw", np.array([]))

        if mode_idx == 0:
            # Power Mode
            mask = ~np.isnan(s1) & ~np.isnan(power)
            x_data = np.array(s1[mask], dtype=float)
            y_data = np.array(power[mask], dtype=float)
            x_label = "Stage 1 (°)"
            y_label = "Power (mW)"
        else:
            # Polarization Mode
            mask = ~np.isnan(s1) & ~np.isnan(s2)
            x_data = np.array(s2[mask], dtype=float)
            y_data = np.array(s1[mask], dtype=float)
            x_label = "Stage 2 (°)"
            y_label = "Stage 1 Step (°)"

        if len(x_data) < 3:
            QMessageBox.warning(self.ui, "Warning", "Not enough valid data points for curve fitting.")
            return

        self.log(f"=== Performing Curve Fitting ({x_label} vs {y_label}) ===")

        try:
            # Formula model selection
            if formula_idx == 0:
                # Malus Law Cosine Square Fit
                # Smarter initial guess: find the actual X coordinate of the maximum Y for theta0!
                idx_max = np.argmax(y_data)
                theta0_guess = x_data[idx_max]
                
                p0_init = [np.min(y_data), np.max(y_data) - np.min(y_data), theta0_guess]
                # Provide loose bounds to prevent optimizer from diverging
                bounds = (
                    [0.0, 0.0, -np.inf], 
                    [np.max(y_data), np.inf, np.inf]
                )
                
                popt, _ = curve_fit(malus_model, x_data, y_data, p0=p0_init, bounds=bounds, maxfev=10000)
                y_fit = malus_model(x_data, *popt)

                # Formula text
                formula_str = f"P(θ1) = P0 + A * cos²(2 * (θ1 - θ0))\n" \
                              f"  P0      = {popt[0]:.6f} mW\n" \
                              f"  A       = {popt[1]:.6f} mW\n" \
                              f"  θ0      = {popt[2]:.4f} °"

                # Dense evaluation for smooth plot
                x_dense = np.linspace(np.min(x_data), np.max(x_data), 500)
                y_dense = malus_model(x_dense, *popt)
                fit_func = lambda theta1: malus_model(theta1, *popt)

            elif formula_idx == 1:
                # Sine Wave Fit
                # Smarter frequency guess: estimate by zero-crossings around the mean
                y_centered = y_data - np.mean(y_data)
                crossings = np.where(np.diff(np.sign(y_centered)))[0]
                if len(crossings) >= 2:
                    period_guess = 2.0 * np.abs(x_data[crossings[1]] - x_data[crossings[0]])
                    w_guess = 2.0 * np.pi / max(period_guess, 1e-5)
                else:
                    w_guess = 2.0 * np.pi / (np.max(x_data) - np.min(x_data) + 1e-5)
                
                amp_guess = (np.max(y_data) - np.min(y_data)) / 2.0
                
                p0_init = [amp_guess, w_guess, 0.0, np.mean(y_data)]
                popt, _ = curve_fit(sine_model, x_data, y_data, p0=p0_init, maxfev=10000)
                y_fit = sine_model(x_data, *popt)

                formula_str = f"y(x) = A * sin(w * x + φ) + C\n" \
                              f"  A = {popt[0]:.6f}\n" \
                              f"  w = {popt[1]:.6f}\n" \
                              f"  φ = {popt[2]:.6f} rad\n" \
                              f"  C = {popt[3]:.6f}"

                x_dense = np.linspace(np.min(x_data), np.max(x_data), 500)
                y_dense = sine_model(x_dense, *popt)
                fit_func = lambda x: sine_model(x, *popt)

            elif formula_idx == 2:
                # Linear Fit
                popt, _ = curve_fit(linear_model, x_data, y_data)
                y_fit = linear_model(x_data, *popt)

                formula_str = f"y(x) = a * x + b\n" \
                              f"  a (slope)     = {popt[0]:.6f}\n" \
                              f"  b (intercept) = {popt[1]:.6f}"

                x_dense = np.linspace(np.min(x_data), np.max(x_data), 500)
                y_dense = linear_model(x_dense, *popt)
                fit_func = lambda x: linear_model(x, *popt)

            elif formula_idx == 3:
                # Polynomial Deg 2 Fit
                popt, _ = curve_fit(poly2_model, x_data, y_data)
                y_fit = poly2_model(x_data, *popt)

                formula_str = f"y(x) = a * x² + b * x + c\n" \
                              f"  a = {popt[0]:.6e}\n" \
                              f"  b = {popt[1]:.6f}\n" \
                              f"  c = {popt[2]:.6f}"

                x_dense = np.linspace(np.min(x_data), np.max(x_data), 500)
                y_dense = poly2_model(x_dense, *popt)
                fit_func = lambda x: poly2_model(x, *popt)
                
            elif formula_idx == 4 or formula_idx == 5:
                # Raw Data Interpolation (4 = Linear, 5 = Cubic)
                from scipy.interpolate import interp1d
                kind = 'linear' if formula_idx == 4 else 'cubic'
                
                # Make sure x_data is strictly increasing for interp1d
                sort_idx = np.argsort(x_data)
                x_sorted = x_data[sort_idx]
                y_sorted = y_data[sort_idx]
                
                # Remove duplicates if any
                x_unique, unique_indices = np.unique(x_sorted, return_index=True)
                y_unique = y_sorted[unique_indices]
                
                if len(x_unique) < (4 if kind == 'cubic' else 2):
                    QMessageBox.warning(self.ui, "Warning", f"Not enough unique points for {kind} interpolation.")
                    return
                
                interp_f = interp1d(x_unique, y_unique, kind=kind, fill_value="extrapolate")
                
                y_fit = interp_f(x_data)
                popt = [0]
                
                formula_str = f"Raw Data Interpolation ({kind.capitalize()})\n" \
                              f"  Connects raw points directly without a formula.\n"
                
                x_dense = np.linspace(np.min(x_data), np.max(x_data), 500)
                y_dense = interp_f(x_dense)
                fit_func = lambda x: interp_f(x)

            # Goodness of fit statistics
            r2 = calculate_r_squared(y_data, y_fit)
            rmse = calculate_rmse(y_data, y_fit)

            self.fitted_func = fit_func
            self.fitted_params = popt

            # Update chart with smooth fitted line
            self.curve_fit.setData(x_dense, y_dense)

            # Print fit formula and statistics
            fit_summary = f"--- FIT RESULTS ({self.ui.combo_formula.currentText()}) ---\n" \
                          f"{formula_str}\n" \
                          f"-----------------------------------------\n" \
                          f"  R² Score = {r2:.6f}\n" \
                          f"  RMSE     = {rmse:.6f}\n"
            self.log(fit_summary)

        except Exception as exc:
            self.log(f"Curve fitting failed: {exc}\n{traceback.format_exc()}")
            QMessageBox.critical(self.ui, "Fitting Error", f"Curve fitting failed:\n{exc}")

    @Slot()
    def calculate_prediction(self):
        """Use fitted formula parameters to predict output for target input angles, and reverse calculate angle for target power."""
        if not hasattr(self, "fitted_func") or self.fitted_func is None:
            QMessageBox.warning(self.ui, "Warning", "Please run curve fitting first before calculating predictions.")
            return

        mode_idx = self.ui.combo_fit_mode.currentIndex()
        val1 = self.ui.spin_calc_in1.value()
        val2 = self.ui.spin_calc_in2.value()

        try:
            pred_val = self.fitted_func(val1)
            
            if mode_idx == 0:
                # Power prediction (Forward: Angle -> Power, Reverse: Power -> Angle)
                target_power = val2
                # Reverse calculate angle using fsolve, with val1 as the initial guess
                def equation_to_solve(x):
                    return self.fitted_func(x) - target_power
                
                # fsolve returns an array, we take the first element
                calc_angle = fsolve(equation_to_solve, x0=val1)[0]
                
                result_str = f"Target {val1}° -> {pred_val:.4f} mW\nTarget {target_power} mW -> {calc_angle:.2f} °"
                self.ui.lbl_calc_result.setText(result_str)
                self.log(f"Calc: [Angle {val1}° -> {pred_val:.4f} mW] | [Power {target_power} mW -> {calc_angle:.4f}°]")
            else:
                # Stage 1 relative step prediction (Forward and Reverse)
                target_step = val2
                def equation_to_solve(x):
                    return self.fitted_func(x) - target_step
                calc_angle = fsolve(equation_to_solve, x0=val1)[0]
                
                result_str = f"Target {val1}° -> Step {pred_val:.2f} °\nTarget Step {target_step}° -> Angle {calc_angle:.2f} °"
                self.ui.lbl_calc_result.setText(result_str)
                self.log(f"Calc: [Angle {val1}° -> Step {pred_val:.2f}°] | [Step {target_step}° -> Angle {calc_angle:.4f}°]")
        except Exception as exc:
            self.log(f"Calculator error: {exc}")
            QMessageBox.critical(self.ui, "Calculator Error", f"Calculation failed: {exc}")

    @Slot()
    def export_dense_csv(self):
        """Export the currently fitted/interpolated curve to a dense CSV file."""
        if not hasattr(self, "fitted_func") or self.fitted_func is None:
            QMessageBox.warning(self.ui, "Warning", "Please run curve fitting or interpolation first.")
            return
            
        if not self.loaded_data:
            return
            
        mode_idx = self.ui.combo_fit_mode.currentIndex()
        s1 = self.loaded_data.get("stage1", np.array([]))
        s2 = self.loaded_data.get("stage2", np.array([]))
        
        if mode_idx == 0:
            x_data = s1[~np.isnan(s1)]
        else:
            x_data = s2[~np.isnan(s2)]
            
        if len(x_data) == 0:
            return
            
        from PySide6.QtWidgets import QInputDialog
        step, ok = QInputDialog.getDouble(
            self.ui, "Export Step Size", 
            "Enter the interpolation step size (°):", 
            0.5, 0.01, 10.0, 2
        )
        
        if not ok:
            return
            
        x_min, x_max = np.min(x_data), np.max(x_data)
        x_export = np.arange(x_min, x_max + step, step)
        
        try:
            y_export = self.fitted_func(x_export)
        except Exception as exc:
            QMessageBox.critical(self.ui, "Export Error", f"Failed to generate dense data: {exc}")
            return
            
        save_path, _ = QFileDialog.getSaveFileName(
            self.ui, "Save Dense CSV", 
            str(Path(__file__).parent / "cali_data" / "dense_cali.csv"), 
            "CSV Files (*.csv)"
        )
        
        if not save_path:
            return
            
        try:
            if mode_idx == 0:
                # Angle vs Power
                df = pd.DataFrame({
                    "Point_Idx": range(len(x_export)),
                    "Stage1_deg": np.round(x_export, 2),
                    "Stage2_deg": np.zeros(len(x_export)),
                    "Stage3_deg": np.zeros(len(x_export)),
                    "Power_mW": np.round(y_export, 4),
                    "Stable": [True] * len(x_export)
                })
            else:
                # Stage 2 vs Stage 1 Step
                df = pd.DataFrame({
                    "Point_Idx": range(len(x_export)),
                    "Stage1_deg": np.round(y_export, 2),
                    "Stage2_deg": np.round(x_export, 2),
                    "Stage3_deg": np.zeros(len(x_export)),
                    "Power_mW": np.zeros(len(x_export)),
                    "Stable": [True] * len(x_export)
                })
            
            df.to_csv(save_path, index=False)
            self.log(f"Exported dense CSV to: {save_path} ({len(x_export)} points)")
            QMessageBox.information(self.ui, "Export Successful", f"Dense CSV exported successfully!\nPoints generated: {len(x_export)}")
        except Exception as exc:
            QMessageBox.critical(self.ui, "Export Error", f"Failed to save CSV: {exc}")

    @Slot()
    def exit_app(self):
        """Trigger window close on self.ui."""
        self.ui.close()

    def on_ui_close_event(self, event):
        """Confirm with user before closing fitting window."""
        reply = QMessageBox.question(
            self.ui,
            "Confirm Exit",
            "Are you sure you want to exit the fitting tool?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            event.accept()
            QApplication.quit()
        else:
            event.ignore()


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    app = QApplication(sys.argv)
    window = PolarizationFitApp()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
