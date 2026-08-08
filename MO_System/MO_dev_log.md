# MO System Development Change Log

This document records the overall development and debugging history for the MO_System project, including version updates, bug fixes, and major functional changes.

## Version history

### v1.8
- Date: 2026-08-08
- Main change: Initialized v1.8 version copies (`MO_system_iTC_v1.8.py` and `MO_system_iTC_v18.ui`) from previous v1.7.
- Details:
  - Duplicated the main executable script and Qt UI layout file to establish the v1.8 baseline.
  - Linked `MO_system_iTC_v1.8.py` to load `MO_system_iTC_v18.ui`.
  - Removed the redundant `get_TDS_peak_pos` logic for `1D_THz` mode. Since the MO system (THz pump, Optical probe) uses Stage2 (PM500) to map out the entire THz waveform over the delay time, the fixed-point peak tracking logic inherited from OPTP is unnecessary and would only waste testing time.
  *(Note: This logic deletion was manually reverted by the user shortly after, in order to preserve the function for potential future OPTP integration testing. The v1.8 file was reverted to its pre-deletion state.)*

### v1.9
- Date: 2026-08-08
- Main change: Patched multiple stability and hardware control bugs inherited from OPTP v1.3-v1.7.
- Details:
  - Fixed MercuryiTC connection exception catching (v1.3 bug): Now safely handles generalized exceptions during connection, calls `.close()`, and properly resets tracking variables (`self.mercuryiTC`, `uid_HTR`, `uid_TEMP`) so subsequent connections don't hang.
  - Fixed QThread lifecycle leak in `iTC_goto_targetT()` (v1.4 bug): Prevents blind overwriting of the temperature stabilization thread by gracefully `.quit()` and `.wait()`ing on any active instance before creating a new one.
  - Resolved instrument shutdown race condition (v1.6 bug): `closeInstruments()` now actively checks for and waits on the temperature stabilization thread to finish before closing the MercuryiTC port, preventing background polling crashes.
  - Patched Stage1 BBD202 (LinearStage) dead-lock vulnerability (v1.7 bug): Changed `connectInstruments()` to use a temporary stage variable during initial homing. If an exception occurs, the temporary handle is safely closed, preventing the COM port from becoming permanently locked.

### v2.0
- Date: 2026-08-08
- Main change: Upgraded polarization calibration file parser to support `.csv` format.
- Details:
  - Rewrote `import_calibration_file()` to safely read standard comma-separated `.csv` files natively using Python's `csv` module.
  - Implemented dynamic handling for empty trailing columns (e.g., missing Stage3_deg) by replacing them with `0.0` to prevent `ValueError` parsing crashes.
  - Preserved fallback logic to read legacy whitespace-separated `.txt` calibration files for backwards compatibility.
