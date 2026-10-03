# THz System Control & Data Acquisition GUI

Windows laboratory control software for terahertz spectroscopy, optical pump–THz probe measurements, magneto-optical measurements, and spatial imaging. Four PySide6 applications share instrument drivers and scan utilities, with interfaces designed in Qt Designer and live plots built with pyqtgraph.

## Latest versions

Current source versions as of **2026-10-04**. Each application has its own Python entry point and matching UI file.

| System | Latest version | Python entry point | Qt Designer UI |
| --- | --- | --- | --- |
| OPTP | **v3.6** | [OPTP_system_iTC_v3.6.py](OPTP_System/OPTP_system_iTC_v3.6.py) | [OPTP_iTC_main_v3.6.ui](OPTP_System/OPTP_iTC_main_v3.6.ui) |
| Magneto-optical (MO) | **v2.6** | [MO_system_iTC_v2.6.py](MO_System/MO_system_iTC_v2.6.py) | [MO_system_iTC_v2.6.ui](MO_System/MO_system_iTC_v2.6.ui) |
| OPTP Imaging | **v1.7** | [OPTP_iTC_image_v1.7.py](OPTP_image_System/OPTP_iTC_image_v1.7.py) | [OPTP_iTC_image_v1.7.ui](OPTP_image_System/OPTP_iTC_image_v1.7.ui) |
| THz Emission | **v1.5** | [THz_emission_system_iTC_v1.5.py](THz_emission_system/THz_emission_system_iTC_v1.5.py) | [THz_emission_system_iTC_v1.5.ui](THz_emission_system/THz_emission_system_iTC_v1.5.ui) |

## Shared capabilities

- **Instrument configuration:** editable VISA addresses, controller serial numbers and channels in the Inst. Config. tab; device discovery and connection settings saved separately for each system.
- **Lock-in settings:** X-channel Auto Zero and an editable decimal Phase field for each SR830. Enter a number; the degree symbol is added automatically. Phase is read on connection and after edits. The controls have multiline help and are disabled during scans.
- **Acquisition:** SR830 X/Y readings, linear and rotary stage scans, repeat measurements, temperature sequences, and live time-domain/frequency-domain plots where supported by the selected mode.
- **Temperature control:** Oxford Mercury iTC setpoints, stability monitoring, heater/PID controls and temperature display.
- **Beam control:** manual Block/Pass and AutoBlock through a Thorlabs flip mount, with a selectable physical Pass channel. Temperature/soak timing follows each system's scan logic.
- **Pump power:** PM100D live display in mW, wavelength and range settings, Zero, and optional Record. With Record and AutoBlock enabled, the program waits for the meter to settle and averages readings while the beam is blocked, just before passing it at each temperature point, or once for a scan without temperature points. Results are saved with the measurement data.
- **Data and logs:** HDF5 measurement files and a daily `ScanLog_YYYY-MM-DD.txt` containing scan conditions and progress events.

## System features

### OPTP — v3.6

Optical pump–THz probe spectroscopy with Stage1 as the THz detection delay and Stage2 as the pump delay.

- **Scan modes:** `THz_Scan` for THz waveforms, `1D_THz` for pump-delay traces at a fixed THz detection position, `2D_THz` for a full THz waveform at each pump delay, and `POL_2D` for polarization scans.
- **Temperature drift compensation:** a two-round peak search around the configured `TDS Ppos` updates the Stage1 reference and compensates Stage2 according to its Forward/Reverse direction.
- **Repeat peak search:** `Re-peak: ON` is the default. With this toggle enabled, a search runs before Stage2 repeats 2, 3, etc. when **`1D_THz`, temperature scanning, Drift comp., and Stage2 Repeat > 1** are all enabled. Each search updates subsequent scan positions. It does not repeat the temperature wait, sample soak or beam-settle wait. `THz_Scan` does not trigger this repeat feature.
- **Beam-heating wait:** Peak search settings offer `Pass → Soak` and `Soak → Pass`. With AutoBlock and temperature scanning enabled, `Beam settle (min)` adds a full extra wait after both sample soak and beam pass, before peak search or acquisition. Default: **5 minutes**; 0 skips this extra wait.
- **Lock-in controls:** each SR830 has **Auto Zero** for its X-channel auto offset, plus an editable decimal Phase field. Connecting reads the instrument's current phase; committing an edit writes it and reads it back. Auto Zero refreshes the actual X reading. Both controls are disabled during a scan; front-panel versus X-readback behavior after Auto Zero remains a hardware verification item.
- **Scan handling:** scan plans are validated before startup and compensated travel is checked after searching. Movement/Lock-in communication errors and temperature-start failures abort through file cleanup. Unacquired samples are NaN. Lock-in Realtime buttons switch off for scanning and remain off afterwards; scan charts still update, and active-instrument checkboxes retain their settings.

