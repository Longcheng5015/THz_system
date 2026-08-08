# OPTP Development Change Log

This document records the overall development and debugging history for the OPTP project, including version updates, bug fixes, and major functional changes.

## Version history

### v1.3
- Date: 2026-07-29
- Main change: fixed the MercuryiTC connection issue.
- Details:
  - broadened the exception handling to catch VisaIOError,
  - reset the MercuryiTC instance on connection failure,
  - refreshed device UIDs when the instrument was already connected but the UIDs were missing,
  - reset UIDs correctly during close.

### v1.4
- Date: 2026-07-30
- Main change: resolved the QThread lifecycle issue during temperature stabilization and scan execution.
- Details:
  - ensured the temperature stabilization thread is properly waited on before being overwritten,
  - added proper thread shutdown handling after scan execution.

### v1.5
- Date: 2026-08-04
- Main change: added temperature-aware Stage1 peak tracking for 1D_THz scans.
- Details:
  - added a local peak-tracking calibration step before the formal 1D_THz scan,
  - used the current Stage1 position as the scan center and scanned around it locally,
  - sampled each point three times and averaged the values to improve robustness,
  - updated the UI with the calibrated peak position,
  - made the formal scan proceed only after successful peak tracking,
  - stopped the scan sequence immediately when a stop request or failed calibration occurred.

### v1.6
- Date: 2026-08-04
- Main change: started modularizing the scan workflow while preserving existing shared core and instrument-library APIs.
- Details:
  - created independent v1.6 Python and UI copies,
  - added `func_cores/scan_data_core.py` for scan-step conversion, peak-tracking position generation, and repeated-sample peak analysis,
  - added `func_cores/scan_storage_core.py` for the standard Lock-in HDF5 dataset creation and single-point writes,
  - kept thread lifecycle, Qt signals, UI access, and hardware movement in the v1.6 main controller,
  - changed v1.6 to reuse the existing shared FFT implementation from `scan_func_core.py`, removing the duplicated main-program FFT method,
  - did not modify or remove functions in existing `func_cores` or `inst_libs` files,
  - corrected the default measurement-data root from `TPOP_Data` to `OPTP_Data`, while preserving manual save-path selection,
  - fixed the iTC shutdown race: `closeInstruments()` now requests and waits for an active stabilization thread before closing and clearing the MercuryiTC instance,
### v1.7
- Date: 2026-08-06
- Main change: Added guarded stage enable flow and safer stage object assignment for BBD202 connections.
- Details:
  - Used guarded temporary stage instances during initial connection and homing.
  - Ensured hardware handle `.close()` is called on failure to prevent locked sessions.

### v1.8
- Date: 2026-08-06
- Main change: Initialized v1.8 version copies (`OPTP_system_iTC_v1.8.py` and `OPTP_iTC_main_v1.8.ui`) from v1.7.
- Details:
  - Duplicated main executable script and Qt UI layout file for v1.8 development.
  - Linked `OPTP_system_iTC_v1.8.py` to load `OPTP_iTC_main_v1.8.ui`.

### v1.9
- Date: 2026-08-08
- Main change: Fixed UI freezing issue caused by blocking I/O on the main thread when updating iTC parameters.
- Details:
  - Refactored `MercuryiTC_Updater` to inherit from `QThread` instead of using a `QTimer` on the main thread.
  - Implemented thread-safe UI updates using the `display_updated` Qt Signal.
  - Updated `closeInstruments()` to gracefully stop and wait for the `MercuryiTC_Updater` background thread before closing the instrument to prevent crashes on termination.

### v1.91
- Date: 2026-08-08
- Main change: Upgraded wait time multiplier input to support decimal values.
- Details:
  - Replaced `QSpinBox` with `QDoubleSpinBox` for `wait1multip` and `wait2multip` in the Qt UI file, allowing float multipliers (e.g., 1.2, 3.5).
  - Updated `apply_lockin_parameter` calculation to properly `round` the multiplied float result before converting to an integer millisecond wait time.

### v2.0
- Date: 2026-08-08
- Main change: Initialized v2.0 version copies (`OPTP_system_iTC_v2.0.py` and `OPTP_iTC_main_v2.0.ui`) from v1.91, and modified 1D THz peak tracking logic.
- Details:
  - Duplicated main executable script and Qt UI layout file for v2.0 development.
  - Linked `OPTP_system_iTC_v2.0.py` to load `OPTP_iTC_main_v2.0.ui`.
  - Moved the `get_TDS_peak_pos` logic inside the main `scan_iterator` loop and removed the `ScanT.isChecked()` dependency. The system will now automatically re-track and calibrate the THz peak at the start of *every* 1D THz sweep (e.g. for every polarization/pump power change or repeat cycle), preventing peak drift issues caused by optical path variations during the experiment.
  - Added a new HDF5 dataset `dynamic_THz_peak_pos` (specifically for `1D_THz` mode) to seamlessly record the tracked Stage1 peak position at each sweep. This ensures the precise zero-delay coordinate is logged for post-processing.

### v2.1
- Date: 2026-08-08
- Main change: Upgraded OPTP polarization calibration parser to natively support `.csv` file format.
- Details:
  - Duplicated OPTP v2.0 files to v2.1.
  - Rewrote `import_calibration_file()` to safely read standard comma-separated `.csv` files using Python's `csv` module, aligning with MO v2.0 logic.
  - Added robust fallback for missing/empty columns (e.g. `Stage3_deg`) to default to `0.0`, avoiding parsing `ValueError`.
  - Maintained backward compatibility for legacy `.txt` whitespace-separated calibration files.

## Summary
The overall objective of this debug/development branch is to make the OPTP scan workflow more stable under temperature variation and to improve reliability during real experimental runs.

## Notes
- This is the project-wide development record for the OPTP debugging workflow, not a v1.5-only log.
- Future changes should be added here with the corresponding version number and description.
