#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# region File info
""" 
Main program for MO system control and data acquisition GUI application.
This program provides a graphical user interface (GUI) for controlling various instruments,
including lock-in amplifiers and motorized stages, as well as real-time data visualization. 
"""
"""
Debugging records:
2025-12-28 v1.6: add thread safety mercuryiTC operations; debug repetition mechanism of scan logic
"""
# endregion

# region IModule info
# Inject inst_libs to path for instrument control, especially for mercuryiTC which is not pip-installable and needs to use the provided .py files
from proj_tools import ProjectTools
ProjectTools.inject_inst_libs(__file__, libs_dir_name="inst_libs")  # inject inst_libs to path for instrument control, especially for mercuryiTC which is not pip-installable and needs to use the provided .py files
ProjectTools.inject_inst_libs(__file__, libs_dir_name="func_cores")

# import pyside6 for GUI
import pyqtgraph as pg
from PySide6.QtWidgets import QApplication, QMessageBox, QVBoxLayout, QFileDialog, QPushButton, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QLineEdit, QWidget, QWidgetItem, QListWidgetItem
from PySide6.QtUiTools import QUiLoader
from PySide6.QtGui import QIcon, QFont, QColor, QPen
from collections import deque
from PySide6.QtCore import QTimer, QThread, Signal, QEventLoop, Slot, Qt
from MyWidget import LedIndicator

# import packages needed
import os, h5py, random, time, itertools, traceback, threading            # h5py for .mat file saving
import numpy as np
import scipy.io as sio
from datetime import datetime
from pathlib import Path


# Import instrument classes
from newport_PM500 import PM500, PM500Error
from thorlabs_LinearStage import LinearStage
from thorlabs_RotaryStage import RotaryStage
from stanford_SR830 import SR830
from Oxford_mercuryiTC_Thread import MercuryiTC, MercuryiTCError
from scan_func_core import DataProcess, ScanPlanner
# endregion

# 在QApplication之前先实例化
uiLoader = QUiLoader()

