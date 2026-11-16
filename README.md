# THz System Control & Data Acquisition GUI

Windows laboratory control software for terahertz spectroscopy, optical pump–THz probe measurements, magneto-optical measurements, and spatial imaging. Four PySide6 applications share instrument drivers and scan utilities, with interfaces designed in Qt Designer and live plots built with pyqtgraph.

## Latest versions

Current source versions as of **2026-11-16**. Each application has its own Python entry point and matching UI file.

| System | Latest version | Python entry point | Qt Designer UI |
| --- | --- | --- | --- |
| OPTP | **v4.3** | [OPTP_system_iTC_v4.3.py](OPTP_System/OPTP_system_iTC_v4.3.py) | [OPTP_iTC_main_v4.3.ui](OPTP_System/OPTP_iTC_main_v4.3.ui) |
| Magneto-optical (MO) | **v2.8** | [MO_system_iTC_v2.8.py](MO_System/MO_system_iTC_v2.8.py) | [MO_system_iTC_v2.8.ui](MO_System/MO_system_iTC_v2.8.ui) |
| OPTP Imaging | **v1.9** | [OPTP_iTC_image_v1.9.py](OPTP_image_System/OPTP_iTC_image_v1.9.py) | [OPTP_iTC_image_v1.9.ui](OPTP_image_System/OPTP_iTC_image_v1.9.ui) |
| THz Emission | **v1.8** | [THz_emission_system_iTC_v1.8.py](THz_emission_system/THz_emission_system_iTC_v1.8.py) | [THz_emission_system_iTC_v1.8.ui](THz_emission_system/THz_emission_system_iTC_v1.8.ui) |

Older versions stay in each system folder (THz Emission v1.0-v1.61 in `THz_emission_system/old_version/`).

## Shared capabilities

- **Instrument configuration:** editable VISA addresses, controller serial numbers and channels in the Inst. Config. tab; connection settings saved separately for each system. **Scan devices** lists the VISA resources and Thorlabs Kinesis serials visible to the PC, plus the Mercury iTC Ethernet address (`TCPIP0::192.168.50.100::7020::SOCKET`, or a SOCKET address already entered) when its TCP port answers. VISA cannot list raw network sockets, so only these addresses are checked; no network range is scanned.
- **Lock-in settings:** X-channel Auto Zero and an editable decimal Phase field for each SR830. Enter a number; the degree symbol is added automatically. Connecting reads sensitivity, time constant and phase without writing defaults or changing acquisition Wait(ms) and multipliers. Failed readbacks show unknown settings; before connection, existing defaults remain. Phase is also read back after edits. The controls have multiline help and are disabled during scans.
- **Acquisition:** SR830 X/Y readings, linear and rotary stage scans, repeat measurements, temperature sequences, and live time-domain/frequency-domain plots where supported by the selected mode.
- **Coupled rotary scans:** pair the checked axes by point index, with equal point counts and individual starting angles/steps. Rot1 and Rot2 can scan together with Rot3 unchecked, regardless of Rot3's point count; unchecked axes receive no movement commands. Independent mode retains its Cartesian scan pattern. Calibration remains driven by Rot2.
- **Temperature control:** Oxford Mercury iTC setpoints, stability monitoring, heater/PID controls and temperature display, over USB/serial (for example `ASRL11::INSTR`) or Ethernet (`TCPIP0::<IP>::7020::SOCKET`). The iTC occasionally drops a newly opened Ethernet connection; the shared driver checks each new Ethernet session with `*IDN?` and reconnects automatically, up to three attempts.
- **Beam control:** manual Block/Pass and AutoBlock through a Thorlabs flip mount, with a selectable physical Pass channel. Temperature/soak timing follows each system's scan logic.
- **Pump power:** PM100D live display in mW, wavelength and range settings, Zero, and optional Record. With Record and AutoBlock enabled, the program waits for the meter to settle and averages readings while the beam is blocked, just before passing it at each temperature point, or once for a scan without temperature points. Results are saved with the measurement data.
- **Interface screenshots:** Screenshot captures the visible application interface, including plots and the selected tabs, during or after a scan. It saves beside the current/latest data file with the same basename and a `.png` extension; before the first scan, it uses the selected data folder and the system's time/mode/suffix naming convention. In OPTP (v4.01 and later) each click saves a separate PNG with a date/time suffix; in the other systems repeated clicks update the same screenshot.
- **Scan configurations:** **Imp. Conf. / Exp. Conf.** beside Screenshot load/save JSON recipes for each system's stage/rotary scan settings, ordered temperature list, acquisition waits, beam controls and power-record settings, plus its own additional scan controls. Import validates the complete recipe and referenced calibration file, then restores the UI/model without operating instruments. Hardware settings, live readouts and data paths are excluded. Each system has a distinct format identifier to prevent cross-system imports. Import is disabled during scans; export remains available and saves current UI values. Calibration files remain external and must be available when importing.
- **Data and logs:** HDF5 measurement files and a daily `ScanLog_YYYY-MM-DD.txt` containing scan conditions and progress events.
- **Live Process (OPTP, THz Emission):** below ScanLog on the Inst. Config. & Log tab, a read-only box shows the program's console output (print messages and errors) from program start until it quits. The terminal still receives the same text; nothing is saved to disk; the latest 1000 lines are kept and the box is not cleared between scans.

