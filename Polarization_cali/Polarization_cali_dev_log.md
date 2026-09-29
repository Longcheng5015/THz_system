# Polarization Calibration Development Change Log

This document records the overall development and debugging history for the Polarization & Power Calibration project (`Polarization_cali`), including version updates, bug fixes, and functional changes.

---

## Version History

### v1.0
- **Date**: 2026-08-06
- **Main Change**: Initial release of the Polarization & Power Calibration UI program (`Polarization_cali_v1.0.py` and `Polarization_cali_v1.0.ui`).
- **Details**:
  - Developed a standalone PySide6 GUI for automated optical polarization and power calibration.
  - Connected instruments: 3 x Thorlabs Rotary Stages (Stage 1: 1/2 HWP, Stage 2: Polarizer, Stage 3: Aux) and 1 x Thorlabs PM100D Power Meter.
  - Implemented auto-discovery for VISA resources (PM100D) and populated default OPTP stage serial numbers (`"27004364"`, `"27255894"`).
  - Designed the power stability detection function (`check_power_stability`), requiring 3 consecutive wait intervals (4 consecutive power readings) to have variation $\le \text{Tolerance}$ before declaring stability.
  - Added two calibration modes:
    1. **`power` Mode**: Fixed Stage 2 angle, scans Stage 1 angles, waits for power stability, and records Stage 1, 2, 3 positions and power.
    2. **`Polar` Mode**: Target power specified by user. For each Stage 1 angle, searches Stage 2 to achieve target power within tolerance.
  - Integrated Stage 2 polar search algorithms: **Sequential Step (方案A, default)** and **Binary Search (方案B)**.
  - Handled disabled/unchecked stages by recording `NaN` in MAT/HDF5 data files and leaving entries blank in CSV files.
  - Added manual debugging controls for each stage (Move To absolute angle and Step + / Step - relative moves).
  - Integrated real-time data plotting using `pyqtgraph.PlotWidget`.
  - Exported calibration data simultaneously into `.mat`, `.csv`, and `.h5` (HDF5 via `h5py`) files.
  - Preserved strict core reusability: reused existing `func_cores` and `inst_libs` without modifying any shared codebase.

### v1.0.1
- **Date**: 2026-08-06
- **Main Change**: Fixed LedIndicator widget attribute error during instrument connection.
- **Details**:
  - Corrected `led.setChecked()` call to `led.status = True / False` to match `MyWidget.py` custom `LedIndicator` property setter.

### v1.0.2
- **Date**: 2026-08-06
- **Main Change**: Reorganized Stage controls into 3 side-by-side GroupBoxes and ensured Step+ / Step- buttons.
- **Details**:
  - Arranged Stage 1, Stage 2, and Stage 3 into three distinct `QGroupBox` panels aligned horizontally from left to right (`grp_stage1`, `grp_stage2`, `grp_stage3`).
  - Positioned individual `Step +` (`btn_stageX_step_plus`) and `Step -` (`btn_stageX_step_minus`) buttons alongside `Move To` controls within each Stage panel.

### v1.0.3
- **Date**: 2026-08-06
- **Main Change**: Replaced Stop angle setting with Step NO. (number of steps) for each Rotary Stage.
- **Details**:
  - Changed stage parameter inputs from `[Start, Step, Stop]` to `[Start (°), Step (°), Step NO.]` in UI (`spin_stageX_no` QSpinBox).
  - Updated sequence generator `build_seq` to generate angle array as `[start + i * step for i in range(no)]`, perfectly aligning with OPTP `ScanPlanner` logic.

### v1.0.4
- **Date**: 2026-08-06
- **Main Change**: Reordered UI layout: moved Calibration Settings below the 3 Stage boxes and above the real-time PlotWidget chart.
- **Details**:
  - Adjusted vertical component hierarchy in `Polarization_cali_v1.0.ui` to place `grp_config` below `layout_three_stages` and directly above execution controls and `powerChart`.

### v1.0.5
- **Date**: 2026-08-06
- **Main Change**: Renamed Calibration Mode options to `Power` and `Polarization`.
- **Details**:
  - Updated UI dropdown (`combo_scan_mode`) options to `Power` and `Polarization`.
  - Updated tooltips and worker thread branch detection to support `Power` and `Polarization` mode names.

### v1.0.6
- **Date**: 2026-08-06
- **Main Change**: Swapped relative step buttons position: placed `Step -` on the left and `Step +` on the right.
- **Details**:
  - Adjusted button layout in Stage 1, Stage 2, and Stage 3 panels so `btn_stageX_step_minus` (`Step -`) is placed on column 3 and `btn_stageX_step_plus` (`Step +`) is placed on column 4.

