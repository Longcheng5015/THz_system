#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""" 
Main program for OPTP system control and data acquisition GUI application.
This program provides a graphical user interface (GUI) for controlling various instruments,
including lock-in amplifiers and motorized stages, as well as real-time data visualization. 
"""
# region Debugging records
# Development history: see OPTP_dev_log.md in this directory (project path: OPTP_System/OPTP_dev_log.md).
# endregion

# region Import modules
# Inject inst_libs to path for instrument control, especially for mercuryiTC which is not pip-installable and needs to use the provided .py files
from proj_tools import ProjectTools
ProjectTools.inject_inst_libs(__file__)
ProjectTools.inject_inst_libs(__file__, libs_dir_name="func_cores")

# import pyside6 for GUI
import pyqtgraph as pg
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog, QPushButton, QToolButton, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QLineEdit, QWidget, QListWidgetItem, QStyle
from PySide6.QtUiTools import QUiLoader
from PySide6.QtGui import QIcon, QFont, QColor, QTextCursor
from collections import deque
from PySide6.QtCore import QObject, QTimer, QThread, Signal, QEventLoop, Slot, Qt, QSettings, QSaveFile, QIODevice, QSignalBlocker
from MyWidget import LedIndicator

# import packages needed
import os, re, json, h5py, time, traceback, threading, sys, socket      # HDF5 measurement files
import numpy as np
from datetime import datetime
from pathlib import Path

# Import instrument classes
from thorlabs_LinearStage_BBD202 import LinearStage
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
    """Pass console text to the terminal and to a callback (the Live Process box and file)."""
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
        ui_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'OPTP_iTC_main_v4.4.ui')
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
        self.ui.stage1Home.clicked.connect(lambda: self.home_stage('stage1'))
        self.ui.stage2Home.clicked.connect(lambda: self.home_stage('stage2'))
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

        # Peak search tab: the toggle captions follow their state
        self.ui.stage2CompDir.toggled.connect(self.on_stage2_comp_dir_toggled)
        self.on_stage2_comp_dir_toggled(self.ui.stage2CompDir.isChecked())
        self.ui.passOrder.toggled.connect(self.on_pass_order_toggled)
        self.on_pass_order_toggled(self.ui.passOrder.isChecked())
        self.ui.repeatPeak.toggled.connect(self.on_repeat_peak_toggled)
        self.on_repeat_peak_toggled(self.ui.repeatPeak.isChecked())

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
            # keyboardTracking is off: steps/commits apply; instrument readbacks block signals.
            phase_box.valueChanged.connect(lambda value, name=f'lockin{index}': self.apply_lockin_parameter(name, 'Phase'))
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

    # apply lockin values
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
                
                waitBox.setValue(new_waittime)
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
                    serial = self.ui.Stage1_res.currentText().strip()  # set in Inst. Config. tab
                    chan = self.ui.Stage1_ch.value()
                    stage1_temp = LinearStage(
                        serial,
                        chan,
                        poll_ms=250,
                        enable_state_guard=True,
                        enable_wait_timeout_ms=5000,
                        enable_retry_count=2,
                        enable_poll_interval_ms=100,
                    )
                    stage1_temp.home_with_guard(60000)  # home with explicit enable guard
                    self.stage1 = stage1_temp
                    self.qwait_time(1000)    # wait for 2 seconds after connect
                    self.ui.stage1CurrPos.setValue(self.stage1.position())  # update current position display
                    self.ui.stage1Led.status = True  # update LED indicator
                    QApplication.processEvents()  # Ensure UI updates immediately
                    print(f"✓ Stage1 connection successful (serial: {serial}, channel: {chan})")
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
    KINESIS_BOXES = ('Stage1_res', 'Stage2_res', 'Rot1_res', 'Rot2_res', 'Rot3_res', 'FM_res')
    CHANNEL_BOXES = ('Stage1_ch', 'Stage2_ch')  # the rotary driver is single-channel

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
        settings = QSettings("OPTP_System", "InstrumentConnections")
        for name in self.VISA_BOXES + self.KINESIS_BOXES:
            value = settings.value(name)
            if value is not None:
                getattr(self.ui, name).setCurrentText(str(value))
        for name in self.CHANNEL_BOXES:
            value = settings.value(name)
            if value is not None:
                getattr(self.ui, name).setValue(int(value))

    def save_connection_settings(self):
        settings = QSettings("OPTP_System", "InstrumentConnections")
        for name in self.VISA_BOXES + self.KINESIS_BOXES:
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

    def home_stage(self, stage_name: str) -> bool:
        """Explicit manual homing, including axes already marked as homed."""
        if getattr(self, '_scanning', False):
            return False
        stage_device = getattr(self, stage_name, None)
        if stage_device is None:
            print(f"Warning: {stage_name} is not connected for homing.")
            return False
        try:
            # Driver home() skips an already-homed axis; a manual Home must move again.
            stage_device.ensure_enabled()
            stage_device._chan.Home(60000)
            self.qwait_time(1000)  # match connection homing: allow polled position to refresh
            position = stage_device.position()
            getattr(self.ui, f'{stage_name}CurrPos').setValue(position)
            print(f"{stage_name.capitalize()} homed. Current position: {position} mm")
            return True
        except Exception as e:
            print(f"Error homing {stage_name}: {e}")
            return False

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
            unit = 'mm' if stage_name in ('stage1', 'stage2') else 'deg'
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
        'iPos1', 'iPos2', 'scanRepNO1', 'scanRepNO2', 'iRot1', 'iRot2', 'iRot3',
        'ScanRepNO_R1', 'ScanRepNO_R2', 'Rot_stages_couple', 'pol_cali_mode', 'cali_file_path',
        'wait1', 'wait2', 'wait1multip', 'wait2multip',
        'ScanT', 'startT', 'stepT', 'T_NO', 'Tolerance', 'waitiTC', 'T_stab_cnt', 'WaitSamStable',
        'driftComp', 'TDS_Ppos', 'R1_step', 'R1_pts', 'R2_step', 'R2_pts',
        'stage2CompDir', 'repeatPeak', 'passOrder', 'beamSettle', 'AutoBlock', 'fmPassCh',
        'pmRecord', 'pmSettle', 'pmAvgNO', 'pmRefresh',
    ) + tuple(f'stage{n}Step{s}{suffix}' for n in (1, 2) for s in (1, 2, 3) for suffix in ('', 'NO')) \
      + tuple(f'rotary{n}{suffix}' for n in (1, 2, 3) for suffix in ('Step', 'StepNO'))

    def collect_scan_config(self):
        """Snapshot current scan inputs, including positions updated by peak tracking."""
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
        return {'format': 'OPTP.scan_config', 'schema_version': 1, 'application_version': '4.4',
                'saved_at': datetime.now().astimezone().isoformat(timespec='seconds'),
                'parameters': values, 'temperature_points_K': list(self.tp_manager.temp_sequence)}

    def validate_scan_config(self, payload, config_dir):
        """Validate everything, including the calibration file, before changing any UI state."""
        if not isinstance(payload, dict) or payload.get('format') != 'OPTP.scan_config':
            raise ValueError('This is not an OPTP scan configuration.')
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
                               ('on_rot_stages_couple_toggled', 'Rot_stages_couple'),
                               ('on_stage2_comp_dir_toggled', 'stage2CompDir'),
                               ('on_pass_order_toggled', 'passOrder'),
                               ('on_repeat_peak_toggled', 'repeatPeak')):
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
        """Save a timestamped UI image beside the current/latest data file."""
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
            stem = os.path.splitext(image_path)[0]
            capture_time = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            image_path = f'{stem}_screenshot_{capture_time}.png'
            suffix = 2
            while os.path.exists(image_path):
                image_path = f'{stem}_screenshot_{capture_time}_{suffix}.png'
                suffix += 1
            image_path = os.path.abspath(image_path)
            os.makedirs(os.path.dirname(image_path), exist_ok=True)
            pixmap = self.ui.grab()
            if pixmap.isNull():
                raise RuntimeError('The application interface could not be captured.')
            # Commit the new PNG only after encoding completes successfully.
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
            
            data_save_dir = os.path.join(parent_dir, 'OPTP_Data')
            if not os.path.exists(data_save_dir):
                os.makedirs(data_save_dir)
                print(f"Created OPTP_Data folder: {data_save_dir}")
            else:
                print(f"OPTP_Data folder already exists: {data_save_dir}")
                
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

    def setup_dataFile_Name(self, add_str: str | None = None, thread=None) -> str | None:
        try:
            # get current time h-m-s
            now = datetime.now()
            time_stamp = now.strftime('%Hh%Mm%Ss')
            file_name_timePart = f'{time_stamp}'
            print(f"Current time part for file name: {file_name_timePart}")

            # display time part in dataFileName QLineEdit
            if thread is not None:
                thread.filename_update.emit(file_name_timePart)
            else:
                self.ui.dataFileName.setText(file_name_timePart)

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
        Loop order is outermost -> innermost; stage1 = THz delay, stage2 = pump delay.
        'THz_Scan': THz time-domain scan; rotation stages -> stage1 -> stage2 (stage2 normally one pump delay);
        '1D_THz': pump-probe 1D scan, stage1 fixed at the THz peak; rotation stages -> stage1 -> stage2;
        'POL_2D': polarization-dependent scan at fixed stage1 / stage2 points; stage1 -> stage2 -> rotation stages
                  (same name as MO and the shared planner, which puts the polarization innermost for 'POL_2D');
        '2D_THz': one full THz waveform (stage1) at each pump delay (stage2); rotation stages -> stage2 -> stage1;
        """
        scan_modes = ['THz_Scan', '1D_THz', 'POL_2D', '2D_THz']
        self.ui.scanMode.addItems(scan_modes)
        
        self.test_mode = scan_modes[0]  # default to first mode 1D Scan
            
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

    # Peak search tab toggles: checked = Reverse (stage2 moves opposite to the stage1 peak shift) / Pass -> Soak
    def on_stage2_comp_dir_toggled(self, checked: bool):
        self.ui.stage2CompDir.setText('Reverse' if checked else 'Forward')

    def on_pass_order_toggled(self, checked: bool):
        self.ui.passOrder.setText('Pass → Soak' if checked else 'Soak → Pass')

    def on_repeat_peak_toggled(self, checked: bool):
        self.ui.repeatPeak.setText('Re-peak: ON' if checked else 'Re-peak: OFF')
    
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
       
        # Never replace a QThread until its native thread has fully exited.
        old_thread = self.itc_stab_thread
        if old_thread is not None:
            if old_thread.isRunning():
                old_thread.stop_flag = True  # stop this worker without aborting the scan
                old_thread.requestInterruption()
            if not old_thread.wait(2000):
                message = "Previous iTC stabilization thread is still stopping; target temperature was not changed. Please retry."
                print(f"Warning: {message}")
                if not update_ui:
                    raise RuntimeError(message)  # a scan must not continue at an unset target
                return False

        if update_ui:
            self.ui.TempDone.status = False

        # Change the hardware target only after the previous worker has stopped.
        with self.mercuryiTC.io_lock:
            self.mercuryiTC.set_temp_point(self.uid_TEMP, target_T)

        # create and start iTCStabilizerThread
        self.itc_stab_thread = iTCstabilizeThread(self, target_T, tolerance, waitiTC, stab_cnt)

        # connect signal
        if update_ui:
            self.itc_stab_thread.stabilized.connect(self.on_temp_done)

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

    #region Extra wait for heating by the pump beam to settle
    def wait_beam_stable(self, thread=None) -> bool:
        """Add the full beamSettle time after both sample soak and confirmed AutoBlock pass.

        Called once per stabilized temperature point, before peak search / measurement,
        regardless of the beam / soak order. Returns False on a stop request.
        """
        if self._check_scan_stop(thread):
            return False
        wait_min = self.ui.beamSettle.value()
        if wait_min <= 0:
            print("Beam settle wait is 0 min; continuing immediately.")
            return True

        total_s = int(round(wait_min * 60))
        message = f"Beam settle: waiting {wait_min:g} min ({total_s} s) after sample soak and beam pass"
        print(message)
        self.scan_log_event(message, thread)
        remaining = total_s
        while remaining > 0:
            sleep_s = min(5, remaining)
            if not self._sleep_unless_stopped(sleep_s, thread):
                self.scan_log_event("Beam settle wait interrupted by stop request", thread)
                return False
            remaining -= sleep_s
            mins, secs = divmod(remaining, 60)
            print(f"Beam settle countdown: {mins:02d}:{secs:02d} remaining ({remaining}/{total_s} s)")

        self.scan_log_event("Beam settle wait complete; proceeding to peak search / measurement", thread)
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

    def get_TDS_peak_pos(self, thread=None, center_pos: float | None = None) -> dict:
        """Two-round (coarse, then fine) search of the stage1 THz peak on Lock-in 1 X around center_pos.

        Step and +/- points of each round come from the Peak search tab; each window is symmetric,
        centre +/- N steps. center_pos defaults to TDS Ppos. Returns 'status' ('ok' / 'failed' /
        'stopped'), 'max_position' (mm) and 'max_lockin1X', plus 'reason' when it failed. A round-1
        maximum on the window edge counts as failed: the peak may have left the window, and an edge
        point is not a peak.
        """
        failed = {'status': 'failed', 'max_position': None, 'max_lockin1X': None, 'positions': [], 'lockin1X': []}

        if not (self.ui.activeStage1.isChecked() and self.stage1):
            print("Warning: Stage1 is not connected for TDS scan.")
            return {**failed, 'reason': 'Stage1 not connected'}
        if not (self.ui.activeLockin1.isChecked() and self.lockin1):
            print("Warning: Lockin1 is not connected for TDS scan.")
            return {**failed, 'reason': 'Lock-in 1 not connected'}

        if self._check_scan_stop(thread):
            return {**failed, 'status': 'stopped'}

        if center_pos is None:
            center_pos = float(self.ui.TDS_Ppos.value())
        wait_time_s = self.ui.wait1.value() / 1000  # lock-in settling time per point

        def run_single_pass(pass_no: int, pass_center: float, pass_step: float, n_side: int) -> dict:
            """Scan pass_center +/- n_side steps once and return the analyzed peak result."""
            pos_seq_stage1 = ScanDataCore.build_peak_tracking_positions(
                pass_center, pass_step, points_before_center=n_side, points_after_center=n_side + 1
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
                    print("Peak search interrupted before moving to the next stage position.")
                    return stopped_peak_result()

                try:
                    self.stage1.move_to(pos)
                except Exception as e:
                    raise RuntimeError(f"Stage1 move to {pos} mm failed during peak search: {e}") from e

                # update curr NO / curr position displays during the peak search
                if thread is not None:
                    thread.stepNO_update.emit({'stage1_NO': idx})
                    thread.position_update.emit({'stage1_pos': round(self.stage1.position(), 3)})

                time.sleep(wait_time_s)  # wait for stage and lock-in to settle

                if self._check_scan_stop(thread):
                    print("Peak search interrupted during sampling.")
                    return stopped_peak_result()

                try:
                    x_val = float(self.lockin1.get_x())
                except Exception as e:
                    raise RuntimeError(f"Lock-in 1 X read failed during peak search at {pos} mm: {e}") from e

                peak_samples.append((pos, [x_val]))

                # show this position's reading live in the realtime Lock-in 1 X chart
                if thread is not None and np.isfinite(x_val):
                    thread.lockin_update.emit({'l1x': x_val})

            result = ScanDataCore.analyze_peak_samples(peak_samples)
            result['window'] = (pos_seq_stage1[0], pos_seq_stage1[-1])
            return result

        # Round 1 finds the peak in a wide window, round 2 refines around it. The coarse step must stay
        # below the THz peak width (~6 um of travel for a ~40 fs pulse), or it steps over the peak.
        rounds = (('coarse', self.ui.R1_step.value() / 1000.0, self.ui.R1_pts.value()),
                  ('fine', self.ui.R2_step.value() / 1000.0, self.ui.R2_pts.value()))
        result = failed
        for pass_no, (kind, step_mm, n_side) in enumerate(rounds, 1):
            print(f"Peak search round {pass_no}/2 ({kind}): step {step_mm * 1000:g} um, +/-{n_side} points "
                  f"(+/-{n_side * step_mm * 1000:g} um) around {center_pos:.3f} mm.")
            result = run_single_pass(pass_no, center_pos, step_mm, n_side)
            if result['status'] != 'ok':
                print(f"Peak search round {pass_no}/2 ({kind}) found no valid peak; stopping search.")
                if result['status'] == 'failed':
                    result['reason'] = 'no valid Lock-in 1 reading'
                return result
            if pass_no == 1 and result['max_position'] in result['window']:
                print(f"Peak search round 1: maximum on the window edge ({result['max_position']} mm); "
                      f"the peak may have left the window. Search counted as failed.")
                result.update(status='failed', reason=f"round-1 maximum on the window edge ({result['max_position']:.3f} mm)",
                              max_position=None, max_lockin1X=None)
                return result
            center_pos = result['max_position']
            print(f"Peak search round {pass_no}/2 ({kind}) complete. Max Lockin1 X: "
                  f"{result['max_lockin1X']} at position: {center_pos} mm.")

        print(f"Peak search complete. Max Lockin1 X: {result['max_lockin1X']} at position: {result['max_position']} mm.")
        return result  # in mm

    #region Peak search and drift compensation (Peak search tab)
    # Thermal expansion of the sample holder / sample shifts the THz and pump paths together, so the drift
    # itself leaves the pump-THz delay alone - but the stage1 move that re-peaks the THz changes it.
    # Moving stage2 by the same amount (sign from the stage2 mounting) undoes that.
    def temperature_scan_active(self) -> bool:
        """True when the scan steps through temperatures: iTC ticked and connected, ScanT ticked, points listed."""
        return bool(self.ui.activeiTC.isChecked() and self.mercuryiTC and self.ui.ScanT.isChecked()
                    and len(self.tp_manager.temp_sequence) > 0)

    def drift_comp_active(self) -> bool:
        return self.ui.driftComp.isChecked()

    def tds_ppos_is_set(self) -> bool:
        return self.ui.TDS_Ppos.value() > self.ui.TDS_Ppos.minimum()  # the minimum shows 'Not set'

    def confirm_drift_compensation(self) -> bool:
        """Before peak tracking: validate the reference and confirm the correction policy."""
        ui = self.ui
        problems = []
        if not self.tds_ppos_is_set():
            problems.append("TDS Ppos is not set (Inst. Config. -> Peak search).")
        if not (ui.activeStage1.isChecked() and self.stage1):
            problems.append("Stage1 is not active and connected - the peak search needs it.")
        if not (ui.activeLockin1.isChecked() and self.lockin1):
            problems.append("Lock-in 1 is not active and connected - the peak search needs it.")
        if problems:
            message = ("Drift compensation is on, but:\n\n" + "\n".join(f"  - {p}" for p in problems)
                       + "\n\nFix this, or untick 'Drift comp.' on the Peak search tab, then start the scan again.")
            print(message)
            QMessageBox.warning(ui, "Drift compensation not ready", message)
            return False

        ppos, ipos1, ipos2 = ui.TDS_Ppos.value(), ui.iPos1.value(), ui.iPos2.value()
        lines = [f"TDS Ppos:  {ppos:.3f} mm", f"iPos1:  {ipos1:.3f} mm", f"iPos2:  {ipos2:.3f} mm",
                 f"Stage2 compensation:  {ui.stage2CompDir.text()}",
                 f"Round 1:  {ui.R1_step.value()} um x \u00b1{ui.R1_pts.value()}",
                 f"Round 2:  {ui.R2_step.value()} um x \u00b1{ui.R2_pts.value()}"]
        if ui.scanMode.currentText() == '1D_THz' and ui.scanRepNO2.value() > 1:
            lines.append(f"Stage2 repeat peak search:  {'on' if ui.repeatPeak.isChecked() else 'off'}")
        if ui.scanMode.currentText() == '1D_THz':
            lines.append("Changed rotary angles: search before the first sweep, even with Re-peak off.")
        if ui.AutoBlock.isChecked() and self.temperature_scan_active():
            lines.append(f"Beam / soak:  {ui.passOrder.text()}")
            lines.append(f"Extra beam settle:  {ui.beamSettle.value():g} min after soak and beam pass")
        note = ""
        stage1_fixed = len(self.scan_planner.generate_position_sequence(ipos1, self.get_step_array('stage1'))[0]) == 1
        if ui.scanMode.currentText() == '1D_THz' and stage1_fixed:
            note = (f"\n\nStage1 will follow the newly found peak directly; its current offset from TDS Ppos "
                    f"is {(ipos1 - ppos) * 1000:+.1f} um and will not be retained. "
                    "Stage2 is compensated using the actual Stage1 correction.")
        elif stage1_fixed and abs(ipos1 - ppos) > ui.R2_step.value() / 1000.0:
            note = (f"\n\nNote: stage1 stays at one position in this scan and iPos1 differs from TDS Ppos by "
                    f"{(ipos1 - ppos) * 1000:+.1f} um - it will keep this offset from the peak.")
        reply = QMessageBox.question(
            ui, "Confirm drift compensation reference",
            "Drift compensation is on: before acquisition (at each temperature point when ScanT is on), the stage1 peak is searched around "
            "TDS Ppos. Stage1 and Stage2 are corrected together.\n\n" + "\n".join(lines) + note
            + "\n\nIs TDS Ppos the stage1 peak for the current iPos1 / iPos2?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return reply == QMessageBox.Yes

    def compensate_temperature_drift(self, thread, iPos1: float, iPos2: float, Ppos: float, iRots: tuple, rotary_stepNOs=None):
        """Search around Ppos and correct iPos1 / iPos2 together (scan thread).

        All stages go to the scan start configuration first. Fixed 1D_THz follows the peak directly;
        other scans retain their window offset. Returns (iPos1, iPos2, Ppos, stopped).
        A failed search keeps the old values.
        """
        _, positions = self.move_active_stages((iPos1, iPos2, *iRots))
        # Show the actual new angle and its progress before peak acquisition begins.
        thread.position_update.emit(dict(zip(
            ('stage1_pos', 'stage2_pos', 'rotary1_pos', 'rotary2_pos', 'rotary3_pos'), positions)))
        if rotary_stepNOs is not None:
            thread.stepNO_update.emit(rotary_stepNOs)
        result = self.get_TDS_peak_pos(thread, Ppos)
        if result.get('status') == 'stopped':
            return iPos1, iPos2, Ppos, True
        if result.get('status') != 'ok':
            self.scan_log_event(f"WARNING: peak search failed ({result.get('reason', 'unknown reason')}); "
                                f"iPos1 {iPos1:.3f}, iPos2 {iPos2:.3f}, Ppos {Ppos:.3f} mm kept", thread)
            return iPos1, iPos2, Ppos, False

        new_peak = result['max_position']
        delta = new_peak - Ppos
        fixed_1d = (self.ui.scanMode.currentText() == '1D_THz'
                    and len(self.scan_planner.generate_position_sequence(iPos1, self.get_step_array('stage1'))[0]) == 1)
        # A fixed 1D probe must sit on the peak; waveform windows retain their offset.
        # Undo the full actual Stage1 correction on Stage2, including a stale initial offset.
        correction = new_peak - iPos1 if fixed_1d else delta
        sign = -1 if self.ui.stage2CompDir.isChecked() else 1
        iPos1 = round(iPos1 + correction, 3)
        iPos2 = round(iPos2 + sign * correction, 3)
        # the scan continues with the returned values; the UI is only told, asynchronously
        thread.tds_peak_update.emit(iPos1)
        thread.ipos2_update.emit(iPos2)
        thread.ppos_update.emit(new_peak)
        self.scan_log_event(f"Peak search: Ppos {Ppos:.3f} -> {new_peak:.3f} mm (delta {delta * 1000:+.1f} um); "
                            f"iPos1 -> {iPos1:.3f}, iPos2 -> {iPos2:.3f} mm ({self.ui.stage2CompDir.text()}); "
                            f"Stage1 correction {correction * 1000:+.1f} um", thread)
        return iPos1, iPos2, new_peak, False
    #endregion

    def update_iPos1_from_tds_peak(self, new_pos: float):
        """Show the drift-compensated iPos1 in the UI."""
        try:
            self.ui.iPos1.setValue(new_pos)
            print(f"Updated iPos1 to {new_pos} mm.")
        except Exception as e:
            print(f"Error updating iPos1: {e}")

    def update_iPos2_from_drift(self, new_pos: float):
        """Show the drift-compensated iPos2 in the UI."""
        self.ui.iPos2.setValue(new_pos)
        print(f"Updated iPos2 to {new_pos} mm.")

    def update_TDS_Ppos(self, new_pos: float):
        """Show the peak found by the last search as the new TDS Ppos."""
        self.ui.TDS_Ppos.setValue(new_pos)
    #endregion
     
    #region Move active stages and display current positions
    def prepare_scan_plan(self):
        """Validate the UI configuration before starting a worker or changing any instruments."""
        ui = self.ui
        repetitions = tuple(getattr(ui, name).value() for name in
                            ('scanRepNO1', 'scanRepNO2', 'ScanRepNO_R1', 'ScanRepNO_R2'))
        rep_plan = DataProcess.validate_scan_repetitions(*repetitions)
        if not rep_plan['is_valid']:
            raise ValueError(str(rep_plan['error_msg']))

        initials = tuple(getattr(ui, name).value() for name in ('iPos1', 'iPos2', 'iRot1', 'iRot2', 'iRot3'))
        arrays = tuple(self.get_step_array(axis) for axis in ('stage1', 'stage2', 'rotary1', 'rotary2', 'rotary3'))
        sequences = tuple(self.scan_planner.generate_position_sequence(start, steps)
                          for start, steps in zip(initials, arrays))
        # Calibration forces coupling, as in the existing acquisition path.
        manu_cali_active = bool(ui.pol_cali_mode.isChecked() and self.cali_table)
        if manu_cali_active and not ui.Rot_stages_couple.isChecked():
            print("Note: a calibration table is loaded, so the rotation stages run coupled for "
                  "this scan even though the button reads 'Independent'.")
        pol_plan = self.scan_planner.build_pol_states(
            iRot1=initials[2], iRot2=initials[3], iRot3=initials[4],
            rotary1_pos_sequence=sequences[2][0],
            rotary2_pos_sequence=sequences[3][0],
            rotary3_pos_sequence=sequences[4][0],
            rotary1_NO=len(sequences[2][0]), rotary2_NO=len(sequences[3][0]), rotary3_NO=len(sequences[4][0]),
            polarization_policy='coupled' if ui.Rot_stages_couple.isChecked() or manu_cali_active else 'independent',
            pol_cali_mode=ui.pol_cali_mode.isChecked(), cali_table=self.cali_table,
            active_rotaries=tuple(getattr(self.ui, f'activeRot{n}').isChecked() for n in (1, 2, 3)),
        )
        error_msg = pol_plan.get('error_msg')
        if isinstance(error_msg, str) and error_msg.startswith('Error:'):
            raise ValueError(error_msg)
        elif error_msg:
            print(f"Warning: {error_msg}")

        # Include the initial rotary configuration used before search/repeat resets,
        # which can differ from the calibrated polarization positions.
        self.validate_scan_travel((
            ('Stage1', ui.activeStage1, self.stage1, sequences[0][0], 'mm'),
            ('Stage2', ui.activeStage2, self.stage2, sequences[1][0], 'mm'),
            ('Rotary1', ui.activeRot1, self.rotary1, [initials[2]] + pol_plan['pol_rot1_list'], 'deg'),
            ('Rotary2', ui.activeRot2, self.rotary2, [initials[3]] + pol_plan['pol_rot2_list'], 'deg'),
            ('Rotary3', ui.activeRot3, self.rotary3, [initials[4]] + pol_plan['pol_rot3_list'], 'deg'),
        ))
        return {'scan_mode': ui.scanMode.currentText(), 'initials': initials, 'arrays': arrays,
                'sequences': sequences, 'repetitions': repetitions, 'pol_rep': int(rep_plan['pol_rep']),
                'pol_plan': pol_plan}

    def validate_scan_travel(self, axis_plans):
        """Reject unreachable planned positions, including paths shifted by a repeat peak search."""
        travel_errors = []
        for label, active_box, device, targets, unit in axis_plans:
            if not (active_box.isChecked() and device):
                continue
            limits = getattr(device, 'travel_limits', None)
            low, high = limits() if limits else (None, None)
            if low is None or high is None:
                continue  # controller did not report a travel; the move itself still guards
            # Full-turn rotary stages may wrap targets into their travel.
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
            raise ValueError("Error: planned positions do not fit the stage travel.\n" + "\n".join(travel_errors))

    def move_active_stages(self, target_positions: tuple):
        """Move enabled axes; propagate driver/readback errors without comparing position tolerances."""
        stage1_pos, stage2_pos, rotary1_pos, rotary2_pos, rotary3_pos = target_positions
        
        # Initialize current positions with placeholder (-1)
        currStage1Pos = -1; currStage2Pos = -1
        currRotary1Pos = -1; currRotary2Pos = -1
        currRotary3Pos = -1
        
        # Names the axis being commanded, so a driver exception can say which one failed
        # instead of just "Error moving active stages" - controllers do not name themselves.
        moving_axis = None
        try:
            # move Stage1 if active
            if self.ui.activeStage1.isChecked() and self.stage1:
                moving_axis = f"Stage1 to {stage1_pos} mm"
                self.stage1.move_to(stage1_pos) # in mm
                currStage1Pos = round(self.stage1.position(), 3)  # # update current position display in mm

            # Stage2 and the rotaries move (and are read back) only when their target changes
            if self.ui.activeStage2.isChecked() and self.stage2:
                moving_axis = f"Stage2 to {stage2_pos} mm"
                currStage2Pos = self._move_unless_there('stage2', self.stage2, stage2_pos)  # update current position display in mm

            # move Rotary1 if active
            if self.ui.activeRot1.isChecked() and self.rotary1:
                moving_axis = f"Rotary1 to {rotary1_pos} deg"
                currRotary1Pos = self._move_unless_there('rotary1', self.rotary1, rotary1_pos)  # update current position display in degrees

            # move Rotary2 if active
            if self.ui.activeRot2.isChecked() and self.rotary2:
                moving_axis = f"Rotary2 to {rotary2_pos} deg"
                currRotary2Pos = self._move_unless_there('rotary2', self.rotary2, rotary2_pos)  # update current position display in degrees
            
            # move Rotary3 if active
            if self.ui.activeRot3.isChecked() and self.rotary3:
                moving_axis = f"Rotary3 to {rotary3_pos} deg"
                currRotary3Pos = self._move_unless_there('rotary3', self.rotary3, rotary3_pos)  # update current position display in degrees

            currPositions = (currStage1Pos, currStage2Pos, currRotary1Pos, currRotary2Pos, currRotary3Pos)

            return True, currPositions
        except Exception as e:
            raise RuntimeError(f"Error moving {moving_axis or 'active stages'}: {e}") from e

    def _move_unless_there(self, name: str, device, target: float) -> float:
        """Move an axis to target and return its read-back position (rounded), unless the same device
        already reached this exact target earlier in this scan; then return that read-back again.

        While Stage1 sweeps, Stage2 and the rotaries keep one target for hundreds of points, and every
        point used to repeat their MoveTo and position read. A failed move leaves no entry, so the next
        point moves again; a reconnected device is a new object and always moves. _execute_scan_logic
        clears _scan_axis_cache at the start of each scan, so the first point of a scan always moves.
        """
        last = self._scan_axis_cache.pop(name, None)
        if last is not None and last[0] is device and last[1] == target:
            self._scan_axis_cache[name] = last
            return last[2]
        device.move_to(target)
        actual = round(device.position(), 3)
        self._scan_axis_cache[name] = (device, target, actual)
        return actual
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
            # The whole window stays disabled until the program quits (or the exit is cancelled): no
            # scan, Goto T, Jog or second Exit can start while the workers stop and the instruments
            # close (closeInstruments() also processes events). Dialogs stay usable.
            self.ui.setEnabled(False)
            if not self.stop_workers_for_exit():
                self.ui.setEnabled(True)
                print("Exit cancelled; the scan still stops at its next checkpoint.")
                return
            # only_active=False on exit: anything still open must be released even if its 'active'
            # box was unticked, otherwise the port stays locked after the application is gone.
            self.closeInstruments(only_active=False)  # close all instruments first

            app = QApplication.instance()
            if app:
                app.quit()  # then exit application
            
        else:
            print("Exit cancelled.")

    def stop_workers_for_exit(self, timeout_s: float = 30.0) -> bool:
        """Stop the scan and temperature-stabilization threads and wait until they have ended, so that
        closeInstruments() never closes a device a worker is still using. Returns True when none runs.

        The exit confirmation already covers stopping the scan, so no second question is asked. The running
        threads are collected again on every pass: a scan that is inside iTC_goto_targetT() when the exit
        starts creates its stabilization thread afterwards, and that thread only watches its own stop flag.
        Events are processed while waiting, so the end-of-scan slots still run (exitApp() keeps the window
        disabled meanwhile). If a worker is still busy after timeout_s (for example in a long stage move),
        the user can keep waiting or cancel the exit; the stop requests stay in place either way.
        """
        def running():
            return [t for t in (self.scan_Thread, self.itc_stab_thread) if t is not None and t.isRunning()]

        if not running():
            return True
        self.stop_flag = True
        requested = []  # thread objects already asked to stop (kept referenced, compared by identity)
        print("Waiting for the scan to stop before closing the instruments...")
        deadline = time.monotonic() + timeout_s
        while True:
            workers = running()
            if not workers:
                break
            for worker in workers:
                if not any(worker is done for done in requested):
                    worker.request_stop()
                    requested.append(worker)
            QApplication.processEvents(QEventLoop.AllEvents, 50)
            QThread.msleep(20)
            if time.monotonic() > deadline:
                reply = QMessageBox.question(
                    self.ui, 'Scan still running',
                    f'The scan has not stopped within {timeout_s:.0f} s (it may be in a long move).\n\n'
                    'Yes: keep waiting.\nNo: cancel the exit; the scan still stops at its next checkpoint.',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if reply != QMessageBox.Yes:
                    return False
                deadline = time.monotonic() + timeout_s
        QApplication.processEvents()  # deliver the workers' last signals before the instruments close
        return True
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
        temperature_scan = self.temperature_scan_active()
        if temperature_scan:
            lines.append(f"Temperature : {', '.join(f'{t:g}' for t in temps)} K "
                         f"(tolerance {ui.Tolerance.value():g} K, sample soak {ui.WaitSamStable.value():g} min)")
        else:
            lines.append("Temperature : no temperature scan")
        if ui.driftComp.isChecked():
            lines.append(f"Drift comp. : on, TDS Ppos {ui.TDS_Ppos.value():.3f} mm, "
                         f"R1 {ui.R1_step.value()} um x \u00b1{ui.R1_pts.value()}, "
                         f"R2 {ui.R2_step.value()} um x \u00b1{ui.R2_pts.value()}, stage2 {ui.stage2CompDir.text()}")
            if ui.scanMode.currentText() == '1D_THz' and ui.scanRepNO2.value() > 1:
                lines.append(f"Repeat peak : {'on' if ui.repeatPeak.isChecked() else 'off'} "
                             "before Stage2 repeats 2 and later")
            if ui.scanMode.currentText() == '1D_THz':
                lines.append("Angle peak  : on before the first sweep at changed rotary angles")
        else:
            lines.append("Drift comp. : off")

        if ui.AutoBlock.isChecked():
            lines.append(f"AutoBlock   : on ({ui.fmPassCh.currentText()})"
                         + (f", {ui.passOrder.text()}" if temperature_scan else ""))
            if temperature_scan:
                lines.append(f"Beam settle : {ui.beamSettle.value():g} min extra after sample soak and beam pass")
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
        """Mirror stdout/stderr into the Live Process box and file from program start until it quits.

        The terminal still gets every line. print() may come from any thread; the text reaches the box
        through a queued signal and is appended at once to LiveProcess_<date>.txt in the data folder
        (write_console_file). The box keeps the latest 1000 lines (maximumBlockCount in the .ui) and is
        not cleared between scans; the file keeps everything.
        """
        self._console_signal = ConsoleSignal()
        self._console_signal.text.connect(self.append_console_text, Qt.QueuedConnection)
        self._console_file_lock = threading.RLock()  # shared by stdout and stderr, which have their own locks
        self._console_file = None
        self._console_file_path = None
        self._console_pending = []  # text printed before the data folder is set
        self._console_session = f"Session started {datetime.now():%Y-%m-%d %H:%M:%S} - {self.ui.windowTitle()}"
        self._console_terminal = sys.stderr  # file-write warnings go here directly, never through print()
        self._console_streams = []
        for name in ('stdout', 'stderr'):
            terminal = getattr(sys, name)
            stream = ConsoleMirrorStream(terminal, self.mirror_console_text)
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
        self.close_console_file()

    def mirror_console_text(self, text: str):
        """Called by the mirror streams from any thread."""
        self.write_console_file(text)
        self._console_signal.text.emit(text)

    def write_console_file(self, text: str):
        """Append console text to LiveProcess_<date>.txt in the current data folder (any thread).

        Text printed before the data folder is set is written first. Every write is flushed, so a crash
        loses nothing. A new data folder or a new day opens a new file with a session header. If the file
        cannot be written, one warning goes to the terminal and the box, and the file is tried again when
        the folder or the day changes. Must not print(): that would come back here.
        """
        with self._console_file_lock:
            self._console_pending.append(text)
            folder = getattr(self, 'dataSave_path', None)
            if not folder:
                return
            path = os.path.join(folder, f"LiveProcess_{datetime.now():%Y-%m-%d}.txt")
            try:
                if path != self._console_file_path:
                    self.close_console_file()
                    self._console_file_path = path
                    self._console_file = open(path, 'a', encoding='utf-8')
                    self._console_file.write(f"\n{'=' * 72}\n{self._console_session}\n{'-' * 72}\n")
                if self._console_file is not None:
                    self._console_file.write(''.join(self._console_pending))
                    self._console_file.flush()
            except OSError as e:
                self.close_console_file()
                warning = f"Warning: could not write Live Process file {path}: {e}\n"
                if self._console_terminal is not None:
                    self._console_terminal.write(warning)
                self._console_signal.text.emit(warning)
            self._console_pending.clear()

    def close_console_file(self):
        with self._console_file_lock:
            if self._console_file is not None:
                try:
                    self._console_file.close()
                except OSError:
                    pass
                self._console_file = None

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
            (self.scan_Thread.ipos2_update, self.update_iPos2_from_drift),
            (self.scan_Thread.ppos_update, self.update_TDS_Ppos),
            (self.scan_Thread.fm_block_led, self.on_fm_block_led),
            (self.scan_Thread.scan_log, self.append_scan_log),
            (self.scan_Thread.filename_update, self.ui.dataFileName.setText),
            (self.scan_Thread.scan_finished, self.on_scan_finished),
            (self.scan_Thread.error_occurred, self.on_handle_scan_error),
            (self.scan_Thread.finished, self.on_scan_thread_finished),
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

        # Reject bad counts/positions before the temperature wait, beam changes, peak search or files.
        try:
            scan_plan = self.prepare_scan_plan()
        except Exception as e:
            message = f"Cannot start scan - invalid scan plan:\n\n{e}"
            print(message)
            QMessageBox.warning(self.ui, "Invalid scan plan", message)
            return

        # Any scan with drift compensation needs a confirmed TDS Ppos reference.
        if self.drift_comp_active() and not self.confirm_drift_compensation():
            return

        # A disabled checkbox does not stop its QTimer. Release both Realtime switches
        # before the worker starts; they stay off after the scan, until explicitly enabled.
        self.ui.realtimeDisp1.setChecked(False)
        self.ui.realtimeDisp2.setChecked(False)
        self.chart_updaters['realDisChart1'].toggle(False)
        self.chart_updaters['realDisChart2'].toggle(False)

        # update data folder date if not using custom path
        if not getattr(self, 'is_custom_save_path', False):
            self.setup_data_folder()

        # Refresh immediately, including scans still waiting/recording/searching.
        self.setup_dataFile_Name()
        self.fullFilePath = None  # a new preparation-stage screenshot must not use the previous scan

        self.start_scan_log()  # test conditions go into the ScanLog box and the day's log file
        
        # reset stop flag
        self.stop_flag = False  # this is the main moSys class stop flag, also used in ScanThread
        
        # setup buttons state during scan
        self.set_ControlsEnabledDuringScan(True)
        
        # Create scan thread, connect to the separate 'ScanThread' class
        self._disconnect_scan_signals()
        self.scan_Thread = ScanThread(self, scan_plan)  # use the same plan that passed validation
        
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
        self.scan_Thread.tds_peak_update.connect(self.update_iPos1_from_tds_peak)  # drift-compensated iPos1
        self.scan_Thread.ipos2_update.connect(self.update_iPos2_from_drift)          # drift-compensated iPos2
        self.scan_Thread.ppos_update.connect(self.update_TDS_Ppos)                   # peak found by the search
        self.scan_Thread.fm_block_led.connect(self.on_fm_block_led)  # flip mount beam state LED
        self.scan_Thread.scan_log.connect(self.append_scan_log)      # key scan events for the ScanLog box and file
        self.scan_Thread.filename_update.connect(self.ui.dataFileName.setText)

        self.scan_Thread.scan_finished.connect(self.on_scan_finished)     # could also add another slot function to handle initial results processing and display after scan finished
        self.scan_Thread.error_occurred.connect(self.on_handle_scan_error)
        self.scan_Thread.finished.connect(self.on_scan_thread_finished)  # controls back only when the worker has ended
        
        
        # start scan thread
        self.scan_Thread.start()
        print("Scan thread started.")
        
    #endregion
        
    #region _execute_scan_logic: actual scan logic executed in ScanThread
    def _execute_scan_logic(self, thread):   
        print("======================Executing scan logic in Thread======================")
        self._scan_axis_cache = {}  # see _move_unless_there: every axis moves at the first point of a scan
        plan = thread.scan_plan
        scan_mode = plan['scan_mode']
        stage1_array, stage2_array, rotary1_array, rotary2_array, rotary3_array = plan['arrays']
        stage1_rep, stage2_rep, rotary1_rep, rotary2_rep = plan['repetitions']
        pol_rep = plan['pol_rep']
        iRot1, iRot2, iRot3 = plan['initials'][2:]
        rotary1_pos_sequence, rotary1_step_sequence, rotary1_stepNO_sequence = plan['sequences'][2]
        rotary2_pos_sequence, rotary2_step_sequence, rotary2_stepNO_sequence = plan['sequences'][3]
        rotary3_pos_sequence, rotary3_step_sequence, rotary3_stepNO_sequence = plan['sequences'][4]
        pol_plan = plan['pol_plan']
        pol_rot1_list, pol_rot2_list, pol_rot3_list = (pol_plan[f'pol_rot{i}_list'] for i in (1, 2, 3))
        N_pol = pol_plan['N_pol']
        
        #region set_Temperature if active and temperature scan is enabled
        has_temperature = self.temperature_scan_active()
        if has_temperature:
            Temp_sequence = self.tp_manager.temp_sequence # get temperature sequence from temperature profile manager
            print(f"Temperature scan enabled. Temperature points: {Temp_sequence}")
        else:
            Temp_sequence = [None]  # single iteration with no temperature change
            print("Temperature scan disabled or no temperature profile defined.")

        # Start positions travel with the scan: drift compensation updates them after each peak search,
        # and the UI is only updated asynchronously, so they are never read back from the UI.
        drift_comp = self.drift_comp_active()
        active_rotaries = tuple(getattr(self.ui, f'activeRot{n}').isChecked() for n in (1, 2, 3))
        angle_peak = (drift_comp and scan_mode == '1D_THz' and any(
            enabled and len(set(angles)) > 1 for enabled, angles in
            zip(active_rotaries, (pol_rot1_list, pol_rot2_list, pol_rot3_list))))
        scan_iPos1, scan_iPos2 = plan['initials'][:2]
        scan_Ppos = self.ui.TDS_Ppos.value()
        scan_iRots = (iRot1, iRot2, iRot3)

        # loop over temperature sequence
        for temp_idx, target_T in enumerate(Temp_sequence):
            beam_passed = False  # AutoBlock: the beam is let through once per temperature point
            temperature_stabilized = False
            pump_power = None    # Record: measured right before the beam is let through, saved into this point's file

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
                # Only wait when a stabilization thread was actually started.
                if stab_started and self.itc_stab_thread is not None:
                    # This is already the scan worker: wait for actual thread termination,
                    # not the stabilization-result signal emitted just before run() returns.
                    self.itc_stab_thread.wait()

                    # The result is available even if the worker finished before this wait.
                    stab_ok = bool(getattr(self.itc_stab_thread, 'stab_success', False))
                    thread.temp_done_led.emit(stab_ok)  # LED reflects the real outcome

                    if not stab_ok:
                        print(f"Temperature stabilization FAILED at {target_T} K "
                              f"(instrument error, or stopped). Aborting the scan instead of "
                              f"measuring at an uncontrolled temperature.")
                        if not (self.stop_flag or thread.stop_flag):
                            self._scan_abort_reason = f"temperature stabilization failed at {target_T} K"
                        break

                    temperature_stabilized = True

                    # AutoBlock 'Pass -> Soak': let the beam through now, so the soak also absorbs the pump heating
                    if self.ui.AutoBlock.isChecked() and self.ui.passOrder.isChecked():
                        pump_power = self.record_pump_power(thread)  # last moment the pump falls on the meter
                        if self._check_scan_stop(thread):
                            print("Stop requested while recording the pump power. Exiting scan loop.")
                            break
                        if not self.set_flipmount_blocked(False, thread):
                            print("AutoBlock could not let the beam pass. Aborting the scan instead of measuring with the beam blocked.")
                            self._scan_abort_reason = "AutoBlock could not let the beam pass"
                            break
                        beam_passed = True

                    # The iTC sensor reaching setpoint does not mean the sample itself has: it lags
                    # behind, and scanning before it settles leaves residual thermal drift. Hold here
                    # for the extra soak time set in the UI before starting the scan.
                    if not self.wait_sample_stable(thread):
                        print("Stop requested during sample soak wait. Exiting scan loop.")
                        break
                    self.scan_log_event(f"T point {temp_idx + 1}/{len(Temp_sequence)} = {target_T} K reached "
                                        f"(stabilized + sample soak)", thread)
                else:
                    raise RuntimeError(f"Temperature stabilization could not start at {target_T} K; "
                                       "check the iTC connection and temperature sensor UID.")
                
                #region stop check before formal scan
                if self._check_scan_stop(thread):
                    print("Stop request detected before formal scan. Exiting current scan sequence.")
                    break
                #endregion

            # AutoBlock: let the beam through before the peak search and the measurement, unless 'Pass -> Soak'
            # already did. A mount that fails to open would produce a whole data set of blocked-beam signal, so abort.
            if self.ui.AutoBlock.isChecked() and not beam_passed:
                pump_power = self.record_pump_power(thread)  # last moment the pump falls on the meter
                if self._check_scan_stop(thread):
                    print("Stop requested while recording the pump power. Exiting scan loop.")
                    break
                if not self.set_flipmount_blocked(False, thread):
                    print("AutoBlock could not let the beam pass. Aborting the scan instead of measuring with the beam blocked.")
                    self._scan_abort_reason = "AutoBlock could not let the beam pass"
                    break
                beam_passed = True

            # Add the full beam-heating wait after BOTH the sample soak and a confirmed pass.
            # It is independent of Drift comp.: measurement also waits when peak search is off.
            if temperature_stabilized and beam_passed:
                if not self.wait_beam_stable(thread):
                    print("Stop requested during beam settle wait. Exiting scan loop.")
                    break

            # Drift compensation: search before acquisition, including scans without temperature control.
            if drift_comp:
                # Calibration may put the first polarization away from the UI starting angles.
                # Reset this reference at every temperature, after the last angle of the previous one.
                scan_iRots = ((pol_rot1_list[0], pol_rot2_list[0], pol_rot3_list[0])
                              if scan_mode == '1D_THz' else (iRot1, iRot2, iRot3))
                scan_iPos1, scan_iPos2, scan_Ppos, stopped = self.compensate_temperature_drift(
                    thread, scan_iPos1, scan_iPos2, scan_Ppos, scan_iRots,
                    {'rotary1_NO': rotary1_stepNO_sequence[0],
                     'rotary2_NO': rotary2_stepNO_sequence[0],
                     'rotary3_NO': rotary3_stepNO_sequence[0]})
                if stopped:
                    print("Peak search interrupted by stop request. Exiting scan loop.")
                    break

            # Peak search can shift both linear plans. Validate the actual compensated positions
            # before opening this temperature's data file or moving to a formal scan point.
            iPos1, iPos2 = scan_iPos1, scan_iPos2
            # Generate position sequences, in mm for linear stages, degree for rotary stages
            stage1_pos_sequence,  stage1_step_sequence,  stage1_stepNO_sequence  = self.scan_planner.generate_position_sequence(iPos1, stage1_array);  stage1_NO = len(stage1_pos_sequence)
            stage2_pos_sequence,  stage2_step_sequence,  stage2_stepNO_sequence  = self.scan_planner.generate_position_sequence(iPos2, stage2_array);  stage2_NO = len(stage2_pos_sequence)
            self.validate_scan_travel((
                ('Stage1', self.ui.activeStage1, self.stage1, stage1_pos_sequence, 'mm'),
                ('Stage2', self.ui.activeStage2, self.stage2, stage2_pos_sequence, 'mm'),
            ))

            #region Navigate to data save path and create file for saving data
            fileName = self.setup_dataFile_Name(f"{scan_mode}_{target_T}K" if self.ui.ScanT.isChecked() else scan_mode, thread)
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
            
            # Start positions after the initial peak search, when Drift comp. is on.
            self.ds_iPos1 = self.h5_file.create_dataset('iPos1', data=iPos1, dtype='f8')
            self.ds_stage1_array = self.h5_file.create_dataset('stage1_array', data=stage1_array, dtype='f8')
                    
            self.ds_iPos2 = self.h5_file.create_dataset('iPos2', data=iPos2, dtype='f8')
            self.ds_stage2_array = self.h5_file.create_dataset('stage2_array', data=stage2_array, dtype='f8')
            
            self.ds_iRot1 = self.h5_file.create_dataset('iRot1', data=iRot1, dtype='f8')
            self.ds_rotary1_array = self.h5_file.create_dataset('rotary1_array', data=rotary1_array, dtype='f8')

            self.ds_iRot2 = self.h5_file.create_dataset('iRot2', data=iRot2, dtype='f8')
            self.ds_rotary2_array = self.h5_file.create_dataset('rotary2_array', data=rotary2_array, dtype='f8')
            
            self.ds_iRot3 = self.h5_file.create_dataset('iRot3', data=iRot3, dtype='f8')
            self.ds_rotary3_array = self.h5_file.create_dataset('rotary3_array', data=rotary3_array, dtype='f8')

            rep_array = np.array([stage1_rep, stage2_rep, rotary1_rep, rotary2_rep], dtype='i8')
            self.ds_rep_array = self.h5_file.create_dataset('rep_array', data=rep_array, dtype='i8') 

            self.h5_file.flush()  # write to file for avoiding data loss
            
            lockin_shape = (stage1_NO, stage1_rep, stage2_NO, stage2_rep, N_pol, pol_rep)
            # An interrupted/failed scan leaves unacquired points as NaN, never as measured zeros.
            self.lockin_datasets = ScanStorageCore.create_lockin_datasets(self.h5_file, lockin_shape, fillvalue=np.nan)
            self.ds_lockin1_X = self.lockin_datasets['lockin1_X']
            self.ds_lockin1_Y = self.lockin_datasets['lockin1_Y']
            self.ds_lockin2_X = self.lockin_datasets['lockin2_X']
            self.ds_lockin2_Y = self.lockin_datasets['lockin2_Y']

            repeat_peak = (drift_comp and scan_mode == '1D_THz' and stage2_rep > 1
                           and self.ui.repeatPeak.isChecked())
            repeat_positions = None
            if repeat_peak or angle_peak:
                # Keep the original iPos1/iPos2 scalars as the first sweep's reference.
                # Record the coordinates actually used by each Stage2 sweep separately.
                repeat_positions = self.h5_file.create_dataset(
                    'repeat_scan_positions_mm',
                    shape=(stage1_NO, stage1_rep, stage2_rep, N_pol, pol_rep, 3),
                    dtype='f8', fillvalue=np.nan)
                repeat_positions.attrs['axes'] = 'stage1_idx,stage1_rep_idx,stage2_rep_idx,pol_idx,pol_rep_idx,column'
                repeat_positions.attrs['columns'] = 'stage1_target_mm,stage2_start_mm,tds_peak_mm'
                repeat_positions.attrs['description'] = 'Commanded sweep coordinates; recorded at the first acquired point.'

            print(f"HDF5 data file and datasets are initialized for saving.")
            
            
            # generate scan_iterator for all stages according to scan_mode
            iterator_plan = self.scan_planner.build_scan_iterator(
                scan_mode=scan_mode,
                stage1_NO=stage1_NO,
                stage1_rep=stage1_rep,
                stage2_NO=stage2_NO,
                stage2_rep=stage2_rep,
                N_pol=N_pol,
                pol_rep=pol_rep,
            )
            scan_iterator = iterator_plan['scan_iterator']

            # 2D_THz must record one full time-domain trace at each pump delay, so stage1 is the
            # fastest axis and stage2 steps outside it. build_scan_iterator() lives in the shared
            # func_cores module and yields stage2 innermost, so the order is rebuilt here instead
            # of changing the shared planner. The tuple layout is unchanged:
            # (stage1_flat_idx, stage2_flat_idx, pol_flat_idx).
            if scan_mode == '2D_THz':
                scan_iterator = (
                    (stage1_flat, stage2_flat, pol_flat)
                    for pol_flat in range(iterator_plan['pol_total'])
                    for stage2_flat in range(iterator_plan['stage2_total'])
                    for stage1_flat in range(iterator_plan['stage1_total'])
                )
                print("2D_THz: stage1 set as the innermost (fastest) scan axis.")
                
            print(f"Generated position scan_iterator indexes for all stages: {scan_iterator}")
            #endregion

            #region Start Scan Loop
            self._last_rep_idx = (-1, -1, -1)  # to track last repeat index for updating display
            self._last_init_rep = (-1, -1, -1)  # to track last initial repeat index for moving back to initial positions
            # move to initial positions before each repeat
            self.move_active_stages((iPos1, iPos2, *scan_iRots))


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
                rotary1_pos = pol_rot1_list[pol_idx]
                rotary2_pos = pol_rot2_list[pol_idx]
                rotary3_pos = pol_rot3_list[pol_idx]
                current_rots = (rotary1_pos, rotary2_pos, rotary3_pos)
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
                        reset_rots = current_rots if scan_mode == '1D_THz' else (iRot1, iRot2, iRot3)
                        self.move_active_stages((iPos1, iPos2, *reset_rots))
                        self._last_init_rep = (stage1_rep_idx, stage2_rep_idx, pol_rep_idx)

                #endregion

                #region check stop flag at the beginning of each repeat
                if self.stop_flag or thread.stop_flag:
                    print(f"Scan stop flag detected. Exiting scan loop.")
                    break  # exit the scan loop if stop flag is set
                #endregion

                rotary_idx_plan = DataProcess.resolve_rotary_step_indices(
                    pol_idx=pol_idx,
                    rotary1_step_sequence=rotary1_step_sequence,
                    rotary2_step_sequence=rotary2_step_sequence,
                    rotary3_step_sequence=rotary3_step_sequence,
                )
                rotary1_idx = rotary_idx_plan['rotary1_idx']
                rotary2_idx = rotary_idx_plan['rotary2_idx']
                rotary3_idx = rotary_idx_plan['rotary3_idx']
                
                # Target positions for each stage
                # Drift comp. covers the first sweep at a new angle; Re-peak controls later repeats.
                # Search after moving to the current polarization, using the latest local reference.
                changed_angle = angle_peak and any(enabled and previous != target for enabled, previous, target
                                                    in zip(active_rotaries, scan_iRots, current_rots))
                if stage2_idx == 0 and (changed_angle or (repeat_peak and stage2_rep_idx > 0)):
                    reason = 'Angle' if changed_angle else 'Repeat'
                    self.scan_log_event(f"{reason} peak search: Stage2 repeat {stage2_rep_idx + 1}/{stage2_rep}; "
                                        f"Stage1 point {stage1_idx + 1}, polarization {pol_idx + 1}, "
                                        f"polarization repeat {pol_rep_idx + 1}; angles {current_rots}", thread)
                    scan_iRots = current_rots
                    scan_iPos1, scan_iPos2, scan_Ppos, stopped = self.compensate_temperature_drift(
                        thread, scan_iPos1, scan_iPos2, scan_Ppos, scan_iRots,
                        {'rotary1_NO': rotary1_stepNO_sequence[rotary1_idx],
                         'rotary2_NO': rotary2_stepNO_sequence[rotary2_idx],
                         'rotary3_NO': rotary3_stepNO_sequence[rotary3_idx]})
                    if stopped:
                        print(f"{reason} peak search interrupted. Exiting scan loop.")
                        break
                    iPos1, iPos2 = scan_iPos1, scan_iPos2
                    stage1_pos_sequence, stage1_step_sequence, stage1_stepNO_sequence = self.scan_planner.generate_position_sequence(iPos1, stage1_array)
                    stage2_pos_sequence, stage2_step_sequence, stage2_stepNO_sequence = self.scan_planner.generate_position_sequence(iPos2, stage2_array)
                    self.validate_scan_travel((
                        ('Stage1', self.ui.activeStage1, self.stage1, stage1_pos_sequence, 'mm'),
                        ('Stage2', self.ui.activeStage2, self.stage2, stage2_pos_sequence, 'mm'),
                    ))

                stage1_pos = stage1_pos_sequence[stage1_idx]
                stage2_pos = stage2_pos_sequence[stage2_idx]
                
                # move active stages to target positions, and real-time display current positions and step sizes
                _, curr_pos_sets = self.move_active_stages((stage1_pos, stage2_pos, rotary1_pos, rotary2_pos, rotary3_pos))
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
                


                #region Lockin data acquisition and saving
                wait_time1_s = self.ui.wait1.value() / 1000.0  # convert ms to s
                wait_time2_s = self.ui.wait2.value() / 1000.0  # convert ms to s
                lockin1_active = self.ui.activeLockin1.isChecked()
                lockin2_active = self.ui.activeLockin2.isChecked()
                l1x, l1y, l2x, l2y = np.nan, np.nan, np.nan, np.nan  # a lock-in not used stays NaN
                # collect data from Lockin1
                try:
                    if lockin1_active:
                        time.sleep(wait_time1_s)
                        l1x, l1y = self.lockin1.snap(1, 2)  # X and Y from one SNAP? query, taken at the same instant
                except Exception as e:
                    raise RuntimeError(f"Lock-in 1 read failed: {e}") from e
                
                # collect data from Lockin2
                try:
                    if lockin2_active:
                        if not lockin1_active:
                            time.sleep(wait_time2_s)  # no Lock-in 1 acquisition to supply the settling delay
                        elif wait_time2_s > wait_time1_s:
                            time.sleep(wait_time2_s - wait_time1_s)  # adjust wait time if lockin2 wait is longer
                        l2x, l2y = self.lockin2.snap(1, 2)  # X and Y from one SNAP? query, taken at the same instant
                except Exception as e:
                    raise RuntimeError(f"Lock-in 2 read failed: {e}") from e
                
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
                if repeat_positions is not None and stage2_idx == 0:
                    repeat_positions[stage1_idx, stage1_rep_idx, stage2_rep_idx, pol_idx, pol_rep_idx, :] = (
                        stage1_pos, stage2_pos_sequence[0], scan_Ppos)
                                    
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
                
                if enable_pol_chart and scan_mode == "POL_2D":
                    pol_data = {
                        'Angle': rotary2_pos,
                        'lockin': l1x,
                        'rotary2_NO': N_pol * pol_rep,
                        'rotary2_idx': pol_idx + pol_rep_idx * N_pol 
                    }
                    thread.pol_update.emit(pol_data)  # emit polar chart update signal
                
                
                self.h5_file.flush()  # write to file for avoiding data loss

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
                        except Exception as e:
                            print(f"Error updating TDS data at stage1 index {stage1_idx + 1} for repeat {stage1_rep_idx + 1}: {e}")
                elif scan_mode == "POL_2D":
                    pass  # no TDS update in POL_2D mode
                #endregion
                
                #region check stop flag at the beginning of each repeat
                if self.stop_flag or thread.stop_flag:
                    print(f"Scan stop flag detected at point {stage1_pos, stage2_pos, rotary1_pos, rotary2_pos, rotary3_pos}. Exiting scan loop.")
                    print("============================Scan stopped by user============================") 
                    break  # exit the scan loop if stop flag is set
                #endregion                    
            #endregion
            
            if self.h5_file:
                self.h5_file.close()  # close HDF5 file after scan
                print(f"HDF5 file closed and data saved to {self.fullFilePath}.")
              
    #endregion
    
    #region set_ControlsEnabledDuringScan function
    """This function is used to enable/disable UI controls during the scan process."""
    
    def set_ControlsEnabledDuringScan(self, scanning: bool):
        self._scanning = scanning
        # Keep stop, exit and display-only controls available during scanning.
        # QToolButton: the Jog buttons. A jog during a scan would leave Stage2/a rotary away from the
        # target that _move_unless_there() assumes it still holds.
        input_type = (QPushButton, QToolButton, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QLineEdit)
        always_enabled = [self.ui.saveScreenshot, self.ui.exportScanConfig, self.ui.stopButton, self.ui.exitApp, self.ui.realtimeDispT, self.ui.PM_realDisp, self.ui.clearLockinDisplay]
        
        if scanning:
            # iterate through all child widgets and disable inputs controls
            for widget in self.ui.findChildren(QWidget):
                # skip PlotWidgets
                if isinstance(widget, pg.PlotWidget):
                    continue  
                
                # Whitelist certain widgets to remain enabled
                if widget in always_enabled:
                    widget.setEnabled(True)
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
    def _update_scan_values(self, values: dict, fields):
        """Update only supplied non-None values, retaining field order and valid zeros."""
        for field, widget_name in fields:
            if field in values and values[field] is not None:
                getattr(self.ui, widget_name).setValue(values[field])

    def update_curr_repeat(self, rep_dict: dict):
        self._update_scan_values(rep_dict, (
            ('stage1_curr_rep', 'stage1CurrScan'), ('stage2_curr_rep', 'stage2CurrScan'),
            ('rotary1_curr_rep', 'Rot1CurrScan'), ('rotary2_curr_rep', 'Rot2CurrScan'),
        ))

    def update_curr_pos(self, positions_dict: dict):
        self._update_scan_values(positions_dict, (
            ('stage1_pos', 'stage1CurrPos'), ('stage2_pos', 'stage2CurrPos'),
            ('rotary1_pos', 'rot1CurrPos'), ('rotary2_pos', 'rot2CurrPos'),
            ('rotary3_pos', 'rot3CurrPos'),
        ))

    def update_curr_step(self, steps_dict: dict):
        for field, widget_name in (('stage1_step', 'stage1CurrStep'), ('stage2_step', 'stage2CurrStep')):
            if field in steps_dict and steps_dict[field] is not None:
                getattr(self.ui, widget_name).setValue(int(steps_dict[field] * 1000))  # mm -> um

    def update_curr_stepNOs(self, stepNOs_dict: dict):
        self._update_scan_values(stepNOs_dict, (
            ('stage1_NO', 'stage1CurrStepNO'), ('stage2_NO', 'stage2CurrStepNO'),
            ('rotary1_NO', 'rotary1CurrStepNO'), ('rotary2_NO', 'rotary2CurrStepNO'),
            ('rotary3_NO', 'rotary3CurrStepNO'),
        ))

    def clear_lockin_display(self):
        """Clear the four live X/Y traces and the two Realtime traces without changing scan data or
        acquisition; a running Realtime display continues from index zero. Number boxes are kept."""
        for chart_name in ('lockin1XChart', 'lockin1YChart', 'lockin2XChart', 'lockin2YChart',
                           'realDisChart1', 'realDisChart2'):
            self.curves[chart_name].clear()
            self.buffers[chart_name].clear()
            self.indices[chart_name] = -1
            chart = getattr(self.ui, chart_name)
            # Reset the scrolling viewport so the next samples are visible from index zero.
            chart.setRange(xRange=(0, 1), yRange=(0, 1), padding=0)
            chart.enableAutoRange(x=True, y=True)

    def update_lockin_charts(self, lockin_readings: dict):
        for field, chart_name in (('l1x', 'lockin1XChart'), ('l1y', 'lockin1YChart'),
                                  ('l2x', 'lockin2XChart'), ('l2y', 'lockin2YChart')):
            if field in lockin_readings and lockin_readings[field] is not None:
                self.chart_updaters[chart_name].update(update_single_shot=True, lockin_reading=lockin_readings[field])

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
            
        # plot new data as blue curve
        blue_curve_TDS.setData(x, y)
        
        ## Update TDS Chart with new data
        # get blue and red curves of tdsChart
        blue_curve_FDS = self.curves['fdsChart']['blue']
        red_curve_FDS  = self.curves['fdsChart']['red']
        # perform FFT calculation. No spectrum for a trace of fewer than 3 points (thz_fft_calc needs a
        # time step, and with 2 points its uniform grid has a single sample) or with points that were not
        # acquired (NaN): interpolating across the gap would draw a spectrum that was never measured.
        y_arr = np.asarray(y, dtype=float)
        missing = int(np.count_nonzero(~np.isfinite(y_arr)))
        usable = len(y_arr) >= 3 and not missing
        if usable:
            freq, amp_FDS = DataProcess.thz_fft_calc(np.array(x), y_arr)
        # check if blue curve exists
        blue_data_FDS = blue_curve_FDS.getData()
        if blue_data_FDS[0] is not None and blue_data_FDS[1] is not None:
            # if exist blue curve, move to red curve
            old_x_FDS, old_y_FDS = blue_data_FDS
            red_curve_FDS.setData(old_x_FDS, old_y_FDS)
        else:
            red_curve_FDS.setData([], [])  # the previous trace had no spectrum (an emptied curve reads back as None)

        if not usable:
            blue_curve_FDS.setData([], [])  # empty, so the previous spectrum is not taken for this trace
            if missing:
                print(f"FDS Chart: no spectrum for this trace, {missing} of {len(y_arr)} points were not acquired (NaN).")
            else:
                print(f"Warning: TDS data has only {len(y_arr)} point(s); no FDS/FFT spectrum. "
                      f"Check that the scanned stage has a valid step size and step NO.")
            return

        # plot new data as blue curve
        blue_curve_FDS.setData(freq, np.abs(amp_FDS))  # plot amplitude spectrum

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
        # Controls are enabled again in on_scan_thread_finished(), once the worker's run() has returned
        # (scan_finished is emitted just before that).

    def on_handle_scan_error(self, error_message: str):
        print(f"Error during scan: {error_message}")
        self.end_scan_log(f"Scan error: {error_message}")  # scan_finished may follow; the first end wins
        # Controls are enabled again in on_scan_thread_finished(): after a rejected scan plan the worker
        # still runs auto_block_after_scan() (flip mount) once this signal has been sent.

    def on_scan_thread_finished(self):
        """QThread.finished: the worker's run() has returned, so no scan code uses an instrument any more."""
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
    tds_peak_update = Signal(float)  # signal to update iPos1 after the drift compensation
    ipos2_update = Signal(float)     # signal to update iPos2 after the drift compensation
    ppos_update = Signal(float)      # signal to update TDS Ppos with the peak found by the search
    fm_block_led = Signal(bool)     # signal to update flip mount beam state LED (True = blocked)
    scan_log = Signal(str)          # signal to append a key event line to the scan log
    filename_update = Signal(str)    # update Save Name on the GUI thread

    error_occurred = Signal(str)    # signal to be emitted when error occurs
    

    def __init__(self, parent_moSys, scan_plan):
        super().__init__()           # initialize QThread
        self.parent = parent_moSys
        self.scan_plan = scan_plan
        self.stop_flag = False       # flag to indicate whether to stop the scan
    
    
    # run method of the thread, called when thread starts            
    def run(self):
        error_msg = None
        try:
            # call the scan_logic method from parent moSys class, this means executing "_execute_scan_logic" in this thread
            self.parent._execute_scan_logic(self)      # here the "(self)" is passing the ScanThread instance to the method
        except Exception as e:
            error_msg = str(e)
            print(f"Error during scan execution: {error_msg}")
            traceback.print_exc()                      # print traceback for debugging
        finally:
            # Always attempt both cleanup operations before the GUI unlocks the controls.
            try:
                self.parent.auto_block_after_scan(self)
            except Exception as e:
                cleanup_error = f"Beam cleanup failed: {e}"
                print(cleanup_error)
                error_msg = f"{error_msg}; {cleanup_error}" if error_msg is not None else cleanup_error
            try:
                data_file = getattr(self.parent, 'h5_file', None)
                if data_file:
                    data_file.close()
            except Exception as e:
                cleanup_error = f"Closing data file failed: {e}"
                print(cleanup_error)
                error_msg = f"{error_msg}; {cleanup_error}" if error_msg is not None else cleanup_error

        if error_msg is not None:
            self.error_occurred.emit(error_msg)
        else:
            self.scan_finished.emit()
            
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
    stabilized = Signal(bool)       # result; QThread.finished remains the native lifecycle signal
    
    error = Signal(str)            # signal to be emitted when error occurs
    
    def __init__(self, parent_moSys, target_T: float, tolerance:float, interval_s: int, stable_count: int = 20):
        super().__init__()           # initialize QThread
        self.setObjectName("iTC stabilization")
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
        self.requestInterruption()
        self.parent.stop_flag = True  # also set parent's stop_flag to True
        print("Received the iTC stabilization stop request.")
        
        
    def run(self):
        # stab_success mirrors the value carried by the 'stabilized' signal, but as plain state that
        # can be read after the fact. A caller that connects to 'stabilized' only after the thread has
        # already failed would never see the signal at all, so the outcome has to be readable too.
        self.stab_success = False
        try:
            # basic safety checks
            if not (self.parent.mercuryiTC and self.parent.ui.activeiTC.isChecked()):
                self.error.emit("MercuryiTC device not connected or not active.")
                self.stabilized.emit(False)
                return
            if self.parent.uid_TEMP is None:
                self.error.emit("MercuryiTC temperature UID not available.")
                self.stabilized.emit(False)
                return

            # poll loop to check temperature stability
            stable_counter = 0
            while not self.stop_flag and not self.isInterruptionRequested():
                with self.parent.mercuryiTC.io_lock:  # ensure thread-safe access to MercuryiTC
                    curr_T = self.parent.mercuryiTC.read_temperature(self.parent.uid_TEMP)
                if self.stop_flag or self.isInterruptionRequested():
                    break
                tol = self.get_tolerance()     # read lastest tolerance value
                diff = abs(curr_T - self.target_T)

                # count consecutive hits within tolerance
                stable_counter = stable_counter + 1 if diff <= tol else 0  # reset counter if out of tolerance
                print(f"iTC Stabilization: Current T = {curr_T:.3f} K, Target T = {self.target_T:.3f} K, Stable Count = {stable_counter}/{self.stable_count}")

                # stabilization condition met
                if stable_counter >= self.stable_count:
                    print(f"Temperature stabilized at {curr_T:.3f} K within tolerance {tol} K.")
                    self.stab_success = True
                    self.stabilized.emit(True)
                    return

                # stop and wait for next poll
                deadline = time.monotonic() + self.interval_s
                while not self.stop_flag and not self.isInterruptionRequested():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    time.sleep(min(0.05, remaining))

            # stop by user request
            self.stabilized.emit(False)
            print("iTC stabilization stopped by user.")

        except Exception as e:
            self.error.emit(str(e))
            self.stabilized.emit(False)
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