## System features

### OPTP — v4.3

Optical pump–THz probe spectroscopy with Stage1 as the THz detection delay and Stage2 as the pump delay.

Changes since v3.9:

- **v4.0:** manual **Home** buttons for Stage1 and Stage2 beside their iPos inputs; a new **Go to T** first stops the running temperature-stabilization worker before sending the setpoint. If it does not stop within 2 s, a manual request is rejected and an automated scan request ends the scan with an error.
- **v4.01:** the current stage positions and rotary angle are shown before a peak search starts; Save Name refreshes as soon as a scan starts; each Screenshot click saves a separate timestamped PNG.
- **v4.2:** Live Process console view below ScanLog (see Shared capabilities). A Realtime lock-in display without a connected lock-in prints its warning once per switch-on instead of on every update.
- **v4.3:** Scan devices offers the Mercury iTC Ethernet address (see Shared capabilities).

- **Scan modes:** `THz_Scan` for THz waveforms, `1D_THz` for pump-delay traces at a fixed THz detection position, `2D_THz` for a full THz waveform at each pump delay, and `POL_2D` for polarization scans.
- **Peak tracking:** **Drift comp.** enables the two-round search around `TDS Ppos` in every mode, with or without temperature scanning. The initial search runs before acquisition, once per temperature when ScanT is active. In `1D_THz`, changing active rotary angles also triggers a search before the first sweep at the new angles, even with Stage2 Repeat = 1 or Re-peak OFF. Searches use the current planned angles, including interpolated calibration angles. A fixed-Stage1 `1D_THz` scan follows the found peak directly; other modes and multi-point Stage1 scans retain their window offset. Stage2 compensates the actual Stage1 correction according to Forward/Reverse. Drift comp. OFF disables all automatic searches.
- **Repeat peak search:** `Re-peak: ON` is the default. With **Drift comp. ON, `1D_THz`, and Stage2 Repeat > 1**, it searches before repeats 2, 3, etc. at the current angle, independently of ScanT. OFF skips these same-angle repeat searches while retaining the initial and angle-change searches. Each search updates subsequent scan positions without repeating the temperature wait, sample soak or beam-settle wait. Other modes, including `THz_Scan`, `2D_THz` and `POL_2D`, retain their initial search only.
- **Beam-heating wait:** Peak search settings offer `Pass → Soak` and `Soak → Pass`. With AutoBlock and temperature scanning enabled, `Beam settle (min)` adds a full extra wait after both sample soak and beam pass, before peak search or acquisition. Default: **5 minutes**; 0 skips this extra wait.
- **Lock-in controls:** each SR830 has **Auto Zero** for its X-channel auto offset, plus an editable decimal Phase field. Phase arrows apply **1-degree steps immediately**; typed decimals commit on Enter or focus loss with 0.01-degree precision. Connection reads **sensitivity, time constant and phase** without writing defaults, and preserves the current acquisition waits and multipliers. Failed readbacks show unknown settings. Auto Zero refreshes the actual X reading. Both controls are disabled during a scan; front-panel versus X-readback behavior after Auto Zero remains a hardware verification item.
- **Scan configurations:** OPTP recipes also include peak tracking, repeat peak search and beam-settle timing. Export uses current UI values, including positions updated by re-peaking.
- **Scan handling:** scan plans are validated before startup and compensated travel is checked after searching. Movement/Lock-in communication errors and temperature-start failures abort through file cleanup. Unacquired samples are NaN. Lock-in Realtime buttons switch off for scanning and remain off afterwards; scan charts still update, and active-instrument checkboxes retain their settings.