### v1.0.7
- **Date**: 2026-08-06
- **Main Change**: Added PM100D CheckBox, unified device connection buttons, and removed Scan Devices button matching OPTP v1.7.
- **Details**:
  - Added CheckBox for PM100D (`chk_pm100d_enable`, default: checked) so users can enable/disable power meter connection and readings.
  - Replaced individual device connect buttons with unified **`Connect Enabled Devices`** (`btn_connect_all`) and **`Disconnect All`** (`btn_disconnect_all`) buttons.
  - Automatically iterates and connects all checked instruments (PM100D, Stage 1, Stage 2, Stage 3) in order, homing each stage upon connection.
  - Removed the `Scan Devices` button as requested.

### v1.0.8
- **Date**: 2026-08-06
- **Main Change**: Removed leftover `scan_connected_devices` call in `__init__`.
- **Details**:
  - Removed outdated `self.scan_connected_devices()` method call from `PolarizationCaliApp.__init__()`, resolving `AttributeError` during startup.

### v1.0.9
- **Date**: 2026-08-06
- **Main Change**: Implemented OPTP v1.7 guarded temporary instance connection & automatic cleanup flow.
- **Details**:
  - Implemented temporary local instances (`stg_temp` / `pm_temp`) inside `connect_all_devices()`.
  - If homing or enabling fails, the exception block immediately executes `stg_temp.close()`, preventing locked Kinesis handles/DLL sessions and allowing clean retries.

### v1.0.10
- **Date**: 2026-08-06
- **Main Change**: Added Exit button and implemented default disconnect-before-close logic.
- **Details**:
  - Added `Exit Program` button (`btn_exit`) in the top connection panel of `Polarization_cali_v1.0.ui`.
  - Implemented `exit_app()` slot and overridden `closeEvent()` window close handler to automatically stop calibration scans and execute `disconnect_all_devices()` before exiting the application window.

### v1.0.11
- **Date**: 2026-08-06
- **Main Change**: Added exit confirmation dialog, active device detection before disconnect, and fixed event loop bug.
- **Details**:
  - Added `QMessageBox.question` confirmation dialog on exit ("Are you sure you want to exit the application?").
  - Fixed infinite recursion loop between `exit_app()` and `closeEvent()`.
  - Added `has_connected_devices` check in `disconnect_all_devices()` and `closeEvent()` so disconnect cleanup only runs if at least one instrument is actually connected.

### v1.0.12
- **Date**: 2026-08-06
- **Main Change**: Fixed PySide6 QUiLoader window close target (`self.ui.closeEvent`).
- **Details**:
  - Bound `self.ui.closeEvent` directly to `self.on_ui_close_event`.
  - Updated `exit_app()` to trigger `self.ui.close()`, bringing up the confirmation box (`QMessageBox.question`) and calling `QApplication.quit()` cleanly when confirmed.

### v1.0.13
- **Date**: 2026-08-06
- **Main Change**: Added initial system welcome and readiness log messages upon startup.
- **Details**:
  - Automatically emits initialization log messages into `txt_log` as soon as the main window opens so users immediately see system readiness status.

### v1.0.14
- **Date**: 2026-08-06
- **Main Change**: Converted all code comments, tooltips, UI text options, and log messages to English.
- **Details**:
  - Translated all remaining Chinese comments, algorithm option labels, tooltips, and log text strings to pure English across both `Polarization_cali_v1.0.py` and `Polarization_cali_v1.0.ui`.

### v1.1.0
- **Date**: 2026-08-06
- **Main Change**: Created standalone Data Fitting & Analysis application (`Polarization_fit_v1.0.py` and `Polarization_fit_v1.0.ui`).
- **Details**:
  - Implemented file parsers for `.mat`, `.csv`, and `.h5` files exported from calibration scans.
  - Implemented Power Mode fitting (Malus Law $\cos^2$, Sine Wave, Polynomial, Linear models) to convert Stage 1/2 angles directly into predicted optical power.
  - Implemented Polarization Mode fitting to calculate required Stage 1 relative step ($\Delta \theta_1$) for constant optical power given any Stage 2 angle change ($\Delta \theta_2$).
  - Built interactive prediction calculator and real-time `pyqtgraph` scatter + smooth fitted curve display.
  - Formatted LaTeX/mathematical equations, $R^2$ scores, and RMSE parameters in the text output box.

### v1.1.1
- **Date**: 2026-08-06
- **Main Change**: Removed external `pandas` dependency in favor of Python standard library `csv` module.
- **Details**:
  - `pandas` is a third-party Python library for data manipulation/CSV handling.
  - Replaced `pd.read_csv()` with Python's built-in `csv.DictReader`, so `Polarization_fit_v1.0.py` zero-depends on external `pandas` package and runs out of the box in standard python environments.

