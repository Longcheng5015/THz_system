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
from scipy.optimize import curve_fit

# Path injection for inst_libs and func_cores
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
if str(parent_dir / "inst_libs") not in sys.path:
    sys.path.append(str(parent_dir / "inst_libs"))
if str(parent_dir / "func_cores") not in sys.path:
    sys.path.append(str(parent_dir / "func_cores"))

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
                df = pd.read_csv(filepath)
                for col in df.columns:
                    clean_col = str(col).strip()
                    parsed[clean_col] = df[col].to_numpy()
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
            self.ui.lbl_calc_in1.setText("Stage 1 Target (°):")
            self.ui.lbl_calc_in2.setText("Stage 2 Fixed (°):")
        else:
            # Polarization mode fitting
            plot_item.setLabel("bottom", "Stage 2 Angle (°)", color="black")
            plot_item.setLabel("left", "Required Stage 1 Step (°)", color="black")
            self.ui.lbl_calc_in1.setText("Stage 2 Target Angle (°):")
            self.ui.lbl_calc_in2.setText("Stage 2 Step Change (°):")

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
                p0_init = [np.min(y_data), np.max(y_data) - np.min(y_data), 0.0]
                popt, _ = curve_fit(malus_model, x_data, y_data, p0=p0_init, maxfev=10000)
                y_fit = malus_model(x_data, *popt)

                # Formula text
                formula_str = f"P(θ1) = P0 + A * cos²(2 * (θ1 - θ0))\n" \
                              f"  P0      = {popt[0]:.6f} mW\n" \
                              f"  A       = {popt[1]:.6f} mW\n" \
                              f"  θ0      = {popt[2]:.4f} °"

                # Dense evaluation for smooth plot
                x_dense = np.linspace(np.min(x_data), np.max(x_data), 500)
                y_dense = malus_model(x_dense, *popt)
                fit_func = lambda theta1, theta2=0.0: malus_model(theta1, *popt)

            elif formula_idx == 1:
                # Sine Wave Fit
                p0_init = [np.std(y_data) * np.sqrt(2), 2 * np.pi / (np.max(x_data) - np.min(x_data) + 1e-5), 0.0, np.mean(y_data)]
                popt, _ = curve_fit(sine_model, x_data, y_data, p0=p0_init, maxfev=10000)
                y_fit = sine_model(x_data, *popt)

                formula_str = f"y(x) = A * sin(w * x + φ) + C\n" \
                              f"  A = {popt[0]:.6f}\n" \
                              f"  w = {popt[1]:.6f}\n" \
                              f"  φ = {popt[2]:.6f} rad\n" \
                              f"  C = {popt[3]:.6f}"

                x_dense = np.linspace(np.min(x_data), np.max(x_data), 500)
                y_dense = sine_model(x_dense, *popt)
                fit_func = lambda x, x2=0.0: sine_model(x, *popt)

            elif formula_idx == 2:
                # Linear Fit
                popt, _ = curve_fit(linear_model, x_data, y_data)
                y_fit = linear_model(x_data, *popt)

                formula_str = f"y(x) = a * x + b\n" \
                              f"  a (slope)     = {popt[0]:.6f}\n" \
                              f"  b (intercept) = {popt[1]:.6f}"

                x_dense = np.linspace(np.min(x_data), np.max(x_data), 500)
                y_dense = linear_model(x_dense, *popt)
                fit_func = lambda x, x2=0.0: linear_model(x, *popt)

            else:
                # Polynomial Deg 2 Fit
                popt, _ = curve_fit(poly2_model, x_data, y_data)
                y_fit = poly2_model(x_data, *popt)

                formula_str = f"y(x) = a * x² + b * x + c\n" \
                              f"  a = {popt[0]:.6e}\n" \
                              f"  b = {popt[1]:.6f}\n" \
                              f"  c = {popt[2]:.6f}"

                x_dense = np.linspace(np.min(x_data), np.max(x_data), 500)
                y_dense = poly2_model(x_dense, *popt)
                fit_func = lambda x, x2=0.0: poly2_model(x, *popt)

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
        """Use fitted formula parameters to predict output for target input angles."""
        if not hasattr(self, "fitted_func") or self.fitted_func is None:
            QMessageBox.warning(self.ui, "Warning", "Please run curve fitting first before calculating predictions.")
            return

        mode_idx = self.ui.combo_fit_mode.currentIndex()
        val1 = self.ui.spin_calc_in1.value()
        val2 = self.ui.spin_calc_in2.value()

        try:
            pred_val = self.fitted_func(val1, val2)
            if mode_idx == 0:
                # Power prediction
                result_str = f"Predicted Power = {pred_val:.4f} mW"
                self.ui.lbl_calc_result.setText(f"Prediction Result: {pred_val:.4f} mW")
            else:
                # Stage 1 relative step prediction
                result_str = f"Required Stage 1 Angle/Step = {pred_val:.2f} °"
                self.ui.lbl_calc_result.setText(f"Prediction Result: {pred_val:.2f} °")

            self.log(f"Calculator Prediction -> Input 1: {val1}°, Input 2: {val2}° ==> {result_str}")
        except Exception as exc:
            self.log(f"Calculator error: {exc}")
            QMessageBox.critical(self.ui, "Calculator Error", f"Calculation failed: {exc}")

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