#region Main MO System UI class
class moSys:

    def __init__(self):     # initialization for ui and functions
        super().__init__()  # initialize parent class, especially for QWidget and user_customized widgets
        # load UI file
        # register custom widgets used in .ui file as charts
        uiLoader.registerCustomWidget(pg.PlotWidget)
        uiLoader.registerCustomWidget(LedIndicator)
        self.ui = uiLoader.load('MO_system_iTC_v18.ui')

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
        
        #region Initialize LED indicators
        self.ui.TempDone.status = False    # temperature stabilization done indicator
        self.ui.autoPID_led.status = False  # auto PID mode indicator
        
        self.ui.stage1Led.status = False  # stage1 connection status indicator
        self.ui.stage2Led.status = False  # stage2 connection status indicator
        self.ui.rotary1Led.status = False    # rotary1 connection status indicator
        self.ui.rotary2Led.status = False    # rotary2 connection status indicator
        self.ui.rotary3Led.status = False    # rotary3 connection status indicator
        self.ui.mercuryiTCLed.status = False  # mercuryiTC connection status indicator
        #endregion
        
        #region Initialize path for data saving
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
        
        # Lockin waittime update: everytime the wait time spinbox value changes, update the corresponding chart updater timer interval and lockin
        self.ui.wait1.editingFinished.connect(lambda: self.chart_updaters['realDisChart1'].update_Interval(int(self.ui.wait1.value())))
        self.ui.wait2.editingFinished.connect(lambda: self.chart_updaters['realDisChart2'].update_Interval(int(self.ui.wait2.value())))
        self.ui.wait1multip.editingFinished.connect(lambda: self.apply_lockin_parameter('lockin1', 'Timeconstant'))  # update wait time based on timeconstant
        self.ui.wait2multip.editingFinished.connect(lambda: self.apply_lockin_parameter('lockin2', 'Timeconstant'))  # update wait time based on timeconstant
        
        # set lockin parameter apply button click events
        self.ui.sensitivity1.currentIndexChanged.connect(lambda: self.apply_lockin_parameter('lockin1', 'Sensitivity'))
        self.ui.timeConst1.currentIndexChanged.connect(lambda: self.apply_lockin_parameter('lockin1', 'Timeconstant'))
        self.ui.autoPhase1.clicked.connect(lambda: self.apply_lockin_parameter('lockin1', 'Autophase'))
        self.ui.sensitivity2.currentIndexChanged.connect(lambda: self.apply_lockin_parameter('lockin2', 'Sensitivity')) 
        self.ui.timeConst2.currentIndexChanged.connect(lambda: self.apply_lockin_parameter('lockin2', 'Timeconstant')) 
        self.ui.autoPhase2.clicked.connect(lambda: self.apply_lockin_parameter('lockin2', 'Autophase')) 
        #endregion
        
        # update fdsChart when fdsDispMin/Max spinbox value changes
        self.ui.fdsDispMin.editingFinished.connect(self.update_fds_chart_dispRange)
        self.ui.fdsDispMax.editingFinished.connect(self.update_fds_chart_dispRange)
        
        #region set button click events
        # stages moveto buttons
        self.ui.stage1MoveTo.clicked.connect(lambda: self.to_target_position('stage1'))   # thorlabs linear stage
        self.ui.stage2MoveTo.clicked.connect(lambda: self.to_target_position('stage2'))   # newport PM500
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
        
        # file operation buttons
        self.ui.browseButton.clicked.connect(self.customize_data_save_path)
        self.ui.scanMode.currentIndexChanged.connect(self.setup_scan_mode)
        
        # connect/close instrument buttons
        self.ui.connectInstr.clicked.connect(self.connectInstruments, False)
        self.ui.closeInstr.clicked.connect(self.closeInstruments, False)
        
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
        self.mercuryiTC = None
        #endregion    
    
        #region Initialize and save ScanThread as None
        self.scan_Thread = None
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
    def apply_lockin_parameter(self, lockinName: str, paraName: str) -> bool:
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
                new_waittime = int(timeConst_ms * multiplier) # in ms
                
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
                
            elif paraName == 'Autophase':
                lockin_device.auto_phase()
                print(f"Applied autophase to {lockinName}.")
                
            else:
                print(f"Warning: Unknown parameter name '{paraName}' for applying to '{lockinName}'.")
                return False
                
            return True
        
        except Exception as e:
            print(f"Error applying {paraName} to {lockinName}: {e}")
            return False    
 
    #endregion
                
    #region connect/close instruments
    def connectInstruments(self):
        print("Start connecting instruments...")
        print("=" * 50)
        
        # connect Lockin1
        if self.ui.activeLockin1.isChecked():
            if self.lockin1:
                print("Lockin1 is already connected.")
                
            else:                
                address = 'GPIB0::3::INSTR' 
                self.lockin1 = SR830(address)
                error_msg = self.lockin1.open()
                
                if error_msg:
                    print(f"✗ Lock-in1 connection failed: {error_msg}")
                else:
                    self.qwait_time(50)  # wait time in  ms for device to be ready
                    lockinID = self.lockin1.idn()
                    print(f"✓ Lock-in1 connection successful (address: {address},  ID: {lockinID})")
                    self.qwait_time(50)  # wait time in  ms for next device to be ready

        # connect Lockin2
        if self.ui.activeLockin2.isChecked():
            if self.lockin2:
                print("Lockin2 is already connected.")
                
            else:
                address = 'GPIB0::6::INSTR' 
                self.lockin2 = SR830(address)
                error_msg = self.lockin2.open()
                
                if error_msg:
                    print(f"✗ Lock-in2 connection failed: {error_msg}")
                else:
                    self.qwait_time(50)  # wait time in  ms for device to be ready
                    lockinID = self.lockin2.idn()
                    print(f"✓ Lock-in2 connection successful (address: {address}, ID: {lockinID})")
                    
        # connect Stage1
        if self.ui.activeStage1.isChecked():
            if self.stage1:
                print("Stage1 is already connected.")
                
            else:
                try:
                    serial = "73877174"  # Replace with your controller serial
                    chan = 1
                    self.stage1 = LinearStage(serial, chan, poll_ms=250)
                    self.qwait_time(300)  # wait for 2 seconds after connect
                    self.stage1.home(60000)  # home the stage
                    self.qwait_time(300)  # wait for 2 seconds after connect
                    self.ui.stage1CurrPos.setValue(self.stage1.position())  # update current position display
                    self.ui.stage1Led.status = True # update LED indicator status
                    QApplication.processEvents()  # Ensure UI updates immediately
                    print(f"✓ Stage1 connection successful (serial: {serial}, channel: {chan})")
                except Exception as e: 
                    print(f"✗ Stage1 connection failed: {str(e)}")
                    
        # connect Stage2
        if self.ui.activeStage2.isChecked():
            if self.stage2:
                print("Stage2 is already connected.")
                
            else:
                RESOURCE   = "GPIB0::4::INSTR"   # e.g. "GPIB0::1::INSTR" or "ASRL3::INSTR"
                AXIS       = "X"                 # "X", "Y", "Z", "A", "B", or "C"
                self.stage2 = PM500(RESOURCE)
                
                try:
                    self.stage2 = PM500(RESOURCE).connect()
                    print("[PM500 Connect] OK")
                    print("[ID]      ", self.stage2.idn())
                    # Make sure motor is enabled
                    self.stage2.motor_on(AXIS)
                    # Initialize position to fiducial location.
                    self.stage2.init_pos(AXIS)
                    print(f"{'='*20} Initializing Position {'='*20}\n Please wait for the stage to initialize to fiducial position(~ 10 seconds)...")
                    self.qwait_time(1000)  # wait for 10 seconds after init_pos
                    self.ui.stage2CurrPos.setValue(self.stage2.read_pos(AXIS) / 1000)  # update current position display, convert um to mm
                    self.ui.stage2Led.status = True # update LED indicator status
                    QApplication.processEvents()  # Ensure UI updates immediately 
                    print(f"[MotorOn]  {AXIS} axis motor enabled and initialized.")
                except PM500Error as e:
                    print("PM500Error:", e)
                
        # connect Rotary1
        if self.ui.activeRot1.isChecked():
            if self.rotary1:
                print("Rotary1 is already connected.")
                
            else:
                try:
                    serial = "27256338"  # Replace with your controller serial
                    self.rotary1 = RotaryStage(serial, poll_ms=250, use_sim=False)
                    self.qwait_time(300)  # wait for 2 seconds after connect
                    self.rotary1.home(60000)  # home the rotary stage
                    self.qwait_time(300)  # wait for 2 seconds after connect
                    self.ui.rot1CurrPos.setValue(self.rotary1.position())  # update current position display
                    self.ui.rotary1Led.status = True # update LED indicator status
                    QApplication.processEvents()  # Ensure UI updates immediately
                    print(f"✓ Rotary1 connection successful (serial: {serial})")
                except Exception as e: 
                    print(f"✗ Rotary1 connection failed: {str(e)}")
                
        # connect Rotary2
        if self.ui.activeRot2.isChecked():
            if self.rotary2:
                print("Rotary2 is already connected.")
                
            else:
                try:
                    serial = "27004364"  # Replace with your controller serial
                    chan = 1
                    self.rotary2 = RotaryStage(serial, poll_ms=250, use_sim=False)
                    self.qwait_time(300)  # wait for 2 seconds after connect
                    self.rotary2.home(60000)  # home the rotary stage
                    self.qwait_time(300)  # wait for 2 seconds after connect
                    self.ui.rot2CurrPos.setValue(self.rotary2.position())  # update current
                    self.ui.rotary2Led.status = True # update LED indicator status
                    QApplication.processEvents()  # Ensure UI updates immediately
                    print(f"✓ Rotary2 connection successful (serial: {serial})")
                except Exception as e: 
                    print(f"✗ Rotary2 connection failed: {str(e)}")
        
        # connect Rotary3
        if self.ui.activeRot3.isChecked():
            if self.rotary3:
                print("Rotary3 is already connected.")
                
            else:
                try:
                    serial = "27255894"  # Replace with your controller serial
                    chan = 2
                    self.rotary3 = RotaryStage(serial, poll_ms=250, use_sim=False)
                    self.qwait_time(300)  # wait for 2 seconds after connect
                    self.rotary3.home(60000)  # home the rotary stage
                    self.qwait_time(300)  # wait for 2 seconds after connect
                    self.ui.rot3CurrPos.setValue(self.rotary3.position())  # update current
                    self.ui.rotary3Led.status = True # update LED indicator status
                    QApplication.processEvents()  # Ensure UI updates immediately
                    print(f"✓ Rotary3 connection successful (serial: {serial})")
                except Exception as e: 
                    print(f"✗ Rotary3 connection failed: {str(e)}")
                
        # connect MercuryiTC temperature controller
        if self.ui.activeiTC.isChecked():
            if self.mercuryiTC:
                print("MercuryiTC is already connected.")
                
            else:
                try:
                    RESOURCE = 'ASRL3::INSTR'  # replace with your address 
                    self.mercuryiTC = MercuryiTC(RESOURCE)
                    self.mercuryiTC.open()
                    self.qwait_time(100)  # wait time in ms for device to be ready
                    devices = self.mercuryiTC.get_system_catalog()
                    self.qwait_time(100)  # wait time in ms for next device to be ready
                    # get heater and temperature sensor UIDs
                    self.uid_HTR_list = [uid for uid, types in devices.items() if 'HTR' in types]    # heater UID
                    self.uid_HTR = self.uid_HTR_list[0] if self.uid_HTR_list else None
                    self.uid_TEMP_list = [uid for uid, types in devices.items() if 'TEMP' in types]  # temperature sensor UID
                    self.uid_TEMP = self.uid_TEMP_list[0] if self.uid_TEMP_list else None
                    # get current heater and temperature values
                    self.ui.targetT.setValue(self.mercuryiTC.get_temperature_setpoint(self.uid_TEMP))
                    self.ui.HeaterLim.setValue(self.mercuryiTC.get_heater_limit(self.uid_HTR))
                    self.ui.mercuryiTCLed.status = True # update LED indicator status
                    QApplication.processEvents()  # Ensure UI updates immediately
                    print(f"✓ MercuryiTC connection successful (resource: {RESOURCE}, heaters: {self.uid_HTR}, temps: {self.uid_TEMP})")
                    
                except MercuryiTCError as e:
                    print(f"✗ MercuryiTC connection failed: {str(e)}")

    def closeInstruments(self):
        print("Start closing instruments...")
        print("=" * 50)
        
        # close Lockin1
        if self.lockin1:
            self.lockin1.close()
            self.lockin1 = None
            print("✓ Lock-in1 closed.")    
            
        # close Lockin2
        if self.lockin2:
            self.lockin2.close()
            self.lockin2 = None
            print("✓ Lock-in2 closed.")
            
        # close Stage1
        if self.stage1:
            self.stage1.close()
            self.stage1 = None
            self.ui.stage1Led.status = False # update LED indicator status
            QApplication.processEvents()  # Ensure UI updates immediately
            print("✓ Stage1 closed.")
            
        # close PM500
        if self.stage2:
            self.stage2.close()
            self.stage2 = None
            self.ui.stage2Led.status = False # update LED indicator status
            QApplication.processEvents()  # Ensure UI updates immediately
            print("✓ PM500 closed.")
            
        # close Rotary1
        if self.rotary1:
            self.rotary1.close()
            self.rotary1 = None
            self.ui.rotary1Led.status = False # update LED indicator status
            QApplication.processEvents()  # Ensure UI updates immediately
            print("✓ Rotary1 closed.")
            
        # close Rotary2
        if self.rotary2:
            self.rotary2.close()
            self.rotary2 = None
            self.ui.rotary2Led.status = False # update LED indicator status
            QApplication.processEvents()  # Ensure UI updates immediately
            print("✓ Rotary2 closed.")
            
        # close Rotary3
        if self.rotary3:
            self.rotary3.close()
            self.rotary3 = None
            self.ui.rotary3Led.status = False # update LED indicator status
            QApplication.processEvents()  # Ensure UI updates immediately
            print("✓ Rotary3 closed.")
            
        # close MercuryiTC
        if self.mercuryiTC:
            # self.mercuryiTC.set_heater_percent(self.uid_HTR, 0)  # set heater percent to 0 before closing
            # self.setup_pid_mode(False)  # disable auto PID mode before closing
            self.mercuryiTC.close()
            self.mercuryiTC = None
            self.ui.mercuryiTCLed.status = False # update LED indicator status
            QApplication.processEvents()  # Ensure UI updates immediately
            print("✓ MercuryiTC closed.")
            
    #endregion         
           
    #region move stage and rotary to target positions    
    def to_target_position(self, stage_name: str) -> bool:
        
        stage_device = getattr(self, stage_name, None)
        if stage_device is None:
                print(f"Warning: {stage_name} is not connected for moving to target position.")
                return False
            
        try:
            if stage_name == 'stage2':
                target_pos = self.ui.stage2SetPos.value() * 1000  # convert mm to um
                print(f"Moving Stage2 to target position: {target_pos} um")
                # move stage to target position
                axis = 'X'  # assuming X axis for Stage2
                stage_device.go_and_wait_abs(axis, target_pos, 10000)
                currPos = stage_device.read_pos(axis) / 1000  # in mm
                # update current position display            
                self.ui.stage2CurrPos.setValue(currPos)  # convert um to mm
                print(f"Stage2 moved to position: {currPos} mm")
            else:
                # Thorlabs stages
                ui_target_pos = {
                    'stage1': self.ui.stage1SetPos,
                    'rotary1': self.ui.rot1SetPos,
                    'rotary2': self.ui.rot2SetPos,
                    'rotary3': self.ui.rot3SetPos
                }.get(stage_name)
                ui_curr_pos = {
                    'stage1': self.ui.stage1CurrPos,
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
            if stage_name == 'stage1':
                stage_device.move_by(direction * step_size)
                currPos = stage_device.position()
                curr_pos_box_name = 'stage1CurrPos'
                
            elif stage_name == 'stage2':
                axis = 'X'  # assuming X axis for Stage2
                stage_device.go_and_wait_rel(axis, direction * step_size * 1000)  # convert mm to um
                currPos = stage_device.read_pos(axis) / 1000  # convert um to mm
                currPos = round(currPos, 3)  # round to 3 decimal places
                curr_pos_box_name = 'stage2CurrPos'
                
            elif stage_name == 'rotary1' or stage_name == 'rotary2' or stage_name == 'rotary3':
                stage_device.move_by(direction * step_size)
                currPos = stage_device.position()
                if stage_name == 'rotary1':
                    curr_pos_box_name = 'rot1CurrPos'
                elif stage_name == 'rotary2':
                    curr_pos_box_name = 'rot2CurrPos'
                elif stage_name == 'rotary3':
                    curr_pos_box_name = 'rot3CurrPos'
                
            # update current position display            
            getattr(self.ui, curr_pos_box_name).setValue(currPos)
            print(f"{stage_name} moved by {direction * step_size}. New position: {currPos}")
            return True
        except Exception as e:
            print(f"Error moving {stage_name} by single step: {e}")
            return False
    #endregion

    #region Setup data folder for saving data
    def setup_data_folder(self) -> str:
        try:
            current_script_dir = os.path.dirname(os.path.abspath(__file__))
            print(f"Current script directory: {current_script_dir}")
            
            parent_dir = os.path.dirname(current_script_dir)
            
            data_save_dir = os.path.join(parent_dir, 'TPOP_Data')
            if not os.path.exists(data_save_dir):
                os.makedirs(data_save_dir)
                print(f"Created TPOP_Data folder: {data_save_dir}")
            else:
                print(f"TPOP_Data folder already exists: {data_save_dir}")
                
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
    def setup_dataFile_Name(self, add_str: str = None) -> str:
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
        Scan modes:
        '1D_POL': scan 1D at each polarization states; 
        'POL_2D': scan polarization at each 1D position;
        
        'TDS_Scan': time-domain scan;
        '1D_TDS': 1D scan at TDS peak, here stage1 beam act as pump, same as OPTP;
        '2D_TDS': TDS scan at each optical pump delay, same as OPTP 2D scan;          
        """
        scan_modes = ['1D_POL', 'POL_2D', 'THz_Scan', '1D_THz', '2D_THz']  
        self.ui.scanMode.addItems(scan_modes)
        
        self.test_mode = scan_modes[0]  # default to first mode 1D Scan
            
    # Choose and update scan mode
    def setup_scan_mode(self):
        mode = self.ui.scanMode.currentText()
        self.test_mode = mode    # update current scan mode
        print(f"Scan mode set to: {mode}")
    #endregion    

    #region Get step array for each stage
    def get_step_array(self, stageName: str) -> list:
        step_sizes = []
        steps_NO = []

        # Collect step info. from UI
        if stageName in ['stage1', 'stage2']:
            for i in range (1, 4):    # up to 3 stepSize
                step_box_name = f'{stageName}Step{i}'
                step_value = getattr(self.ui, step_box_name).value()
                step_value = step_value / 1000                         # convert from um to mm
                step_sizes.append(float(step_value))
                
                stepNO_box_name = f'{stageName}Step{i}NO'
                stepNO_value = getattr(self.ui, stepNO_box_name).value()
                steps_NO.append(int(stepNO_value))
                
        elif stageName in ['rotary1', 'rotary2', 'rotary3']:
            step_box_name = f'{stageName}Step'
            step_value = getattr(self.ui, step_box_name).value()
            step_sizes.append(float(step_value))
            
            stepNO_box_name = f'{stageName}StepNO'
            stepNO_value = getattr(self.ui, stepNO_box_name).value()
            steps_NO.append(int(stepNO_value))

        stage_array = np.array([step_sizes, steps_NO], dtype = 'f8')

        return stage_array
        #endregion

    #region Generate position sequences for stages
    def generate_position_sequence(self, iPos, step_array) -> list:
        position_sequence = []
        step_sequence = []
        stepNO_sequence = []
        num_step_size = step_array.shape[1]   # column number of the step array, number of step sizes
        
        for step_idx in range(num_step_size):
            step_size = step_array[0, step_idx]       # get step size, row 0
            step_NO   = int(step_array[1, step_idx])  # get step NO., row 1
            
            # Skip if step size or step NO is zero
            if step_size == 0 or step_NO == 0:
                continue
            
            if len(position_sequence) == 0:
                new_positions = iPos + np.arange(step_NO) * step_size  # for the first step size, start from iPos
            else: 
                new_positions = iPos + (np.arange(step_NO) + 1) * step_size  # for subsequent step sizes, start from last position + step_size
                
            new_positions = np.round(new_positions, 3)  # round to 3 decimal places to avoid floating point precision issues
            position_sequence.extend(new_positions.tolist())  # transform new_positions into list and append to overall position sequence
            step_sequence.extend(([float(step_size)] * step_NO))  # extend step size sequence in um
            stepNO_sequence.extend(list(range(1, step_NO + 1)))  # extend step NO. sequence
            iPos = position_sequence[-1]  # update iPos for next step_size
            
        if len(position_sequence) == 0:
            position_sequence = [iPos]  # if no steps defined, stay at initial position
            step_sequence = [0.0]       # step size is 
            stepNO_sequence = [0]        # step NO. is 0

        return position_sequence, step_sequence, stepNO_sequence
    #endregion
    
    #region Import calibration sequences for rotary stages in polarization/intensity dependent scans
    # on_pol_cali_mode_toggled event
    def on_pol_cali_mode_toggled(self, checked: bool):
        self.ui.pol_cali_mode.setText('Manu. Cali.' if checked else 'Auto Cali.')
    
    # Import calibration file
    def import_calibration_file(self, interp_cali_data: bool = False) -> dict:
        if not self.ui.pol_cali_mode.isChecked():
            QMessageBox.information(self.ui, "Calibration", 
                                    "Please switch Cali. button into 'Manu. Cali.' before importing Cali. file.")
            return
        
        # Import calibration file
        cali_file_path, _ = QFileDialog.getOpenFileName(
            self.ui,
            "Select Calibration File",
            "",
            "Text Files (*.txt);;All Files (*)"
        )
        if not cali_file_path:
            return
        
        # Display selected file path in UI
        if hasattr(self.ui, 'cali_file_path'):
            self.ui.cali_file_path.setText(cali_file_path)
            print(f"Calibration file path set in UI: {cali_file_path}")
            
        # Read calibration data from file
        try:
            rows = []
            with open(cali_file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # skip empty lines and comments starting with '#'
                    if not line or line.startswith('#'):
                        continue
                    
                    parts = line.split()  # split by whitespace
                    if len(parts) < 4:
                        continue  # skip lines with insufficient data
                    
                    try: # incase of non-numeric data, title or non-# comment lines
                        current_row = [float(p) for p in parts[:4]]
                        rows.append(current_row)     
                    except ValueError:
                        continue  # skip lines with non-numeric data
                    
            if not rows:
                QMessageBox.warning(self.ui, "Calibration", "No valid data found in calibration file.")
                return
            
            data = np.array(rows, dtype=float)
            rot1, rot2, rot3, power = data.T  # transpose to get each column
            
            # Resort calibration data by rot2 ascending
            rot2 = np.round(rot2, 1)  # round to 0.1 degree to avoid floating point precision issues
            sort_idx = np.argsort(rot2)
            rot2_sorted = rot2[sort_idx]
            rot1_sorted = rot1[sort_idx]
            rot3_sorted = rot3[sort_idx]
            power_sorted = power[sort_idx]
            
            # Delete duplicate rot2 entries
            rot2_unique, unique_idx = np.unique(rot2_sorted, return_index=True)
            rot1_unique = rot1_sorted[unique_idx]
            rot3_unique = rot3_sorted[unique_idx]
            power_unique = power_sorted[unique_idx]
            
            if interp_cali_data is False:
                # Store new calibration table
                self.cali_table = {
                    'rot2_cali': rot2_unique,
                    'rot1_cali': rot1_unique,
                    'rot3_cali': rot3_unique, 
                    'power_cali': power_unique
                }
                print(f"Calibration data imported from file: {cali_file_path}, total {len(rot2_unique)} unique points.")
                return self.cali_table
            elif interp_cali_data is True:
                # Generate new rot2 grid for interpolation
                start = rot2_unique.min()
                stop = rot2_unique.max()
                n_step = int(np.round((stop - start) / 0.1))  # number of 0.1 degree steps
                rot2_grid = start + np.arange(n_step + 1) * 0.1  # 0.1 degree step
                rot2_grid = np.round(rot2_grid, 1)  # round to 0.1 degree
                
                # Interpolate rot1, rot3, power onto new rot2 grid
                rot1_interp = np.interp(rot2_grid, rot2_unique, rot1_unique)
                rot3_interp = np.interp(rot2_grid, rot2_unique, rot3_unique)
                power_interp = np.interp(rot2_grid, rot2_unique, power_unique)
                
                # Round to three decimal places, in case rotary stages could not recognize too many decimal places
                rot2_grid = np.round(rot2_grid, 1)
                rot1_interp = np.round(rot1_interp, 2)
                rot3_interp = np.round(rot3_interp, 2)
                power_interp = np.round(power_interp, 3)
            
                # Store new calibration table
                self.cali_table = {
                    'rot2_cali': rot2_grid,
                    'rot1_cali': rot1_interp,
                    'rot3_cali': rot3_interp, 
                    'power_cali': power_interp
                }
                print(f"Calibration data imported and interpolation done from file: {cali_file_path}, total {len(rot2_grid)} points.")
                return self.cali_table
            
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self.ui, "Calibration", f"Error reading calibration file: {e}")
    #endregion
    
    #region iTC_go_to_target temperature function
    def setup_pid_mode(self, checked: bool) -> bool:
        if not (self.ui.activeiTC.isChecked() and self.mercuryiTC):
            print("Warning: MercuryiTC is not connected for setting PID mode.")
            return False
                        
        result = self.itc_updater.setup_autoPID_mode(checked)
        self.ui.autoPID_led.status = result  # setup auto PID mode indicator
        print(f"iTC PID mode set to {'Auto' if checked else 'Manual'}.")
        return True
    
    
    def iTC_goto_targetT(self, targetT: float, update_ui: bool = True):
        """
        Read UI parameters and start iTCStabilizerThread.
        - targetT: target temperature (K)
        - Tolerance: tolerance (K)
        - waitiTC: polling interval (seconds)
        """
        if not (self.ui.activeiTC.isChecked() and self.mercuryiTC):
            print("Warning: MercuryiTC is not connected for going to target temperature.")
            return
        
        target_T  = targetT
        tolerance = self.ui.Tolerance.value()
        waitiTC   = self.ui.waitiTC.value()       # in seconds
        stab_cnt  = self.ui.T_stab_cnt.value()    # number of stable counts required
        
        if update_ui:
            self.ui.TempDone.status = False  # reset TempDone indicator
            QApplication.processEvents()  # Ensure UI updates immediately
            
        # setup and goto targetT
        with self.mercuryiTC.io_lock:
            T_set  = self.mercuryiTC.set_temp_point(self.uid_TEMP, target_T)
            
        # create and start iTCStabilizerThread
        self.itc_stab_thread = iTCstabilizeThread(self, target_T, tolerance, waitiTC, stab_cnt)
        
        # connect 
        if update_ui:    
            self.itc_stab_thread.finished.connect(self.on_temp_done)
        
        self.itc_stab_thread.error.connect(lambda msg: print(f"iTC Stabilization Error: {msg}"))
        
        # start thread
        self.itc_stab_thread.start()
        print(f"Started iTC stabilization thread to reach {target_T} K with tolerance {tolerance} K.")
        
                    
    def on_tolerance_changed(self):
        """ Set tolerance for iTC stabilization."""
        try:
            new_tolerance = float(self.ui.Tolerance.value())
        except Exception:
            return
        
        # if the stabilization thread is running, update its tolerance
        if hasattr(self, "itc_stab_thread") and self.itc_stab_thread.isRunning():
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
    
    #region Calibrate TDS peak position at each temperature point
    def get_TDS_peak_pos(self) -> dict:
        tds_max_positions = {}
        
        if not (self.ui.activeStage2.isChecked() and self.stage2):
            print("Warning: Stage2 is not connected for TDS scan.")
            return tds_max_positions
        if not (self.ui.activeLockin1.isChecked() and self.lockin1):
            print("Warning: Lockin1 is not connected for TDS scan.")
            return tds_max_positions
        
        # Get iPos of Stage2 and generate position sequence
        iPos_stage2 = getattr(self.ui, 'iPos2').value()
        step_mm = 0.001  # default step size in mm
        pos_seq_stage2 = np.round(iPos_stage2 + np.arange(-100, 101) * step_mm, 3).tolist()  # from -100 to +100 steps
        
        wait_time_ms = self.ui.wait1.value() / 1000  # wait time in ms from UI
        lockin_data = []

        total = len(pos_seq_stage2)
        for idx, pos in enumerate(pos_seq_stage2, 1):
            print(f"TDS scan progress: {idx}/{total} positions...")
            # move Stage2 to position
            try:
                self.stage2.go_and_wait_abs('X', pos * 1000, 10) # convert mm to um for stage2
            except Exception as e:
                print(f"Error moving Stage2 to position {pos} mm during TDS scan: {e}")
                continue

            time.sleep(wait_time_ms)  # wait for stage to settle

            # read Lockin1 X value
            try:
                x_val = float(self.lockin1.get_x())
                lockin_data.append((pos, x_val))
            except Exception as e:
                print(f"Error reading Lockin1 X value at position {pos} mm during TDS scan: {e}")
            
        if not lockin_data:
            print("No valid Lockin1 data collected during TDS scan.")
            return tds_max_positions
        
        max_pos, max_x = max(lockin_data, key=lambda item: item[1])
        tds_max_positions = {
            'max_position': max_pos,
            'max_lockin1X': max_x,
            'positions': [p for p, _ in lockin_data],
            'lockin1X': [x for _, x in lockin_data]
        }
        print(f"TDS scan complete. Max Lockin1 X: {max_x} at position: {max_pos} mm.")

        return tds_max_positions  # in mm
    
    def update_iPos2_from_tds_peak(self, new_pos: float):
        """Update iPos2 in UI from TDS peak position."""
        try:
            self.ui.iPos2.setValue(new_pos)
            QApplication.processEvents()  # Ensure UI updates immediately
            print(f"Updated iPos2 to TDS peak position: {new_pos} mm.")
        except Exception as e:
            print(f"Error updating iPos2 from TDS peak position: {e}")
    #endregion
     
    #region Move active stages and display current positions
    def move_active_stages(self, target_positions: tuple):
        
        stage1_pos, stage2_pos, rotary1_pos, rotary2_pos, rotary3_pos = target_positions
        move_tol = 1e-4
        
        # Initialize current positions with placeholder (-1)
        currStage1Pos = -1; currStage2Pos = -1
        currRotary1Pos = -1; currRotary2Pos = -1
        currRotary3Pos = -1
        
        try:
            # move Stage1 if active
            if self.ui.activeStage1.isChecked() and self.stage1:
                currStage1Pos = self.stage1.position()
                if abs(currStage1Pos - stage1_pos) > move_tol:
                    self.stage1.move_to(stage1_pos) # in mm
                currStage1Pos = round(self.stage1.position(), 3)  # update current position display in mm

            # move Stage2 if active
            if self.ui.activeStage2.isChecked() and self.stage2:
                axis = 'X'  # assuming X axis for Stage2
                currStage2Pos = self.stage2.read_pos(axis) / 1000
                if abs(currStage2Pos - stage2_pos) > move_tol:
                    self.stage2.go_and_wait_abs(axis, stage2_pos*1000, 10) # convert mm to um
                currStage2Pos = round(self.stage2.read_pos(axis) / 1000, 3)  # update current position display in mm

            # move Rotary1 if active
            if self.ui.activeRot1.isChecked() and self.rotary1:
                currRotary1Pos = self.rotary1.position()
                if abs(currRotary1Pos - rotary1_pos) > move_tol:
                    self.rotary1.move_to(rotary1_pos)
                currRotary1Pos = round(self.rotary1.position(), 3)  # update current position display in degrees

            # move Rotary2 if active
            if self.ui.activeRot2.isChecked() and self.rotary2:
                currRotary2Pos = self.rotary2.position()
                if abs(currRotary2Pos - rotary2_pos) > move_tol:
                    self.rotary2.move_to(rotary2_pos)
                currRotary2Pos = round(self.rotary2.position(), 3)  # update current position display in degrees
            
            # move Rotary3 if active
            if self.ui.activeRot3.isChecked() and self.rotary3:
                currRotary3Pos = self.rotary3.position()
                if abs(currRotary3Pos - rotary3_pos) > move_tol:
                    self.rotary3.move_to(rotary3_pos)
                currRotary3Pos = round(self.rotary3.position(), 3)  # update current position display in degrees

            currPositions = (currStage1Pos, currStage2Pos, currRotary1Pos, currRotary2Pos, currRotary3Pos)

            return True, currPositions
        except Exception as e:
            print(f"Error moving active stages: {e}")
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
            if hasattr(self, 'itc_stab_thread') and self.itc_stab_thread.isRunning():
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
            self.closeInstruments()  # close all instruments first
            
            QApplication.instance().quit()  # then exit application
            
        else:
            print("Exit cancelled.")
    #endregion                   
                
    #region Main function for running scan in a separate thread
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
        
        # reset stop flag
        self.stop_flag = False  # this is the main moSys class stop flag, also used in ScanThread
        
        # setup buttons state during scan
        self.set_ControlsEnabledDuringScan(True)
        
        # Create scan thread, connect to the separate 'ScanThread' class
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
        self.scan_Thread.tds_peak_update.connect(self.update_iPos2_from_tds_peak)  # update iPos2 from TDS peak position
        
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
                
                # go to target temperature and stabilize
                thread.enable_pid.emit(True) # emit signal for enable pid
                self.iTC_goto_targetT(target_T, update_ui=False)  # do not update UI from here, let the signal-slot handle it in main thread
                ### Or can emit signal to main thread to call iTC_goto_targetT, and need not use 'update_ui' here  
                
                # wait for temperature stabilization to complete
                loop_for_Tstab = QEventLoop()
                self.itc_stab_thread.finished.connect(loop_for_Tstab.quit)
                loop_for_Tstab.exec()  # wait until itc_stab_thread is finished   
                thread.temp_done_led.emit(True)  # set temperature done LED
                    
                #region Calibrate TDS peak position for 1D_THz scan mode at each temperature point
                if scan_mode_box and scan_mode == '1D_THz':  # 1D_Scan mode
                    print("Calibrating TDS peak position for 1D scan mode...")
                    tds_peak_info = self.get_TDS_peak_pos()
                    new_peak = tds_peak_info.get('max_position') if tds_peak_info else None

                    if new_peak is not None:
                        thread.tds_peak_update.emit(new_peak)  # emit signal to update iPos1 in UI
                        print(f"Applied new TDS peak position: {new_peak} mm to iPos1.")
                    else:
                        print(f"TDS peak calibration skipped: no peak found.")                
        #endregion
        #endregion
            #region Navigate to data save path and create file for saving data
            fileName = self.setup_dataFile_Name(f"{scan_mode}_{target_T}K" if self.ui.ScanT.isChecked() else scan_mode)
            filePath = self.dataSave_path
            os.makedirs(filePath, exist_ok=True)  # Ensure directory exists， create if not exist
            self.fullFilePath = os.path.join(filePath, f"{fileName}.h5")    # full file path with .h5 extension
            print(f"Data will be saved to: {self.fullFilePath}")
            
            # Create HDF5 file
            self.h5_file = h5py.File(self.fullFilePath, 'w')
            #endregion
            
            #region Save scan parameters in HDF5 file || generate all position sequences || initialize datasets
            stage1_rep = getattr(self.ui, 'scanRepNO1').value()
            stage2_rep = getattr(self.ui, 'scanRepNO2').value()
            rotary1_rep = getattr(self.ui, 'ScanRepNO_R1').value()
            rotary2_rep = getattr(self.ui, 'ScanRepNO_R2').value()
            rep_array = np.array([stage1_rep, stage2_rep, rotary1_rep, rotary2_rep], dtype='i8')
            self.ds_rep_array = self.h5_file.create_dataset('rep_array', data=rep_array, dtype='i8')
            
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

            self.h5_file.flush()  # write to file for avoiding data loss
            #endregion
            
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
            stage1_pos_sequence,  stage1_step_sequence,  stage1_stepNO_sequence  = self.generate_position_sequence(iPos1, stage1_array);  stage1_NO = len(stage1_pos_sequence)
            stage2_pos_sequence,  stage2_step_sequence,  stage2_stepNO_sequence  = self.generate_position_sequence(iPos2, stage2_array);  stage2_NO = len(stage2_pos_sequence)
            rotary1_pos_sequence, rotary1_step_sequence, rotary1_stepNO_sequence = self.generate_position_sequence(iRot1, rotary1_array); rotary1_NO = len(rotary1_pos_sequence)
            rotary2_pos_sequence, rotary2_step_sequence, rotary2_stepNO_sequence = self.generate_position_sequence(iRot2, rotary2_array); rotary2_NO = len(rotary2_pos_sequence)
            rotary3_pos_sequence, rotary3_step_sequence, rotary3_stepNO_sequence = self.generate_position_sequence(iRot3, rotary3_array); rotary3_NO = len(rotary3_pos_sequence)

            #region Decide if use calibration data for rotary2-based polarization dependence scan 
            pol_policy = 'coupled' if scan_mode in ('1D_POL', 'POL_2D') else 'independent'
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
                polarization_policy=pol_policy,
                pol_cali_mode=self.ui.pol_cali_mode.isChecked(),
                cali_table=self.cali_table,
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

            # create datasets: shape: meaning current size; maxshape: None means unlimited; chunks: chunk size for I/O; dtype: data type, f8: float64
            self.ds_lockin1_X = self.h5_file.create_dataset('lockin1_X', shape=(stage1_NO, stage1_rep, stage2_NO, stage2_rep, N_pol, pol_rep), chunks=(1, 1, 1, 1, 1, 1), dtype='f8')
            self.ds_lockin1_Y = self.h5_file.create_dataset('lockin1_Y', shape=(stage1_NO, stage1_rep, stage2_NO, stage2_rep, N_pol, pol_rep), chunks=(1, 1, 1, 1, 1, 1), dtype='f8')
            self.ds_lockin2_X = self.h5_file.create_dataset('lockin2_X', shape=(stage1_NO, stage1_rep, stage2_NO, stage2_rep, N_pol, pol_rep), chunks=(1, 1, 1, 1, 1, 1), dtype='f8')
            self.ds_lockin2_Y = self.h5_file.create_dataset('lockin2_Y', shape=(stage1_NO, stage1_rep, stage2_NO, stage2_rep, N_pol, pol_rep), chunks=(1, 1, 1, 1, 1, 1), dtype='f8')

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
            stage1_total = iterator_plan['stage1_total']
            stage2_total = iterator_plan['stage2_total']
            pol_total = iterator_plan['pol_total']
            scan_iterator = iterator_plan['scan_iterator']
                
            print(f"Generated position scan_iterator indexes for all stages: {scan_iterator}")
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
                if move_success:
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
                    #continue  # skip data acquisition if movement failed


                #region Lockin data acquisition and saving
                wait_time1_s = self.ui.wait1.value() / 1000.0  # convert ms to s
                wait_time2_s = self.ui.wait2.value() / 1000.0  # convert ms to s
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
                self.ds_lockin1_X[stage1_idx, stage1_rep_idx, stage2_idx, stage2_rep_idx, pol_idx, pol_rep_idx] = l1x
                self.ds_lockin1_Y[stage1_idx, stage1_rep_idx, stage2_idx, stage2_rep_idx, pol_idx, pol_rep_idx] = l1y
                self.ds_lockin2_X[stage1_idx, stage1_rep_idx, stage2_idx, stage2_rep_idx, pol_idx, pol_rep_idx] = l2x
                self.ds_lockin2_Y[stage1_idx, stage1_rep_idx, stage2_idx, stage2_rep_idx, pol_idx, pol_rep_idx] = l2y
                                    
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
                        'rotary2_idx': pol_rep_idx * N_pol + pol_idx
                    }
                    thread.pol_update.emit(pol_data)  # emit polar chart update signal
                
                
                self.h5_file.flush(),  # write to file for avoiding data loss

                print(f"Acquired data point {stage1_idx+1}|{stage1_rep_idx+1}|{stage2_idx+1}|{stage2_rep_idx+1}|{pol_idx+1}|{pol_rep_idx+1}: "
                      f"Lockin1 X={l1x:.4e}, Y={l1y:.4e}; " f"Lockin2 X={l2x:.4e}, Y={l2y:.4e}")
                #endregion
                
                #region Emit "stage_pos, lockin1_X"" data signal after each repeat for TDS chart update
                if scan_mode in ["1D_POL", "1D_THz"]:  # emit stage1 position and lockin1 X data for TDS chart update
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
                            
                elif scan_mode in ["THz_Scan", "2D_THz"]:  # emit stage2 position and lockin1 X data for TDS chart update
                        if stage2_idx == stage2_NO -1:
                            try:
                                tds_y_data = self.ds_lockin1_X[stage1_idx, stage1_rep_idx, :, stage2_rep_idx, pol_idx, pol_rep_idx] # read data from HDF5 dataset for current repeat
                                tds_data = {
                                    'tds_x': stage2_pos_sequence,
                                    'tds_y': tds_y_data.tolist()
                                }
                                thread.tds_update.emit(tds_data)  # emit TDS data update signal if needed
                                print(f"TDS data updated at stage1 index {stage1_idx + 1} for repeat {stage1_rep_idx + 1}.")
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
        # Disable all controls during scan except stop and exit button
        input_type = (QPushButton, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QLineEdit)
        always_enabled = [self.ui.stopButton, self.ui.exitApp, self.ui.realtimeDispT]
        
        if scanning:
            # iterate through all child widgets and disable inputs controls
            for widget in self.ui.findChildren(QWidget):
                # skip PlotWidgets
                if isinstance(widget, pg.PlotWidget):
                    continue  
                
                # Whitelist certain widgets to remain enabled
                if widget in always_enabled:
                    if widget == self.ui.stopButton:
                        widget.setEnabled(True)  # enable stop button
                    elif widget == self.ui.exitApp:
                        widget.setEnabled(True)  # enable exit button
                    elif widget == self.ui.realtimeDispT:
                        widget.setEnabled(True)  # enable realtime temperature display checkbox
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
    #endregion

    #region Update current scan parameters in UI
    """ The following functions are slots connected to signals emitted from ScanThread to update the UI in real-time during the scan process."""
    def update_curr_repeat(self, rep_dict: dict):
        if 'stage1_curr_rep' in rep_dict and rep_dict['stage1_curr_rep'] is not None:
            self.ui.stage1CurrScan.setValue(rep_dict['stage1_curr_rep'])
        if 'stage2_curr_rep' in rep_dict and rep_dict['stage2_curr_rep'] is not None:
            self.ui.stage2CurrScan.setValue(rep_dict['stage2_curr_rep'])
        if 'rotary1_curr_rep' in rep_dict and rep_dict['rotary1_curr_rep'] is not None:
            self.ui.Rot1CurrScan.setValue(rep_dict['rotary1_curr_rep'])
        if 'rotary2_curr_rep' in rep_dict and rep_dict['rotary2_curr_rep'] is not None:
            self.ui.Rot2CurrScan.setValue(rep_dict['rotary2_curr_rep'])
        # process events to update UI immediately
        QApplication.processEvents()
        
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
            
        # process events to update UI immediately
        QApplication.processEvents()
        
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
            
        # process events to update UI immediately
        QApplication.processEvents()
        
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
            
        # process events to update UI immediately
        QApplication.processEvents()
        

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
        # process events to update UI immediately
        QApplication.processEvents()
        
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
                QApplication.processEvents()   # force execute events to update UI immediately
        
            if 'lockin' in pol_data and pol_data['lockin'] is not None:
                self.chart_updaters['polChart'].update(update_single_shot=True, lockin_reading=pol_data['lockin'])
            else:
                print("Warning: Polar chart data is incomplete, skipping update.")
                return
        # process events to update UI immediately
        QApplication.processEvents()
            
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
        
        ## Update TDS Chart with new data
        # get blue and red curves of tdsChart
        blue_curve_FDS = self.curves['fdsChart']['blue']
        red_curve_FDS  = self.curves['fdsChart']['red']  
        # perform FFT calculation
        freq, amp_FDS = self.thz_fft_calc(np.array(x), np.array(y))   # use np.array() to convert list to numpy array and avoid compatibility issues
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
        
        # process events to update UI immediately
        QApplication.processEvents()

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
    
    #region THz FFT calculation function
    def thz_fft_calc(self, position_mm, TDS_amplitude):
        """Here, multi-steps scan is taken into considuration for FFT processing.
       The resolution is find the smallest step size in position_mm and use it as new_time_step.
       Use the new_time_step to interpolate TDS_amplitude and then perform FFT processing."""
       
        print(f"thz_fft_calc: position_mm length = {len(position_mm)}, TDS_amplitude length = {len(TDS_amplitude)}")
        c = 3e8  # speed of light in m/s
        time_ps = 2 * position_mm * 1e-3 / c * 1e12  # convert position in mm to time in ps (round-trip)
        # make sure time_ps sort from small to large
        if time_ps[0] > time_ps[-1]:
            time_ps = time_ps[::-1]      # reverse time_ps, [start stop:step]--> ':' means all elements from begin to end of the array
            TDS_amplitude = TDS_amplitude[::-1]
            
        time_step_min = np.min(np.abs(np.diff(time_ps)))  # find the minimum time step in ps
        time_step_uniform = np.arange(time_ps.min(), time_ps.max(), time_step_min)  # uniform time steps
        TDS_amplitude_interp = np.interp(time_step_uniform, time_ps, TDS_amplitude)  # interpolate amplitude

        # Perform FFT
        Num_amp = len(TDS_amplitude_interp) # Number of sample points
        amp_FDS = np.fft.fft(TDS_amplitude_interp)
        freq = np.fft.fftfreq(Num_amp, time_step_uniform[1] - time_step_uniform[0])  # frequency bins in THz

        # Only take the positive frequencies
        idx = np.where(freq >= 0)
        amp_FDS = amp_FDS[idx]
        freq = freq[idx]

        return freq, amp_FDS
    #endregion

    #region Scan finished and error handling functions
    def on_scan_finished(self):
        print("============================Scan finished============================")
        # disable stop button and enable run button after scan
        self.set_ControlsEnabledDuringScan(False)
        
    def on_handle_scan_error(self, error_message: str):
        print(f"Error during scan: {error_message}")
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
            self.timer.start(self.interval)
        else:
            self.timer.stop()
            
    def update(self, update_single_shot: bool = False, lockin_reading: float = None):  
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
                print(f"Warning: Lockin device '{self.lockin_name}' is not connected for {chartName}.")
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
            print(f"Updating number box: {numberBox_name} with value: {y}")   
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
            # emit scan finished signal
            self.scan_finished.emit()
        except Exception as e:
            error_msg = str(e)
            print(f"Error during scan execution: {error_msg}")
            traceback.print_exc()                      # print traceback for debugging
            self.error_occurred.emit(error_msg)        # emit error signal to main thread through error_occurred signal
            
    def request_stop(self):
        """ Set the stop flag to True to request stopping the scan."""
        self.stop_flag = True
        self.parent.stop_flag = True  # also set parent's stop_flag to True
        print("Received the stop request.")
#endregion

#region MercuryiTC class for real-time update
class MercuryiTC_Updater:
    """ This class handles the real-time update of MercuryiTC parameters in the UI."""
    def __init__(self, parent_moSys: moSys, interval: int = 1000):
        
        self.parent = parent_moSys
        self.interval = interval
        self.iTC_timer = QTimer(self.parent.ui)
        self.iTC_timer.timeout.connect(self.update_disp_oneshot)
        self.iTC_timer.setInterval(self.interval)
        
    def update_Interval(self, new_interval: int):
        # avoid invalid interval
        new_interval = max(1000, new_interval * 1000)  # minimum 1000 ms
        self.interval = new_interval
        self.iTC_timer.setInterval(self.interval) # update timer interval
        print(f"MercuryiTC update interval set to {self.interval} ms.")
        
    def update_mercuryiTC_display(self, checked: bool):
        """ Start/stop the MercuryiTC real-time update based on checkbox state."""
        if not self.parent.ui.activeiTC.isChecked() or self.parent.mercuryiTC is None:
            print("MercuryiTC device not connected.")
            return  # skip update if MercuryiTC is not active or not connected
    
        if checked:
            self.iTC_timer.start(self.interval)
        else:
            self.iTC_timer.stop()   
            
    def update_disp_oneshot(self):
        """ Update MercuryiTC display parameters in UI."""
        if  not self.parent.ui.activeiTC.isChecked() or self.parent.mercuryiTC is None:
            print("MercuryiTC device not connected.")
            return  # skip update if MercuryiTC is not active or not connected
            
        try:
            with self.parent.mercuryiTC.io_lock:
                curr_temp = self.parent.mercuryiTC.read_temperature(self.parent.uid_TEMP)
                print(f"Current MercuryiTC temperature: {curr_temp} K")
                curr_setpoint = self.parent.mercuryiTC.get_temperature_setpoint(self.parent.uid_TEMP)
                curr_heater = self.parent.mercuryiTC.read_heater_voltage(self.parent.uid_HTR)
                curr_heater_limit = self.parent.mercuryiTC.get_heater_voltage_limit(self.parent.uid_HTR)
                curr_heater_percent = (curr_heater / curr_heater_limit) * 100 if curr_heater_limit != 0 else 0.0  # calculate heater percent

            self.parent.ui.realDispiTC.setText(f"{curr_temp:.3f} K")
            #self.parent.ui.targetT.setValue(curr_setpoint)
            self.parent.ui.HeaterBar.setValue(curr_heater_percent)
        except Exception as e:
            print(f"Error updating MercuryiTC display: {e}") 
            
    def set_heater_limit(self, new_limit: float):
        """ Update MercuryiTC heater limit from UI."""
        if self.parent.ui.activeiTC.isChecked() and self.parent.mercuryiTC:
            try:
                new_limit = new_limit
                with self.parent.mercuryiTC.io_lock:
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
        if self.parent.ui.activeiTC.isChecked() and self.parent.mercuryiTC and not self.parent.ui.autoPID.isChecked(): # if auto PID is enabled, skip manual heater setting
            try:
                with self.parent.mercuryiTC.io_lock:
                    heater_limit = self.parent.mercuryiTC.get_heater_voltage_limit(self.parent.uid_HTR)
                    new_heater_voltage = (percent / 100.0) * heater_limit
                    self.parent.mercuryiTC.set_heater_voltage(self.parent.uid_HTR, new_heater_voltage)
                    
                    verified_voltage = self.parent.mercuryiTC.read_heater_voltage(self.parent.uid_HTR) # verify the heater voltage
                verified_percent = (verified_voltage / heater_limit) * 100 if heater_limit != 0 else 0.0
                if abs(verified_voltage - new_heater_voltage) < 0.1:
                    print(f"MercuryiTC heater voltage set to {verified_voltage} V ({verified_percent:.2f} %) successfully.")
                else:
                    print(f"Warning: MercuryiTC heater voltage verification failed. Set to {new_heater_voltage} V, but read back {verified_voltage} V.") 
            except Exception as e:
                print(f"Error setting MercuryiTC heater voltage: {e}")
        else:
            print("MercuryiTC device not connected.")
    
    def setup_autoPID_mode(self, checked: bool) -> bool:
        """ Update MercuryiTC auto PID mode from UI."""
        if self.parent.ui.activeiTC.isChecked() and self.parent.mercuryiTC:
            auto_PID_status = checked
            with self.parent.mercuryiTC.io_lock:
                PID_tab_status = self.parent.mercuryiTC.enable_auto_pid_table(self.parent.uid_TEMP, auto_PID_status)
                pid_status = self.parent.mercuryiTC.enable_pid_control(self.parent.uid_TEMP, auto_PID_status)
            result = PID_tab_status and pid_status
            if result:
                print(f"MercuryiTC auto PID mode set to {auto_PID_status}.")
                return auto_PID_status
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
        try:
            # basic safety checks
            if not (self.parent.mercuryiTC and self.parent.ui.activeiTC.isChecked()):
                self.error.emit("MercuryiTC device not connected or not active.")
                self.finished.emit(False)
                return
                
            # poll loop to check temperature stability
            stable_counter = 0
            while not self.stop_flag:
                with self.parent.mercuryiTC.io_lock:
                    curr_T = self.parent.mercuryiTC.read_temperature(self.parent.uid_TEMP)
                tol = self.get_tolerance()     # read lastest tolerance value
                diff = abs(curr_T - self.target_T)
                
                # count consecutive hits within tolerance
                stable_counter = stable_counter + 1 if diff <= tol else 0  # reset counter if out of tolerance
                print(f"iTC Stabilization: Current T = {curr_T:.3f} K, Target T = {self.target_T:.3f} K, Stable Count = {stable_counter}/{self.stable_count}")
                
                # stabilization condition met
                if stable_counter >= self.stable_count:
                    print(f"Temperature stabilized at {curr_T:.3f} K within tolerance {tol} K.")
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
