#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""" 
Main program for MO system control and data acquisition GUI application.
This program provides a graphical user interface (GUI) for controlling various instruments,
including lock-in amplifiers and motorized stages, as well as real-time data visualization. 
"""
# region Debugging records
# Development history: see THz_emission_dev_log.md in this directory (project path: THz_emission_system/THz_emission_dev_log.md).
# endregion

# region Import modules
# Inject inst_libs to path for instrument control, especially for mercuryiTC which is not pip-installable and needs to use the provided .py files
from proj_tools import ProjectTools
ProjectTools.inject_inst_libs(__file__)
ProjectTools.inject_inst_libs(__file__, libs_dir_name="func_cores")

# import pyside6 for GUI
import pyqtgraph as pg
from PySide6.QtWidgets import QApplication, QMessageBox, QVBoxLayout, QFileDialog, QPushButton, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QLineEdit, QWidget, QWidgetItem, QListWidgetItem, QStyle
from PySide6.QtUiTools import QUiLoader
from PySide6.QtGui import QIcon, QFont, QColor, QPen, QTextCursor
from collections import deque
from PySide6.QtCore import QObject, QTimer, QThread, Signal, QEventLoop, Slot, Qt, QSettings, QSaveFile, QIODevice, QSignalBlocker
from MyWidget import LedIndicator

# import packages needed
import os, json, re, h5py, random, time, traceback, threading, sys, socket            # h5py for .mat file saving
import numpy as np
import scipy.io as sio
from datetime import datetime
from pathlib import Path

# Import instrument classes
from thorlabs_LinearStage_BBD202 import LinearStage
from physik_E861 import LinearStage as PILinearStage   # stage1: PI N-565.360 on E-861
from thorlabs_RotaryStage import RotaryStage
from thorlabs_MFF02 import FilterFlipper
from thorlabs_PM100D import PM100D
from stanford_SR830 import SR830
from Oxford_mercuryiTC_Thread import MercuryiTC
from scan_func_core import DataProcess, ScanPlanner
from scan_data_core import ScanDataCore
from scan_storage_core import ScanStorageCore
from inst_tools import InstrumentTools
# endregion

# 在QApplication之前先实例化
uiLoader = QUiLoader()

class ConsoleSignal(QObject):
    """Carries mirrored console text to the GUI thread."""
    text = Signal(str)

class ConsoleMirrorStream:
    """Mirror console text through a Qt signal without creating any log file."""
    def __init__(self, terminal, emit):
        self.terminal = terminal
        self.emit = emit
        self.lock = threading.RLock()

    def write(self, text):
        with self.lock:
            if self.terminal is not None:
                self.terminal.write(text)
            if text and self.emit is not None:
                self.emit(text)
        return len(text)

    def flush(self):
        if self.terminal is not None:
            self.terminal.flush()

    def __getattr__(self, name):
        return getattr(self.terminal, name)

#region Main MO System UI class
class moSys:

    def __init__(self):     # initialization for ui and functions
        super().__init__()  # initialize parent class, especially for QWidget and user_customized widgets
        # load UI file
        # register custom widgets used in .ui file as charts
        uiLoader.registerCustomWidget(pg.PlotWidget)
        uiLoader.registerCustomWidget(LedIndicator)
        import os
        ui_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'THz_emission_system_iTC_v1.8.ui')
        self.ui = uiLoader.load(ui_path)
        self.start_console_mirror()  # Live Process box shows print output from here until the program quits

        #region create attributes dynamically for each chart to hold curve and data buffer(linked to "setup_chart_axis" function)
        self.curves = {}
        self.buffers = {}
        self.indices = {}

        # Define function for configuring axis of plotwidgets
        def setup_chart_axis(chart, bottom_value_disp = False):
            
            chartname = chart.objectName()    # get the name of the chart widget        
            chart.setBackground(None)         # set background of charts as transparent
            plotItems = chart.getPlotItem()   # get plot item
            
            # configure styles for right and top axis
            plotItems.showAxis('right')
            right_axis = plotItems.getAxis('right')        
            right_axis.setStyle(showValues=False, tickLength=0)  # 无数字、无刻度
            right_axis.setWidth(5)                              # 留一点宽度让轴线可见
            
            plotItems.showAxis('top')
            top_axis = plotItems.getAxis('top')        
            top_axis.setStyle(showValues=False, tickLength=0)  # 无数字、无刻度
            
            # configure styles for bottom and left axis
            if bottom_value_disp == False:                             # hide ticks and values for bottom axis (realtime display charts)
                bottom_axis = plotItems.getAxis('bottom')   
                bottom_axis.setStyle(showValues=False, tickLength=0)   
                bottom_axis.setHeight(5)                               # show axis line only
                
                left_axis = plotItems.getAxis('left')
                left_axis.setStyle(showValues=True, tickLength=0)       # hide ticks for left axis
            else:                                                       # show values and ticks for bottom axis(TDS and FDS charts) 
                # plotItems.setLabel('left', 'Amp (a.u.)')  # set label for bottom axis
                if chartname == 'tdsChart':
                    plotItems.setLabel('bottom', 'Position (mm)')       # set label for bottom axis
                elif chartname == 'fdsChart':
                    plotItems.setLabel('bottom', 'Frequency (THz)')     # set label for bottom axis
                elif chartname == 'polChart':
                    plotItems.setLabel('bottom', 'Angle (degrees)')     # set label for bottom axis
                
            # cinfigure chart-specific curve and buffer (double curve and single curve)
            if chartname == 'tdsChart' or chartname == 'fdsChart':
                # setup double curves for TDS and FDS charts
                blue_curve = chart.plot([], [], pen=pg.mkPen('b'))
                red_curve  = chart.plot([], [], pen=pg.mkPen('r'))
                # set up date for both curves in blue and red
                self.curves[chartname] = {'blue': blue_curve, 'red': red_curve}
                #print(f"Initializing data buffer and curve for {chartname}")
                
            # elif chartname == 'polChart':
            #     # setup double curves for polarization chart
            #     polar_item = pg.PolarPlotItem() # create polar plot item
            #     chart = pg.PlotWidget(plotItem=polar_item) # set polar plot item to plot widget
                
            #     theta = np.linspace(0, 360, 30)
            #     r = np.abs(np.sin(np.deg2rad(theta)))  # example data
                
            #     self.curves[chartname] = chart.plot(theta, r, pen=pg.mkPen('r'), symbol='o', symbolBrush='b')
            
            else:
                self.curves[chartname]  = chart.plot([], [], pen=pg.mkPen('k'))
                self.buffers[chartname] = deque(maxlen=500) # data buffer for real-time display charts
                self.indices[chartname] = -1
                print(f"Initializing data buffer and curve for {chartname}")
        #endregion    
  
        #region initialize/config. all charts
        setup_chart_axis(self.ui.realDisChart1)
        setup_chart_axis(self.ui.realDisChart2)
        setup_chart_axis(self.ui.lockin1XChart)
        setup_chart_axis(self.ui.lockin1YChart)
        setup_chart_axis(self.ui.lockin2XChart)
        setup_chart_axis(self.ui.lockin2YChart)
        setup_chart_axis(self.ui.polChart)
        setup_chart_axis(self.ui.tdsChart, True)
        setup_chart_axis(self.ui.fdsChart, True)
        #endregion
        
        #region Initialize/apply comboboxes
        # Initialize comboboxes for lockin timeconstants and sensitivities
        self._init_sr830_comboboxes()

        # Initialize comboboxe of Scan Mode
        self._init_scanMode_combobox()
        #endregion

        #region Initialize extra info input box
        # Placeholder text is shown greyed-out when empty and is NOT returned by text(),
        # so an untouched box still counts as "no extra info".
        self.ui.ext_info.setPlaceholderText("Please input extra info.")
        self.ui.cali_file_path.setPlaceholderText("Cali. file")
        #endregion
        
        #region Initialize LED indicators
        self.ui.TempDone.status = False    # temperature stabilization done indicator
        self.ui.autoPID_led.status = False  # auto PID mode indicator
        
        self.ui.stage1Led.status = False  # stage1 connection status indicator
        self.ui.stage2Led.status = False  # stage2 connection status indicator
        self.ui.rotary1Led.status = False    # rotary1 connection status indicator
        self.ui.rotary2Led.status = False    # rotary2 connection status indicator
        self.ui.rotary3Led.status = False    # rotary3 connection status indicator
        self.ui.mercuryiTCLed.status = False  # mercuryiTC connection status indicator
        self.ui.FM_connect.status = False     # flip mount connection status indicator
        self.ui.FM_Indicate.status = False    # flip mount beam state indicator: on = pass, off = blocked / not connected
        self.ui.PMLed.status = False          # power meter connection status indicator
        #endregion
        
        #region Initialize path for data saving
        self.is_custom_save_path = False
        self.setup_data_folder()
        self.setup_dataFile_Name()
        #endregion
        
        #region Setup buttons and their events
        #region configure buttons for lockin realtime display as checkable/toggleable
        # creat dict for chart updaters, could add more chart updaters later
        self.chart_updaters = {
            'realDisChart1': ChartUpdater(self, self.ui.realDisChart1, 'lockin1', 'X', int(self.ui.wait1.value())),     # here, the 'self' is the main moSys class instance
            'realDisChart2': ChartUpdater(self, self.ui.realDisChart2, 'lockin2', 'X', int(self.ui.wait2.value())),
            'lockin1XChart': ChartUpdater(self, self.ui.lockin1XChart),
            'lockin1YChart': ChartUpdater(self, self.ui.lockin1YChart),
            'lockin2XChart': ChartUpdater(self, self.ui.lockin2XChart),
            'lockin2YChart': ChartUpdater(self, self.ui.lockin2YChart),
            'polChart':      ChartUpdater(self, self.ui.polChart),
        }
        # Lockin realtime display switch: connect toggles to start/stop chart updates for lockins by dict defined above 
        self.ui.realtimeDisp1.toggled.connect(lambda checked: self.chart_updaters['realDisChart1'].toggle(checked))
        self.ui.realtimeDisp2.toggled.connect(lambda checked: self.chart_updaters['realDisChart2'].toggle(checked))
        self.ui.clearLockinDisplay.setIcon(self.ui.clearLockinDisplay.style().standardIcon(QStyle.SP_DialogResetButton))
        self.ui.clearLockinDisplay.clicked.connect(self.clear_lockin_display)
        
        # Lockin waittime update: everytime the wait time spinbox value changes, update the corresponding chart updater timer interval and lockin
        self.ui.wait1.editingFinished.connect(lambda: self.chart_updaters['realDisChart1'].update_Interval(int(self.ui.wait1.value())))
        self.ui.wait2.editingFinished.connect(lambda: self.chart_updaters['realDisChart2'].update_Interval(int(self.ui.wait2.value())))
        self.ui.wait1multip.editingFinished.connect(lambda: self.apply_lockin_parameter('lockin1', 'Timeconstant'))  # update wait time based on timeconstant
        self.ui.wait2multip.editingFinished.connect(lambda: self.apply_lockin_parameter('lockin2', 'Timeconstant'))  # update wait time based on timeconstant
        
        # set lockin parameter apply button click events
        self.ui.sensitivity1.currentIndexChanged.connect(lambda: self.apply_lockin_parameter('lockin1', 'Sensitivity'))
        self.ui.timeConst1.currentIndexChanged.connect(lambda: self.apply_lockin_parameter('lockin1', 'Timeconstant'))
        self.ui.autoZero1.clicked.connect(lambda: self.apply_lockin_parameter('lockin1', 'AutoZero'))
        self.ui.phase1.editingFinished.connect(lambda: self.apply_lockin_parameter('lockin1', 'Phase'))
        self.ui.sensitivity2.currentIndexChanged.connect(lambda: self.apply_lockin_parameter('lockin2', 'Sensitivity')) 
        self.ui.timeConst2.currentIndexChanged.connect(lambda: self.apply_lockin_parameter('lockin2', 'Timeconstant')) 
        self.ui.autoZero2.clicked.connect(lambda: self.apply_lockin_parameter('lockin2', 'AutoZero'))
        self.ui.phase2.editingFinished.connect(lambda: self.apply_lockin_parameter('lockin2', 'Phase')) 
        #endregion
        
        # update fdsChart when fdsDispMin/Max spinbox value changes
        self.ui.fdsDispMin.editingFinished.connect(self.update_fds_chart_dispRange)
        self.ui.fdsDispMax.editingFinished.connect(self.update_fds_chart_dispRange)
        
        #region set button click events
        # stages moveto buttons
        self.ui.stage1MoveTo.clicked.connect(lambda: self.to_target_position('stage1'))   # thorlabs linear stage
        self.ui.stage2MoveTo.clicked.connect(lambda: self.to_target_position('stage2'))   # thorlabs linear stage
        self.ui.rot1MoveTo.clicked.connect(lambda: self.to_target_position('rotary1'))    # thorlabs rotary stage
        self.ui.rot2MoveTo.clicked.connect(lambda: self.to_target_position('rotary2'))
        self.ui.rot3MoveTo.clicked.connect(lambda: self.to_target_position('rotary3'))    # thorlabs rotary stage
        
        # stage move_rel buttons
        self.ui.stage1JogL.clicked.connect(lambda: self.single_move_by_step('stage1', -1))
        self.ui.stage1JogR.clicked.connect(lambda: self.single_move_by_step('stage1', 1))
        self.ui.stage2JogL.clicked.connect(lambda: self.single_move_by_step('stage2', -1))
        self.ui.stage2JogR.clicked.connect(lambda: self.single_move_by_step('stage2', 1))
        self.ui.rot1JogL.clicked.connect(lambda: self.single_move_by_step('rotary1', -1))
        self.ui.rot1JogR.clicked.connect(lambda: self.single_move_by_step('rotary1', 1))
        self.ui.rot2JogL.clicked.connect(lambda: self.single_move_by_step('rotary2', -1))
        self.ui.rot2JogR.clicked.connect(lambda: self.single_move_by_step('rotary2', 1))
        self.ui.rot3JogL.clicked.connect(lambda: self.single_move_by_step('rotary3', -1))
        self.ui.rot3JogR.clicked.connect(lambda: self.single_move_by_step('rotary3', 1))
        
        # rotaty stage calibration file import button
        self.ui.load_cali_file.clicked.connect(self.import_calibration_file, False)
        self.ui.pol_cali_mode.toggled.connect(self.on_pol_cali_mode_toggled)
        self.on_pol_cali_mode_toggled(self.ui.pol_cali_mode.isChecked())  # initialize calibration mode
        self.ui.Rot_stages_couple.toggled.connect(self.on_rot_stages_couple_toggled)
        self.on_rot_stages_couple_toggled(self.ui.Rot_stages_couple.isChecked())  # initialize rotary coupling mode

        # flip mount: changing which channel is 'pass' only re-reads the beam state, it never moves the mount
        self.ui.fmPassCh.currentIndexChanged.connect(self.update_flipmount_indicator)
        self.ui.fmManual.toggled.connect(self.on_fm_manual_toggled)  # manual block/pass outside a scan
        self.show_flipmount_state(None)  # not connected yet: state unknown

        # power meter: live display, zeroing, and the PM config tab (wavelength, range, refresh);
        # pmRecord / pmSettle / pmAvgNO are read by the scan thread
        self.pm_timer = QTimer(self.ui)
        self.pm_timer.timeout.connect(self.update_power_display)
        self.ui.pmRefresh.editingFinished.connect(lambda: self.pm_timer.setInterval(self.ui.pmRefresh.value()))
        self.ui.pmWavelength.editingFinished.connect(self.set_pm_wavelength)
        self.ui.pmRange.currentIndexChanged.connect(self.set_pm_range)
        self.ui.pmZero.clicked.connect(lambda: self.zero_power_meter())
        self.ui.PM_realDisp.toggled.connect(self.on_pm_realdisp_toggled)  # live display on/off

        # file operation buttons
        self.ui.browseButton.clicked.connect(self.customize_data_save_path)
        self.ui.saveScreenshot.setIcon(QIcon(str(Path(__file__).with_name("camera.svg"))))
        self.ui.saveScreenshot.clicked.connect(self.save_ui_screenshot)
        self.ui.importScanConfig.setIcon(self.ui.importScanConfig.style().standardIcon(QStyle.SP_DialogOpenButton))
        self.ui.exportScanConfig.setIcon(self.ui.exportScanConfig.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.ui.importScanConfig.clicked.connect(lambda: self.import_scan_config())
        self.ui.exportScanConfig.clicked.connect(lambda: self.export_scan_config())
        self.ui.scanMode.currentIndexChanged.connect(self.setup_scan_mode)
        
        # connect/close instrument buttons
        self.ui.connectInstr.clicked.connect(self.connectInstruments, False)

        # Inst. Config. tab: connection parameters, remembered between sessions
        self.ui.scanDevices.clicked.connect(self.scan_devices, False)
        self.load_connection_settings()
        # Wrapped in a lambda on purpose: clicked() emits a 'checked' bool, which Qt would otherwise
        # pass straight into closeInstruments()'s first parameter and force only_active to False.
        self.ui.closeInstr.clicked.connect(lambda: self.closeInstruments(only_active=True), False)
        
        # run/stop/exit buttons
        self.ui.runButton.clicked.connect(self.runScan, False)
        self.ui.stopButton.clicked.connect(self.stopscan)
        self.ui.exitApp.clicked.connect(self.exitApp, False)
        #endregion
        
        #endregion
        
        #region Initialize necessary objects as None
        # Initiallize relevant variable objects as None
        self.cali_table = None  # calibration table for rotary stages in polarization/intensity dependent scans
        
        # Initialize instrument objects as None   
        self.lockin1 = None
        self.lockin2 = None
        self.stage1  = None
        self.stage2  = None
        self.rotary1 = None
        self.rotary2 = None
        self.rotary3 = None
        self.flipmount = None
        self._fm_blocked_since = None  # time.monotonic() of the last confirmed move to block; None = passing or unknown
        self.powermeter = None
        self.pm_lock = threading.Lock()  # the display timer (GUI thread) and Record (scan thread) share the meter
        self.mercuryiTC = None
        self.uid_HTR = None
        self.uid_TEMP = None
        #endregion    
    
        #region Initialize and save ScanThread as None
        self.scan_Thread = None
        self.itc_stab_thread = None   # created on demand by iTC_goto_targetT
        self._scanning = False
        self._lockin_phases = {'lockin1': None, 'lockin2': None}
        for index in (1, 2):
            phase_box = getattr(self.ui, f'phase{index}')
            phase_box.lineEdit().setPlaceholderText('Phase')
            phase_box.valueChanged.connect(lambda value, box=phase_box: box.setProperty('phaseEdited', True))
            phase_box.lineEdit().textEdited.connect(lambda text, box=phase_box: box.setProperty('phaseEdited', True))
            self.show_lockin_phase(f'lockin{index}', None)
        self.update_lockin_controls()
        #endregion

        #region Initialize scan logic core planner
        self.scan_planner = ScanPlanner()
        #endregion
    
        #region Initialize temperature setup and events
        self.tp_manager = TempPointsManager(self.ui.T_list)  # create temperature points manager instance
        
        # MercuryiTC events for temperature control
        # itc operation buttons
        self.itc_updater = MercuryiTC_Updater(self, interval = 1000)  # create itc updater instance
        
        self.ui.realtimeDispT.toggled.connect(lambda checked: self.itc_updater.update_mercuryiTC_display(checked))
        self.ui.waitiTC.editingFinished.connect(lambda: self.itc_updater.update_Interval(int(self.ui.waitiTC.value()))) 
        self.ui.HeaterLim.editingFinished.connect(lambda: self.itc_updater.set_heater_limit(float(self.ui.HeaterLim.value())))
        self.ui.HeaterSetPercent.editingFinished.connect(lambda: self.itc_updater.set_heater_percent(float(self.ui.HeaterSetPercent.value())))
        self.ui.autoPID.toggled.connect(lambda checked: self.setup_pid_mode(checked))
        self.ui.iTCgoT.clicked.connect(lambda: self.iTC_goto_targetT(float(self.ui.targetT.value())), False)
        self.ui.Tolerance.editingFinished.connect(self.on_tolerance_changed)
        self.ui.add_T.clicked.connect(self.on_add_T_points, False)
        self.ui.Del_T.clicked.connect(self.tp_manager.del_T_points, False)
        self.ui.Clear_T.clicked.connect(self.tp_manager.clear_all, False)
        #endregion
    
    #region Create a singleshot QTimer to delay some processing after UI is shown
    def qwait_time(self, wait_ms: int):
        loop = QEventLoop()
        QTimer.singleShot(wait_ms, loop.quit)
        loop.exec()
    #endregion
    
    #region Initialize comboboxes and apply value for lockin timeconstants and sensitivities
    # initialize comboboxes
    def _init_sr830_comboboxes(self):
        
        # get timeconstant and sensitivity labels
        sens_labels = SR830.get_sensitivity_labels()
        timeconst_labels = SR830.get_time_constant_labels()
        
        # fill sensitivity comboboxes
        self.ui.sensitivity1.clear()
        self.ui.sensitivity1.addItems(sens_labels)
        self.ui.sensitivity1.setCurrentIndex(23)  # default 100 mV/fA
        
        self.ui.sensitivity2.clear()
        self.ui.sensitivity2.addItems(sens_labels)
        self.ui.sensitivity2.setCurrentIndex(23)  # default 100 mV/fA
        
        # fill timeconstant comboboxes
        self.ui.timeConst1.clear()
        self.ui.timeConst1.addItems(timeconst_labels)
        self.ui.timeConst1.setCurrentIndex(8)  # default 100 ms 
        
        self.ui.timeConst2.clear()
        self.ui.timeConst2.addItems(timeconst_labels)
        self.ui.timeConst2.setCurrentIndex(8)  # default 100 ms

    # apply lockin values
    def update_lockin_controls(self):
        """New setting controls are available only for a connected lock-in outside a scan."""
        for index in (1, 2):
            name = f'lockin{index}'
            connected = getattr(self, name) is not None
            getattr(self.ui, f'phase{index}').setEnabled(connected and not self._scanning)
            getattr(self.ui, f'autoZero{index}').setEnabled(connected and not self._scanning)
            if not connected:
                self.show_lockin_phase(name, None)

    def show_lockin_phase(self, lockin_name, phase):
        """Programmatic readbacks must never become user edits or send a default phase."""
        box = getattr(self.ui, f'phase{lockin_name[-1]}')
        blocked = box.blockSignals(True)
        try:
            box.clear() if phase is None else box.setValue(phase)
        finally:
            box.blockSignals(blocked)
        self._lockin_phases[lockin_name] = phase
        box.setProperty('phaseEdited', False)

    def refresh_lockin_phase(self, lockin_name):
        """Read instrument state without writing it back through the edit control."""
        box = getattr(self.ui, f'phase{lockin_name[-1]}')
        try:
            phase = float(getattr(self, lockin_name).get_phase())
            if not np.isfinite(phase) or not box.minimum() <= phase <= box.maximum():
                raise ValueError(f'invalid phase readback: {phase}')
            self.show_lockin_phase(lockin_name, phase)
            return True
        except Exception as e:
            self.show_lockin_phase(lockin_name, None)
            print(f"Warning: could not read {lockin_name} phase: {e}")
            return False

    def refresh_lockin_settings(self, lockin_name):
        """Read hardware settings without sending commands or changing acquisition waits."""
        device = getattr(self, lockin_name, None)
        if device is None:
            return False  # leave the disconnected defaults alone
        errors = []
        suffix = lockin_name[-1]
        for prefix, getter in (('sensitivity', device.get_sensitivity_index),
                               ('timeConst', device.get_time_constant_index)):
            box = getattr(self.ui, f'{prefix}{suffix}')
            try:
                index = getter()
                if not 0 <= index < box.count():
                    raise ValueError(f'invalid index {index}')
            except Exception as e:
                index = -1  # unknown must not look like a verified default
                errors.append(f'{prefix}: {e}')
            with QSignalBlocker(box):
                box.setCurrentIndex(index)
        if not self.refresh_lockin_phase(lockin_name):
            errors.append('Phase readback failed.')
        if errors:
            QMessageBox.warning(self.ui, f'Lock-in {suffix} readback', '\n'.join(errors))
        return not errors


    def connect_lockin(self, index):
        name = f'lockin{index}'
        if not getattr(self.ui, f'activeLockin{index}').isChecked():
            return
        if getattr(self, name) is None:
            address = getattr(self.ui, f'Lockin{index}_res').currentText().strip()
            device = SR830(address)
            try:
                error_msg = device.open()
                if error_msg:
                    raise RuntimeError(error_msg)
                self.qwait_time(50)
                identity = device.idn()
                setattr(self, name, device)
                print(f"Lock-in {index} connected (address: {address}, ID: {identity})")
            except Exception as e:
                try:
                    device.close()
                except Exception:
                    pass
                print(f"Lock-in {index} connection failed: {e}")
                return
        else:
            print(f"Lock-in {index} is already connected; refreshing settings.")
        self.refresh_lockin_settings(name)

    def apply_lockin_parameter(self, lockinName: str, paraName: str) -> bool:
        if paraName in ('AutoZero', 'Phase') and self._scanning:
            return False
        # use getattr to get lockin_device from self by name
        lockin_device = getattr(self, lockinName, None)
        if lockin_device is None:
            print(f"Warning: Lockin device '{lockinName}' is not connected for applying {paraName}.")
            return False
        
        if lockinName == 'lockin1':
            suffix = '1'
        elif lockinName == 'lockin2':
            suffix = '2'
        else:
            print(f"Warning: Unknown lockin name '{lockinName}' for applying {paraName}.")
            return False
           
        try:
            if paraName == 'Sensitivity':
                combobox = getattr(self.ui, f'sensitivity{suffix}', None)  # get combobox by name
                if combobox is None:
                    print(f"Warning: Sensitivity combobox for '{lockinName}' not found.")
                    return False
                
                index = combobox.currentIndex()
                lockin_device.set_sensitivity(index)
                print(f"Applied sensitivity index {index} to {lockinName}.")
            
            elif paraName == 'Timeconstant':
                combobox = getattr(self.ui, f'timeConst{suffix}', None)  # get combobox by name
                if combobox is None:
                    print(f"Warning: Timeconstant combobox for '{lockinName}' not found.")
                    return False    
                
                index = combobox.currentIndex()
                lockin_device.set_time_constant(index)  
                print(f"Applied timeconstant index {index} to {lockinName}.")
                
                # update the waittime interval for corresponding chart updater
                timeConst_ms = SR830._TC_VALUES_S[index] * 1000 # in s
                waitmultipBoxName = f'wait{suffix}multip'
                waitmultipBox = getattr(self.ui, waitmultipBoxName, None)
                if waitmultipBox is None:
                    print(f"Warning: Wait time multiplier box for '{lockinName}' not found.")
                    return False
                
                # get multiplier value
                multiplier = waitmultipBox.value()
                new_waittime = int(round(timeConst_ms * multiplier)) # in ms
                
                # update new waittime to corresponding box and display
                waitBoxName = f'wait{suffix}'
                waitBox = getattr(self.ui, waitBoxName, None)
                if waitBox is None:
                    print(f"Warning: Wait time box for '{lockinName}' not found.")
                    return False
                
                #waitBox.blockSignals(True)  # block signals to avoid recursive calls, also would block wait time update to chart updater
                waitBox.setValue(new_waittime)
                #waitBox.blockSignals(False)
                print(f"Updated wait time to {new_waittime} ms for {lockinName} based on timeconstant and multiplier.")
                
            elif paraName == 'AutoZero':
                lockin_device.auto_offset(1)  # hardware X offset only; leave Y/R and phase unchanged
                x = float(lockin_device.get_x())
                if not np.isfinite(x):
                    raise ValueError('non-finite X readback after Auto Zero')
                getattr(self.ui, f'realDisChart{suffix}Num').setText(f'{x:.4e}')
                self.chart_updaters[f'realDisChart{suffix}'].update(update_single_shot=True, lockin_reading=x)
                print(f"Applied X Auto Zero to {lockinName}; X readback = {x:.4e}.")

            elif paraName == 'Phase':
                box = getattr(self.ui, f'phase{suffix}')
                if not box.property('phaseEdited') or not box.hasAcceptableInput():
                    return False
                value = box.value()
                if value == self._lockin_phases[lockinName]:
                    box.setProperty('phaseEdited', False)
                    return True  # focus changes / repeated editingFinished must not resend settings
                lockin_device.set_phase(value)
                if not self.refresh_lockin_phase(lockinName):
                    raise RuntimeError('phase command sent, but instrument readback failed')
                print(f"Applied phase to {lockinName}: {box.value():.2f} deg.")
                
            else:
                print(f"Warning: Unknown parameter name '{paraName}' for applying to '{lockinName}'.")
                return False
                
            return True
        
        except Exception as e:
            print(f"Error applying {paraName} to {lockinName}: {e}")
            if paraName == 'Phase':
                self.show_lockin_phase(lockinName, None)
            elif paraName == 'AutoZero':
                getattr(self.ui, f'realDisChart{suffix}Num').setText('--')
            if paraName in ('AutoZero', 'Phase'):
                QMessageBox.warning(self.ui, f'Lock-in {suffix}', f'{paraName} failed or could not be verified:\n{e}')
            return False
 
    #endregion
                
    #region connect/close instruments
    def connectInstruments(self):
        self.save_connection_settings()  # remember the parameters used, for the next session
        print("Start connecting instruments...")
        print("=" * 50)
        
        for index in (1, 2):
            self.connect_lockin(index)
        self.update_lockin_controls()

        # connect Stage1
        if self.ui.activeStage1.isChecked():
            if self.stage1:
                print("Stage1 is already connected.")
                
            else:
                stage1_temp = None
                try:
                    serial = self.ui.Stage1_res.currentText().strip()  # E-861 controller serial, set in Inst. Config. tab
                    chan = str(self.ui.Stage1_ch.value())  # GCS axis ID of the N-565.360 stage
                    stage1_temp = PILinearStage(
                        serial,
                        axis=chan,
                        servo_on=True,
                        reference_if_needed=True,
                    )
                    stage1_temp.home_with_guard(60000)  # reference with explicit servo guard
                    self.stage1 = stage1_temp
                    self.qwait_time(1000)    # wait for 2 seconds after connect
                    self.ui.stage1CurrPos.setValue(self.stage1.position())  # update current position display
                    self.ui.stage1Led.status = True  # update LED indicator
                    QApplication.processEvents()  # Ensure UI updates immediately
                    print(f"✓ Stage1 connection successful (serial: {serial}, axis: {chan})")
                except Exception as e: 
                    try:
                        if stage1_temp is not None:
                            stage1_temp.close()
                    except Exception:
                        pass
                    self.stage1 = None
                    print(f"✗ Stage1 connection failed: {str(e)}")
                
        # connect Stage2
        if self.ui.activeStage2.isChecked():
            if self.stage2:
                print("Stage2 is already connected.")
                
            else:
                stage2_temp = None
                try:
                    serial = self.ui.Stage2_res.currentText().strip()  # set in Inst. Config. tab
                    chan = self.ui.Stage2_ch.value()
                    stage2_temp = LinearStage(
                        serial,
                        chan,
                        poll_ms=250,
                        enable_state_guard=True,
                        enable_wait_timeout_ms=5000,
                        enable_retry_count=2,
                        enable_poll_interval_ms=100,
                    )
                    stage2_temp.home_with_guard(60000)  # home with explicit enable guard
                    self.stage2 = stage2_temp
                    self.qwait_time(1000)  # wait for 2 seconds after connect
                    self.ui.stage2CurrPos.setValue(self.stage2.position())  # update current position display    
                    self.ui.stage2Led.status = True  # update LED indicator
                    QApplication.processEvents()  # Ensure UI updates immediately
                    print(f"✓ Stage2 connection successful (serial: {serial}, channel: {chan})")
                except Exception as e: 
                    try:
                        if stage2_temp is not None:
                            stage2_temp.close()
                    except Exception:
                        pass
                    self.stage2 = None
                    print(f"✗ Stage2 connection failed: {str(e)}")
                
        # connect Rotary1
        if self.ui.activeRot1.isChecked():
            if self.rotary1:
                print("Rotary1 is already connected.")
                
            else:
                rotary1_temp = None
                try:
                    serial = self.ui.Rot1_res.currentText().strip()  # set in Inst. Config. tab
                    rotary1_temp = RotaryStage(serial, poll_ms=250, use_sim=False)
                    rotary1_temp.home(60000)  # home the stage
                    self.rotary1 = rotary1_temp
                    self.qwait_time(1000)  # wait for 1 seconds after connect
                    self.ui.rot1CurrPos.setValue(self.rotary1.position())  # update current position display
                    self.ui.rotary1Led.status = True  # update LED indicator
                    QApplication.processEvents()  # Ensure UI updates immediately
                    print(f"✓ Rotary1 connection successful (serial: {serial})")
                except Exception as e: 
                    try:
                        if rotary1_temp is not None:
                            rotary1_temp.close()
                    except Exception:
                        pass
                    self.rotary1 = None
                    print(f"✗ Rotary1 connection failed: {str(e)}")
                
        # connect Rotary2
        if self.ui.activeRot2.isChecked():
            if self.rotary2:
                print("Rotary2 is already connected.")
                
            else:
                rotary2_temp = None
                try:
                    serial = self.ui.Rot2_res.currentText().strip()  # set in Inst. Config. tab
                    rotary2_temp = RotaryStage(serial, poll_ms=250, use_sim=False)
                    rotary2_temp.home(60000)  # home the rotary stage
                    self.rotary2 = rotary2_temp
                    self.qwait_time(1000)  # wait for 2 seconds after connect
                    self.ui.rot2CurrPos.setValue(self.rotary2.position())  # update current position display
                    self.ui.rotary2Led.status = True  # update LED indicator
                    QApplication.processEvents()  # Ensure UI updates immediately
                    print(f"✓ Rotary2 connection successful (serial: {serial})")
                except Exception as e: 
                    try:
                        if rotary2_temp is not None:
                            rotary2_temp.close()
                    except Exception:
                        pass
                    self.rotary2 = None
                    print(f"✗ Rotary2 connection failed: {str(e)}")
        
        # connect Rotary3
        if self.ui.activeRot3.isChecked():
            if self.rotary3:
                print("Rotary3 is already connected.")
                
            else:
                rotary3_temp = None
                try:
                    serial = self.ui.Rot3_res.currentText().strip()  # set in Inst. Config. tab
                    rotary3_temp = RotaryStage(serial, poll_ms=250, use_sim=False)
                    rotary3_temp.home(60000)  # home the rotary stage
                    self.rotary3 = rotary3_temp
                    self.qwait_time(1000)  # wait for 1 seconds after connect
                    self.ui.rot3CurrPos.setValue(self.rotary3.position())  # update current position display
                    self.ui.rotary3Led.status = True  # update LED indicator
                    QApplication.processEvents()  # Ensure UI updates immediately
                    print(f"✓ Rotary3 connection successful (serial: {serial})")
                except Exception as e: 
                    try:
                        if rotary3_temp is not None:
                            rotary3_temp.close()
                    except Exception:
                        pass
                    self.rotary3 = None
                    print(f"✗ Rotary3 connection failed: {str(e)}")

        # connect flip mount (beam block)
        if self.ui.activeFlipMount.isChecked():
            if self.flipmount:
                print("Flip mount is already connected.")

            else:
                flipmount_temp = None
                try:
                    serial = self.ui.FM_res.currentText().strip()  # set in Inst. Config. tab
                    flipmount_temp = FilterFlipper(serial)
                    # no homing: homing flips the mount and could expose the sample
                    self.flipmount = flipmount_temp
                    self.ui.FM_connect.status = True  # update LED indicator
                    self.update_flipmount_indicator()  # show whether the beam is blocked right now
                    QApplication.processEvents()  # Ensure UI updates immediately
                    print(f"✓ Flip mount connection successful (serial: {serial}, position: {self.flipmount.position()})")
                except Exception as e:
                    try:
                        if flipmount_temp is not None:
                            flipmount_temp.close()
                    except Exception:
                        pass
                    self.flipmount = None
                    print(f"✗ Flip mount connection failed: {str(e)}")

        # connect power meter (pump power; the pump reaches it while the flip mount blocks the beam)
        if self.ui.activePowerMeter.isChecked():
            if self.powermeter:
                print("Power meter is already connected.")

            else:
                pm_temp = None
                try:
                    resource = self.ui.PM_res.currentText().strip()  # set in Inst. Config. tab
                    pm_temp = PM100D(resource, timeout_ms=3000)
                    pm_temp.open()
                    idn = pm_temp.idn()
                    self.load_pm_settings(pm_temp)  # PM config: wavelength box -> meter, meter's range -> box
                    self.powermeter = pm_temp
                    self.ui.PMLed.status = True  # update LED indicator
                    self.sync_pm_display_timer()  # live power display, if PM_realDisp is pressed
                    QApplication.processEvents()  # Ensure UI updates immediately
                    print(f"✓ Power meter connection successful ({idn}, {self.ui.pmWavelength.value()} nm)")
                except Exception as e:
                    try:
                        if pm_temp is not None:
                            pm_temp.close()
                    except Exception:
                        pass
                    self.powermeter = None
                    print(f"✗ Power meter connection failed: {str(e)}")

        # connect MercuryiTC temperature controller
        if self.ui.activeiTC.isChecked():
            if self.mercuryiTC:
                print("MercuryiTC is already connected.")
                # UID may be missing if a previous connection attempt failed partway through; retry now
                if self.uid_HTR is None or self.uid_TEMP is None:
                    print("MercuryiTC UIDs missing — re-fetching system catalog...")
                    try:
                        devices = self.mercuryiTC.get_system_catalog()
                        self.uid_HTR_list  = [uid for uid, types in devices.items() if 'HTR' in types]
                        self.uid_HTR       = self.uid_HTR_list[0] if self.uid_HTR_list else None
                        self.uid_TEMP_list = [uid for uid, types in devices.items() if 'TEMP' in types]
                        self.uid_TEMP      = self.uid_TEMP_list[0] if self.uid_TEMP_list else None
                        if self.uid_TEMP is not None:
                            self.ui.targetT.setValue(self.mercuryiTC.get_temperature_setpoint(self.uid_TEMP))
                        if self.uid_HTR is not None:
                            self.ui.HeaterLim.setValue(self.mercuryiTC.get_heater_voltage_limit(self.uid_HTR))
                        self._sync_autoPID_from_instrument()  # reflect the loop state the controller holds
                        print(f"MercuryiTC UIDs updated: heaters={self.uid_HTR}, temps={self.uid_TEMP}")
                    except Exception as e:
                        print(f"✗ MercuryiTC UID re-fetch failed: {e}")

            else:
                try:
                    RESOURCE = self.ui.iTC_res.currentText().strip()  # set in Inst. Config. tab
                    self.mercuryiTC = MercuryiTC(RESOURCE)
                    self.mercuryiTC.open()
                    self.qwait_time(100)  # wait time in ms for device to be ready
                    devices = self.mercuryiTC.get_system_catalog()
                    self.qwait_time(200)  # wait time in ms for next device to be ready
                    # get heater and temperature sensor UIDs
                    self.uid_HTR_list  = [uid for uid, types in devices.items() if 'HTR' in types]    # heater UID
                    self.uid_HTR       = self.uid_HTR_list[0] if self.uid_HTR_list else None
                    self.uid_TEMP_list = [uid for uid, types in devices.items() if 'TEMP' in types]  # temperature sensor UID
                    self.uid_TEMP      = self.uid_TEMP_list[0] if self.uid_TEMP_list else None
                    # get current heater and temperature values when UIDs are available
                    if self.uid_TEMP is not None:
                        self.ui.targetT.setValue(self.mercuryiTC.get_temperature_setpoint(self.uid_TEMP))
                    if self.uid_HTR is not None:
                        self.ui.HeaterLim.setValue(self.mercuryiTC.get_heater_voltage_limit(self.uid_HTR))
                    self._sync_autoPID_from_instrument()  # reflect the loop state the controller holds
                    self.ui.mercuryiTCLed.status = True  # update LED indicator
                    QApplication.processEvents()  # Ensure UI updates immediately
                    print(f"✓ MercuryiTC connection successful (resource: {RESOURCE}, heaters: {self.uid_HTR}, temps: {self.uid_TEMP})")

                except Exception as e:
                    print(f"✗ MercuryiTC connection failed: {e}")
                    self.mercuryiTC = None  # reset so reconnection is possible on next attempt

    def closeInstruments(self, only_active: bool = True):
        """Close instruments.

        only_active=True  (the "Close Instr." button): close only the ones whose 'active' box is
                          ticked, so unticking a box and closing does not drop the rest.
        only_active=False (application exit): close everything that is open, otherwise a connected
                          but unticked instrument would keep its handle and leave the port locked.
        """
        print("Start closing instruments...")
        print("=" * 50)

        closing_itc = (self.ui.activeiTC.isChecked() or not only_active) and self.mercuryiTC

        # The stabilization worker may still be sleeping after stopscan's timed wait.
        # It must exit before MercuryiTC is closed and its reference is cleared. Gate it on actually
        # closing the iTC: request_stop() also raises the main stop_flag, which would abort a
        # running scan, and that must not happen just because some other instrument is being closed.
        itc_stab_thread = getattr(self, 'itc_stab_thread', None)
        if closing_itc and itc_stab_thread is not None and itc_stab_thread.isRunning():
            print("Waiting for iTC stabilization thread to stop before closing MercuryiTC...")
            itc_stab_thread.request_stop()
            itc_stab_thread.wait()

        # Only close instruments whose 'active' box is ticked, mirroring connectInstruments().
        # Closing everything regardless meant unticking a box and pressing "Close Instr." also
        # dropped the instruments the user meant to keep connected.
        def should_close(active_box_name: str) -> bool:
            if not only_active:
                return True
            box = getattr(self.ui, active_box_name, None)
            return box is not None and box.isChecked()

        def close_one(attr_name: str, active_box_name: str, label: str, led_name: str = None):
            """Close one instrument, isolating its failure from the rest of the shutdown.

            An instrument whose session has already died - e.g. the iTC after remote/unlock mode is
            switched off at the controller - raises on close(). Without isolation that exception
            propagated out of closeInstruments() and every instrument after it stayed open, with its
            port still locked. The reference and LED are cleared either way: the session is gone
            regardless of whether the handle could be closed cleanly.
            """
            if not (should_close(active_box_name) and getattr(self, attr_name, None)):
                return
            try:
                getattr(self, attr_name).close()
                print(f"✓ {label} closed.")
            except Exception as e:
                print(f"Warning: error while closing {label} ({type(e).__name__}: {e}). "
                      f"Dropping the reference anyway.")
            finally:
                setattr(self, attr_name, None)
                if led_name is not None:
                    getattr(self.ui, led_name).status = False  # update LED indicator
                    QApplication.processEvents()  # Ensure UI updates immediately

        close_one('lockin1', 'activeLockin1', 'Lock-in1')
        close_one('lockin2', 'activeLockin2', 'Lock-in2')
        self.update_lockin_controls()
        close_one('stage1',  'activeStage1',  'Stage1',  'stage1Led')
        close_one('stage2',  'activeStage2',  'Stage2',  'stage2Led')
        close_one('rotary1', 'activeRot1',    'Rotary1', 'rotary1Led')
        close_one('rotary2', 'activeRot2',    'Rotary2', 'rotary2Led')
        close_one('rotary3', 'activeRot3',    'Rotary3', 'rotary3Led')
        close_one('flipmount', 'activeFlipMount', 'Flip mount', 'FM_connect')
        if self.flipmount is None:
            self.show_flipmount_state(None)  # beam state is unknown once disconnected
        close_one('powermeter', 'activePowerMeter', 'Power meter', 'PMLed')
        if self.powermeter is None:
            self.pm_timer.stop()
            self.ui.PowerMeterDisp.setText("-- mW")

        # close MercuryiTC
        # Isolated like the others: taking the controller out of remote/unlock mode kills the
        # session, so close() raises VI_ERROR_INV_OBJECT. The state must still be cleared.
        if closing_itc:
            if hasattr(self, 'itc_updater'):
                self.itc_updater.stop_flag = True
                self.itc_updater.wait()
            # self.mercuryiTC.set_heater_percent(self.uid_HTR, 0)  # set heater percent to 0 before closing
            # self.setup_pid_mode(False)  # disable auto PID mode before closing
            try:
                self.mercuryiTC.close()
                print("✓ MercuryiTC closed.")
            except Exception as e:
                print(f"Warning: error while closing MercuryiTC ({type(e).__name__}: {e}). "
                      f"Dropping the reference anyway - was the controller taken out of remote mode?")
            finally:
                self.mercuryiTC = None
                self.uid_HTR = None
                self.uid_TEMP = None
                self.ui.mercuryiTCLed.status = False  # update LED indicator
                QApplication.processEvents()  # Ensure UI updates immediately

    #endregion

    #region Instrument connection parameters (Inst. Config. tab)
    # address/serial boxes by interface; the *_ch channel spinboxes are saved alongside
    VISA_BOXES = ('Lockin1_res', 'Lockin2_res', 'iTC_res', 'PM_res')
    # Mercury iTC on the instrument Ethernet link. VISA cannot list raw SOCKET resources, so Scan devices
    # checks these addresses (and any SOCKET address already entered) by opening their TCP port.
    ITC_SOCKETS = ('TCPIP0::192.168.50.100::7020::SOCKET',)
    KINESIS_BOXES = ('Stage2_res', 'Rot1_res', 'Rot2_res', 'Rot3_res', 'FM_res')
    OTHER_BOXES = ('Stage1_res',)  # PI E-861 serial: typed in, not found by Scan devices
    CHANNEL_BOXES = ('Stage1_ch', 'Stage2_ch')  # Stage1_ch is the E-861 axis ID; the rotary driver is single-channel

    def scan_devices(self):
        """Offer the VISA resources and Kinesis serials visible to this PC in the drop-down lists, keeping the entered values."""
        for label, scan, boxes in (('VISA', InstrumentTools.list_visa_resources, self.VISA_BOXES),
                                   ('Kinesis', InstrumentTools.list_kinesis_serials, self.KINESIS_BOXES)):
            try:
                found = scan()
            except RuntimeError as e:
                print(f"✗ {e}")
                continue
            if label == 'VISA':
                found += self.reachable_sockets()
            print(f"{label} devices found: {found if found else 'none'}")
            for name in boxes:
                box = getattr(self.ui, name)
                current = box.currentText()
                box.clear()
                box.addItems(found)
                box.setCurrentText(current)  # the scan only offers choices, it never changes the setting

    def reachable_sockets(self) -> list[str]:
        """SOCKET resources (ITC_SOCKETS and any entered in a VISA box) whose TCP port accepts a connection."""
        entered = [getattr(self.ui, name).currentText().strip() for name in self.VISA_BOXES]
        found = []
        for res in dict.fromkeys(self.ITC_SOCKETS + tuple(r for r in entered if r.upper().endswith('::SOCKET'))):
            try:
                _, host, port, _ = res.split('::')
                with socket.create_connection((host, int(port)), timeout=0.5):
                    found.append(res)
            except (OSError, ValueError):
                pass  # not answering, or not a TCPIP0::host::port::SOCKET string
        return found

    def load_connection_settings(self):
        """Restore the parameters saved at the last Conn. Instr.; the .ui defaults stay for anything never saved."""
        settings = QSettings("THz_emission_system", "InstrumentConnections")
        for name in self.VISA_BOXES + self.KINESIS_BOXES + self.OTHER_BOXES:
            value = settings.value(name)
            if value is not None:
                getattr(self.ui, name).setCurrentText(str(value))
        for name in self.CHANNEL_BOXES:
            value = settings.value(name)
            if value is not None:
                getattr(self.ui, name).setValue(int(value))

    def save_connection_settings(self):
        settings = QSettings("THz_emission_system", "InstrumentConnections")
        for name in self.VISA_BOXES + self.KINESIS_BOXES + self.OTHER_BOXES:
            settings.setValue(name, getattr(self.ui, name).currentText().strip())
        for name in self.CHANNEL_BOXES:
            settings.setValue(name, getattr(self.ui, name).value())
    #endregion

    #region Flip mount beam block
    def flipmount_positions(self) -> tuple[int, int]:
        """Return (pass_position, block_position) from the CH1/CH2 box: CH1 = position 1, CH2 = position 2."""
        pass_pos = self.ui.fmPassCh.currentIndex() + 1
        return pass_pos, 3 - pass_pos

    def show_flipmount_state(self, blocked: bool | None):
        """Show the beam state on FM_Indicate and the manual button (GUI thread only). None = unknown / not connected."""
        self.ui.FM_Indicate.status = blocked is False  # lit only when the beam is confirmed to pass
        self.ui.fmManual.blockSignals(True)  # reflecting the state must not trigger another move
        self.ui.fmManual.setChecked(bool(blocked))
        self.ui.fmManual.setText("Blocked" if blocked else ("Pass" if blocked is not None else "Block / Pass"))
        self.ui.fmManual.blockSignals(False)

    def update_flipmount_indicator(self):
        """Read the mount position and show whether the beam is blocked (GUI thread only)."""
        if self.flipmount is None:
            self.show_flipmount_state(None)
            return
        try:
            pass_pos, _ = self.flipmount_positions()
            self.show_flipmount_state(self.flipmount.position() != pass_pos)
        except Exception as e:
            print(f"Warning: could not read flip mount position ({type(e).__name__}: {e}).")

    def on_fm_manual_toggled(self, checked: bool):
        """Manual Block/Pass button: pressed = block, released = pass."""
        if self.flipmount is None:
            print("Flip mount is not connected. Tick it and press Conn. Instr. first.")
            self.show_flipmount_state(None)  # undo the press
            return
        if not self.set_flipmount_blocked(checked):
            self.update_flipmount_indicator()  # move failed: show where the mount really is

    def set_flipmount_blocked(self, blocked: bool, thread=None) -> bool:
        """Move the flip mount to its block or pass position and confirm it arrived.

        Called from the scan thread, so the LED is updated through the thread's signal when one is given.
        Returns True only when the read-back position matches the target.
        """
        if self.flipmount is None:
            print("Flip mount is not connected; beam state unchanged.")
            return False
        pass_pos, block_pos = self.flipmount_positions()
        target = block_pos if blocked else pass_pos
        state = "BLOCK" if blocked else "PASS"
        try:
            self.flipmount.move_to(target)
            reached = self.flipmount.position() == target
        except Exception as e:
            print(f"✗ Flip mount move to {state} (position {target}) failed: {type(e).__name__}: {e}")
            return False
        if not reached:
            print(f"✗ Flip mount did not reach {state} (position {target}).")
            return False
        self._fm_blocked_since = time.monotonic() if blocked else None  # Record's settle time counts from here
        if thread is not None:
            thread.fm_block_led.emit(blocked)
        else:
            self.show_flipmount_state(blocked)
        print(f"Flip mount set to {state} (position {target}).")
        return True

    def on_fm_block_led(self, blocked: bool):
        self.show_flipmount_state(blocked)

    def auto_block_after_scan(self, thread=None):
        """Block the beam when a scan ends, however it ended, if AutoBlock is on. Never raises."""
        if not self.ui.AutoBlock.isChecked():
            return
        print("AutoBlock: scan ended, blocking the beam.")
        if not self.set_flipmount_blocked(True, thread):
            print("Warning: AutoBlock could not block the beam after the scan - the sample may still be exposed!")
    #endregion

    #region Power meter: pump power, which reaches the meter while the flip mount blocks the beam
    def sync_pm_display_timer(self):
        """Run the live power display only while PM_realDisp is pressed and the meter is connected."""
        if self.ui.PM_realDisp.isChecked() and self.powermeter is not None:
            if not self.pm_timer.isActive():
                self.pm_timer.start(self.ui.pmRefresh.value())
        else:
            self.pm_timer.stop()

    def on_pm_realdisp_toggled(self, checked: bool):
        """PM_realDisp: pressed = read and show the power every refresh interval; released = no reading."""
        if checked and self.powermeter is None:
            print("Power meter is not connected; the live display starts once it is connected.")
        if not checked:
            self.ui.PowerMeterDisp.setText("-- mW")  # a frozen number would look like a live reading
        self.sync_pm_display_timer()

    def update_power_display(self):
        """Timer slot: show the current power in mW (GUI thread). Skips a tick while Record holds the meter."""
        if self.powermeter is None:
            self.pm_timer.stop()
            return
        if not self.pm_lock.acquire(blocking=False):
            return
        try:
            power_w = self.powermeter.measure_power()
        except Exception as e:
            # a dead session would freeze the GUI for a full timeout on every tick
            self.pm_timer.stop()
            self.ui.PM_realDisp.blockSignals(True)
            self.ui.PM_realDisp.setChecked(False)  # released: pressing it again retries
            self.ui.PM_realDisp.blockSignals(False)
            self.ui.PowerMeterDisp.setText("error")
            print(f"✗ Power meter read failed ({type(e).__name__}: {e}); display stopped. "
                  f"Press Realtime to retry, or close and reconnect the meter.")
            return
        finally:
            self.pm_lock.release()
        self.ui.PowerMeterDisp.setText(f"{power_w * 1e3:.3f} mW")

    def load_pm_settings(self, pm):
        """PM config tab on connect: the wavelength box (default 800 nm, limited to the sensor) is sent to the
        meter; the power range box offers the sensor's ranges and shows the meter's current range setting."""
        wl_min = float(pm.query("SENS:CORR:WAV? MIN"))
        wl_max = float(pm.query("SENS:CORR:WAV? MAX"))
        self.ui.pmWavelength.setRange(round(wl_min), round(wl_max))  # clamps the box value into the sensor's limits
        pm.set_wavelength_nm(self.ui.pmWavelength.value())
        self.ui.pmWavelength.setValue(round(pm.get_wavelength_nm()))  # what the meter accepted
        self.show_pm_ranges(pm)

    def probe_pm_ranges(self, pm) -> list:
        """The meter's real power ranges (W), lowest first, walked on the meter and its range setting restored.

        They depend on the sensor and the wavelength and are not exact decades (S302C at 800 nm: 3.695 mW,
        34.99 mW, 347.9 mW, 3.477 W), so they cannot be derived from the lowest one: from the lowest range,
        ask for just above the current range until the meter stops moving up.
        """
        auto = pm.get_power_auto_range()
        current = pm.get_power_range_upper()
        ranges = []
        try:
            pm.set_power_auto_range(False)
            pm.write("SENS:POW:RANG:UPP MIN")
            upper = pm.get_power_range_upper()
            for _ in range(12):
                ranges.append(upper)
                pm.set_power_range_upper(upper * 1.01)  # above the top range the meter refuses and keeps it
                following = pm.get_power_range_upper()
                if following <= upper * 1.0001:
                    break
                upper = following
        finally:
            if auto:
                pm.set_power_auto_range(True)
            else:
                pm.set_power_range_upper(current * 0.999)  # see set_pm_range: the read-back value is rounded
            for _ in range(20):  # clear the 'Data out of range' left by the step above the top range
                if pm.get_error()[0] == 0:
                    break
        return ranges

    def show_pm_ranges(self, pm):
        """Offer the meter's real ranges at the current wavelength in the Power range box and show its setting."""
        try:
            ranges = self.probe_pm_ranges(pm)
        except Exception as e:  # the meter stays usable on Auto; no reason to refuse the connection
            ranges = []
            print(f"Warning: could not read the power meter ranges ({type(e).__name__}: {e}); only Auto is offered.")
        box = self.ui.pmRange
        box.blockSignals(True)  # only showing the meter's state; nothing is sent back
        box.clear()
        box.addItem("Auto", None)
        for r in ranges:
            box.addItem(f"{r * 1e3:.4g} mW" if r < 1 else f"{r:.4g} W", r)
        if not ranges or pm.get_power_auto_range():
            box.setCurrentIndex(0)
        else:
            current = pm.get_power_range_upper()
            box.setCurrentIndex(1 + min(range(len(ranges)), key=lambda i: abs(ranges[i] - current)))
        box.blockSignals(False)

    def set_pm_range(self, index: int):
        """Power range box: Auto, or one fixed range (the meter then stops switching ranges)."""
        if self.powermeter is None or index < 0:
            return
        upper = self.ui.pmRange.itemData(index)
        with self.pm_lock:
            try:
                if upper is None:
                    self.powermeter.set_power_auto_range(True)
                else:
                    self.powermeter.set_power_auto_range(False)
                    # The meter reports a range rounded to 7 digits, which can lie just above the range itself and
                    # would select the next one up; 0.1 % below it is inside this range and far above the one below.
                    self.powermeter.set_power_range_upper(upper * 0.999)
                auto = self.powermeter.get_power_auto_range()
                actual = self.powermeter.get_power_range_upper()
            except Exception as e:
                print(f"✗ Setting the power meter range failed: {e}")
                return
        print("Power meter range: Auto." if auto else f"Power meter range fixed at {actual * 1e3:.4g} mW.")

    def set_pm_wavelength(self):
        """Send the wavelength box to the meter, show the value it accepted and the ranges at that wavelength."""
        if self.powermeter is None:
            return
        with self.pm_lock:
            try:
                self.powermeter.set_wavelength_nm(self.ui.pmWavelength.value())
                accepted = self.powermeter.get_wavelength_nm()
                self.show_pm_ranges(self.powermeter)  # the ranges move with the wavelength
            except Exception as e:
                print(f"✗ Setting the power meter wavelength failed: {e}")
                return
        self.ui.pmWavelength.setValue(round(accepted))
        print(f"Power meter wavelength set to {accepted:g} nm.")

    def zero_power_meter(self):
        """Zero button: take the dark offset. The sensor must be dark, i.e. the flip mount on Pass."""
        if self.powermeter is None:
            print("Power meter is not connected. Tick it and press Conn. Instr. first.")
            return
        reply = QMessageBox.question(
            self.ui, "Zero power meter",
            "The sensor must be dark while it is zeroed.\n\n"
            "Is the flip mount on Pass, and has the thermal sensor had about 20 s to cool down?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.pm_timer.stop()  # no power reads while the meter is zeroing
        self.ui.pmZero.setEnabled(False)
        try:
            with self.pm_lock:
                self.powermeter.zero_initiate()
            deadline = time.monotonic() + 30
            while True:
                self.qwait_time(200)  # keeps the GUI responsive; the lock is not held while waiting
                with self.pm_lock:
                    zeroing = self.powermeter.get_zero_state()
                if not zeroing or time.monotonic() > deadline:
                    break
            with self.pm_lock:
                offset_w = self.powermeter.get_zero_magnitude()
            if zeroing:
                print("Warning: the power meter still reports zeroing after 30 s.")
            else:
                print(f"Power meter zeroed (offset {offset_w * 1e3:.4f} mW).")
        except Exception as e:
            print(f"✗ Zeroing the power meter failed: {type(e).__name__}: {e}")
        finally:
            self.ui.pmZero.setEnabled(True)
            self.sync_pm_display_timer()

    def _sleep_unless_stopped(self, seconds: float, thread=None) -> bool:
        """Sleep in short steps; return False as soon as a scan stop is requested."""
        end = time.monotonic() + seconds
        while True:
            if self._check_scan_stop(thread):
                return False
            left = end - time.monotonic()
            if left <= 0:
                return True
            time.sleep(min(0.5, left))

    def record_pump_power(self, thread=None) -> dict | None:
        """Record: measure the pump power right before AutoBlock lets the beam through (scan thread).

        While the flip mount blocks the beam the pump falls on the power meter. A thermal sensor lags
        several seconds, so the meter must have been lit for the settle time (counted from the last
        block move) before N readings one refresh interval apart are averaged. Returns None when
        Record or AutoBlock is off, a stop was requested, or the meter could not be read; the scan
        carries on either way, and a failure is written to the ScanLog.
        """
        if not (self.ui.pmRecord.isChecked() and self.ui.AutoBlock.isChecked()):
            return None
        if self.powermeter is None:
            print("Record: power meter not connected; pump power not recorded.")
            return None

        # the pump only reaches the meter while the beam is blocked
        _, block_pos = self.flipmount_positions()
        try:
            blocked = self.flipmount.position() == block_pos
        except Exception:
            blocked = False
        if not blocked and not self.set_flipmount_blocked(True, thread):
            print("Record: could not block the beam, so the power meter is dark; pump power not recorded.")
            self.scan_log_event("Pump power NOT recorded: the beam could not be blocked", thread)
            return None

        settle_s = self.ui.pmSettle.value()
        since = self._fm_blocked_since  # None: blocked since before we took over, so the full settle time applies
        remaining = settle_s - (time.monotonic() - since if since is not None else 0.0)
        if remaining > 0:
            print(f"Record: waiting {remaining:.0f} s for the power meter to settle...")
            if not self._sleep_unless_stopped(remaining, thread):
                return None

        n = self.ui.pmAvgNO.value()
        interval_ms = self.ui.pmRefresh.value()
        samples = []
        try:
            for i in range(n):
                if i and not self._sleep_unless_stopped(interval_ms / 1000, thread):
                    return None
                with self.pm_lock:
                    samples.append(self.powermeter.measure_power())
            with self.pm_lock:
                wavelength_nm = self.powermeter.get_wavelength_nm()
        except Exception as e:
            print(f"✗ Record: reading the power meter failed ({type(e).__name__}: {e}); pump power not recorded.")
            self.scan_log_event(f"Pump power NOT recorded: {type(e).__name__}: {e}", thread)
            return None

        samples = np.asarray(samples, dtype=float)
        result = {
            'mean_W': float(samples.mean()),
            'std_W': float(samples.std(ddof=1)) if n > 1 else 0.0,
            'samples_W': samples,
            'wavelength_nm': wavelength_nm,
            'settle_s': settle_s,
            'interval_ms': interval_ms,
            'time': datetime.now().isoformat(timespec='seconds'),
        }
        print(f"Record: pump power {result['mean_W'] * 1e3:.3f} mW ± {result['std_W'] * 1e3:.3f} mW (N={n}).")
        self.scan_log_event(f"Pump power {result['mean_W'] * 1e3:.3f} mW ± {result['std_W'] * 1e3:.3f} mW "
                            f"(N={n}, {wavelength_nm:g} nm)", thread)
        return result

    def save_pump_power(self, pump_power: dict):
        """Write a Record result into the current HDF5 file; scalars as datasets, like the other scan parameters."""
        self.h5_file.create_dataset('pump_power_W', data=pump_power['mean_W'], dtype='f8')
        self.h5_file.create_dataset('pump_power_std_W', data=pump_power['std_W'], dtype='f8')
        self.h5_file.create_dataset('pump_power_samples_W', data=pump_power['samples_W'], dtype='f8')
        self.h5_file.create_dataset('pump_power_wavelength_nm', data=pump_power['wavelength_nm'], dtype='f8')
        self.h5_file.create_dataset('pump_power_settle_s', data=pump_power['settle_s'], dtype='f8')
        self.h5_file.create_dataset('pump_power_interval_ms', data=pump_power['interval_ms'], dtype='f8')
        self.h5_file.create_dataset('pump_power_time', data=pump_power['time'])
    #endregion

    #region move stage and rotary to target positions
    def to_target_position(self, stage_name: str) -> bool:
        
        stage_device = getattr(self, stage_name, None)
        if stage_device is None:
                print(f"Warning: {stage_name} is not connected for moving to target position.")
                return False
            
        try:
            # Thorlabs stages
            ui_target_pos = {
                'stage1': self.ui.stage1SetPos,
                'stage2': self.ui.stage2SetPos,
                'rotary1': self.ui.rot1SetPos,
                'rotary2': self.ui.rot2SetPos,
                'rotary3': self.ui.rot3SetPos
            }.get(stage_name)
            ui_curr_pos = {
                'stage1': self.ui.stage1CurrPos,
                'stage2': self.ui.stage2CurrPos,
                'rotary1': self.ui.rot1CurrPos,
                'rotary2': self.ui.rot2CurrPos,
                'rotary3': self.ui.rot3CurrPos
            }.get(stage_name)
            
            if ui_target_pos is None or ui_curr_pos is None:
                print(f"Warning: UI elements for {stage_name} not found.")
                return False
            
            target_pos = ui_target_pos.value()
            stage_device.move_to(target_pos)
            currPos = stage_device.position()
            ui_curr_pos.setValue(currPos)
            unit = 'mm' if stage_name == 'stage1' else 'deg'
            print(f"{stage_name.capitalize()} moved to position: {currPos} {unit}")
            return True
        except Exception as e:
            print(f"Error moving {stage_name} to target position: {e}")
            return False
        #endregion

    #region move stage and rotary by single step
    def single_move_by_step(self, stage_name: str, direction: int) -> bool:
        
        stage_device = getattr(self, stage_name, None)
        if stage_device is None:
                print(f"Warning: {stage_name} is not connected for single step move.")
                return False
            
        # get step size from UI
        jog_step_box_name = f"{stage_name}JogStep"
        curr_pos_box_name = None
        
        step_size = getattr(self.ui, jog_step_box_name).value() # get step size from UI
        try:
            if stage_name in ['stage1', 'stage2']:
                stage_device.move_by(direction * step_size)
                currPos = stage_device.position()
                curr_pos_box_name = f'{stage_name}CurrPos'
                
            elif stage_name in ['rotary1', 'rotary2', 'rotary3']:
                stage_device.move_by(direction * step_size)
                currPos = stage_device.position()
                if stage_name == 'rotary1':
                    curr_pos_box_name = 'rot1CurrPos'
                elif stage_name == 'rotary2':
                    curr_pos_box_name = 'rot2CurrPos'
                elif stage_name == 'rotary3':
                    curr_pos_box_name = 'rot3CurrPos'
            else:
                print(f"Warning: Unsupported stage name '{stage_name}' for single step move.")
                return False
                
            # update current position display
            if curr_pos_box_name is None:
                print(f"Warning: Current position UI box for {stage_name} not found.")
                return False
            getattr(self.ui, curr_pos_box_name).setValue(currPos)
            print(f"{stage_name} moved by {direction * step_size}. New position: {currPos}")
            return True
        except Exception as e:
            print(f"Error moving {stage_name} by single step: {e}")
            return False
    #endregion

    # Scan recipes contain UI inputs only, never hardware settings or live readouts.
    SCAN_CONFIG_FIELDS = (
        'scanMode', 'ext_info', 'activeLockin1', 'activeLockin2', 'activeStage1', 'activeStage2',
        'activeRot1', 'activeRot2', 'activeRot3', 'activeiTC', 'activeFlipMount', 'activePowerMeter',
        'iPos1', 'iPos2', 'scanRepNO1', 'scanRepNO2', 'iRot1', 'iRot2',
        'iRot3', 'ScanRepNO_R1', 'ScanRepNO_R2', 'Rot_stages_couple', 'pol_cali_mode', 'cali_file_path',
        'wait1', 'wait2', 'wait1multip', 'wait2multip', 'ScanT', 'startT',
        'stepT', 'T_NO', 'Tolerance', 'waitiTC', 'T_stab_cnt', 'WaitSamStable',
        'AutoBlock', 'fmPassCh', 'pmRecord', 'pmSettle', 'pmAvgNO', 'pmRefresh',
    ) + tuple(f'stage{n}Step{s}{suffix}' for n in (1, 2) for s in (1, 2, 3) for suffix in ('', 'NO')) \
      + tuple(f'rotary{n}{suffix}' for n in (1, 2, 3) for suffix in ('Step', 'StepNO'))

    def collect_scan_config(self):
        """Snapshot current scan inputs; live instrument readouts are excluded."""
        values = {}
        for name in self.SCAN_CONFIG_FIELDS:
            box = getattr(self.ui, name)
            if isinstance(box, (QCheckBox, QPushButton)):
                values[name] = box.isChecked()
            elif isinstance(box, (QSpinBox, QDoubleSpinBox)):
                values[name] = box.value()
            elif isinstance(box, QComboBox):
                values[name] = box.currentText()
            else:
                values[name] = box.text()
        values['cali_file_path'] = values['cali_file_path'].strip()
        if values['cali_file_path']:
            values['cali_file_path'] = os.path.abspath(values['cali_file_path'])
        return {'format': 'THz_Emission.scan_config', 'schema_version': 1, 'application_version': '1.8',
                'saved_at': datetime.now().astimezone().isoformat(timespec='seconds'),
                'parameters': values, 'temperature_points_K': list(self.tp_manager.temp_sequence)}

    def validate_scan_config(self, payload, config_dir):
        """Validate everything, including the calibration file, before changing any UI state."""
        if not isinstance(payload, dict) or payload.get('format') != 'THz_Emission.scan_config':
            raise ValueError('This is not a THz Emission scan configuration.')
        if type(payload.get('schema_version')) is not int or payload['schema_version'] != 1:
            raise ValueError('Unsupported scan configuration format version.')
        values = payload.get('parameters')
        if not isinstance(values, dict) or set(values) != set(self.SCAN_CONFIG_FIELDS):
            raise ValueError('The scan parameter list is incomplete or contains unsupported fields.')
        values = values.copy()
        for name, value in values.items():
            box = getattr(self.ui, name)
            valid = False
            if isinstance(box, (QCheckBox, QPushButton)):
                valid = type(value) is bool
            elif isinstance(box, (QSpinBox, QDoubleSpinBox)):
                valid = (type(value) in (int, float) and np.isfinite(value)
                         and box.minimum() <= value <= box.maximum())
                if isinstance(box, QSpinBox):
                    valid = valid and type(value) is int
                elif valid:
                    valid = abs(value - round(value, box.decimals())) <= 1e-9
            elif isinstance(box, QComboBox):
                valid = isinstance(value, str) and box.findText(value) >= 0
            elif isinstance(box, QLineEdit):
                valid = isinstance(value, str) and len(value) <= box.maxLength()
            if not valid:
                raise ValueError(f'Invalid value for {name}: {value!r}')
        if values['Tolerance'] < 0:
            raise ValueError('Temperature tolerance cannot be negative.')
        temperatures = payload.get('temperature_points_K')
        if not isinstance(temperatures, list) or any(
                type(t) not in (int, float) or not np.isfinite(t)
                or not self.ui.targetT.minimum() <= t <= self.ui.targetT.maximum() for t in temperatures):
            raise ValueError('Invalid temperature list (use kelvin within the target-temperature range).')
        cali_table = None
        cali_path = values['cali_file_path'].strip()
        values['cali_file_path'] = cali_path
        if values['pol_cali_mode'] and not cali_path:
            raise ValueError('Manual calibration needs a calibration file.')
        if cali_path:
            path = Path(cali_path)
            if not path.is_absolute():
                path = Path(config_dir) / path
            path = path.resolve()
            if not path.is_file():
                raise ValueError(f'Calibration file not found: {path}')
            data = ScanDataCore.parse_calibration_file(str(path))
            if data is None or data.ndim != 2 or data.shape[1] != 4 or not len(data) or not np.isfinite(data).all():
                raise ValueError(f'Invalid calibration data: {path}')
            cali_table = ScanDataCore.build_cali_table(*data.T)
            values['cali_file_path'] = str(path)
        return values, temperatures.copy(), cali_table

    def apply_scan_config(self, payload, config_dir):
        if self._scanning:
            raise RuntimeError('Scan configuration cannot be imported during a scan.')
        values, temperatures, cali_table = self.validate_scan_config(payload, config_dir)
        old_pass_channel = self.ui.fmPassCh.currentText()
        blockers = [QSignalBlocker(getattr(self.ui, name)) for name in values]
        try:
            for name, value in values.items():
                box = getattr(self.ui, name)
                if isinstance(box, (QCheckBox, QPushButton)):
                    box.setChecked(value)
                elif isinstance(box, (QSpinBox, QDoubleSpinBox)):
                    box.setValue(value)
                elif isinstance(box, QComboBox):
                    box.setCurrentText(value)
                else:
                    box.setText(value)
            self.tp_manager.temp_sequence = temperatures
            self.tp_manager.update_list_widget()
            self.cali_table = cali_table
        finally:
            del blockers
        # Synchronize derived software state explicitly, without calling hardware handlers.
        self.setup_scan_mode()
        for handler, field in (('on_pol_cali_mode_toggled', 'pol_cali_mode'),
                               ('on_rot_stages_couple_toggled', 'Rot_stages_couple')):
            getattr(self, handler)(values[field])
        for index in (1, 2):
            self.chart_updaters[f'realDisChart{index}'].update_Interval(values[f'wait{index}'])
        self.itc_updater.update_Interval(values['waitiTC'])
        self.pm_timer.setInterval(values['pmRefresh'])
        if old_pass_channel != values['fmPassCh']:
            self.show_flipmount_state(None)
            self._fm_blocked_since = None

    def export_scan_config(self, file_path=None):
        output = None
        try:
            if file_path is None:
                suggested = os.path.join(self.dataSave_path,
                    f"{datetime.now():%Y%m%d_%H%M%S}_{self.ui.scanMode.currentText()}_config.json")
                file_path, _ = QFileDialog.getSaveFileName(self.ui, 'Export scan configuration', suggested,
                                                         'JSON configuration (*.json)')
            if not file_path:
                return None
            file_path = os.path.abspath(file_path)
            if not file_path.lower().endswith('.json'):
                file_path += '.json'
            payload = self.collect_scan_config()
            self.validate_scan_config(payload, os.path.dirname(file_path))
            content = (json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf-8')
            output = QSaveFile(file_path)
            if not output.open(QIODevice.WriteOnly):
                raise OSError(output.errorString())
            if output.write(content) != len(content) or not output.commit():
                raise OSError(output.errorString() or 'Could not save the complete configuration.')
            self.ui.statusbar.showMessage(f'Scan configuration exported: {file_path}', 8000)
            return file_path
        except Exception as e:
            if output is not None:
                output.cancelWriting()
            QMessageBox.warning(self.ui, 'Export scan configuration', f'Could not export configuration:\n\n{e}')
            return None

    def import_scan_config(self, file_path=None):
        try:
            if self._scanning:
                raise RuntimeError('Scan configuration cannot be imported during a scan.')
            if file_path is None:
                file_path, _ = QFileDialog.getOpenFileName(self.ui, 'Import scan configuration', self.dataSave_path,
                                                         'JSON configuration (*.json)')
            if not file_path:
                return False
            with open(file_path, 'r', encoding='utf-8-sig') as stream:
                payload = json.load(stream)
            self.apply_scan_config(payload, os.path.dirname(os.path.abspath(file_path)))
            self.ui.statusbar.showMessage(f'Scan configuration imported: {file_path}', 8000)
            return True
        except Exception as e:
            QMessageBox.warning(self.ui, 'Import scan configuration', f'Could not import configuration:\n\n{e}')
            return False

    def save_ui_screenshot(self):
        """Save the visible UI beside the current/latest data file, without changing scan state."""
        output = None
        try:
            data_path = getattr(self, 'fullFilePath', None)
            if data_path:
                image_path = os.path.splitext(data_path)[0] + '.png'
            else:
                # Before the first data file, follow this system's naming convention.
                name = datetime.now().strftime('%Hh%Mm%Ss') + '_' + self.ui.scanMode.currentText()
                extra = self.get_ext_info()
                if extra:
                    name += '_' + extra
                image_path = os.path.join(self.dataSave_path, name + '.png')
            image_path = os.path.abspath(image_path)
            os.makedirs(os.path.dirname(image_path), exist_ok=True)
            pixmap = self.ui.grab()
            if pixmap.isNull():
                raise RuntimeError('The application interface could not be captured.')
            # Replace an earlier PNG only after the new image has been written successfully.
            output = QSaveFile(image_path)
            if not output.open(QIODevice.WriteOnly):
                raise OSError(output.errorString())
            if not pixmap.save(output, 'PNG'):
                raise OSError('Could not encode or write the PNG image.')
            if not output.commit():
                raise OSError(output.errorString())
            self.ui.statusbar.showMessage(f'Screenshot saved: {image_path}', 8000)
            print(f'Screenshot saved: {image_path}')
            return image_path
        except Exception as e:
            if output is not None:
                output.cancelWriting()
            QMessageBox.warning(self.ui, 'Screenshot failed', f'Could not save the screenshot:\n\n{e}')
            return None

    #region Setup data folder for saving data
    def setup_data_folder(self) -> str | None:
        try:
            current_script_dir = os.path.dirname(os.path.abspath(__file__))
            print(f"Current script directory: {current_script_dir}")
            
            parent_dir = os.path.dirname(current_script_dir)
            
            data_save_dir = os.path.join(parent_dir, 'THz_emission_Data')
            if not os.path.exists(data_save_dir):
                os.makedirs(data_save_dir)
                print(f"Created THz_emission_Data folder: {data_save_dir}")
            else:
                print(f"THz_emission_Data folder already exists: {data_save_dir}")
                
            now = datetime.now()
            month_name = now.strftime("%B")  # Full month name
            month_dir = os.path.join(data_save_dir, month_name)
            
            if not os.path.exists(month_dir):
                os.makedirs(month_dir)
                print(f"Created month folder: {month_dir}")
            else:
                print(f"Month folder already exists: {month_dir}")
                
            day_str = now.strftime("%d")
            day_folder_name = f"{month_name}_{day_str}"
            day_dir = os.path.join(month_dir, day_folder_name)  
            
            if not os.path.exists(day_dir):
                os.makedirs(day_dir)
                print(f"Created day folder: {day_dir}")
            else:
                print(f"Day folder already exists: {day_dir}")
            
            # display the data folder path in UI
            file_path_box = getattr(self.ui, 'dataSavePath', None)
            if file_path_box:
                file_path_box.setText(day_dir)
                self.dataSave_path = day_dir
                print(f"Data save path set in UI: {day_dir}")
            else:
                print("Warning: dataSavePath box not found in UI.")
            return day_dir
        
        except Exception as e:
            print(f"Error setting up data folder: {e}")
            import traceback
            traceback.print_exc()
            return None
        # endregion
        
    #region Display time h-m-s for 'dataFileName' box
    def get_ext_info(self) -> str:
        """Return the extra-info suffix, stripped of characters that are illegal in file names.

        Returns an empty string when the box is empty (an untouched box only shows placeholder
        text, which text() does not return).
        """
        raw = self.ui.ext_info.text().strip()
        if not raw:
            return ''

        # Windows forbids \ / : * ? " < > | in file names; replace them so h5py.File() cannot fail.
        safe = re.sub(r'[\\/:*?"<>|]', '_', raw)
        safe = safe.strip(' .')  # trailing spaces/dots are also invalid on Windows
        if safe != raw:
            print(f"Extra info sanitized for file name: '{raw}' -> '{safe}'")
        return safe

    def setup_dataFile_Name(self, add_str: str | None = None) -> str | None:
        try:
            # get current time h-m-s
            now = datetime.now()
            time_stamp = now.strftime('%Hh%Mm%Ss')
            file_name_timePart = f'{time_stamp}'
            print(f"Current time part for file name: {file_name_timePart}")

            # display time part in dataFileName QLineEdit
            data_file_name_box = getattr(self.ui, "dataFileName", None)
            if data_file_name_box:
                data_file_name_box.setText(file_name_timePart)

            data_file_name = f"{file_name_timePart}_{add_str}" if add_str else f"{file_name_timePart}"

            # append the extra-info suffix from the ext_info box, if any
            ext_info = self.get_ext_info()
            if ext_info:
                data_file_name = f"{data_file_name}_{ext_info}"

            print(f"File name updated: {data_file_name}")

            return data_file_name

        except Exception as e:
            print(f"Error updating file name: {e}")
            return None
    #endregion
    
    #region Customize data save path
    def customize_data_save_path(self) -> str:
        
        try:
        # open folder selection dialog
            folder_path = QFileDialog.getExistingDirectory(
                self.ui,
                "Select Data Save Path",  # title of dialog window
                os.path.expanduser("~"),  # 初始打开位置 (用户主目录)
                QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
            )
            
            # if choose "cancel", 
            if not folder_path:
                print("User cancelled - keeping previous settings")
                return ""
            
            print(f"\nUser selected folder: {folder_path}")

            # Display selected folder in dataSavePath QLineEdit
            data_save_path_box = getattr(self.ui, 'dataSavePath', None)
            if data_save_path_box is not None:
                data_save_path_box.setText(folder_path)
                self.dataSave_path = folder_path
                self.is_custom_save_path = True
                print(f"✓ Save path displayed in 'dataSavePath' QLineEdit: {folder_path}\n")
            else:
                print(f"Warning: dataSavePath box 'dataSavePath' not found in UI")
            
            return folder_path
        
        except Exception as e:
            print(f" Error browsing for save path: {e}")
            import traceback
            traceback.print_exc()
            return ""
    #endregion
        
    #region Initialize and Choose scan mode
    # initialize scanMode combobox
    def _init_scanMode_combobox(self):
        """
        'THz_Scan': time-domain scan; loop order rotation stages (outermost) -> stage2 -> stage1 (swept innermost);
        '2D_THz': one full time-domain trace at each optical pump delay; same loop order as 'THz_Scan';
        'THz_pol': polarization dependent scan; loop order stage2 (outermost) -> stage1 -> rotation stages (innermost);
        """
        scan_modes = ['THz_Scan', '2D_THz', 'THz_pol']
        self.ui.scanMode.addItems(scan_modes)
        
        self.test_mode = scan_modes[0]  # default to first mode THz_Scan
            
    # Choose and update scan mode
    def setup_scan_mode(self):
        mode = self.ui.scanMode.currentText()
        self.test_mode = mode    # update current scan mode
        print(f"Scan mode set to: {mode}")
    #endregion    

    #region Get step array for each stage
    def get_step_array(self, stageName: str) -> np.ndarray:
        step_sizes = []
        steps_NO = []
        input_unit = 'mm'

        # Collect step info. from UI
        if stageName in ['stage1', 'stage2']:
            input_unit = 'um'
            for i in range (1, 4):    # up to 3 stepSize
                step_box_name = f'{stageName}Step{i}'
                step_value = getattr(self.ui, step_box_name).value()
                step_sizes.append(float(step_value))
                
                stepNO_box_name = f'{stageName}Step{i}NO'
                stepNO_value = getattr(self.ui, stepNO_box_name).value()
                steps_NO.append(int(stepNO_value))
                
        elif stageName in ['rotary1', 'rotary2', 'rotary3']:
            input_unit = 'deg'
            step_box_name = f'{stageName}Step'
            step_value = getattr(self.ui, step_box_name).value()
            step_sizes.append(float(step_value))
            
            stepNO_box_name = f'{stageName}StepNO'
            stepNO_value = getattr(self.ui, stepNO_box_name).value()
            steps_NO.append(int(stepNO_value))

        return ScanDataCore.build_step_array(step_sizes, steps_NO, input_unit=input_unit)
        #endregion

    #region Import calibration sequences for rotary stages in polarization/intensity dependent scans
    # on_pol_cali_mode_toggled event
    def on_pol_cali_mode_toggled(self, checked: bool):
        self.ui.pol_cali_mode.setText('Manu. Cali.' if checked else 'Auto Cali.')

    # on_rot_stages_couple_toggled event
    def on_rot_stages_couple_toggled(self, checked: bool):
        self.ui.Rot_stages_couple.setText('Coupled' if checked else 'Independent')
    
    # Import calibration file
    def import_calibration_file(self, interp_cali_data: bool = False) -> dict | None:
        if not self.ui.pol_cali_mode.isChecked():
            QMessageBox.information(self.ui, "Calibration", 
                                    "Please switch Cali. button into 'Manu. Cali.' before importing Cali. file.")
            return
        
        # Import calibration file
        cali_file_path, _ = QFileDialog.getOpenFileName(
            self.ui,
            "Select Calibration File",
            "",
            "CSV Files (*.csv);;Text Files (*.txt);;All Files (*)"
        )
        if not cali_file_path:
            return
        
        # Display selected file path in UI
        if hasattr(self.ui, 'cali_file_path'):
            self.ui.cali_file_path.setText(cali_file_path)
            print(f"Calibration file path set in UI: {cali_file_path}")
            
        # Read calibration data from file
        try:
            data = ScanDataCore.parse_calibration_file(cali_file_path)
            if data is None:
                QMessageBox.warning(self.ui, "Calibration", "No valid data found in calibration file.")
                return
            
            rot1, rot2, rot3, power = data.T  # transpose to get each column

            self.cali_table = ScanDataCore.build_cali_table(
                rot1=rot1,
                rot2=rot2,
                rot3=rot3,
                power=power,
                interp_cali_data=interp_cali_data,
            )

            cali_points = len(self.cali_table['rot2_cali'])
            if interp_cali_data:
                print(f"Calibration data imported and interpolation done from file: {cali_file_path}, total {cali_points} points.")
            else:
                print(f"Calibration data imported from file: {cali_file_path}, total {cali_points} unique points.")
            return self.cali_table
            
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self.ui, "Calibration", f"Error reading calibration file: {e}")
    #endregion
    
    #region iTC_go_to_target temperature function
    def _set_autoPID_button(self, state: bool):
        """Set the Auto PID button and LED to `state` without re-entering setup_pid_mode().

        The button is checkable and latches on click, so a rejected or unattempted change would
        otherwise leave it advertising a mode the instrument never entered - and set_heater_percent()
        reads the button, not the LED, when deciding whether manual heater control is allowed.
        """
        self.ui.autoPID.blockSignals(True)
        self.ui.autoPID.setChecked(state)
        self.ui.autoPID.blockSignals(False)
        self.ui.autoPID_led.status = state

    def _sync_autoPID_from_instrument(self):
        """Match the Auto PID button and LED to the loop state the controller actually holds.

        The button was only ever a local flag - nothing read the controller back - so a session
        started while the iTC was still in PID mode showed 'Manual' while the loop was in fact
        driving the heater, and any manual heater setting was silently overridden by it.
        """
        if self.uid_TEMP is None:
            return
        try:
            with self.mercuryiTC.io_lock:
                pid_on = self.mercuryiTC.get_pid_control_state(self.uid_TEMP)
        except Exception as e:
            print(f"Warning: could not read MercuryiTC PID state ({e}); Auto PID button left as-is.")
            return
        self._set_autoPID_button(pid_on)   # reflect the instrument, do not re-issue the command
        print(f"MercuryiTC PID loop is currently {'ON (Auto)' if pid_on else 'OFF (Manual)'}; Auto PID button synced.")

    def setup_pid_mode(self, checked: bool) -> bool:
        if not (self.ui.activeiTC.isChecked() and self.mercuryiTC):
            print("Warning: MercuryiTC is not connected for setting PID mode.")
            self._set_autoPID_button(not checked)  # the click latched the button; undo it
            return False
                        
        accepted = self.itc_updater.setup_autoPID_mode(checked)
        if not accepted:
            self._set_autoPID_button(not checked)
            print(f"iTC PID mode unchanged - the instrument rejected '{'Auto' if checked else 'Manual'}'.")
            return False
        self.ui.autoPID_led.status = checked  # setup auto PID mode indicator
        
        print(f"iTC PID mode set to {'Auto' if checked else 'Manual'}.")
        return True
        
        
    def iTC_goto_targetT(self, targetT: float, update_ui: bool = True) -> bool:
        """
        Read UI parameters and start iTCStabilizerThread.
        - targetT: target temperature (K)
        - Tolerance: tolerance (K)
        - waitiTC: polling interval (seconds)

        Returns True only when a stabilization thread was actually started, so callers can tell
        whether it is safe to wait on self.itc_stab_thread.
        """
        if not (self.ui.activeiTC.isChecked() and self.mercuryiTC):
            print("Warning: MercuryiTC is not connected for going to target temperature.")
            return False
        if self.uid_TEMP is None:
            print("Warning: Temperature UID is unavailable for setting target temperature.")
            return False

        target_T  = targetT
        tolerance = self.ui.Tolerance.value()
        waitiTC   = self.ui.waitiTC.value()       # in seconds
        stab_cnt  = self.ui.T_stab_cnt.value()    # number of stable counts required        
       
        if update_ui:
            self.ui.TempDone.status = False           # reset TempDone indicator
            QApplication.processEvents()  # Ensure UI updates immediately
            
        # setup and goto targetT
        with self.mercuryiTC.io_lock:  # ensure thread-safe access to MercuryiTC
            T_set  = self.mercuryiTC.set_temp_point(self.uid_TEMP, target_T)
            
        # ensure any previous stabilization thread is fully stopped before creating a new one
        # (prevents "QThread: Destroyed while thread is still running" when called repeatedly).
        # If the old thread is still polling toward its own target, ask it to exit instead of
        # blocking this (GUI) thread indefinitely until it happens to stabilize on its own -
        # that unbounded wait() was freezing the UI whenever "Goto T" was clicked while a
        # previous stabilization was still in progress (e.g. right after a scan finished).
        if self.itc_stab_thread is not None:
            if self.itc_stab_thread.isRunning():
                self.itc_stab_thread.stop_flag = True  # stop only this stale thread, without touching self.stop_flag
            if not self.itc_stab_thread.wait(2000):
                print("Warning: previous iTC stabilization thread did not stop within 2 s; proceeding anyway.")

        # create and start iTCStabilizerThread
        self.itc_stab_thread = iTCstabilizeThread(self, target_T, tolerance, waitiTC, stab_cnt)

        # connect signal
        if update_ui:
            self.itc_stab_thread.finished.connect(self.on_temp_done)

        self.itc_stab_thread.error.connect(lambda msg: print(f"iTC Stabilization Error: {msg}"))

        # start thread
        self.itc_stab_thread.start()
        print(f"Started iTC stabilization thread to reach {target_T} K with tolerance {tolerance} K.")
        return True
        
                            
    def on_tolerance_changed(self):
        """ Set tolerance for iTC stabilization."""
        try:
            new_tolerance = float(self.ui.Tolerance.value())
        except Exception:
            return
        
        # if the stabilization thread is running, update its tolerance
        if self.itc_stab_thread is not None and self.itc_stab_thread.isRunning():
            self.itc_stab_thread.set_tolerance(new_tolerance)
            print(f"Updated iTC stabilization tolerance to: {new_tolerance} K")
        else:
            # not running, next time start, use new tolerance anyway
            print(f"Tolerance set to: {new_tolerance} K for next iTC stabilization.")
    
            
    # add temperature points event handler
    def on_add_T_points(self):
        """Handle adding temperature points from input."""
        startT = float(self.ui.startT.value())
        stepT  = float(self.ui.stepT.value())
        T_NO   = int(self.ui.T_NO.value())
        self.tp_manager.add_sequence(startT, stepT, T_NO)
        self.tp_manager.update_list_widget()
   
    @Slot(int)    
    def update_temp_hightlight(self, index: int):
        """Highlight the temperature point at the given index in the UI list."""
        try:
            self.tp_manager.highlight_T_point(index)
            QApplication.processEvents()  # Ensure UI updates immediately
            print(f"Highlighted temperature point at index: {index + 1}")
        except Exception as e:
            print(f"Error highlighting temperature point at index {index}: {e}")
            import traceback
            traceback.print_exc()
    
    @Slot(bool)        
    def on_temp_done(self, is_done: bool):
        """Handle temperature stabilization done event."""
        try:
            self.ui.TempDone.status = is_done
            QApplication.processEvents()  # Ensure UI updates immediately
            status_str = "done" if is_done else "not done"
            print(f"Temperature stabilization is {status_str}.")
        except Exception as e:
            print(f"Error updating temperature done status: {e}")

    
    #endregion

    #region Extra soak wait for the sample to reach the sensor temperature
    def wait_sample_stable(self, thread=None) -> bool:
        """Hold for the extra sample-soak time set in the WaitSamStable box (minutes).

        The iTC sensor stabilizing does not mean the sample has: it lags behind, and scanning
        too early leaves residual thermal expansion. Counts down in 5 s steps and stays
        responsive to a stop request.

        Returns False when a stop was requested during the wait, True otherwise.
        """
        wait_min = float(self.ui.WaitSamStable.value())
        if wait_min <= 0:
            print("Sample soak wait is 0 min; continuing immediately.")
            return True

        total_s = int(round(wait_min * 60))
        tick_s = 5  # countdown print interval
        print(f"Temperature sensor stable. Waiting {wait_min:g} min ({total_s} s) "
              f"for the sample to reach thermal equilibrium...")

        remaining = total_s
        while remaining > 0:
            if self._check_scan_stop(thread):
                print(f"Sample soak wait interrupted with {remaining} s remaining.")
                return False

            sleep_s = min(tick_s, remaining)
            time.sleep(sleep_s)
            remaining -= sleep_s

            mins, secs = divmod(remaining, 60)
            print(f"Sample soak countdown: {mins:02d}:{secs:02d} remaining "
                  f"({remaining}/{total_s} s)")

        print("Sample soak wait complete. Proceeding with the scan.")
        return True
    #endregion

    #region Calibrate TDS peak position at each temperature point
    def _check_scan_stop(self, thread=None) -> bool:
        """Return True when a stop request has been issued for the current scan workflow."""
        if self.stop_flag:
            print("Scan stop flag detected by main controller. Exiting current operation.")
            return True
        if thread is not None and getattr(thread, 'stop_flag', False):
            print("Scan stop flag detected by scan thread. Exiting current operation.")
            return True
        return False

    def get_TDS_peak_pos(self, thread=None) -> dict:
        tds_max_positions = {
            'status': 'failed',
            'max_position': None,
            'max_lockin1X': None,
            'positions': [],
            'lockin1X': []
        }
        
        if not (self.ui.activeStage1.isChecked() and self.stage1):
            print("Warning: Stage1 is not connected for TDS scan.")
            return tds_max_positions
        if not (self.ui.activeLockin1.isChecked() and self.lockin1):
            print("Warning: Lockin1 is not connected for TDS scan.")
            return tds_max_positions
        
        if self._check_scan_stop(thread):
            return {
                'status': 'stopped',
                'max_position': None,
                'max_lockin1X': None,
                'positions': [],
                'lockin1X': []
            }
        
        # Use the current iPos1 value as the center and scan around it using stage1's configured step size.
        center_pos = float(getattr(self.ui, 'iPos1').value())
        step_mm = None
        for step_idx in range(1, 4):
            step_box_name = f'stage1Step{step_idx}'
            step_value = getattr(self.ui, step_box_name).value()
            if step_value != 0:
                step_mm = float(step_value / 1000.0)
                break
        if step_mm is None or step_mm <= 0:
            step_mm = 0.001  # default step size in mm

        wait_time_ms = self.ui.wait1.value() / 1000  # wait time in seconds from UI

        def run_single_pass(pass_no: int, pass_center: float, pass_step: float) -> dict:
            """Scan the local window once around pass_center and return the analyzed peak result."""
            # +/-30 steps around the centre -> exactly 60 positions (offsets -30 .. +29)
            pos_seq_stage1 = ScanDataCore.build_peak_tracking_positions(
                pass_center, pass_step, points_before_center=30, points_after_center=30
            )
            peak_samples = []

            def stopped_peak_result() -> dict:
                result = ScanDataCore.analyze_peak_samples(peak_samples)
                result['status'] = 'stopped'
                result['max_position'] = None
                result['max_lockin1X'] = None
                return result

            total = len(pos_seq_stage1)
            for idx, pos in enumerate(pos_seq_stage1, 1):
                if self._check_scan_stop(thread):
                    print("Peak-tracking scan interrupted before moving to the next stage position.")
                    return stopped_peak_result()

                print(f"TDS/peak-tracking round {pass_no}/2 progress: {idx}/{total} positions...")
                try:
                    self.stage1.move_to(pos)
                except Exception as e:
                    print(f"Error moving Stage1 to position {pos} mm during TDS scan: {e}")
                    continue

                # update curr NO / curr position displays during peak-tracking scan
                if thread is not None:
                    thread.stepNO_update.emit({'stage1_NO': idx})
                    thread.position_update.emit({'stage1_pos': round(self.stage1.position(), 3)})

                time.sleep(wait_time_ms)  # wait for stage to settle

                # Take a single reading per position; the coarse round localises the peak and the
                # fine round refines it.
                if self._check_scan_stop(thread):
                    print("Peak-tracking scan interrupted during sampling.")
                    return stopped_peak_result()

                try:
                    x_val = float(self.lockin1.get_x())
                except Exception as e:
                    print(f"Error reading Lockin1 X value at position {pos} mm during TDS scan: {e}")
                    x_val = np.nan

                peak_samples.append((pos, [x_val]))

                # show this position's reading live in the realtime Lock-in 1 X chart
                if thread is not None and np.isfinite(x_val):
                    thread.lockin_update.emit({'l1x': x_val})

            return ScanDataCore.analyze_peak_samples(peak_samples)

        # Two-round coarse-to-fine search.
        # Round 1 sweeps with COARSE_STEP_FACTOR x the step, covering +/-30*N steps instead of
        # +/-30, so the peak is still found after the large thermal expansion that comes with a
        # wide temperature range. The factor stays small because this is an ultra-broadband THz
        # pulse (~40 fs FWHM, only ~6 um of stage travel): a large coarse step would sample right
        # over the top of the peak and miss it.
        # Round 2 re-centres on the coarse result and refines at the normal step.
        COARSE_STEP_FACTOR = 3

        tds_max_positions = {'status': 'failed', 'max_position': None, 'max_lockin1X': None, 'positions': [], 'lockin1X': []}
        for pass_no in range(1, 3):
            pass_step = step_mm * COARSE_STEP_FACTOR if pass_no == 1 else step_mm
            pass_kind = 'coarse' if pass_no == 1 else 'fine'
            print(
                f"Peak-tracking round {pass_no}/2 ({pass_kind}): step {pass_step * 1000:.3f} um, "
                f"range +/-{30 * pass_step * 1000:.1f} um around {center_pos} mm."
            )

            tds_max_positions = run_single_pass(pass_no, center_pos, pass_step)
            if tds_max_positions['status'] != 'ok':
                print(f"Peak-tracking round {pass_no}/2 ({pass_kind}) found no valid peak; stopping search.")
                return tds_max_positions
            center_pos = tds_max_positions['max_position']
            print(
                f"Peak-tracking round {pass_no}/2 ({pass_kind}) complete. Max Lockin1 X: "
                f"{tds_max_positions['max_lockin1X']} at position: {center_pos} mm."
            )

        print(
            f"TDS scan complete after 2 rounds. Max Lockin1 X: {tds_max_positions['max_lockin1X']} "
            f"at position: {tds_max_positions['max_position']} mm."
        )

        return tds_max_positions  # in mm
    
    def update_iPos1_from_tds_peak(self, new_pos: float):
        """Update iPos1 in UI from TDS peak position."""
        try:
            self.ui.iPos1.setValue(new_pos)
            print(f"Updated iPos1 to TDS peak position: {new_pos} mm.")
        except Exception as e:
            print(f"Error updating iPos1 from TDS peak position: {e}")
    #endregion
     
    #region Move active stages and display current positions
    def move_active_stages(self, target_positions: tuple):
        
        stage1_pos, stage2_pos, rotary1_pos, rotary2_pos, rotary3_pos = target_positions
        
        # Initialize current positions with placeholder (-1)
        currStage1Pos = -1; currStage2Pos = -1
        currRotary1Pos = -1; currRotary2Pos = -1
        currRotary3Pos = -1
        
        # Names the axis being commanded, so a driver exception can say which one failed instead of
        # just "Error moving active stages" - the controllers raise without naming themselves.
        moving_axis = None
        try:
            # move Stage1 if active
            if self.ui.activeStage1.isChecked() and self.stage1:
                moving_axis = f"Stage1 to {stage1_pos} mm"
                self.stage1.move_to(stage1_pos) # in mm
                currStage1Pos = round(self.stage1.position(), 3)  # # update current position display in mm

            # move Stage2 if active
            if self.ui.activeStage2.isChecked() and self.stage2:
                moving_axis = f"Stage2 to {stage2_pos} mm"
                self.stage2.move_to(stage2_pos) # in mm
                currStage2Pos = round(self.stage2.position(), 3)  # update current position display in mm

            # move Rotary1 if active
            if self.ui.activeRot1.isChecked() and self.rotary1:
                moving_axis = f"Rotary1 to {rotary1_pos} deg"
                self.rotary1.move_to(rotary1_pos)
                currRotary1Pos = round(self.rotary1.position(), 3)  # update current position display in degrees

            # move Rotary2 if active
            if self.ui.activeRot2.isChecked() and self.rotary2:
                moving_axis = f"Rotary2 to {rotary2_pos} deg"
                self.rotary2.move_to(rotary2_pos)
                currRotary2Pos = round(self.rotary2.position(), 3)  # update current position display in degrees
            
            # move Rotary3 if active
            if self.ui.activeRot3.isChecked() and self.rotary3:
                moving_axis = f"Rotary3 to {rotary3_pos} deg"
                self.rotary3.move_to(rotary3_pos)
                currRotary3Pos = round(self.rotary3.position(), 3)  # update current position display in degrees

            currPositions = (currStage1Pos, currStage2Pos, currRotary1Pos, currRotary2Pos, currRotary3Pos)

            return True, currPositions
        except Exception as e:
            print(f"Error moving {moving_axis or 'active stages'}: {e}")
            return False, None
        #endregion
    
    #region Stop_Scan flag and message function
    def stopscan(self):
        """ Stop the ongoing scan process."""
        # pop up confirmation dialog
        reply = QMessageBox.question(self.ui, 'Confirm Stop', 'Are you sure you want to stop the scan?\n\nCurrent progress will be saved.',
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No) # default is No

        if reply == QMessageBox.Yes:
            # stop the threaded scan by setting stop flag
            if self.scan_Thread and self.scan_Thread.isRunning():
                self.scan_Thread.request_stop()  # request stop for scan thread
                self.scan_Thread.wait(2000)  # wait for scan thread to finish
                
            # stop the itc stabilization thread if running
            if self.itc_stab_thread is not None and self.itc_stab_thread.isRunning():
                self.itc_stab_thread.request_stop()  # request stop for itc stabilization thread
                self.itc_stab_thread.wait(2000)  # wait for itc stabilization thread to finish
                
                
                
            self.stop_flag = True  # set stop flag to True
            print("Stopping scan... Scan will terminate at next checkpoint... Please wait for current operation to finish.")
            
        else:
            print("Scan continue...")

    #endregion
    
    #region Exiting application function 
    def exitApp(self):
        # pop up a confirmation dialog
        reply = QMessageBox.question(self.ui, 'Confirm Exit', 'Exit the program and close all instruments?',
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No) # default is No
        
        # further action based on user choice
        if reply == QMessageBox.Yes:
            print("Closing all instruments and exiting application...")
            self.stopscan()  # stop scan if running
            # only_active=False on exit: anything still open must be released even if its 'active'
            # box was unticked, otherwise the port stays locked after the application is gone.
            self.closeInstruments(only_active=False)  # close all instruments first

            app = QApplication.instance()
            if app:
                app.quit()  # then exit application
            
        else:
            print("Exit cancelled.")
    #endregion                   
                
    #region Scan log: test conditions and key events, shown in the ScanLog box and appended to a per-day file
    def start_scan_log(self):
        """Open a new block in the day's scan log and write the scan's test conditions (GUI thread only).

        Only instruments that are ticked and connected are listed. Point-by-point readings and other
        progress prints are deliberately not logged.
        """
        ui = self.ui
        now = datetime.now()
        self._scan_log_start = now
        self._scan_log_ended = False
        self._scan_abort_reason = None
        self._scan_log_path = os.path.join(self.dataSave_path, f"ScanLog_{now:%Y-%m-%d}.txt")

        def in_use(box_name: str, attr_name: str) -> bool:
            return getattr(ui, box_name).isChecked() and getattr(self, attr_name) is not None

        lines = ["", "=" * 72, f"Scan started {now:%Y-%m-%d %H:%M:%S}", "-" * 72,
                 f"Mode        : {ui.scanMode.currentText()}"]
        ext_info = ui.ext_info.text().strip()
        if ext_info:
            lines.append(f"Extra info  : {ext_info}")
        lines.append(f"Save folder : {self.dataSave_path}")

        for n in (1, 2):
            if in_use(f'activeLockin{n}', f'lockin{n}'):
                lines.append(f"Lock-in {n}   : sens {getattr(ui, f'sensitivity{n}').currentText()}, "
                             f"TC {getattr(ui, f'timeConst{n}').currentText()}, wait {getattr(ui, f'wait{n}').value()} ms")

        for n, rep_box in ((1, 'scanRepNO1'), (2, 'scanRepNO2')):
            if in_use(f'activeStage{n}', f'stage{n}'):
                steps = [f"{getattr(ui, f'stage{n}Step{i}').value():g} um x {getattr(ui, f'stage{n}Step{i}NO').value()}"
                         for i in (1, 2, 3) if getattr(ui, f'stage{n}Step{i}NO').value() > 0]
                lines.append(f"Stage{n}      : start {getattr(ui, f'iPos{n}').value()} mm, "
                             f"steps {', '.join(steps) or 'none'}, repeat {getattr(ui, rep_box).value()}")

        rotaries = [n for n in (1, 2, 3) if in_use(f'activeRot{n}', f'rotary{n}')]
        for n in rotaries:
            lines.append(f"Rotary{n}     : start {getattr(ui, f'iRot{n}').value()} deg, "
                         f"step {getattr(ui, f'rotary{n}Step').value():g} deg x {getattr(ui, f'rotary{n}StepNO').value()}")
        if rotaries:
            # same rule as the scan: a loaded calibration table forces coupled
            cali_active = bool(ui.pol_cali_mode.isChecked() and self.cali_table)
            rot_mode = 'Coupled' if (ui.Rot_stages_couple.isChecked() or cali_active) else 'Independent'
            if cali_active:
                rot_mode += f", calibration {os.path.basename(ui.cali_file_path.text())}"
            lines.append(f"Rotation    : {rot_mode}, repeat R1 {ui.ScanRepNO_R1.value()} / R2 {ui.ScanRepNO_R2.value()}")

        temps = self.tp_manager.temp_sequence
        if in_use('activeiTC', 'mercuryiTC') and ui.ScanT.isChecked() and len(temps) > 0:
            lines.append(f"Temperature : {', '.join(f'{t:g}' for t in temps)} K "
                         f"(tolerance {ui.Tolerance.value():g} K, sample soak {ui.WaitSamStable.value():g} min)")
        else:
            lines.append("Temperature : no temperature scan")

        if ui.AutoBlock.isChecked():
            lines.append(f"AutoBlock   : on ({ui.fmPassCh.currentText()})")
        if ui.pmRecord.isChecked():
            if ui.AutoBlock.isChecked():
                lines.append(f"Pump power  : Record on (settle {ui.pmSettle.value()} s, N {ui.pmAvgNO.value()} "
                             f"x {ui.pmRefresh.value()} ms, {ui.pmWavelength.value()} nm)")
            else:
                lines.append("Pump power  : Record is on but AutoBlock is off, so nothing is recorded")
        lines.append("-" * 72)

        self.append_scan_log("\n".join(lines))

    def scan_log_event(self, message: str, thread=None):
        """Log one timestamped key event. From the scan thread it goes through the thread's signal."""
        line = f"[{datetime.now():%H:%M:%S}] {message}"
        if thread is not None:
            thread.scan_log.emit(line)
        else:
            self.append_scan_log(line)

    def start_console_mirror(self):
        """Mirror stdout/stderr into the Live Process box from program start until it quits.

        The terminal still gets every line and nothing is written to disk. print() may come from any
        thread; the text reaches the box through a queued signal. The box keeps the latest 1000 lines
        (maximumBlockCount in the .ui) and is not cleared between scans.
        """
        self._console_signal = ConsoleSignal()
        self._console_signal.text.connect(self.append_console_text, Qt.QueuedConnection)
        self._console_streams = []
        for name in ('stdout', 'stderr'):
            terminal = getattr(sys, name)
            stream = ConsoleMirrorStream(terminal, self._console_signal.text.emit)
            self._console_streams.append((name, terminal, stream))
            setattr(sys, name, stream)
        # hand the streams back before the widgets are destroyed, so prints during shutdown still work
        QApplication.instance().aboutToQuit.connect(self.stop_console_mirror)

    def stop_console_mirror(self):
        for name, terminal, stream in self._console_streams:
            with stream.lock:
                stream.emit = None
                if getattr(sys, name) is stream:
                    setattr(sys, name, terminal)
        self._console_streams.clear()

    @Slot(str)
    def append_console_text(self, text: str):
        # This slot runs on the GUI thread; print() may originate in any thread.
        edit = self.ui.scanProgressText
        cursor = edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        edit.setTextCursor(cursor)
        edit.ensureCursorVisible()

    def append_scan_log(self, text: str):
        """Show text in the ScanLog box and append it to the day's log file (GUI thread only)."""
        self.ui.scanLogText.appendPlainText(text)
        path = getattr(self, '_scan_log_path', None)
        if not path:
            return
        try:
            with open(path, 'a', encoding='utf-8') as f:  # opened per write, so every line is on disk at once
                f.write(text + "\n")
        except OSError as e:
            print(f"Warning: could not write scan log {path}: {e}")

    def end_scan_log(self, result: str):
        """Close the current scan block with how it ended and how long it took. Only the first call counts."""
        if getattr(self, '_scan_log_ended', True):
            return
        self._scan_log_ended = True
        elapsed = int((datetime.now() - self._scan_log_start).total_seconds())
        hours, rest = divmod(elapsed, 3600)
        self.scan_log_event(f"{result} (duration {hours}:{rest // 60:02d}:{rest % 60:02d})")
    #endregion

    #region Main function for running scan in a separate thread
    def _disconnect_scan_signals(self):
        """Disconnect any existing scan-thread signal connections to avoid duplicate callbacks on repeated scans."""
        if not hasattr(self, 'scan_Thread') or self.scan_Thread is None:
            return

        signal_slot_pairs = [
            (self.scan_Thread.repeat_update, self.update_curr_repeat),
            (self.scan_Thread.position_update, self.update_curr_pos),
            (self.scan_Thread.step_update, self.update_curr_step),
            (self.scan_Thread.stepNO_update, self.update_curr_stepNOs),
            (self.scan_Thread.lockin_update, self.update_lockin_charts),
            (self.scan_Thread.pol_update, self.update_pol_chart),
            (self.scan_Thread.tds_update, self.update_TDS_FDS_chart),
            (self.scan_Thread.temp_highlight, self.update_temp_hightlight),
            (self.scan_Thread.temp_done_led, self.on_temp_done),
            (self.scan_Thread.enable_pid, self.setup_pid_mode),
            (self.scan_Thread.tds_peak_update, self.update_iPos1_from_tds_peak),
            (self.scan_Thread.fm_block_led, self.on_fm_block_led),
            (self.scan_Thread.scan_log, self.append_scan_log),
            (self.scan_Thread.scan_finished, self.on_scan_finished),
            (self.scan_Thread.error_occurred, self.on_handle_scan_error),
        ]

        for signal, slot in signal_slot_pairs:
            try:
                signal.disconnect(slot)
            except TypeError:
                pass

    def check_instruments_ready(self) -> list[str]:
        """Return the display names of instruments that are ticked 'active' but not connected.

        Also reports when nothing at all is available, since a scan with no devices produces
        only zeros and spins with no hardware latency.
        """
        # (active checkbox, instrument attribute, display name)
        instrument_map = [
            ('activeStage1',  'stage1',      'Stage1 (linear)'),
            ('activeStage2',  'stage2',      'Stage2 (linear)'),
            ('activeRot1',    'rotary1',     'Rotary1'),
            ('activeRot2',    'rotary2',     'Rotary2'),
            ('activeRot3',    'rotary3',     'Rotary3'),
            ('activeFlipMount', 'flipmount', 'Flip mount'),
            ('activePowerMeter', 'powermeter', 'Power meter'),
            ('activeLockin1', 'lockin1',     'Lock-in 1'),
            ('activeLockin2', 'lockin2',     'Lock-in 2'),
            ('activeiTC',     'mercuryiTC',  'MercuryiTC'),
        ]

        missing = []
        any_active = False
        for box_name, attr_name, display_name in instrument_map:
            box = getattr(self.ui, box_name, None)
            if box is None or not box.isChecked():
                continue
            if attr_name not in ('flipmount', 'powermeter'):  # beam block and pump monitor: neither measures scan data
                any_active = True
            if getattr(self, attr_name, None) is None:
                missing.append(display_name)

        if not any_active:
            missing.append("no instrument is marked active at all")

        # AutoBlock protects the sample; running without a connected mount would leave it exposed silently
        if self.ui.AutoBlock.isChecked() and self.flipmount is None and 'Flip mount' not in missing:
            missing.append("Flip mount (AutoBlock is on)")

        # Record would otherwise save data files without the pump power, silently
        if (self.ui.pmRecord.isChecked() and self.ui.AutoBlock.isChecked()
                and self.powermeter is None and 'Power meter' not in missing):
            missing.append("Power meter (Record is on)")

        return missing

    def runScan(self):
        """Here, the 'runScan' function is responsible for starting the scan process in a separate thread. Main execute steps:
            1. Call the ScanThread class to create a scan thread and name it as 'scan_Thread'.
            2. Connect the signals from ScanThread to the corresponding function slots in the main thread for corresponding progress/UI updates.
            3. Start the scan thread. the entrance of the execution is the 'run' method in ScanThread class
            4. In the 'run' method of ScanThread, it further calls the '_execute_scan_logic' method in the main moSys class.
            5. When it executed to the 'repeat_update' part, it emit 'repeat_update' signal and trigger the connected slot function 'update_curr_repeat'
               in main thread to update the scanRepNO bar.
            6. Similarly, when it executed to the 'position_update' part, it emit 'position_update' signal and trigger the connected slot function 
               'update_curr_pos' in main thread to update the current position display.
            7. When the scan is finished, it emit 'scan_finished' signal and trigger the connected slot function 'on_scan_finished' in main thread: 
               also for further data processing/display after scan.
            8. If any error occurs during the scan execution, it emit 'error_occurred' signal and trigger the connected slot function 'on_handle_scan_error'
               in main thread to handle the error.
            9. During the scan process, the 'stopscan' function can be called to set the stop flag in both ScanThread and main moSys class to True,
               so that the scan process can be stopped at the next checkpoint.
               Note: there are two stop flags here for safety consideration, one in ScanThread and one in main moSys class.
        """
        print("======================starting scan in thread======================")

        # refuse to start when instruments marked active are not actually connected, otherwise the
        # scan loop runs with None devices: stage moves and lock-in reads are silently skipped and
        # the loop spins with no hardware latency at all.
        missing = self.check_instruments_ready()
        if missing:
            message = "Cannot start scan - the following instruments are marked active but not connected:\n\n" \
                      + "\n".join(f"  - {name}" for name in missing) \
                      + "\n\nConnect them, or uncheck their 'active' boxes, then start the scan again."
            print(message)
            QMessageBox.warning(self.ui, "Instruments not ready", message)
            return

        # update data folder date if not using custom path
        if not getattr(self, 'is_custom_save_path', False):
            self.setup_data_folder()

        self.start_scan_log()  # test conditions go into the ScanLog box and the day's log file
        
        # reset stop flag
        self.stop_flag = False  # this is the main moSys class stop flag, also used in ScanThread
        
        # setup buttons state during scan
        self.set_ControlsEnabledDuringScan(True)
        
        # Create scan thread, connect to the separate 'ScanThread' class
        self._disconnect_scan_signals()
        self.scan_Thread = ScanThread(self)  # create scan thread
        
        # connect signals to update UI
        self.scan_Thread.repeat_update.connect(self.update_curr_repeat)
        self.scan_Thread.position_update.connect(self.update_curr_pos)
        self.scan_Thread.step_update.connect(self.update_curr_step)
        self.scan_Thread.stepNO_update.connect(self.update_curr_stepNOs)
        self.scan_Thread.lockin_update.connect(self.update_lockin_charts)
        self.scan_Thread.pol_update.connect(self.update_pol_chart)
        self.scan_Thread.tds_update.connect(self.update_TDS_FDS_chart)
        self.scan_Thread.temp_highlight.connect(self.update_temp_hightlight)
        self.scan_Thread.temp_done_led.connect(self.on_temp_done)    # could be unset, set, or stable
        self.scan_Thread.enable_pid.connect(self.setup_pid_mode)     # enable or disable pid mode during temperature scan
        self.scan_Thread.tds_peak_update.connect(self.update_iPos1_from_tds_peak)  # update iPos2 from TDS peak position
        self.scan_Thread.fm_block_led.connect(self.on_fm_block_led)  # flip mount beam state LED
        self.scan_Thread.scan_log.connect(self.append_scan_log)      # key scan events for the ScanLog box and file

        self.scan_Thread.scan_finished.connect(self.on_scan_finished)     # could also add another slot function to handle initial results processing and display after scan finished
        self.scan_Thread.error_occurred.connect(self.on_handle_scan_error)
        
        
        # start scan thread
        self.scan_Thread.start()
        print("Scan thread started.")
        
    #endregion
        
    #region _execute_scan_logic: actual scan logic executed in ScanThread
    def _execute_scan_logic(self, thread):   
        print("======================Executing scan logic in Thread======================")
        scan_mode_box = getattr(self.ui, 'scanMode', None)
        scan_mode = scan_mode_box.currentText() if scan_mode_box else "UnknownMode"
        
        #region set_Temperature if active and temperature scan is enabled
        if self.ui.activeiTC.isChecked() and self.mercuryiTC and self.ui.ScanT.isChecked():
            Temp_sequence = self.tp_manager.temp_sequence # get temperature sequence from temperature profile manager
            if len(Temp_sequence) > 0:
                has_temperature = True
                print(f"Temperature scan enabled. Temperature points: {Temp_sequence}")
            else:
                Temp_sequence = [None]  # single iteration with no temperature change
                has_temperature = False
                print("Warning: No temperature profile defined. Proceeding with")
            
        else:
            Temp_sequence = [None]  # single iteration with no temperature change
            has_temperature = False
            print("Temperature scan disabled or no temperature profile defined.")
        
        # loop over temperature sequence    
        for temp_idx, target_T in enumerate(Temp_sequence):
            pump_power = None  # Record: measured right before the beam is let through, saved into this point's file

            #region check stop flag
            if self.stop_flag or thread.stop_flag:
                print("Scan stop flag detected. Exiting scan loop...")
                break      # exit temperature loop
            #endregion
            
            if has_temperature and target_T is not None:
                target_T = round(target_T, 3)  # round to 3 decimal places
                print(f"\n--- Starting temperature setpoint {temp_idx + 1}/{len(Temp_sequence)}: {target_T} K ---")
                print(f"{'=' * 50}\n")
                
                # emit signal to highlight current temperature setpoint in temperature profile manager UI
                thread.temp_highlight.emit(temp_idx)
                thread.temp_done_led.emit(False)  # reset temperature done LED, already defined in goto_targetT

                # AutoBlock: keep the beam off the sample while the temperature changes and settles
                if self.ui.AutoBlock.isChecked():
                    if not self.set_flipmount_blocked(True, thread):
                        print("Warning: AutoBlock could not block the beam; the temperature change continues with the sample exposed.")

                # go to target temperature and stabilize
                thread.enable_pid.emit(True) # emit signal for enable pid
                stab_started = self.iTC_goto_targetT(target_T, update_ui=False)
                ### Or can emit signal to main thread to call iTC_goto_targetT, and need not use 'update_ui' here

                # wait for temperature stabilization to complete.
                # Only wait when a stabilization thread was really started: if the iTC is not
                # connected, iTC_goto_targetT() returns early, and waiting on a missing/stale
                # thread would either raise AttributeError or block this scan thread forever
                # (its 'finished' signal has already been emitted and will never fire again).
                if stab_started and self.itc_stab_thread is not None:
                    loop_for_Tstab = QEventLoop()
                    self.itc_stab_thread.finished.connect(loop_for_Tstab.quit)
                    # Only block if it is still running: a thread that failed immediately has already
                    # emitted 'finished', and this connection - made after the fact - would never
                    # fire, leaving exec() waiting forever.
                    if self.itc_stab_thread.isRunning():
                        loop_for_Tstab.exec()  # wait until itc_stab_thread is finished
                    self.itc_stab_thread.wait()  # ensure Qt fully cleans up the thread before next temperature point

                    # Read the outcome as state rather than from the signal payload, which the
                    # connection above discards. 'finished' is emitted with False on a read error,
                    # a missing UID and a user stop, so reaching this point does not mean the
                    # temperature actually settled.
                    stab_ok = bool(getattr(self.itc_stab_thread, 'stab_success', False))
                    thread.temp_done_led.emit(stab_ok)  # LED reflects the real outcome

                    if not stab_ok:
                        print(f"Temperature stabilization FAILED at {target_T} K "
                              f"(instrument error, or stopped). Aborting the scan instead of "
                              f"measuring at an uncontrolled temperature.")
                        if not (self.stop_flag or thread.stop_flag):
                            self._scan_abort_reason = f"temperature stabilization failed at {target_T} K"
                        break

                    # The iTC sensor reaching setpoint does not mean the sample itself has: it lags
                    # behind, and scanning before it settles leaves residual thermal drift. Hold here
                    # for the extra soak time set in the UI before starting the scan.
                    if not self.wait_sample_stable(thread):
                        print("Stop requested during sample soak wait. Exiting scan loop.")
                        break
                    self.scan_log_event(f"T point {temp_idx + 1}/{len(Temp_sequence)} = {target_T} K reached "
                                        f"(stabilized + sample soak)", thread)
                else:
                    print(f"Skipping temperature stabilization wait for {target_T} K: "
                          f"no stabilization thread was started (iTC not connected?).")
                    self.scan_log_event(f"T point {temp_idx + 1}/{len(Temp_sequence)} = {target_T} K: "
                                        f"stabilization not started, measuring without waiting", thread)
                
                should_run_scan = True

                #region stop check before formal scan
                if self._check_scan_stop(thread):
                    print("Stop request detected before formal scan. Exiting current scan sequence.")
                    break
                #endregion

                if not should_run_scan:
                    continue

            # AutoBlock: let the beam through right before measuring (peak tracking below also needs it).
            # A mount that fails to open would produce a whole data set of blocked-beam signal, so abort.
            if self.ui.AutoBlock.isChecked():
                pump_power = self.record_pump_power(thread)  # last moment the pump falls on the meter
                if self._check_scan_stop(thread):
                    print("Stop requested while recording the pump power. Exiting scan loop.")
                    break
                if not self.set_flipmount_blocked(False, thread):
                    print("AutoBlock could not let the beam pass. Aborting the scan instead of measuring with the beam blocked.")
                    self._scan_abort_reason = "AutoBlock could not let the beam pass"
                    break

            #region Navigate to data save path and create file for saving data
            fileName = self.setup_dataFile_Name(f"{scan_mode}_{target_T}K" if self.ui.ScanT.isChecked() else scan_mode)
            filePath = self.dataSave_path
            os.makedirs(filePath, exist_ok=True)  # Ensure directory exists， create if not exist
            self.fullFilePath = os.path.join(filePath, f"{fileName}.h5")    # full file path with .h5 extension
            print(f"Data will be saved to: {self.fullFilePath}")
            self.scan_log_event(f"Data file: {os.path.basename(self.fullFilePath)}", thread)
            
            # Create HDF5 file
            self.h5_file = h5py.File(self.fullFilePath, 'w')
            if pump_power is not None:
                self.save_pump_power(pump_power)
            #endregion
            
            #region Save scan parameters in HDF5 file || generate all position sequences || initialize datasets
            
            # extract position parameters from UI
            iPos1 = getattr(self.ui,'iPos1').value()                 
            stage1_array = self.get_step_array('stage1')
            self.ds_iPos1 = self.h5_file.create_dataset('iPos1', data=iPos1, dtype='f8')
            self.ds_stage1_array = self.h5_file.create_dataset('stage1_array', data=stage1_array, dtype='f8')
                    
            iPos2 = getattr(self.ui,'iPos2').value()
            stage2_array = self.get_step_array('stage2')
            self.ds_iPos2 = self.h5_file.create_dataset('iPos2', data=iPos2, dtype='f8')
            self.ds_stage2_array = self.h5_file.create_dataset('stage2_array', data=stage2_array, dtype='f8')
            
            iRot1 = getattr(self.ui,'iRot1').value()
            rotary1_array = self.get_step_array('rotary1')
            self.ds_iRot1 = self.h5_file.create_dataset('iRot1', data=iRot1, dtype='f8')
            self.ds_rotary1_array = self.h5_file.create_dataset('rotary1_array', data=rotary1_array, dtype='f8')

            iRot2 = getattr(self.ui,'iRot2').value()
            rotary2_array = self.get_step_array('rotary2')
            self.ds_iRot2 = self.h5_file.create_dataset('iRot2', data=iRot2, dtype='f8')
            self.ds_rotary2_array = self.h5_file.create_dataset('rotary2_array', data=rotary2_array, dtype='f8')
            
            iRot3 = getattr(self.ui,'iRot3').value()
            rotary3_array = self.get_step_array('rotary3')
            self.ds_iRot3 = self.h5_file.create_dataset('iRot3', data=iRot3, dtype='f8')
            self.ds_rotary3_array = self.h5_file.create_dataset('rotary3_array', data=rotary3_array, dtype='f8')

            stage1_rep = getattr(self.ui, 'scanRepNO1').value()
            stage2_rep = getattr(self.ui, 'scanRepNO2').value()
            rotary1_rep = getattr(self.ui, 'ScanRepNO_R1').value()
            rotary2_rep = getattr(self.ui, 'ScanRepNO_R2').value()
            rep_array = np.array([stage1_rep, stage2_rep, rotary1_rep, rotary2_rep], dtype='i8')
            self.ds_rep_array = self.h5_file.create_dataset('rep_array', data=rep_array, dtype='i8') 

            self.h5_file.flush()  # write to file for avoiding data loss
            
            #region check if both stage repetitions are greater than 1
            rep_plan = DataProcess.validate_scan_repetitions(
                stage1_rep=stage1_rep,
                stage2_rep=stage2_rep,
                rotary1_rep=rotary1_rep,
                rotary2_rep=rotary2_rep,
            )
            if not rep_plan['is_valid']:
                error_msg = str(rep_plan['error_msg'])
                print(error_msg)
                thread.error_occurred.emit(error_msg)
                if self.h5_file:
                    self.h5_file.close()
                return

            pol_rep = int(rep_plan['pol_rep'])

            #endregion

            # Generate position sequences, in mm for linear stages, degree for rotary stages
            stage1_pos_sequence,  stage1_step_sequence,  stage1_stepNO_sequence  = self.scan_planner.generate_position_sequence(iPos1, stage1_array);  stage1_NO = len(stage1_pos_sequence)
            stage2_pos_sequence,  stage2_step_sequence,  stage2_stepNO_sequence  = self.scan_planner.generate_position_sequence(iPos2, stage2_array);  stage2_NO = len(stage2_pos_sequence)
            rotary1_pos_sequence, rotary1_step_sequence, rotary1_stepNO_sequence = self.scan_planner.generate_position_sequence(iRot1, rotary1_array); rotary1_NO = len(rotary1_pos_sequence)
            rotary2_pos_sequence, rotary2_step_sequence, rotary2_stepNO_sequence = self.scan_planner.generate_position_sequence(iRot2, rotary2_array); rotary2_NO = len(rotary2_pos_sequence)
            rotary3_pos_sequence, rotary3_step_sequence, rotary3_stepNO_sequence = self.scan_planner.generate_position_sequence(iRot3, rotary3_array); rotary3_NO = len(rotary3_pos_sequence)

            #region Decide if use calibration data for rotary2-based polarization dependence scan
            # The Rot_stages_couple button picks how the three rotary axes are combined:
            # unchecked ('Independent', the default) -> cartesian product, an axis left at a single
            # state simply holds its initial angle; checked ('Coupled') -> the three axes step
            # together, one angle each per polarization point, and must have equal step counts.
            # Manual calibration overrides the button: build_pol_states() only reads the calibration
            # table on the coupled path, so an imported table would otherwise be silently ignored.
            manu_cali_active = bool(self.ui.pol_cali_mode.isChecked() and self.cali_table)
            rot_stages_coupled = self.ui.Rot_stages_couple.isChecked() or manu_cali_active
            if manu_cali_active and not self.ui.Rot_stages_couple.isChecked():
                print("Note: a calibration table is loaded, so the rotation stages run coupled for "
                      "this scan even though the button reads 'Independent'.")
            pol_plan = self.scan_planner.build_pol_states(
                iRot1=iRot1,
                iRot2=iRot2,
                iRot3=iRot3,
                rotary1_pos_sequence=rotary1_pos_sequence,
                rotary2_pos_sequence=rotary2_pos_sequence,
                rotary3_pos_sequence=rotary3_pos_sequence,
                rotary1_NO=rotary1_NO,
                rotary2_NO=rotary2_NO,
                rotary3_NO=rotary3_NO,
                polarization_policy='coupled' if rot_stages_coupled else 'independent',
                pol_cali_mode=self.ui.pol_cali_mode.isChecked(),
                cali_table=self.cali_table,
                active_rotaries=tuple(getattr(self.ui, f'activeRot{n}').isChecked() for n in (1, 2, 3)),
            )

            error_msg = pol_plan.get('error_msg')
            if isinstance(error_msg, str) and error_msg.startswith('Error:'):
                print(error_msg)
                thread.error_occurred.emit(error_msg)
                if self.h5_file:
                    self.h5_file.close()
                return
            elif error_msg:
                print(f"Warning: {error_msg}")

            pol_rot1_list = pol_plan['pol_rot1_list']
            pol_rot2_list = pol_plan['pol_rot2_list']
            pol_rot3_list = pol_plan['pol_rot3_list']
            N_pol = pol_plan['N_pol']
            #endregion

            #region Check the planned positions against the travel of each active axis
            # A target outside the travel is only rejected when it is actually commanded, and the
            # rotation stages sit in the outer loop, so one bad angle silently kills every point of
            # that sweep. Everything is known here, so the whole plan is checked before anything moves.
            travel_errors = []
            for label, active_box, device, targets, unit in (
                ('Stage1',  self.ui.activeStage1, self.stage1,  stage1_pos_sequence, 'mm'),
                ('Stage2',  self.ui.activeStage2, self.stage2,  stage2_pos_sequence, 'mm'),
                ('Rotary1', self.ui.activeRot1,   self.rotary1, pol_rot1_list,       'deg'),
                ('Rotary2', self.ui.activeRot2,   self.rotary2, pol_rot2_list,       'deg'),
                ('Rotary3', self.ui.activeRot3,   self.rotary3, pol_rot3_list,       'deg'),
            ):
                if not (active_box.isChecked() and device):
                    continue
                limits = getattr(device, 'travel_limits', None)
                low, high = limits() if limits else (None, None)
                if low is None or high is None:
                    continue  # controller did not report a travel; the move itself still guards
                # A rotary resolves a target itself (a full-turn axis wraps), so ask it rather than
                # comparing against the raw limits, which would reject angles it handles fine.
                resolve = getattr(device, 'resolve_target', None)
                unreachable = []
                for target in targets:
                    if resolve is not None:
                        try:
                            resolve(target)
                        except Exception:
                            unreachable.append(target)
                    elif not low <= target <= high:
                        unreachable.append(target)
                if unreachable:
                    travel_errors.append(
                        f"{label}: {len(unreachable)} of {len(targets)} planned positions are outside "
                        f"its travel {low} .. {high} {unit}, e.g. {sorted(set(unreachable))[:3]}"
                    )
            if travel_errors:
                error_msg = "Error: planned positions do not fit the stage travel.\n" + "\n".join(travel_errors)
                print(error_msg)
                thread.error_occurred.emit(error_msg)
                if self.h5_file:
                    self.h5_file.close()
                return
            #endregion

            lockin_shape = (stage1_NO, stage1_rep, stage2_NO, stage2_rep, N_pol, pol_rep)
            self.lockin_datasets = ScanStorageCore.create_lockin_datasets(self.h5_file, lockin_shape)
            self.ds_lockin1_X = self.lockin_datasets['lockin1_X']
            self.ds_lockin1_Y = self.lockin_datasets['lockin1_Y']
            self.ds_lockin2_X = self.lockin_datasets['lockin2_X']
            self.ds_lockin2_Y = self.lockin_datasets['lockin2_Y']

            if scan_mode == '1D_THz':
                self.ds_dynamic_peak = self.h5_file.create_dataset(
                    'dynamic_THz_peak_pos',
                    shape=(stage1_NO, stage1_rep, N_pol, pol_rep),
                    dtype='f8',
                    fillvalue=np.nan
                )
            else:
                self.ds_dynamic_peak = None

            print(f"HDF5 data file and datasets are initialized for saving.")
            
            
            # generate scan_iterator for all stages according to scan_mode
            iterator_mode = 'POL_2D' if scan_mode == 'THz_pol' else scan_mode
            iterator_plan = self.scan_planner.build_scan_iterator(
                scan_mode=iterator_mode,
                stage1_NO=stage1_NO,
                stage1_rep=stage1_rep,
                stage2_NO=stage2_NO,
                stage2_rep=stage2_rep,
                N_pol=N_pol,
                pol_rep=pol_rep,
            )
            scan_iterator = iterator_plan['scan_iterator']

            # Both time-domain modes must record one full trace before anything else moves, so
            # stage1 is the fastest axis, stage2 steps outside it and the rotation stages outside
            # that. THz_pol is the mirror image: there the polarization sweep is the measurement,
            # so the rotation stages are innermost and the two delay lines step outside them with
            # stage2 outermost. build_scan_iterator() lives in the shared func_cores module and
            # nests both cases differently, so the order is rebuilt here instead of changing the
            # shared planner. The tuple layout is unchanged in either case:
            # (stage1_flat_idx, stage2_flat_idx, pol_flat_idx).
            if scan_mode in ('THz_Scan', '2D_THz'):
                scan_iterator = (
                    (stage1_flat, stage2_flat, pol_flat)
                    for pol_flat in range(iterator_plan['pol_total'])
                    for stage2_flat in range(iterator_plan['stage2_total'])
                    for stage1_flat in range(iterator_plan['stage1_total'])
                )
                print(f"{scan_mode}: stage1 set as the innermost (fastest) scan axis.")
            elif scan_mode == 'THz_pol':
                scan_iterator = (
                    (stage1_flat, stage2_flat, pol_flat)
                    for stage2_flat in range(iterator_plan['stage2_total'])
                    for stage1_flat in range(iterator_plan['stage1_total'])
                    for pol_flat in range(iterator_plan['pol_total'])
                )
                print("THz_pol: rotation stages set as the innermost (fastest) scan axis.")
                
            print(f"Generated position scan_iterator indexes for all stages: {scan_iterator}")
            #endregion

            #region Decide whether stage1 peak tracking is worth running
            # Peak tracking only pays for itself when something that can move the THz peak varies
            # between sweeps: the sample temperature, or the polarization configuration. When
            # neither varies there is a single sweep at a single polarization point, the peak was
            # already aligned manually, and the 3-round search would just waste time.

            # The temperature only really varies when ScanT is ticked AND the iTC is actually
            # usable with points to run. has_temperature already encodes exactly that combination
            # (activeiTC ticked, iTC connected, ScanT ticked, non-empty temperature list), so an
            # unticked ScanT skips tracking while leaving the temperature points in the list, and
            # a ticked ScanT with no/unconnected iTC also skips instead of scanning for nothing.
            temperature_varies = has_temperature

            # A rotary only moves the polarization when it is both ticked active AND has more than
            # one step; an unticked rotary's step NO is irrelevant because it never moves.
            polarization_varies = any(
                getattr(self.ui, box_name).isChecked() and rotary_NO > 1
                for box_name, rotary_NO in (
                    ('activeRot1', rotary1_NO),
                    ('activeRot2', rotary2_NO),
                    ('activeRot3', rotary3_NO),
                )
            )

            peak_tracking_enabled = (
                scan_mode_box is not None
                and scan_mode == '1D_THz'
                and (temperature_varies or polarization_varies)
            )

            if scan_mode == '1D_THz' and not peak_tracking_enabled:
                print("Peak tracking disabled for this run: single polarization point and no "
                      "temperature scan, so the manually aligned stage1 peak is used as-is.")
            if scan_mode == '1D_THz' and not peak_tracking_enabled and temp_idx == 0:
                self.scan_log_event("Stage1 peak tracking: off (no temperature or polarization change)", thread)
            # per-sweep peaks are in 'dynamic_THz_peak_pos'; the log only gets one summary line per data file
            tracked_peaks, failed_peak_sweeps = [], 0
            #endregion

            #region Start Scan Loop
            self._last_rep_idx = (-1, -1, -1)  # to track last repeat index for updating display
            self._last_init_rep = (-1, -1, -1)  # to track last initial repeat index for moving back to initial positions
            # move to initial positions before each repeat
            self.move_active_stages((iPos1, iPos2, iRot1, iRot2, iRot3))


            # iterate through all position combinations
            for stage1_flat_idx, stage2_flat_idx, pol_flat_idx in scan_iterator:
                
                #region Extract and update indexes for each stage and repetition
                idx_plan = DataProcess.decode_scan_indices(
                    stage1_flat_idx=stage1_flat_idx,
                    stage2_flat_idx=stage2_flat_idx,
                    pol_flat_idx=pol_flat_idx,
                    stage1_NO=stage1_NO,
                    stage2_NO=stage2_NO,
                    N_pol=N_pol,
                    rotary1_rep=rotary1_rep,
                    rotary2_rep=rotary2_rep,
                )
                stage1_rep_idx = idx_plan['stage1_rep_idx']
                stage1_idx = idx_plan['stage1_idx']
                stage2_rep_idx = idx_plan['stage2_rep_idx']
                stage2_idx = idx_plan['stage2_idx']
                pol_rep_idx = idx_plan['pol_rep_idx']
                pol_idx = idx_plan['pol_idx']
                rotary1_curr_rep = idx_plan['rotary1_curr_rep']
                rotary2_curr_rep = idx_plan['rotary2_curr_rep']
                # emit signal to update current repeat display for all stages only when repeat changes
                if (stage1_rep_idx, stage2_rep_idx, pol_rep_idx) != getattr(self, "_last_rep_idx", (-1, -1, -1)):
                    thread.repeat_update.emit({
                        'stage1_curr_rep': stage1_rep_idx + 1,
                        'stage2_curr_rep': stage2_rep_idx + 1,
                        'rotary1_curr_rep': rotary1_curr_rep,
                        'rotary2_curr_rep': rotary2_curr_rep
                    })
                    self._last_rep_idx = (stage1_rep_idx, stage2_rep_idx, pol_rep_idx)

                # Move back to initial positions at start of a new repeat block
                if stage1_idx == 0 and stage2_idx == 0 and pol_idx == 0 and (stage1_rep_idx, stage2_rep_idx, pol_rep_idx) != (0, 0, 0):
                    if (stage1_rep_idx, stage2_rep_idx, pol_rep_idx) != getattr(self, "_last_init_rep", (-1, -1, -1)):
                        # only execute when new repeat block starts, avoid move at the first iteration
                        print(f"Starting new repeat block: Stage1 Rep {stage1_rep_idx + 1}, Stage2 Rep {stage2_rep_idx + 1},"
                              f" Pol Rep {pol_rep_idx + 1}. Moving back to initial positions.")
                        self.move_active_stages((iPos1, iPos2, iRot1, iRot2, iRot3))
                        self._last_init_rep = (stage1_rep_idx, stage2_rep_idx, pol_rep_idx)

                #endregion

                #region Calibrate stage1 peak position for 1D_THz scan mode before each sweep
                if peak_tracking_enabled and stage2_flat_idx == 0:
                    print(f"Calibrating stage1 peak position for 1D_THz scan mode (Pol Idx {pol_idx}, Pol Rep {pol_rep_idx})...")
                    tds_peak_info = self.get_TDS_peak_pos(thread)
                    peak_status = tds_peak_info.get('status', 'failed')

                    if peak_status == 'stopped':
                        print("Peak-tracking calibration interrupted by stop request. Exiting scan loop.")
                        break

                    new_peak = tds_peak_info.get('max_position') if peak_status == 'ok' else None
                    if peak_status == 'ok' and new_peak is not None:
                        # Note: the peak-search window is NOT sent to the TDS/FDS charts - it is a local
                        # alignment sweep, not a THz time-domain trace, so FFT of it is meaningless.
                        # It is displayed live in the realtime Lock-in 1 X chart from get_TDS_peak_pos().
                        thread.tds_peak_update.emit(new_peak)  # emit signal to update iPos1 in UI
                        print(f"Applied new stage1 peak position: {new_peak} mm.")
                        tracked_peaks.append(new_peak)
                        
                        # Update local variables so the subsequent moves use the new peak
                        iPos1 = new_peak
                        if len(stage1_pos_sequence) > 0:
                            stage1_pos_sequence[0] = new_peak
                        
                        # Save the dynamic peak position to the HDF5 dataset
                        if hasattr(self, 'ds_dynamic_peak') and self.ds_dynamic_peak is not None:
                            self.ds_dynamic_peak[stage1_idx, stage1_rep_idx, pol_idx, pol_rep_idx] = new_peak
                            self.h5_file.flush()
                    else:
                        print("TDS peak calibration skipped: no valid peak found.")
                        failed_peak_sweeps += 1
                #endregion

                #region check stop flag at the beginning of each repeat
                if self.stop_flag or thread.stop_flag:
                    print(f"Scan stop flag detected. Exiting scan loop.")
                    break  # exit the scan loop if stop flag is set
                #endregion

                # Target positions for each stage
                stage1_pos = stage1_pos_sequence[stage1_idx]
                stage2_pos = stage2_pos_sequence[stage2_idx]
                rotary1_pos = pol_rot1_list[pol_idx]
                rotary2_pos = pol_rot2_list[pol_idx]
                rotary3_pos = pol_rot3_list[pol_idx]
                
                # move active stages to target positions, and real-time display current positions and step sizes
                move_success, curr_pos_sets = self.move_active_stages((stage1_pos, stage2_pos, rotary1_pos, rotary2_pos, rotary3_pos))
                if move_success and curr_pos_sets is not None:
                    print(f"Move successful! Actual positions: {curr_pos_sets}")
                    # emit position to update signal
                    curr_positions = {
                        'stage1_pos': curr_pos_sets[0],
                        'stage2_pos': curr_pos_sets[1],
                        'rotary1_pos': curr_pos_sets[2],
                        'rotary2_pos': curr_pos_sets[3],
                        'rotary3_pos': curr_pos_sets[4]
                    }
                    thread.position_update.emit(curr_positions)

                    # Emit step size to update signal
                    # Decide step according to number of step sizes defined
                    rotary_idx_plan = DataProcess.resolve_rotary_step_indices(
                        pol_idx=pol_idx,
                        rotary1_step_sequence=rotary1_step_sequence,
                        rotary2_step_sequence=rotary2_step_sequence,
                        rotary3_step_sequence=rotary3_step_sequence,
                    )
                    rotary1_idx = rotary_idx_plan['rotary1_idx']
                    rotary2_idx = rotary_idx_plan['rotary2_idx']
                    rotary3_idx = rotary_idx_plan['rotary3_idx']
                    
                    curr_steps = {
                        'stage1_step': stage1_step_sequence[stage1_idx],
                        'stage2_step': stage2_step_sequence[stage2_idx],   # in mm
                        'rotary1_step': rotary1_step_sequence[rotary1_idx],
                        'rotary2_step': rotary2_step_sequence[rotary2_idx],
                        'rotary3_step': rotary3_step_sequence[rotary3_idx]
                    }
                    thread.step_update.emit(curr_steps)
                    
                    curr_stepNOs = {
                        'stage1_NO': stage1_stepNO_sequence[stage1_idx],
                        'stage2_NO': stage2_stepNO_sequence[stage2_idx],
                        'rotary1_NO': rotary1_stepNO_sequence[rotary1_idx],
                        'rotary2_NO': rotary2_stepNO_sequence[rotary2_idx],
                        'rotary3_NO': rotary3_stepNO_sequence[rotary3_idx]
                    }
                    thread.stepNO_update.emit(curr_stepNOs)
                    
                else:
                    print(f"Skipping data acquisition at point {stage1_pos, stage2_pos, rotary1_pos, rotary2_pos, rotary3_pos} due to movement error.")
                    # the stop flag is only checked at the end of the loop, so check it here too:
                    # otherwise a permanently failing stage would make the scan unstoppable
                    if self.stop_flag or thread.stop_flag:
                        print("============================Scan stopped by user============================")
                        break
                    continue  # skip data acquisition if movement failed


                #region Lockin data acquisition and saving
                wait_time1_s = self.ui.wait1.value() / 1000.0  # convert ms to s
                wait_time2_s = self.ui.wait2.value() / 1000.0  # convert ms to s
                l1x, l1y, l2x, l2y = 0.0, 0.0, 0.0, 0.0
                # collect data from Lockin1
                try:
                    if self.lockin1:
                        time.sleep(wait_time1_s)
                        l1x = self.lockin1.get_x() if self.lockin1 else 0.0
                        time.sleep(0.05)
                        l1y = self.lockin1.get_y() if self.lockin1 else 0.0  
                except Exception as e:
                    print(f"Error acquiring data from lockin1: {e}")
                    l1x, l1y = 0.0, 0.0  # assign default values on error
                
                # collect data from Lockin2
                try:
                    if self.lockin2:
                        if self.lockin1 and wait_time2_s > wait_time1_s:
                            time.sleep(wait_time2_s - wait_time1_s)  # adjust wait time if lockin2 wait is longer
                        l2x = self.lockin2.get_x() if self.lockin2 else 0.0
                        time.sleep(0.05)
                        l2y = self.lockin2.get_y() if self.lockin2 else 0.0
                except Exception as e:
                    print(f"Error acquiring data from lockin2: {e}")
                    l2x, l2y = 0.0, 0.0  # assign default values on error
                
                # Store acquired data into h5py datasets, according to 'position indexes' and scan mode                    
                scan_index = (stage1_idx, stage1_rep_idx, stage2_idx, stage2_rep_idx, pol_idx, pol_rep_idx)
                ScanStorageCore.write_lockin_point(
                    self.lockin_datasets,
                    scan_index,
                    {
                        'lockin1_X': l1x,
                        'lockin1_Y': l1y,
                        'lockin2_X': l2x,
                        'lockin2_Y': l2y,
                    },
                )
                                    
                # emit lockin readings to update lockin 1 and 2 charts
                lockin_readings = {
                    'l1x': l1x,
                    'l1y': l1y,
                    'l2x': l2x,
                    'l2y': l2y
                }
                thread.lockin_update.emit(lockin_readings) # emit lockin data update signal if needed
                                    
                # emit lockin readings to update polar chart
                enable_pol_chart = (N_pol >= 2)
                
                if enable_pol_chart and scan_mode == "THz_pol":
                    pol_data = {
                        'Angle': rotary2_pos,
                        'lockin': l1x,
                        'rotary2_NO': N_pol * pol_rep,
                        'rotary2_idx': pol_idx + pol_rep_idx * N_pol 
                    }
                    thread.pol_update.emit(pol_data)  # emit polar chart update signal
                
                
                self.h5_file.flush()  # write to file for avoiding data loss

                print(f"Acquired data point {stage1_idx+1}|{stage1_rep_idx+1}|{stage2_idx+1}|{stage2_rep_idx+1}|{pol_idx+1}|{pol_rep_idx+1}: "
                    f"Lockin1 X={l1x:.4e}, Y={l1y:.4e}; " f"Lockin2 X={l2x:.4e}, Y={l2y:.4e}")
                #endregion
                
                #region Emit "stage_pos, lockin1_X"" data signal after each repeat for TDS chart update
                if scan_mode in ["THz_Scan", "2D_THz"]:  # emit stage1 position and lockin1 X data for TDS chart update
                    if stage1_idx == stage1_NO -1:
                        try:
                            tds_y_data = self.ds_lockin1_X[:, stage1_rep_idx, stage2_idx, stage2_rep_idx, pol_idx, pol_rep_idx] # read data from HDF5 dataset for current repeat
                            tds_data = {
                                'tds_x': stage1_pos_sequence,
                                'tds_y': tds_y_data.tolist()
                            }
                            thread.tds_update.emit(tds_data)  # emit TDS data update signal if needed
                            print(f"TDS data updated at stage2 index {stage2_idx + 1} for repeat {stage2_rep_idx + 1}.")
                        except Exception as e:
                            print(f"Error updating TDS data at stage2 index {stage2_idx + 1} for repeat {stage2_rep_idx + 1}: {e}")
                            
                elif scan_mode in ["1D_THz"]:  # emit stage2 position and lockin1 X data for TDS chart update
                    if stage2_idx == stage2_NO -1:
                        try:
                            tds_y_data = self.ds_lockin1_X[stage1_idx,stage1_rep_idx, :, stage2_rep_idx, pol_idx, pol_rep_idx] # read data from HDF5 dataset for current repeat
                            tds_data = {
                                'tds_x': stage2_pos_sequence,
                                'tds_y': tds_y_data.tolist()
                            }
                            thread.tds_update.emit(tds_data)  # emit TDS data update signal if needed
                            print(f"TDS data updated at stage1 index {stage1_idx + 1} for repeat {stage1_rep_idx + 1}.")
                        except Exception as e:
                            print(f"Error updating TDS data at stage1 index {stage1_idx + 1} for repeat {stage1_rep_idx + 1}: {e}")
                elif scan_mode == "THz_pol":
                    pass  # no TDS update in THz_pol mode
                #endregion
                
                #region check stop flag at the beginning of each repeat
                if self.stop_flag or thread.stop_flag:
                    print(f"Scan stop flag detected at point {stage1_pos, stage2_pos, rotary1_pos, rotary2_pos, rotary3_pos}. Exiting scan loop.")
                    print("============================Scan stopped by user============================") 
                    break  # exit the scan loop if stop flag is set
                #endregion                    
            #endregion
            
            if tracked_peaks or failed_peak_sweeps:
                summary = f"Stage1 peak tracking: {len(tracked_peaks) + failed_peak_sweeps} sweeps"
                if tracked_peaks:
                    summary += f", peak {min(tracked_peaks)} .. {max(tracked_peaks)} mm"
                if failed_peak_sweeps:
                    summary += f", {failed_peak_sweeps} found no peak (previous position kept)"
                self.scan_log_event(summary, thread)

            if self.h5_file:
                self.h5_file.close()  # close HDF5 file after scan
                print(f"HDF5 file closed and data saved to {self.fullFilePath}.")
              
    #endregion
    
    #region set_ControlsEnabledDuringScan function
    """This function is used to enable/disable UI controls during the scan process."""
    
    def set_ControlsEnabledDuringScan(self, scanning: bool):
        self._scanning = scanning
        # Disable all controls during scan except stop and exit button
        input_type = (QPushButton, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QLineEdit)
        always_enabled = [self.ui.saveScreenshot, self.ui.exportScanConfig, self.ui.stopButton, self.ui.exitApp, self.ui.realtimeDispT, self.ui.PM_realDisp, self.ui.clearLockinDisplay]
        
        if scanning:
            # iterate through all child widgets and disable inputs controls
            for widget in self.ui.findChildren(QWidget):
                # skip PlotWidgets
                if isinstance(widget, pg.PlotWidget):
                    continue  
                
                # Whitelist certain widgets to remain enabled
                if widget in always_enabled:
                    if widget in (self.ui.saveScreenshot, self.ui.exportScanConfig, self.ui.clearLockinDisplay):
                        widget.setEnabled(True)
                    elif widget == self.ui.stopButton:
                        widget.setEnabled(True)  # enable stop button
                    elif widget == self.ui.exitApp:
                        widget.setEnabled(True)  # enable exit button
                    elif widget == self.ui.realtimeDispT:
                        widget.setEnabled(True)  # enable realtime temperature display checkbox
                    elif widget == self.ui.PM_realDisp:
                        widget.setEnabled(True)  # enable realtime power display button
                    continue
                
                # Disable all input controls
                if isinstance(widget, input_type):
                    widget.setEnabled(False)  # disable input controls
            
            self.ui.runButton.setEnabled(False)
            
        else:
            # re-enable all input controls
            for widget in self.ui.findChildren(QWidget):
                # re-enable all input controls
                widget.setEnabled(True)
        self.update_lockin_controls()
    #endregion

    #region Update current scan parameters in UI
    """ The following functions are slots connected to signals emitted from ScanThread to update the UI in real-time during the scan process.

    These slots already execute on the main (GUI) thread via queued connections, so Qt repaints on
    its own once they return. They must NOT call QApplication.processEvents(): doing so re-enters
    the event loop and dispatches the next queued scan signal from inside the current slot. When the
    scan loop emits faster than the GUI drains (most easily when instruments are missing and there is
    no hardware latency), that nesting grows without bound until the stack overflows and the process
    dies with no Python traceback - the app window simply disappears.
    """
    def update_curr_repeat(self, rep_dict: dict):
        if 'stage1_curr_rep' in rep_dict and rep_dict['stage1_curr_rep'] is not None:
            self.ui.stage1CurrScan.setValue(rep_dict['stage1_curr_rep'])
        if 'stage2_curr_rep' in rep_dict and rep_dict['stage2_curr_rep'] is not None:
            self.ui.stage2CurrScan.setValue(rep_dict['stage2_curr_rep'])
        if 'rotary1_curr_rep' in rep_dict and rep_dict['rotary1_curr_rep'] is not None:
            self.ui.Rot1CurrScan.setValue(rep_dict['rotary1_curr_rep'])
        if 'rotary2_curr_rep' in rep_dict and rep_dict['rotary2_curr_rep'] is not None:
            self.ui.Rot2CurrScan.setValue(rep_dict['rotary2_curr_rep'])

    def update_curr_pos(self, positions_dict: dict):
        # position_dict format: {'stage1': pos1, 'stage2': pos2, 'rotary1': rot1, 'rotary2': rot2}
        if 'stage1_pos' in positions_dict and positions_dict['stage1_pos'] is not None:
            self.ui.stage1CurrPos.setValue(positions_dict['stage1_pos'])
        if 'stage2_pos' in positions_dict and positions_dict['stage2_pos'] is not None:
            self.ui.stage2CurrPos.setValue(positions_dict['stage2_pos'])
        if 'rotary1_pos' in positions_dict and positions_dict['rotary1_pos'] is not None:
            self.ui.rot1CurrPos.setValue(positions_dict['rotary1_pos'])
        if 'rotary2_pos' in positions_dict and positions_dict['rotary2_pos'] is not None:
            self.ui.rot2CurrPos.setValue(positions_dict['rotary2_pos'])
        if 'rotary3_pos' in positions_dict and positions_dict['rotary3_pos'] is not None:
            self.ui.rot3CurrPos.setValue(positions_dict['rotary3_pos'])

    def update_curr_step(self, steps_dict: dict):
        # steps_dict format: {'stage1_step': step1, 'stage2_step': step2, 'rotary1_step': rot1, 'rotary2_step': rot2}
        if 'stage1_step' in steps_dict and steps_dict['stage1_step'] is not None:
            currStep_mm = steps_dict['stage1_step'] * 1000  # convert mm to um for display
            self.ui.stage1CurrStep.setValue(int(currStep_mm))
        if 'stage2_step' in steps_dict and steps_dict['stage2_step'] is not None:
            currStep_mm = steps_dict['stage2_step'] * 1000  # convert mm to um for display
            self.ui.stage2CurrStep.setValue(int(currStep_mm))
        # if 'rotary1_step' in steps_dict and steps_dict['rotary1_step'] is not None:
        #     self.ui.rotary1Step.setValue(steps_dict['rotary1_step'])
        # if 'rotary2_step' in steps_dict and steps_dict['rotary2_step'] is not None:
        #     self.ui.rotary2Step.setValue(steps_dict['rotary2_step'])
        # if 'rotary3_step' in steps_dict and steps_dict['rotary3_step'] is not None:
        #     self.ui.rotary3Step.setValue(steps_dict['rotary3_step'])

    def update_curr_stepNOs(self, stepNOs_dict: dict):
        # stepNOs_dict format: {'stage1_NO': no1, 'stage2_NO': no2, 'rotary1_NO': no1, 'rotary2_NO': no2}
        if 'stage1_NO' in stepNOs_dict and stepNOs_dict['stage1_NO'] is not None:
            self.ui.stage1CurrStepNO.setValue(stepNOs_dict['stage1_NO'])
        if 'stage2_NO' in stepNOs_dict and stepNOs_dict['stage2_NO'] is not None:
            self.ui.stage2CurrStepNO.setValue(stepNOs_dict['stage2_NO'])
        if 'rotary1_NO' in stepNOs_dict and stepNOs_dict['rotary1_NO'] is not None:
            self.ui.rotary1CurrStepNO.setValue(stepNOs_dict['rotary1_NO'])
        if 'rotary2_NO' in stepNOs_dict and stepNOs_dict['rotary2_NO'] is not None:
            self.ui.rotary2CurrStepNO.setValue(stepNOs_dict['rotary2_NO'])
        if 'rotary3_NO' in stepNOs_dict and stepNOs_dict['rotary3_NO'] is not None:
            self.ui.rotary3CurrStepNO.setValue(stepNOs_dict['rotary3_NO'])

    def clear_lockin_display(self):
        """Clear the four live X/Y traces without changing scan data or acquisition."""
        for chart_name in ('lockin1XChart', 'lockin1YChart', 'lockin2XChart', 'lockin2YChart'):
            self.curves[chart_name].clear()
            self.buffers[chart_name].clear()
            self.indices[chart_name] = -1
            chart = getattr(self.ui, chart_name)
            # Reset the scrolling viewport so the next samples are visible from index zero.
            chart.setRange(xRange=(0, 1), yRange=(0, 1), padding=0)
            chart.enableAutoRange(x=True, y=True)

    def update_lockin_charts(self, lockin_readings: dict):
        # lockin_readings format: {'l1x': val1, 'l1y': val2, 'l2x': val3, 'l2y': val4}
        # update_lockin_reading during scan loop
        # Update lock-in amplifier charts with new readings
        if 'l1x' in lockin_readings and lockin_readings['l1x'] is not None:
            self.chart_updaters['lockin1XChart'].update(update_single_shot=True, lockin_reading=lockin_readings['l1x'])
        if 'l1y' in lockin_readings and lockin_readings['l1y'] is not None:
            self.chart_updaters['lockin1YChart'].update(update_single_shot=True, lockin_reading=lockin_readings['l1y'])
        if 'l2x' in lockin_readings and lockin_readings['l2x'] is not None:
            self.chart_updaters['lockin2XChart'].update(update_single_shot=True, lockin_reading=lockin_readings['l2x'])
        if 'l2y' in lockin_readings and lockin_readings['l2y'] is not None:
            self.chart_updaters['lockin2YChart'].update(update_single_shot=True, lockin_reading=lockin_readings['l2y'])

    def update_pol_chart(self, pol_data: dict):
        # pol_data format: {'Angle': x_data_list, 'l2x': y_data_list, 'rotary2_NO': int, 'rotary2_idx': int}
        x = pol_data.get('Angle', [])
        y = pol_data.get('lockin', [])
        rotary2_NO = pol_data.get('rotary2_NO', 1)
        rotary2_idx = pol_data.get('rotary2_idx', 0)
        
        if 'rotary2_idx' in pol_data and pol_data['rotary2_idx'] is not None:
            if rotary2_idx == 0:
                self.curves['polChart'].clear()  # clear previous data for new scan
                self.buffers['polChart'].clear()  # clear buffer as well
                self.indices['polChart'] = -1  # reset index

            if 'lockin' in pol_data and pol_data['lockin'] is not None:
                self.chart_updaters['polChart'].update(update_single_shot=True, lockin_reading=pol_data['lockin'])
            else:
                print("Warning: Polar chart data is incomplete, skipping update.")
                return

    def update_TDS_FDS_chart(self, tds_data: dict):
        # tds_data format: {'tds_x': x_data_list, 'tds_y': y_data_list}
        x = tds_data.get('tds_x', [])
        y = tds_data.get('tds_y', [])
        
        if len(x) == 0 or len(y) == 0:
            print("Warning: TDS data is empty, skipping update.")
            return
        
        ## Update TDS Chart with new data
        # get blue and red curves of tdsChart
        blue_curve_TDS = self.curves['tdsChart']['blue']
        red_curve_TDS  = self.curves['tdsChart']['red']  
        
        # check if blue curve exists
        blue_data_TDS = blue_curve_TDS.getData()
        if blue_data_TDS[0] is not None and blue_data_TDS[1] is not None:
            # if exist blue curve, move to red curve
            old_x_TDS, old_y_TDS = blue_data_TDS
            red_curve_TDS.setData(old_x_TDS, old_y_TDS)
            print("TDS Chart: Moved previous blue curve to red curve.")
            
        # plot new data as blue curve
        blue_curve_TDS.setData(x, y)
        print("TDS Chart: Updated blue curve with new data.")
        
        # Auto scale view to fit new data
        # plot_widget = self.ui.tdsChart.getViewBox()    #get ViewBox of tdsChart
        # plot_widget.enableAutoRange(axis='xy', enable=True)  # enable auto range for both x and y axes
        # plot_widget.autoRange()     # perform auto range
        # plot_widget.disableAutoRange(axis='xy') # disable auto range after fitting, allow manual panning/zooming afterwards
        
        # FFT needs at least 2 points to derive a time step; a single point makes np.diff empty
        # and thz_fft_calc raises "zero-size array to reduction operation minimum".
        if len(x) < 2:
            print(f"Warning: TDS data has only {len(x)} point(s); skipping FDS/FFT update. "
                  f"Check that the scanned stage has a valid step size and step NO.")
            return

        ## Update TDS Chart with new data
        # get blue and red curves of tdsChart
        blue_curve_FDS = self.curves['fdsChart']['blue']
        red_curve_FDS  = self.curves['fdsChart']['red']
        # perform FFT calculation
        freq, amp_FDS = DataProcess.thz_fft_calc(np.array(x), np.array(y))
        # check if blue curve exists
        blue_data_FDS = blue_curve_FDS.getData()
        if blue_data_FDS[0] is not None and blue_data_FDS[1] is not None:
            # if exist blue curve, move to red curve
            old_x_FDS, old_y_FDS = blue_data_FDS
            red_curve_FDS.setData(old_x_FDS, old_y_FDS)
            print("FDS Chart: Moved previous blue curve to red curve.")
            
        # plot new data as blue curve
        blue_curve_FDS.setData(freq, np.abs(amp_FDS))  # plot amplitude spectrum
        print("FDS Chart: Updated blue curve with new data.")

    def update_fds_chart_dispRange(self):
        """ Update FDS chart display range based on UI settings."""
        min_freq = self.ui.fdsDispMin.value()
        max_freq = self.ui.fdsDispMax.value()
        vb = self.ui.fdsChart.getPlotItem().getViewBox() # get ViewBox of fdsChart
        vb.disableAutoRange(axis='x') # disable auto range for x axis
        vb.setXRange(min_freq, max_freq, padding=0)  # set x range
        vb.enableAutoRange(axis='y', enable=True)  # enable auto range for y axis
        print(f"FDS Chart: Updated display range to {min_freq} - {max_freq} THz.")
        
    #endregion
    
    #region Scan finished and error handling functions
    def on_scan_finished(self):
        print("============================Scan finished============================")
        abort_reason = getattr(self, '_scan_abort_reason', None)
        if abort_reason:
            self.end_scan_log(f"Scan aborted: {abort_reason}")
        else:
            self.end_scan_log("Scan stopped by user" if self.stop_flag else "Scan finished")
        # disable stop button and enable run button after scan
        self.set_ControlsEnabledDuringScan(False)
        
    def on_handle_scan_error(self, error_message: str):
        print(f"Error during scan: {error_message}")
        self.end_scan_log(f"Scan error: {error_message}")  # scan_finished may follow; the first end wins
        # disable stop button and enable run button after scan
        self.set_ControlsEnabledDuringScan(False)
    #endregion

#endregion

#region ChartUpdater class for real-time chart update    
class ChartUpdater:
    def __init__(self, parent_moSys, chart_Widget, lockin_name: str = '', channel: str = '', interval: int = 100):    # here the parent is moSys instance
        self.parent = parent_moSys
        self.chart_Widget = chart_Widget
        self.lockin_name = lockin_name
        self.lockin_channel = channel
        self.interval = interval
        self.chart_name = chart_Widget.objectName()
        self._warned_missing = False  # 'lock-in not connected' is printed once per Realtime switch-on
        
        self.timer = QTimer(self.parent.ui)
        self.timer.timeout.connect(self.update)
        self.timer.setInterval(self.interval)
    
    def update_Interval(self, new_interval: int):
        # avoid invalid interval
        new_interval = max(1, new_interval)
        self.interval = new_interval
        self.timer.setInterval(self.interval) # update timer interval
        
    def toggle(self, checked: bool):   
        """ Here, checked botton used to start/stop the QTimer for looping update automatically 
            Note: if need to update charts depending on incoming locking data(during scan), one can call the update() method directly in the scan loop instead of using QTimer.
        """
        if checked:
            self._warned_missing = False
            self.timer.start(self.interval)
        else:
            self.timer.stop()
            
    def update(self, update_single_shot: bool = False, lockin_reading: float | None = None):  
        """ Notes:
              1. updata_single_shot: indicates whether this is a single update call for updating chart from scan loop
              2. lockin_reading: the reading value from lockin, used when update_single_shot is True
              3. if update_single_shot is False, then get the lockin reading from the lockin device directly, used in QTimer timeout update   
        """
        chartName = self.chart_name
        
        # use getattr to get lockin_device from parent by name
        
        
        # update data for real-time display chart
        self.parent.indices[chartName] += 1
        
        if update_single_shot and lockin_reading is not None:
            y = lockin_reading
        elif not update_single_shot:
            lockin_device = getattr(self.parent, self.lockin_name, None)
            if lockin_device is None:
                if not self._warned_missing:
                    print(f"Warning: Lockin device '{self.lockin_name}' is not connected for {chartName}.")
                    self._warned_missing = True
                return
            
            # get lockin reading from device
            if self.lockin_channel == 'X':
                y = lockin_device.get_x()
            elif self.lockin_channel == 'Y':
                y = lockin_device.get_y()
            elif self.lockin_channel == 'R':
                y = lockin_device.get_r()
            elif self.lockin_channel == 'Theta':
                y = lockin_device.get_theta()
            else:
                y = 0.0
            
            # Display in number box if exists
            numberBox_name = chartName + 'Num' 
            numberBox = getattr(self.parent.ui, numberBox_name, None)
            if numberBox:
                try:
                    format_value = f"{y:.4e}"
                    numberBox.setText(format_value)
                except Exception as e:
                    print(f"Warning: Unable to set value for {numberBox_name}: {e}")          
        else:
            return  # nothing to update if no valid reading
        
        self.parent.buffers[chartName].append(y)
        buf = list(self.parent.buffers[chartName])
        # keynotes： x use the global index to align with ViewBox scrolling window
        x_start = self.parent.indices[chartName] - len(buf) + 1  
        x = list(range(x_start, self.parent.indices[chartName] + 1))
        self.parent.curves[chartName].setData(x, buf)

        # view follows scrolling
        N = self.parent.buffers[chartName].maxlen
        if self.parent.indices[chartName] >= N:
            vb = self.chart_Widget.getPlotItem().getViewBox()
            vb.setXRange(
                self.parent.indices[chartName] - N + 1, 
                self.parent.indices[chartName], 
                padding=0
            )
#endregion

#region ScanThread class for running scan in a separate thread
class ScanThread(QThread):
    
    # define signals for communicating with main thread/UI
    repeat_update = Signal(dict)     # signal to update progress bar of repetitions
    position_update = Signal(dict)  # signal to update current position display
    step_update = Signal(dict)      # signal to update current step size display
    stepNO_update = Signal(dict)    # signal to update current step number display
    lockin_update = Signal(dict)    # signal to update lockin readings display
    tds_update = Signal(dict)       # signal to update TDS readings display
    pol_update = Signal(dict)       # signal to update polarimeter readings display
    scan_finished = Signal()        # signal to be emitted when scan is finished
    temp_highlight = Signal(int)    # signal to highlight temperature in UI
    temp_done_led = Signal(bool)    # signal to indicate temperature stabilization done
    enable_pid = Signal(bool)       # signal to enable/disable PID control in UI
    tds_peak_update = Signal(float)  # signal to update TDS peak value display
    fm_block_led = Signal(bool)     # signal to update flip mount beam state LED (True = blocked)
    scan_log = Signal(str)          # signal to append a key event line to the scan log

    error_occurred = Signal(str)    # signal to be emitted when error occurs
    

    def __init__(self, parent_moSys):
        super().__init__()           # initialize QThread
        self.parent = parent_moSys
        self.stop_flag = False       # flag to indicate whether to stop the scan
    
    
    # run method of the thread, called when thread starts            
    def run(self):
        try:
            # call the scan_logic method from parent moSys class, this means executing "_execute_scan_logic" in this thread
            self.parent._execute_scan_logic(self)      # here the "(self)" is passing the ScanThread instance to the method
            self.parent.auto_block_after_scan(self)    # finished or stopped: block the beam if AutoBlock is on
            # emit scan finished signal
            self.scan_finished.emit()
        except Exception as e:
            error_msg = str(e)
            print(f"Error during scan execution: {error_msg}")
            traceback.print_exc()                      # print traceback for debugging
            self.parent.auto_block_after_scan(self)    # failed: block the beam if AutoBlock is on
            self.error_occurred.emit(error_msg)        # emit error signal to main thread through error_occurred signal
            
    def request_stop(self):
        """ Set the stop flag to True to request stopping the scan."""
        self.stop_flag = True
        self.parent.stop_flag = True  # also set parent's stop_flag to True
        print("Received the stop request.")
#endregion

#region MercuryiTC class for real-time update
class MercuryiTC_Updater(QThread):
    """ This class handles the real-time update of MercuryiTC parameters in a background thread."""
    
    display_updated = Signal(dict)
    
    def __init__(self, parent_moSys, interval: int = 1000):
        super().__init__()
        self.parent = parent_moSys
        self.interval = interval
        self.stop_flag = False
        self.is_active = False
        
        # Connect the signal to the main thread slot for UI updates
        self.display_updated.connect(self.update_ui_display)
        
    def update_Interval(self, new_interval: int):
        # avoid invalid interval
        new_interval = max(1000, new_interval * 1000)  # minimum 1000 ms
        self.interval = new_interval
        print(f"MercuryiTC update interval set to {self.interval} ms.")
        
    def update_mercuryiTC_display(self, checked: bool):
        """ Start/stop the MercuryiTC real-time update based on checkbox state."""
        if not self.parent.ui.activeiTC.isChecked() or self.parent.mercuryiTC is None:
            print("MercuryiTC device not connected.")
            return  # skip update if MercuryiTC is not active or not connected
    
        self.is_active = checked
        if checked:
            if not self.isRunning():
                self.start()
        else:
            self.stop_flag = True
            
    def run(self):
        self.stop_flag = False
        while not self.stop_flag and self.is_active:
            if not self.parent.ui.activeiTC.isChecked() or self.parent.mercuryiTC is None:
                time.sleep(self.interval / 1000.0)
                continue
                
            if getattr(self.parent, 'uid_TEMP', None) is None or getattr(self.parent, 'uid_HTR', None) is None:
                time.sleep(self.interval / 1000.0)
                continue
                
            try:
                with self.parent.mercuryiTC.io_lock:  # ensure thread-safe access to MercuryiTC
                    curr_temp = self.parent.mercuryiTC.read_temperature(self.parent.uid_TEMP)
                    # curr_setpoint = self.parent.mercuryiTC.get_temperature_setpoint(self.parent.uid_TEMP)
                    # Read the loop's own percentage (HSET) instead of deriving one from voltage:
                    # heater power scales as V^2, so voltage/VLIM disagreed with the front panel.
                    curr_heater_percent = self.parent.mercuryiTC.get_heater_manual(self.parent.uid_TEMP)
                    

                # Emit data to main thread
                self.display_updated.emit({
                    'temp': curr_temp,
                    'heater_percent': curr_heater_percent
                })
            except Exception as e:
                print(f"Error updating MercuryiTC display: {e}") 
                
            # Sleep for the specified interval before polling again
            time.sleep(self.interval / 1000.0)
            
    @Slot(dict)
    def update_ui_display(self, data: dict):
        """ Update UI components on the main thread safely. """
        try:
            self.parent.ui.realDispiTC.setText(f"{data['temp']:.3f} K")
            self.parent.ui.HeaterBar.setValue(data['heater_percent'])
        except Exception:
            pass 
            
    def set_heater_limit(self, new_limit: float):
        """ Update MercuryiTC heater limit from UI."""
        if self.parent.ui.activeiTC.isChecked() and self.parent.mercuryiTC:
            if self.parent.uid_HTR is None:
                print("MercuryiTC heater UID not available.")
                return
            try:
                new_limit = new_limit
                with self.parent.mercuryiTC.io_lock:  # ensure thread-safe access to MercuryiTC
                    self.parent.mercuryiTC.set_heater_voltage_limit(self.parent.uid_HTR, new_limit)
                    self.parent.qwait_time(50)  # wait for a short time to ensure setting is applied
                    verified_limit = self.parent.mercuryiTC.get_heater_voltage_limit(self.parent.uid_HTR) # verify the limit
                self.parent.qwait_time(50)
                if abs(verified_limit - new_limit) < 0.1:
                    self.parent.ui.HeaterLim.setValue(verified_limit)
                    print(f"MercuryiTC heater limit set to {verified_limit} V successfully.")
                else:
                    print(f"Warning: MercuryiTC heater limit verification failed. Set to {new_limit} V, but read back {verified_limit} V.") 
            except Exception as e:
                print(f"Error setting MercuryiTC heater limit: {e}")
        else:
            print("MercuryiTC device not connected.")
    
    def set_heater_percent(self, percent: float):
        """ Update MercuryiTC heater set percent from UI."""
        # Each precondition reports its own reason: the old single guard collapsed "not active /
        # not connected" and "Auto PID is on" into one misleading "device not connected." message.
        if not (self.parent.ui.activeiTC.isChecked() and self.parent.mercuryiTC):
            print("MercuryiTC device not connected.")
            return
        if self.parent.ui.autoPID.isChecked():  # if auto PID is enabled, skip manual heater setting
            print("MercuryiTC is in Auto PID mode - manual heater setting skipped. Turn off Auto PID first.")
            return
        if self.parent.uid_TEMP is None:
            print("MercuryiTC temperature UID not available.")
            return
        try:
            # HSET is the control loop's own percentage of full power, so the UI value maps 1:1 onto
            # the instrument's. The previous route - percent -> voltage -> VLIM fraction - disagreed
            # with the front panel, because heater power scales as V^2 rather than as V.
            with self.parent.mercuryiTC.io_lock:  # ensure thread-safe access to MercuryiTC
                self.parent.mercuryiTC.set_heater_manual(self.parent.uid_TEMP, percent)
            self.parent.qwait_time(50)  # let the setting take effect before reading it back
            with self.parent.mercuryiTC.io_lock:
                verified_percent = self.parent.mercuryiTC.get_heater_manual(self.parent.uid_TEMP)
            if abs(verified_percent - percent) < 0.1:
                print(f"MercuryiTC heater output set to {verified_percent:.2f} % successfully.")
            else:
                print(f"Warning: MercuryiTC heater output verification failed. Set to {percent} %, but read back {verified_percent} %.")
        except Exception as e:
            print(f"Error setting MercuryiTC heater output: {e}")
    
    def setup_autoPID_mode(self, checked: bool) -> bool:
        """ Update MercuryiTC auto PID mode from UI.

        Returns whether the instrument accepted the change, NOT the resulting mode: switching
        PID *off* succeeds and previously returned False, indistinguishable from a failure.
        """
        if self.parent.ui.activeiTC.isChecked() and self.parent.mercuryiTC:
            if self.parent.uid_TEMP is None:
                print("MercuryiTC temperature UID not available.")
                return False
            auto_PID_status = checked
            with self.parent.mercuryiTC.io_lock:  # ensure thread-safe access to MercuryiTC
                PID_tab_status = self.parent.mercuryiTC.enable_auto_pid_table(self.parent.uid_TEMP, auto_PID_status)
                pid_status = self.parent.mercuryiTC.enable_pid_control(self.parent.uid_TEMP, auto_PID_status)
            result = PID_tab_status and pid_status
            if result:
                print(f"MercuryiTC auto PID mode set to {auto_PID_status}.")
                return True
            else:
                print(f"Warning: Failed to set MercuryiTC auto PID mode to {auto_PID_status}.")
                return False
        else:
            print("MercuryiTC device not connected.")
            return False
                            
#endregion

#region iTCstabilizeThread class for running temperature stabilization in a separate thread
class iTCstabilizeThread(QThread):
    """
    Background thread to:
      1) set the iTC target temperature,
      2) poll the current temperature at a fixed interval,
      3) declare 'stable' when |T - target| < tol for N consecutive polls.
    """
    finished = Signal(bool)         # signal to be emitted when stabilization is finished
    
    error = Signal(str)            # signal to be emitted when error occurs
    
    def __init__(self, parent_moSys, target_T: float, tolerance:float, interval_s: int, stable_count: int = 20):
        super().__init__()           # initialize QThread
        self.parent = parent_moSys
        self.target_T = target_T
        self.tolerance = float(tolerance)
        self.tolerance_lock = threading.Lock()  # lock for thread-safe tolerance access
        self.interval_s = int(interval_s)
        self.stable_count = int(stable_count)
        self.stop_flag = False       # flag to indicate whether to stop the stabilization
        self.stab_success = False    # True only once the temperature really settled (see run())

    
    @Slot(float)   
    # Slot decorator to indicate this method can be connected to a signal, could be updated during thread running
    # The @Slot make the "set_tolerance" method be safe entrance that can be called from main or other threads safely.
    def set_tolerance(self, new_tol: float):
        """ Update tolerance value for stabilization."""
        with self.tolerance_lock:      # start the critical section to lock the tolerance, use threading lock to avoid race condition, ensure thread-safe access
            self.tolerance = float(new_tol)
            print(f"iTC stabilization tolerance updated to {new_tol} K.")
            
    def get_tolerance(self) -> float:
        """ Get the current tolerance value in a thread-safe manner."""
        with self.tolerance_lock:
            return self.tolerance
        
    def request_stop(self):
        """ Set the stop flag to True to request stopping the stabilization."""
        self.stop_flag = True
        self.parent.stop_flag = True  # also set parent's stop_flag to True
        print("Received the iTC stabilization stop request.")
        
        
    def run(self):
        # stab_success mirrors the value carried by the 'finished' signal, but as plain state that
        # can be read after the fact. A caller that connects to 'finished' only after the thread has
        # already failed would never see the signal at all, so the outcome has to be readable too.
        self.stab_success = False
        try:
            # basic safety checks
            if not (self.parent.mercuryiTC and self.parent.ui.activeiTC.isChecked()):
                self.error.emit("MercuryiTC device not connected or not active.")
                self.finished.emit(False)
                return
            if self.parent.uid_TEMP is None:
                self.error.emit("MercuryiTC temperature UID not available.")
                self.finished.emit(False)
                return

            # poll loop to check temperature stability
            stable_counter = 0
            while not self.stop_flag:
                with self.parent.mercuryiTC.io_lock:  # ensure thread-safe access to MercuryiTC
                    curr_T = self.parent.mercuryiTC.read_temperature(self.parent.uid_TEMP)
                tol = self.get_tolerance()     # read lastest tolerance value
                diff = abs(curr_T - self.target_T)

                # count consecutive hits within tolerance
                stable_counter = stable_counter + 1 if diff <= tol else 0  # reset counter if out of tolerance
                print(f"iTC Stabilization: Current T = {curr_T:.3f} K, Target T = {self.target_T:.3f} K, Stable Count = {stable_counter}/{self.stable_count}")

                # stabilization condition met
                if stable_counter >= self.stable_count:
                    print(f"Temperature stabilized at {curr_T:.3f} K within tolerance {tol} K.")
                    self.stab_success = True
                    self.finished.emit(True)
                    return

                # stop and wait for next poll
                time.sleep(self.interval_s)

            # stop by user request
            self.finished.emit(False)
            print("iTC stabilization stopped by user.")

        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(False)
#endregion

#region Temperature points management class
class TempPointsManager:
    
    """ This class manages the temperature points for iTC stabilization."""
    def __init__(self, list_widget):
        self.list_widget = list_widget
        self.temp_sequence = []  # list to store temperature points

        
    def add_sequence(self, start_T: float, step_T: float, NO_T: int):
        """ Add temperature sequence from UI inputs."""
        new_points = [start_T + i * step_T for i in range(NO_T)]

        self.temp_sequence.extend(new_points)
        self.update_list_widget()
        print(f"Added temperature points: {new_points}")

        
    def del_T_points(self):
        """ Delete selected temperature point from the list.
            If there is not any selected item, then delet the last item"""
        selected_items = self.list_widget.selectedItems()       # get selected items from the list widget
        temp_indices = []                    # list to store indices of selected items
        
        # collect indices of selected items, exclude title and illustration items
        for item in selected_items:
            idx = item.data(Qt.UserRole)        # get index stored in UserRole
            if isinstance(idx, int):            # ensure idx is an integer, skip title/illustration items
                temp_indices.append(idx) 
                
        if temp_indices:
            # delete items in reverse order to avoid index shifting
            temp_indices.sort(reverse=True)    # sort indices in descending order
            for idx in temp_indices:
                self.temp_sequence.pop(idx)   # remove temperature point from the list
                
            self.update_list_widget()
            print(f"Deleted slected temperature points at indices: {temp_indices}") 
        else:
            # if no selected items, delete the last item
            if self.temp_sequence:        # check if Temp list is not empty
                removed_point = self.temp_sequence.pop()  # remove last temperature point
                self.update_list_widget()
                print(f"Deleted last temperature point: {removed_point} K")
            else:
                print("No temperature points to delete.")

                    
    def clear_all(self):
        """ Clear all temperature points from the list."""
        self.temp_sequence.clear()
        self.update_list_widget()
        print("Cleared all temperature points.")

        
    def update_list_widget(self):
        """ Update the QListWidget to display current temperature points."""
        self.list_widget.clear()   # clear existing items
        
        # add title item
        if self.temp_sequence:    # only add title if there are temperature points
            title = (f"Temperature Points (K):\n" 
                     f"Total {len(self.temp_sequence)} points, from {self.temp_sequence[0]:.3f} K to {self.temp_sequence[-1]:.3f} K")
            title_item = QListWidgetItem(title) # create title item for the list
            title_item.setFlags(Qt.ItemIsEnabled)  # make title non-selectable
            title_item.setBackground(QColor(200, 200, 200))  # light gray background for title
            font = QFont(); font.setBold(True)
            title_item.setFont(font)    # set bold font for title
            self.list_widget.addItem(title_item)
            
            for idx, T in enumerate(self.temp_sequence):       # add temperature T points
                item = QListWidgetItem(f"Point   {idx + 1}  :     {T:.2f} K")
                item.setData(Qt.UserRole, idx)   #add self-customized value/data into the UserRole, each UserRole corresponds to one item. Here store index in UserRole for identification, highlight and delete
                self.list_widget.addItem(item)

                
    def highlight_T_point(self, H_index: int):
        """ Highlight the temperature point at the given index in the list widget."""
        for i in range(self.list_widget.count()):  # iterate through all items
            item = self.list_widget.item(i)
            idx = item.data(Qt.UserRole)   # get index stored in UserRole
            
            if idx == H_index:                                   # highlight the current temperature point
                item.setBackground(QColor(144, 238, 144))        # highlight with light green background
                font = item.font(); font.setBold(True); item.setFont(font)  # set bold font for highlighted item
                self.list_widget.scrollToItem(item)         # scroll to the highlighted item
            elif isinstance(idx, int):                           # skip title/illustration items
                item.setBackground(QColor(255, 255, 255))        # reset to white background
                font = item.font(); font.setBold(False); item.setFont(font)  # reset font to normal
#endregion
            
    
#endregion                

app = QApplication()
# load icon for mainwindow
app.setWindowIcon(QIcon('mo_icon.png'))
mosys = moSys()
mosys.ui.show()
app.exec()