### MO — v2.6

Magneto-optical measurements using a Thorlabs linear Stage1 and Newport PM500 Stage2, with polarization control and temperature sequences.

- **Scan modes:** `1D_POL`, `POL_2D`, `THz_Scan`, `1D_THz` and `2D_THz`.
- Independent or coupled rotary motion, including calibration-file-based polarization settings.
- Temperature stabilization followed by a configurable sample-soak wait. Routine MO scans retain their existing behavior; this version adds no new peak-search workflow.
- Integrated PM100D display, configuration, Zero and pump-power Record alongside AutoBlock and ScanLog. Acquisition supports operation without Lock-in 2; disconnected Lock-in channels retain zero placeholders in this system's data.

### OPTP Imaging — v1.7

Spatial THz/OPTP acquisition with an XY raster and a live image display.

- **Scan modes:** `THz_Scan`, `1D_THz`, `POL_2D`, `2D_THz` and `2D_IMG`.
- In the imaging setup, X/Y linear stages use the **Rotary1/Rotary2** control slots. Independent mode forms an XY grid with X slow and Y fast; coupled mode follows paired positions. `THz_Scan` records a THz waveform at each grid point, while `1D_THz` records a pump-delay trace.
- **Live image:** select Lock-in 1/2 X, Y or R, and display Peak-Peak, Max, Min, Mean or a chosen trace point. Changing these selectors redraws acquired pixels without another measurement.
- PM100D controls, pump-power Record, AutoBlock, temperature sequences and ScanLog are integrated. Automatic temperature peak search is currently disabled in this system.

### THz Emission — v1.5

THz emission measurements using a **PI N-565.360 / E-861** Stage1 and a Thorlabs Stage2.

- **Scan modes:** `THz_Scan`, `2D_THz` and `THz_pol`.
- Stage1 arrival is checked before Lock-in acquisition. For waveform scans, Stage1 is the innermost sweep, acquiring a complete trace at each Stage2 position.
- Polarization scans, independent/coupled rotary motion, temperature stabilization and sample-soak waits.
- PM100D display and configuration, Zero, pump-power Record, AutoBlock and daily ScanLog.

## Environment and startup

The instrument integrations target **64-bit Windows**. The lab environment documented in the development logs is the `opto_test` Conda environment with Python 3.13.13.

| Component | Dependency |
| --- | --- |
| GUI and plots | `PySide6`, `pyqtgraph` |
| Numerical processing and files | `numpy`, `scipy`, `h5py` |
| VISA instruments | `pyvisa` and a working VISA runtime, such as NI-VISA |
| Thorlabs motion controllers | `pythonnet` and Thorlabs Kinesis; drivers currently expect `C:\Program Files\Thorlabs\Kinesis` |
| PI Stage1 in THz Emission | `pipython` and the PI GCS driver/DLL |
| Auxiliary polarization fitting tool | `pandas`, in addition to the common numerical/GUI packages |

Python packages for the four applications can be installed in the selected environment with:

```powershell
python -m pip install PySide6 pyqtgraph numpy scipy h5py pyvisa pythonnet pipython
```

Vendor runtimes and USB/GPIB drivers are separate installations. The PM100D driver in this repository uses VISA/SCPI; the meter must be available through its VISA driver. Keep the system folders, `inst_libs/` and `func_cores/` together when deploying the applications.

From the repository root, run the command for the desired system:

**OPTP**

```powershell
python OPTP_System/OPTP_system_iTC_v3.6.py
```

**MO**

```powershell
python MO_System/MO_system_iTC_v2.6.py
```

**OPTP Imaging** — run from its own folder because this entry point loads its UI relative to the working directory.

```powershell
Push-Location OPTP_image_System
python OPTP_iTC_image_v1.7.py
Pop-Location
```

**THz Emission**

```powershell
python THz_emission_system/THz_emission_system_iTC_v1.5.py
```

Before a measurement, set the addresses/channels for the actual setup in **Inst. Config.**, select the required instruments, connect them, and configure the scan mode, positions, repeats and save directory. For temperature-dependent OPTP repeat tracking, use **`1D_THz`** and the conditions listed above.

## Measurement files

The four measurement applications save **`.h5` HDF5 files**, readable with Python `h5py` or MATLAB `h5read`/`h5info`. Lock-in datasets are `lockin1_X`, `lockin1_Y`, `lockin2_X` and `lockin2_Y`, accompanied by scan positions, step arrays and repetition settings. Successfully recorded pump power is stored in `pump_power_*` datasets; power values use watts in the file.

| System | Default data root |
| --- | --- |
| OPTP | `OPTP_Data/` |
| MO | `TPOP_Data/` |
| OPTP Imaging | `TPOP_Data/` |
| THz Emission | `THz_emission_Data/` |

The save directory can be selected in the GUI. ScanLog is appended in the selected data folder.

For OPTP scans with repeat peak search enabled, **`repeat_scan_positions_mm`** stores each sweep's commanded Stage1 position, Stage2 start and TDS peak. Use this dataset when reconstructing absolute coordinates of later repeats: the original `iPos1`/`iPos2` scalars describe the first sweep. Dataset attributes document the axes and columns.

## Auxiliary tools and shared code

- [Polarization calibration](Polarization_cali/Polarization_cali_v1.0.py): automated angle/power calibration and `.mat`, `.csv`, `.h5` export.
- [Polarization fitting](Polarization_cali/Polarization_fit_v1.0.py): curve fitting, raw-data interpolation, angle/power prediction and dense calibration-table export.
- [inst_libs/](inst_libs/): shared SR830, Mercury iTC, Thorlabs, Newport and PI drivers, device discovery and custom widgets.
- [func_cores/](func_cores/): scan planning, FFT/data calculations, calibration parsing and reusable HDF5 storage helpers. Applications retain their own hardware sequencing.
- [OPTP_System/tests/](OPTP_System/tests/): simulated-instrument regression checks for scan behavior and UI controls.
- [UI/](UI/): additional UI resources. Local lab copies may also contain `ui_users/` resources and instrument documentation in `manuals/`.

## Development and verification

Edit the matching `.ui` in Qt Designer and keep it alongside its Python entry point. Current system details are recorded in the corresponding development logs:

| System | Development log |
| --- | --- |
| OPTP | [OPTP_dev_log.md](OPTP_System/OPTP_dev_log.md) |
| MO | [MO_dev_log.md](MO_System/MO_dev_log.md) |
| OPTP Imaging | [OPTP_image_dev_log.md](OPTP_image_System/OPTP_image_dev_log.md) |
| THz Emission | [THz_emission_dev_log.md](THz_emission_system/THz_emission_dev_log.md) |

The following checks target OPTP v3.6 using simulated instruments and temporary files:

```powershell
python OPTP_System/tests/test_lockin_controls.py
python OPTP_System/tests/test_scan_failures.py 3.6
python OPTP_System/tests/test_drift_comp.py 3.6
```

The Lock-in control checks also accept `mo`, `img` or `thz` to select the corresponding latest system, for example `python OPTP_System/tests/test_lockin_controls.py mo`. Add `--native-preview` to check the Windows layout.

They cover Lock-in Auto Zero/Phase, scan failure cleanup, temperature drift compensation, beam timing and repeat peak search. Instrument libraries still require the environment described above. Hardware verification status and pending work are tracked in [OPTP_handoff.md](OPTP_System/OPTP_handoff.md).