### MO — v2.8

Magneto-optical measurements using a Thorlabs linear Stage1 and Newport PM500 Stage2, with polarization control and temperature sequences.

- **v2.8:** Scan devices offers the Mercury iTC Ethernet address. Conn. Instr. now connects the iTC: v2.0-v2.7 called a heater-limit method the iTC driver does not have and failed after opening the iTC, over USB as well.

- **Scan modes:** `1D_POL`, `POL_2D`, `THz_Scan`, `1D_THz` and `2D_THz`.
- Independent or coupled rotary motion, including calibration-file-based polarization settings.
- Temperature stabilization followed by a configurable sample-soak wait. Routine MO scans retain their existing behavior; this version adds no new peak-search workflow.
- Integrated PM100D display, configuration, Zero and pump-power Record alongside AutoBlock and ScanLog. Acquisition supports operation without Lock-in 2; disconnected Lock-in channels retain zero placeholders in this system's data.

### OPTP Imaging — v1.9

Spatial THz/OPTP acquisition with an XY raster and a live image display.

- **v1.9:** Scan devices offers the Mercury iTC Ethernet address.

- **Scan modes:** `THz_Scan`, `1D_THz`, `POL_2D`, `2D_THz` and `2D_IMG`.
- In the imaging setup, X/Y linear stages use the **Rotary1/Rotary2** control slots. Independent mode forms an XY grid with X slow and Y fast; coupled mode follows paired positions. `THz_Scan` records a THz waveform at each grid point, while `1D_THz` records a pump-delay trace.
- **Live image:** select Lock-in 1/2 X, Y or R, and display Peak-Peak, Max, Min, Mean or a chosen trace point. Changing these selectors redraws acquired pixels without another measurement.
- PM100D controls, pump-power Record, AutoBlock, temperature sequences and ScanLog are integrated. Automatic temperature peak search is currently disabled in this system.

### THz Emission — v1.8

THz emission measurements using a **PI N-565.360 / E-861** Stage1 and a Thorlabs Stage2.

