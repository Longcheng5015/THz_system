# Polarization Calibration Development Log

This document records the development and debugging history for the `Polarization_cali` sub-system.

### v1.0
- **Main Change**: Initial development of the polarization fitting tool (`Polarization_fit_v1.0.py`).
- **Details**:
  - Implemented curve fitting models (Malus, Sine, Linear, Poly2) for polarization calibration data.

### v1.0 (Hotfix)
- **Date**: 2026-08-08
- **Main Change**: Fixed CSV file header parsing logic for data importing.
- **Details**: 
  - Originally, the parser used a standalone `pandas.read_csv` function which failed on standard outputs like `Stage1_deg`. Although a local fuzzy mapping was temporarily applied, it was ultimately refactored.
  - **Refactoring**: Completely replaced the standalone pandas parsing loop with the newly unified `ScanDataCore.parse_calibration_file()` from the core functional module. 
  - This ensures that `Polarization_fit_v1.0.py` shares exactly the same `.csv` reading and sanitization engine as the main MO and OPTP systems, guaranteeing future compatibility without redundant code.

### v1.0 (Algorithm Update)
- **Date**: 2026-08-08
- **Main Change**: Improved the initial parameter estimation (P0_guess) for non-linear curve fitting to eliminate large fitting deviations.
- **Details**:
  - **Malus Law Fit**: Previously, the initial phase shift (`theta0`) was hardcoded to `0.0°`. This caused the optimizer to fall into a local minimum if the peak power angle was far from 0. Now dynamically calculates `theta0_guess = x_data[np.argmax(y_data)]` and applies parameter bounds to guarantee robust convergence.
  - **Sine Wave Fit**: Previously, the frequency `w` was guessed by assuming exactly 1 full period existed across the X-axis range. Upgraded to dynamically evaluate zero-crossings around the mean `y_data` to mathematically estimate the true period and frequency, eliminating extreme phase/frequency mismatches during curve fitting.

### v1.0 (Feature Update)
- **Date**: 2026-08-09
- **Main Change**: Added **Raw Data Interpolation Mode** and **Dense CSV Export** features to the Fit Tool.
- **Details**:
  - The UI now features "Raw Data Interpolation (Linear)" and "Raw Data Interpolation (Cubic Spline)" options in the formula list, bypassing mathematical curve fitting when data is extremely noisy or non-standard.
  - The UI Calculator seamlessly supports reverse calculating angles based on interpolated raw data.
  - Added a dynamic `Export Dense CSV` button which prompts for a step size (e.g. `0.1°`) and generates a mathematically interpolated high-density calibration table for export and immediate usage in OPTP.

### v1.0 (Feature Update)
- **Date**: 2026-08-09
- **Main Change**: Upgraded the **Power Calibration Mode** to support `rot1` and `rot2` coupled movement.
- **Details**: 
  - Previously, `Power mode` hardcoded `Stage 2` and `Stage 3` to their starting positions and only iterated through `Stage 1` points.
  - Now, the scanning logic zips `Stage 1` and `Stage 2` sequence arrays to allow them to move in parallel, corresponding 1-to-1 pairs. If they have different sequence lengths, it intelligently pads the shorter sequence with its final value to match the maximum iterations.