### v1.1.2
- **Date**: 2026-08-06
- **Main Change**: Installed `pandas` in active conda environment (`opto_test`) and cleared pip cache.
- **Details**:
  - Installed `pandas` into `opto_test` environment via `pip install pandas`.
  - Executed `pip cache purge` to remove cached wheel files (freed 365.3 MB of cache).
  - Restored `pandas` DataFrame parsing for data import in `Polarization_fit_v1.0.py`.

### v1.1.3
- **Date**: 2026-08-06
- **Main Change**: Registered `pg.PlotWidget` custom widget with `uiLoader` in `Polarization_fit_v1.0.py` and executed automated smoke tests.
- **Details**:
  - Registered `pg.PlotWidget` with PySide6 `QUiLoader` via `uiLoader.registerCustomWidget(pg.PlotWidget)`.
  - Resolved `AttributeError: 'PySide6.QtWidgets.QWidget' object has no attribute 'setBackground'` when rendering the main chart.
  - Passed automated smoke testing for UI instantiation, custom widget registration, fitting math, and clean exit.

### v1.1.4
- **Date**: 2026-09-29
- **Main Change**: `inst_libs/thorlabs_PM100D.py` now talks to the PM100D over pyvisa (SCPI) instead of the Thorlabs TLPM DLL. The meter (P0020951) was switched to its NI-VISA driver with the Thorlabs Power Meter Driver Switcher; on the TLPM driver pyvisa does not see it, and on the NI-VISA driver the old TLPM code no longer finds it.
- **Details**:
  - Transport: `open()` / `close()` / `write()` / `query()` use pyvisa like `stanford_SR830` (read/write termination `
`, `timeout_ms`, `query_delay_s`; `close()` leaves the shared ResourceManager open). `query()` honours `retry_count` / `retry_delay_s`. `idn()`, `set/get_wavelength_nm()`, `measure_power()` are now SCPI (`*IDN?`, `SENS:CORR:WAV`, `MEAS:POW?`). All the SCPI methods that used to raise ("Raw SCPI ... not supported by the TLPM driver transport") now work.
  - `list_resources()` asks VISA for `USB?*::0x1313::0x8078::?*::INSTR` only (0.06 s; a full VISA scan of the serial/GPIB ports took 6-30 s on this PC). `list_resources_with_idn()` returns the real `*IDN?`.
  - No `viClear()` on open or before a retry: measured on this meter, the first query after a clear timed out 15/15 times (8/15 within a running session), which made the first connect take 12.5 s. A query that gets no reply recovers without a clear.
  - "Busy" is now detected with pyvisa's `error_resource_busy`; the old constant `-1073807343` was actually VI_ERROR_RSRC_NFOUND, so a wrong address was reported as "PM100D is busy".
  - SCPI headers corrected after the firmware (2.6.0) answered "Undefined header": line frequency `SYST:LFR`, zeroing `SENS:CORR:COLL:ZERO:INIT/ABOR/STAT/MAGN`, responses `SENS:CORR:POW:PDI:RESP`, `SENS:CORR:POW:THER:RESP`, `SENS:CORR:ENER:PYRO:RESP`, delta state `SENS:<mode>:REF:STAT`, photodiode low-pass `INP:PDI:FILT:LPAS:STAT`. Display brightness/contrast are 0..1 floats (were parsed as int and raised).
  - Interface used by `Polarization_cali_v1.0.py` is unchanged (constructor arguments, `open`, `idn`, `measure_power`, `close`). Its `query_delay_s=0.1` is now applied, so one power reading takes ~100 ms (the meter itself answers in ~3 ms).
  - `inst_libs/test_PM00D.py`: "not found" message now points at the VISA driver instead of TLPM.
  - Verified on the PM100D P0020951 with the S302C thermal sensor (opto_test env): connect flow 3x (0.15 s each), 96 calls each followed by `SYST:ERR?` with no error, set -> read back -> restore for unit, averaging, wavelength, auto range, range, attenuation, beam diameter, delta state, low-pass and brightness; settings left as found (W, 525 nm, avg 1, auto range, POW). Not supported by this sensor (instrument reports "Wrong sensor type"/"Illegal parameter"): energy range, energy, energy density, temperature. `zero_initiate()` / `set_line_frequency()` not executed (zeroing needs the sensor covered).

---

## Summary
The primary objective of the `Polarization_cali` program is to provide precise, automated polarization angle and power calibration for OPTP/MO experimental optical setups.

## Notes
- Future modifications, bug fixes, and feature additions should be appended to this log with date, version number, and detailed change descriptions.