- **Scan modes:** `THz_Scan`, `2D_THz` and `THz_pol`.
- Stage1 arrival is checked before Lock-in acquisition. For waveform scans, Stage1 is the innermost sweep, acquiring a complete trace at each Stage2 position.
- **Stage1 arrival (since v1.61, shared PI driver):** a move is complete when the E-861 reports on-target within 50 nm, or when the position has stayed within 50 nm of the target for 200 ms while the controller is still hunting at the nm level. This removes the occasional multi-second stalls seen with 1 µm steps; the 50 nm tolerance stays well below the 1 µm step.
- **v1.7:** Live Process console view below ScanLog (see Shared capabilities); **Clear Display** in the Scan-tab action row clears the four Lock-in X/Y traces, also during a scan; the Realtime lock-in display no longer prints every update, and its missing-lock-in warning appears once per switch-on.
- **v1.8:** Scan devices offers the Mercury iTC Ethernet address.
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
python OPTP_System/OPTP_system_iTC_v4.3.py
```

**MO**

```powershell
python MO_System/MO_system_iTC_v2.8.py
```

**OPTP Imaging** — run from its own folder because this entry point loads its UI relative to the working directory.

```powershell
Push-Location OPTP_image_System
python OPTP_iTC_image_v1.9.py
Pop-Location
```

**THz Emission**

```powershell
python THz_emission_system/THz_emission_system_iTC_v1.8.py
```

Before a measurement, set the addresses/channels for the actual setup in **Inst. Config.**, select the required instruments, connect them, and configure the scan mode, positions, repeats and save directory. For the Mercury iTC over Ethernet, the PC's instrument port must be on the iTC's subnet (lab PC: `Ethernet 2` at 192.168.50.10/24, iTC at 192.168.50.100, port 7020); press **Scan devices** and pick `TCPIP0::192.168.50.100::7020::SOCKET` in the MercuryiTC list. Conn. Instr. saves the choice for the next start. OPTP peak tracking requires a valid **TDS Ppos** and active, connected Stage1 and Lock-in 1, even with ScanT off. For repeat tracking, use **`1D_THz`** and the conditions listed above.

## Measurement files

The four measurement applications save **`.h5` HDF5 files**, readable with Python `h5py` or MATLAB `h5read`/`h5info`. Lock-in datasets are `lockin1_X`, `lockin1_Y`, `lockin2_X` and `lockin2_Y`, accompanied by scan positions, step arrays and repetition settings. Successfully recorded pump power is stored in `pump_power_*` datasets; power values use watts in the file.

| System | Default data root |
| --- | --- |
| OPTP | `OPTP_Data/` |
| MO | `TPOP_Data/` |
| OPTP Imaging | `TPOP_Data/` |
| THz Emission | `THz_emission_Data/` |

The save directory can be selected in the GUI. ScanLog is appended in the selected data folder.

For OPTP `1D_THz` scans with repeat or angle-change peak tracking, **`repeat_scan_positions_mm`** stores each sweep's commanded Stage1 position, Stage2 start and TDS peak, including the first sweep at each angle. Use this dataset when reconstructing absolute coordinates of later angles/repeats: the original `iPos1`/`iPos2` scalars describe the first sweep. Dataset attributes document the axes and columns.

## Auxiliary tools and shared code

- [Polarization calibration v1.3](Polarization_cali/Polarization_cali_v1.3.py): automated angle/power calibration and `.mat`, `.csv`, `.h5` export. Each reading waits after the move, runs a stability check, then averages a set number of new power readings. Details in [Polarization_cali_dev_log.md](Polarization_cali/Polarization_cali_dev_log.md).
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

The following checks use simulated instruments or instrument-free UI rendering and temporary files:

```powershell
python OPTP_System/tests/test_lockin_controls.py
python OPTP_System/tests/test_scan_config.py --native-preview
python OPTP_System/tests/test_scan_config.py mo --native-preview
python OPTP_System/tests/test_scan_config.py img --native-preview
python OPTP_System/tests/test_scan_config.py thz --native-preview
python OPTP_System/tests/test_scan_failures.py 4.3
python OPTP_System/tests/test_drift_comp.py 3.9
python OPTP_System/tests/test_v39_refactor.py
python OPTP_System/tests/test_rotary_coupling.py optp
python OPTP_System/tests/test_rotary_coupling.py mo
python OPTP_System/tests/test_rotary_coupling.py img
python OPTP_System/tests/test_rotary_coupling.py thz
python OPTP_System/tests/test_ui_screenshot.py optp --native-preview
python OPTP_System/tests/test_ui_screenshot.py mo --native-preview
python OPTP_System/tests/test_ui_screenshot.py img --native-preview
python OPTP_System/tests/test_ui_screenshot.py thz --native-preview
```

The Lock-in control checks also accept `mo`, `img` or `thz` to select the corresponding system, for example `python OPTP_System/tests/test_lockin_controls.py mo`. Add `--native-preview` to check the Windows layout.

The v3.9 refactor check compares UI update order, zero/missing/None handling, unit conversion, exceptions, UI defaults and acquisition structure against the preserved v3.8 source without operating instruments.

They cover Lock-in connection readback and Auto Zero/Phase, JSON scan recipes, scan failure cleanup, peak tracking with and without temperature scanning, beam timing, repeat peak search, selected-axis coupling and PNG capture/naming/replacement. The Lock-in, configuration, rotary and screenshot checks run against the versions named in each script (OPTP v3.9, MO v2.7, OPTP Imaging v1.8, THz Emission v1.6), not the current versions; `test_scan_failures.py` takes the OPTP version as an argument. Instrument libraries still require the environment described above.

Checks for the current versions:

```powershell
python OPTP_System/tests/test_v42_live_process.py
python OPTP_System/tests/test_v43_itc_ethernet.py
python OPTP_System/tests/test_v43_itc_ethernet.py MO_System/MO_system_iTC_v2.8.py
python OPTP_System/tests/test_v43_itc_ethernet.py OPTP_image_System/OPTP_iTC_image_v1.9.py
python OPTP_System/tests/test_v43_itc_ethernet.py THz_emission_system/THz_emission_system_iTC_v1.8.py
```

`test_v42_live_process.py` checks the always-on Live Process box of OPTP v4.2 (unchanged in v4.3). `test_v43_itc_ethernet.py` checks the Ethernet address in Scan devices with local stand-in ports; when the Mercury iTC answers at 192.168.50.100, it also connects to it (reads only) through Scan devices, Conn. Instr., the realtime display and Close Instr. Hardware verification status and pending work are tracked in [OPTP_handoff.md](OPTP_System/OPTP_handoff.md).
