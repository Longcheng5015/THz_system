# THz System Control & Data Acquisition GUI

This repository contains a PyQt/PySide6-based Graphical User Interface (GUI) application for laboratory automation, specifically designed for various Terahertz (THz) spectroscopy setups, including Magneto-optical (MO) systems, Optical Pump Terahertz Probe (OPTP) systems, OPTP imaging, and polarization calibration. It provides integrated control over scientific instruments, automated data acquisition, and real-time visualization.

## 🌟 Key Features

* **Multiple Specialized Systems**: Tailored GUI applications for different experimental needs:
  * **OPTP System**: For standard time-domain and optical pump terahertz probe spectroscopy.
  * **OPTP Imaging System**: For scanning and imaging terahertz responses.
  * **MO System**: Dedicated system for Magneto-optical measurements.
  * **Polarization Calibration**: Dedicated tools for calibrating polarizers and fitting polarization data.
* **Instrument Control**: Centralized control for a variety of hardware devices:
  * **Lock-in Amplifiers**: Stanford Research Systems SR830
  * **Motorized Stages**: Thorlabs Linear Stages (BBD202 controller), Thorlabs Rotary Stages, Newport PM500
  * **Temperature Controllers**: Oxford Mercury iTC (Cryostat control)
  * **Optomechanics**: Thorlabs MFF02 Motorized Filter Flippers
  * **Power Meters**: Thorlabs PM100D
* **Real-time Visualization**: Live plotting of time-domain spectroscopy (TDS) and other experimental data using `pyqtgraph`.
* **Experiment Automation**: Automated scan planning, data collection, and execution for complex scans (e.g., optical delay scans, polarization scans, temperature-dependent sweeps).
* **Data Storage**: Robust data saving workflows in HDF5 (`.mat`) format for seamless integration with MATLAB and Python post-processing tools.
* **Thread-safe Execution**: Utilizes `QThread` to ensure a responsive UI during long-running instrument communication and measurement sweeps.

## 📁 Codebase Structure

* **`OPTP_System/`**: Contains the main GUI scripts for the standard OPTP setup (e.g., `OPTP_system_iTC_v1.8.py`) and `.ui` files.
* **`OPTP_image_System/`**: Contains the GUI scripts for the OPTP Imaging system (e.g., `OPTP_iTC_image_v1.0.py`).
* **`MO_System/`**: Contains GUI components and scripts specific to the Magneto-optical system setup (e.g., `MO_system_iTC_v18.py` in `MO_System/GUI`).
* **`Polarization_cali/`**: Contains dedicated tools for polarization calibration (`Polarization_cali_v1.0.py`) and data fitting (`Polarization_fit_v1.0.py`).
* **`func_cores/`**: Core logical modules separating the UI from the business logic:
  * `scan_func_core.py`: Defines scan planners, experiment loops, and overall workflow.
  * `scan_data_core.py`: Reusable data processing and calculation routines (e.g., peak tracking, signal averaging).
  * `scan_storage_core.py`: File I/O and HDF5 storage utilities.
* **`inst_libs/`**: A comprehensive collection of Python classes wrapping VISA/Serial commands for direct hardware control.
* **`UI/` & `ui_users/`**: Reusable UI elements, custom widgets (like LED indicators in `MyWidget.py`), and layouts.
* **`TPOP_Data/` & `OPTP_Data/`**: Default directories for exporting and storing experimental data.
* **`manuals/`**: Device reference manuals and instrument documentation.

## 🚀 Getting Started

### Requirements
The following primary libraries are required to run the application:
* Python 3.8+
* `PySide6` (GUI framework)
* `pyqtgraph` (Real-time plotting)
* `numpy`, `scipy`, `h5py` (Data processing and storage)
* `pyvisa` (Hardware communication)

### Running the Applications
Depending on your experimental setup, you can launch the specific GUI by running its respective main script:

**For OPTP System:**
```bash
python OPTP_System/OPTP_system_iTC_v1.8.py
```

**For MO System:**
```bash
python MO_System/GUI/MO_system_iTC_v18.py
```

**For OPTP Imaging System:**
```bash
python OPTP_image_System/OPTP_iTC_image_v1.0.py
```

**For Polarization Calibration:**
```bash
python Polarization_cali/Polarization_cali_v1.0.py
```

## 📝 Development Notes
* **Instrument Simulation**: Many instrument libraries are structured to allow offline testing (with some mock responses) if the physical hardware is not connected.
* **UI Design**: The GUIs are designed using Qt Designer. You can edit the `.ui` files in their respective folders using Qt Designer and load them dynamically using `QUiLoader`.
