# Polarization & Power Calibration System Implementation Plan

This document outlines the architecture, UI layout, scanning logic, and instrument integration for the **Polarization & Power Calibration Tool** (`Polarization_cali_v1.0.py` and `Polarization_cali_v1.0.ui`), located in `Polarization_cali/`.

---

## 1. System Overview & Objectives

### Target Directory & Files
- Directory: `Polarization_cali/`
- Main Program: `Polarization_cali_v1.0.py`
- UI Layout: `Polarization_cali_v1.0.ui`
- Initial Version: `v1.0`

### Hardware Integration
- **3 x Thorlabs KCube DC Servo Rotary Stages** (via `inst_libs/thorlabs_RotaryStage.py`):
  - Stage 1: 1/2 Waveplate (半波片)
  - Stage 2: Polarizer (偏振片)
  - Stage 3: Auxiliary / Extra Rotation Stage
- **1 x Thorlabs PM100D Power Meter** (via `inst_libs/thorlabs_PM100D.py`).

### Key Operational Requirements
1. **Device Auto-Discovery & Connection**:
   - Auto-scans VISA resources for PM100D (`PM100D.list_resources()`).
   - Auto-populates OPTP default stage serial numbers (`"27004364"`, `"27255894"`).
   - Editable `QComboBox` allows manual input if auto-discovery fails.
2. **Measurement Parameters**:
   - Target Power (mW), Power Tolerance (mW), Wait Time (s, default 10s).
3. **Power Stability Function (`check_power_stability`)**:
   - Reads power at wait time intervals until 3 CONSECUTIVE intervals have absolute changes $\le \text{Tolerance}$ (reads 4 consecutive power samples $P_0, P_1, P_2, P_3$ where $|P_1-P_0| \le \text{Tol}$, $|P_2-P_1| \le \text{Tol}$, and $|P_3-P_2| \le \text{Tol}$).
4. **Calibration Modes**:
   - **`power` Mode**: Fixed Stage 2 angle, scans Stage 1 angles. Waits for power stability at each point, then records Stage 1, 2, 3 positions & measured power.
   - **`Polar` Mode**: Target power specified by user. For each Stage 1 angle, searches Stage 2 (via Sequential Step (方案A) or Binary Search (方案B)) until measured power matches Target Power ± Tolerance and stabilizes.
5. **Unchecked / Disabled Stage Handling**:
   - When a stage is not enabled/checked, its recorded position is left blank (`NaN` in `.mat` and `.h5`, and empty string `""` in `.csv`).
6. **Manual Debugging Controls**:
   - Move To (absolute angle) & Relative Step (+ / -) for Stage 1, 2, and 3.
7. **Real-time Visualization & Storage**:
   - Real-time `pyqtgraph.PlotWidget` displays measured power vs point index.
   - Saves data simultaneously in `.mat`, `.csv`, and `.h5` (HDF5) formats.
8. **Code Reusability & Constraints**:
   - Reuses `func_cores` and `inst_libs` without modifying any existing shared code.

---

## 2. System Architecture & Component Design

```
+-----------------------------------------------------------------------------------+
|                  Polarization & Power Calibration System v1.0                     |
+-----------------------------------------------------------------------------------+
|  [Hardware Connections]                                                           |
|  PM100D Power Meter : [ Combo / LineEdit ]  [ Scan ]  [ Connect ]  (LED Status)   |
|  Stage 1 (1/2 HWP)   : [ Combo: 27004364 ]  [ Home ]  [ Connect ]  (LED Status)   |
|  Stage 2 (Polarizer) : [ Combo: 27255894 ]  [ Home ]  [ Connect ]  (LED Status)   |
|  Stage 3 (Auxiliary) : [ Combo: 27255894 ]  [ Home ]  [ Connect ]  (LED Status)   |
+-----------------------------------------------------------------------------------+
|  [Calibration Settings & Parameters]                                              |
|  Mode: [ power / Polar ]   Polar Search: [ Sequential Step (方案A) / Binary ]     |
|  Target Power: [ 5.000 ] mW   Tolerance: [ 0.050 ] mW   Wait Time: [ 10.0 ] s     |
+-----------------------------------------------------------------------------------+
|  [Stage Scan Configurations & Manual Controls]                                    |
|  [x] Stage 1: Start [ 0.0 ]° Step [ 5.0 ]° Stop [ 90.0 ]° Pos: 0.0°               |
|      [ Goto Angle ] [ Move To ]   [ Step Size ] [ Step + ] [ Step - ]             |
|  [x] Stage 2: Start [ 0.0 ]° Step [ 2.0 ]° Stop [ 180.0 ]° Pos: 0.0°              |
|      [ Goto Angle ] [ Move To ]   [ Step Size ] [ Step + ] [ Step - ]             |
|  [ ] Stage 3: Start [ 0.0 ]° Step [ 1.0 ]° Stop [ 45.0 ]° Pos: --                 |
|      [ Goto Angle ] [ Move To ]   [ Step Size ] [ Step + ] [ Step - ]             |
+-----------------------------------------------------------------------------------+
|  [Execution & Visualization]                                                      |
|  [ Start Calibration ]  [ Stop Calibration ]  Save Dir: [ Path ] [ Browse... ]    |
|  +-----------------------------------------------------------------------------+  |
|  | pyqtgraph PlotWidget (Realtime Power (mW) vs Step Index)                    |  |
|  +-----------------------------------------------------------------------------+  |
|  Log Output Box                                                                   |
+-----------------------------------------------------------------------------------+
```
