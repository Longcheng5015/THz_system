#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""" Main program for MO system control and data acquisition GUI application.
    This program provides a graphical user interface (GUI) for controlling various instruments,
    including lock-in amplifiers and motorized stages, as well as real-time data visualization. """
# region Import modules
# import pyside6 for GUI
import pyqtgraph as pg
from PySide6.QtWidgets import QApplication, QMessageBox, QVBoxLayout, QFileDialog, QPushButton, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QLineEdit, QWidget
from PySide6.QtUiTools import QUiLoader
from PySide6.QtGui import QIcon
from collections import deque
from PySide6.QtCore import QTimer, QThread, Signal, QEventLoop

# import packages needed
import os, h5py, random, time, itertools, traceback             # h5py for .mat file saving
import numpy as np
import scipy.io as sio
from datetime import datetime
from pathlib import Path


# Import instrument classes
from newport_PM500 import PM500, PM500Error
from thorlabs_LinearStage import LinearStage
from thorlabs_RotaryStage import RotaryStage
from stanford_SR830 import SR830
# endregion

# 在QApplication之前先实例化
uiLoader = QUiLoader()

#region Main MO System UI class
class moSys:

    def __init__(self):     # initialization for ui and functions
        # load UI file
        # register custom widgets used in .ui file as charts
        uiLoader.registerCustomWidget(pg.PlotWidget)
        self.ui = uiLoader.load('mo_main.ui')

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
                plotItems.setLabel('left', 'Amp (a.u.)')  # set label for bottom axis
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
                print(f"Initializing data buffer and curve for {chartname}")
                
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
        setup_chart_axis(self.ui.polChart, True)
        setup_chart_axis(self.ui.tdsChart, True)
        setup_chart_axis(self.ui.fdsChart, True)
        #endregion
        
        #region Initialize/apply comboboxes
        # Initialize comboboxes for lockin timeconstants and sensitivities
        self._init_sr830_comboboxes()

        # Initialize comboboxe of Scan Mode
        self._init_scanMode_combobox()
        #endregion
        
        #region Initialize path for data saving
        self.setup_data_folder()
        self.setup_dataFile_Name()
        #endregion
        
        #region Setup buttons and their events
        # configure buttons for lockin realtime display as checkable/toggleable
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
        # connect toggles to start/stop chart updates for lockins by dict defined above 
        self.ui.realtimeDisp1.toggled.connect(lambda checked: self.chart_updaters['realDisChart1'].toggle(checked))
        self.ui.realtimeDisp2.toggled.connect(lambda checked: self.chart_updaters['realDisChart2'].toggle(checked))
        
        # everytime the wait time spinbox value changes, update the corresponding chart updater timer interval and lockin
        self.ui.wait1.valueChanged.connect(lambda value: self.chart_updaters['realDisChart1'].update_Interval(int(value)))
        self.ui.wait2.valueChanged.connect(lambda value: self.chart_updaters['realDisChart2'].update_Interval(int(value)))
        
        # update fdsChart when fdsDispMin/Max spinbox value changes
        self.ui.fdsDispMin.valueChanged.connect(self.update_fds_chart_dispRange)
        self.ui.fdsDispMax.valueChanged.connect(self.update_fds_chart_dispRange)

        # set lockin parameter apply button click events
        self.ui.sensitivity1.currentIndexChanged.connect(lambda: self.apply_lockin_parameter('lockin1', 'Sensitivity'))
        self.ui.timeConst1.currentIndexChanged.connect(lambda: self.apply_lockin_parameter('lockin1', 'Timeconstant'))
        self.ui.autoPhase1.clicked.connect(lambda: self.apply_lockin_parameter('lockin1', 'Autophase'))
        self.ui.sensitivity2.currentIndexChanged.connect(lambda: self.apply_lockin_parameter('lockin2', 'Sensitivity')) 
        self.ui.timeConst2.currentIndexChanged.connect(lambda: self.apply_lockin_parameter('lockin2', 'Timeconstant')) 
        self.ui.autoPhase2.clicked.connect(lambda: self.apply_lockin_parameter('lockin2', 'Autophase')) 
        
        # set button click events
        self.ui.stage1MoveTo.clicked.connect(lambda: self.to_target_position('stage1'))   # thorlabs linear stage
        self.ui.stage2MoveTo.clicked.connect(lambda: self.to_target_position('stage2'))   # newport PM500
        self.ui.rot1MoveTo.clicked.connect(lambda: self.to_target_position('rotary1'))    # thorlabs rotary stage
        self.ui.rot2MoveTo.clicked.connect(lambda: self.to_target_position('rotary2'))
        self.ui.browseButton.clicked.connect(self.customize_data_save_path)
        self.ui.scanMode.currentIndexChanged.connect(self.setup_scan_mode)
        self.ui.runButton.clicked.connect(self.runScan, False)
        self.ui.stopButton.clicked.connect(self.stopscan)
        
        self.ui.connectInstr.clicked.connect(self.connectInstruments, False)
        self.ui.closeInstr.clicked.connect(self.closeInstruments, False)
        self.ui.exitApp.clicked.connect(self.exitApp, False)
        
        #endregion
        
        #region Initialize instrument objects as None   
        self.lockin1 = None
        self.lockin2 = None
        self.stage1  = None
        self.stage2  = None
        self.rotary1 = None
        self.rotary2 = None 
        #endregion    
    
        #region Initialize and save thread as None
        self.scan_thread = None
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
            address = 'GPIB0::8::INSTR' 
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
            address = 'GPIB0::10::INSTR' 
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
            try:
                serial = "73877174"  # Replace with your controller serial
                chan = 1
                self.stage1 = LinearStage(serial, chan, poll_ms=250)
                print(f"✓ Stage1 connection successful (serial: {serial}, channel: {chan})")
            except Exception as e: 
                print(f"✗ Stage1 connection failed: {str(e)}")
                
        # connect Stage2
        if self.ui.activeStage2.isChecked():
            RESOURCE   = "GPIB0::4::INSTR"   # e.g. "GPIB0::1::INSTR" or "ASRL3::INSTR"
            AXIS       = "X"                 # "X", "Y", "Z", "A", "B", or "C"
            self.stage2 = PM500(RESOURCE)
            
            try:
                self.stage2 = PM500(RESOURCE).connect()
                print("[PM500 Connect] OK")
                print("[ID]      ", self.stage2.idn())
                # Make sure motor is enabled
                self.stage2.motor_on(AXIS)
                self.stage2.init_pos(AXIS)
                self.qwait_time(10000)  # wait for 10 seconds after init_pos
                print(f"[MotorOn]  {AXIS} axis motor enabled and initialized.")
            except PM500Error as e:
                print("PM500Error:", e)
                
        # connect Rotary1
        if self.ui.activeRot1.isChecked():
            try:
                serial = "27256338"  # Replace with your controller serial
                self.rotary1 = RotaryStage(serial, poll_ms=250, use_sim=False)
                print(f"✓ Rotary1 connection successful (serial: {serial})")
            except Exception as e: 
                print(f"✗ Rotary1 connection failed: {str(e)}")
                
        # connect Rotary2
        if self.ui.activeRot2.isChecked():
            try:
                serial = "27004364"  # Replace with your controller serial
                chan = 1
                self.rotary2 = RotaryStage(serial, poll_ms=250, use_sim=False)
                print(f"✓ Rotary2 connection successful (serial: {serial})")
            except Exception as e: 
                print(f"✗ Rotary2 connection failed: {str(e)}")
    
        
    def closeInstruments(self):
        print("Start closing instruments...")
        print("=" * 50)
        
        # close Lockin1
        if self.lockin1:
            self.lockin1.close()
            print("✓ Lock-in1 closed.")    
            
        # close Lockin2
        if self.lockin2:
            self.lockin2.close()
            print("✓ Lock-in2 closed.")
            
        # close Stage1
        if self.stage1:
            self.stage1.close()
            print("✓ Stage1 closed.")
            
        # close PM500
        if self.stage2:
            self.stage2.close()
            print("✓ PM500 closed.")
            
        # close Rotary1
        if self.rotary1:
            self.rotary1.close()
            print("✓ Rotary1 closed.")
            
        # close Rotary2
        if self.rotary2:
            self.rotary2.close()
            print("✓ Rotary2 closed.")
            
    #endregion         
           
    #region move stage and rotary to target positions    
    def to_target_position(self, stage_name: str) -> bool:
        
        stage_device = getattr(self, stage_name, None)
        if stage_device is None:
                print(f"Warning: {stage_name} is not connected for moving to target position.")
                return False
            
        try:
            if stage_name == 'stage1':
                target_pos = self.ui.stage1SetPos.value()  # convert mm to um
                
                stage_device.move_to(target_pos)
                currPos = stage_device.position()
                self.ui.stage1CurrPos.setValue(currPos)  # convert um to mm
                print(f"Stage1 moved to position: {currPos} mm")
                
            elif stage_name == 'stage2':
                target_pos = self.ui.stage2SetPos.value() * 1000  # convert mm to um
                print(f"Moving Stage2 to target position: {target_pos} um")
                # move stage to target position
                axis = 'X'  # assuming X axis for Stage2
                stage_device.go_and_wait_abs(axis, target_pos, 10000)
                currPos = stage_device.read_pos(axis) / 1000  # in mm
                # update current position display            
                self.ui.stage2CurrPos.setValue(currPos)  # convert um to mm
                print(f"Stage2 moved to position: {currPos} mm")
                
                
            elif stage_name == 'rotary1':
                target_pos = self.ui.rot1SetPos.value()  # in degrees
                
                stage_device.move_to(target_pos)
                currPos = stage_device.position()
                self.ui.rot1CurrPos.setValue(currPos)  # in degrees
                print(f"Rotary1 moved to position: {currPos} degrees")
            elif stage_name == 'rotary2':
                target_pos = self.ui.rot2SetPos.value()  # in degrees   
                
                stage_device.move_to(target_pos)
                currPos = stage_device.position()
                self.ui.rot2CurrPos.setValue(currPos)  # in degrees
                print(f"Rotary2 moved to position: {currPos} degrees")
            return True
        
        except Exception as e:
            print(f"Error moving {stage_name} to target position: {e}")
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
            day_dir = os.path.join(month_dir, day_str)  
            
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
    def setup_dataFile_Name(self) -> str:
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

            # get current scan mode 
            scanMode_box = getattr(self.ui, 'scanMode', None)
            if scanMode_box:
                scan_mode = scanMode_box.currentText()
                
            data_file_name = f"{file_name_timePart}_{scan_mode}"
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
            scan_modes = ['1D_Scan', '2D_Scan', 'TDS_Scan']
            self.ui.scanMode.clear()
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
        if stageName == 'stage1' or stageName == 'stage2':
            for i in range (1, 4):    # up to 3 stepSize
                step_box_name = f'{stageName}Step{i}'
                step_value = getattr(self.ui, step_box_name).value()
                step_value = step_value / 1000                         # convert from um to mm
                step_sizes.append(float(step_value))
                
                stepNO_box_name = f'{stageName}Step{i}NO'
                stepNO_value = getattr(self.ui, stepNO_box_name).value()
                steps_NO.append(int(stepNO_value))
                
        elif stageName == 'rotary1' or stageName == 'rotary2':
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
            
            new_positions = iPos + (np.arange(step_NO) + 1) * step_size  # generate new positions for this step size
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
    
    #region Move active stages and display current positions
    def move_active_stages(self, target_positions: tuple):
        
        stage1_pos, stage2_pos, rotary1_pos, rotary2_pos = target_positions
        
        # Initialize current positions with placeholder (-1)
        currStage1Pos = -1; currStage2Pos = -1
        currRotary1Pos = -1; currRotary2Pos = -1
        
        try:
            # move Stage1 if active
            if self.ui.activeStage1.isChecked() and self.stage1:
                self.stage1.move_to(stage1_pos) # in mm
                currStage1Pos = self.stage1.position()  # # update current position display in mm

            # move Stage2 if active
            if self.ui.activeStage2.isChecked() and self.stage2:
                axis = 'X'  # assuming X axis for Stage2
                self.stage2.go_and_wait_abs(axis, stage2_pos*1000, 10) # convert mm to um
                currStage2Pos = self.stage2.read_pos(axis) / 1000  # update current position display in mm

            # move Rotary1 if active
            if self.ui.activeRot1.isChecked() and self.rotary1:
                self.rotary1.move_to(rotary1_pos)
                currRotary1Pos = self.rotary1.position()  # update current position display in degrees

            # move Rotary2 if active
            if self.ui.activeRot2.isChecked() and self.rotary2:
                self.rotary2.move_to(rotary2_pos)
                currRotary2Pos = self.rotary2.position()  # update current position display in degrees

            currPositions = (currStage1Pos, currStage2Pos, currRotary1Pos, currRotary2Pos)

            return True, currPositions
        except Exception as e:
            print(f"Error moving active stages: {e}")
            return False, None
        #endregion
    
    #region Stop Scan flag function
    def stopscan(self):
        """ Stop the ongoing scan process."""
        # pop up confirmation dialog
        reply = QMessageBox.question(self.ui, 'Confirm Stop', 'Are you sure you want to stop the scan?\n\nCurrent progress will be saved.',
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No) # default is No

        if reply == QMessageBox.Yes:
            # stop the threaded scan by setting stop flag
            if self.scan_thread and self.scan_thread.isRunning():
                self.scan_thread.request_stop()  # request stop for scan thread
                
                
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
        self.scan_Thread.scan_finished.connect(self.on_scan_finished)     # could also add another slot function to handle initial results processing and display after scan finished
        self.scan_Thread.error_occurred.connect(self.on_handle_scan_error)
        
        # start scan thread
        self.scan_Thread.start()
        print("Scan thread started.")
        
    #endregion
        
    #region _execute_scan_logic: actual scan logic executed in ScanThread
    def _execute_scan_logic(self, thread):   
        print("======================Executing scan logic in Thread======================")

        #region Navigate to data save path and create file for saving data
        fileName = self.setup_dataFile_Name()
        filePath = self.dataSave_path
        os.makedirs(filePath, exist_ok=True)  # Ensure directory exists， create if not exist
        self.fullFilePath = os.path.join(filePath, f"{fileName}.h5")    # full file path with .h5 extension
        print(f"Data will be saved to: {self.fullFilePath}")
        
        # Create HDF5 file
        self.h5_file = h5py.File(self.fullFilePath, 'w')
        #endregion
        
        #region Save scan parameters in HDF5 file || generate all position sequences || initialize datasets
        scan_repeats  = getattr(self.ui, 'scanRepNO1').value()   # Get scan repeatNO. from UI
        
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

        self.h5_file.flush()  # write to file for avoiding data loss
        
        # Generate position sequences, in mm for linear stages, degree for rotary stages
        stage1_pos_sequence,  stage1_step_sequence,  stage1_stepNO_sequence = self.generate_position_sequence(iPos1, stage1_array);  stage1_NO = len(stage1_pos_sequence)
        stage2_pos_sequence,  stage2_step_sequence,  stage2_stepNO_sequence = self.generate_position_sequence(iPos2, stage2_array);  stage2_NO = len(stage2_pos_sequence)
        rotary1_pos_sequence, rotary1_step_sequence, rotary1_stepNO_sequence = self.generate_position_sequence(iRot1, rotary1_array); rotary1_NO = len(rotary1_pos_sequence)
        rotary2_pos_sequence, rotary2_step_sequence, rotary2_stepNO_sequence = self.generate_position_sequence(iRot2, rotary2_array); rotary2_NO = len(rotary2_pos_sequence)

        # generate total position points for all stages
        total_position_points = itertools.product(stage1_pos_sequence, stage2_pos_sequence, rotary1_pos_sequence, rotary2_pos_sequence)
        total_position_idx    = itertools.product(range(stage1_NO), range(stage2_NO), range(rotary1_NO), range(rotary2_NO))

        total_position_list = list(total_position_points)  # convert to list for counting total points
        total_idx_list = list(total_position_idx)
        print(f"Generated position sequences for all stages: {total_position_list}")
        print(f"Generated position indexes for all stages: {total_idx_list}")

        # create datasets: shape: meaning current size; maxshape: None means unlimited; chunks: chunk size for I/O; dtype: data type, f8: float64
        self.ds_lockin1_X = self.h5_file.create_dataset('lockin1_X', shape=(stage1_NO, rotary2_NO, scan_repeats), chunks=(1, 1, 1), dtype='f8')
        self.ds_lockin1_Y = self.h5_file.create_dataset('lockin1_Y', shape=(stage1_NO, rotary2_NO, scan_repeats), chunks=(1, 1, 1), dtype='f8')
        self.ds_lockin2_X = self.h5_file.create_dataset('lockin2_X', shape=(stage1_NO, rotary2_NO, scan_repeats), chunks=(1, 1, 1), dtype='f8')
        self.ds_lockin2_Y = self.h5_file.create_dataset('lockin2_Y', shape=(stage1_NO, rotary2_NO, scan_repeats), chunks=(1, 1, 1), dtype='f8')

        print(f"HDF5 data file and datasets are initialized for saving.")
        #endregion
        
        #region Start Scan Loop
        for rep in range(scan_repeats):
               
            thread.repeat_update.emit(int(rep + 1))  # update current repeat display
            
            #region check stop flag at the beginning of each repeat
            if self.stop_flag or thread.stop_flag:
                print(f"Scan stop flag detected before starting repeat {rep + 1}/{scan_repeats}. Exiting scan loop.")
                break  # exit the scan loop if stop flag is set
            #endregion
            
            print(f"Starting scan repeat {rep + 1} of {scan_repeats}...")
            # move to initial positions before each repeat
            self.move_active_stages((iPos1, iPos2, iRot1, iRot2))

            # iterate through all position combinations
            for stage1_idx, stage2_idx, rotary1_idx, rotary2_idx in itertools.product(range(stage1_NO), range(stage2_NO), range(rotary1_NO), range(rotary2_NO)):
                stage1_pos, stage2_pos, rotary1_pos, rotary2_pos = stage1_pos_sequence[stage1_idx], stage2_pos_sequence[stage2_idx], rotary1_pos_sequence[rotary1_idx], rotary2_pos_sequence[rotary2_idx]

                # move active stages to target positions, and real-time display current positions and step sizes
                move_success, curr_pos_sets = self.move_active_stages((stage1_pos, stage2_pos, rotary1_pos, rotary2_pos))
                if move_success:
                    print(f"Move successful! Actual positions: {curr_pos_sets}")
                    # emit position to update signal
                    curr_positions = {
                        'stage1_pos': curr_pos_sets[0],
                        'stage2_pos': curr_pos_sets[1],
                        'rotary1_pos': curr_pos_sets[2],
                        'rotary2_pos': curr_pos_sets[3]
                    }
                    thread.position_update.emit(curr_positions)

                    # Emit step size to update signal
                    curr_steps = {
                        'stage1_step': stage1_step_sequence[stage1_idx],
                        'stage2_step': stage2_step_sequence[stage2_idx],   # in mm
                        'rotary1_step': rotary1_step_sequence[rotary1_idx],
                        'rotary2_step': rotary2_step_sequence[rotary2_idx]
                    }
                    
                    thread.step_update.emit(curr_steps)
                    
                    curr_stepNOs = {
                        'stage1_NO': stage1_stepNO_sequence[stage1_idx],
                        'stage2_NO': stage2_stepNO_sequence[stage2_idx],
                        'rotary1_NO': rotary1_stepNO_sequence[rotary1_idx],
                        'rotary2_NO': rotary2_stepNO_sequence[rotary2_idx]
                    }
                    thread.stepNO_update.emit(curr_stepNOs)
                    
                else:
                    print(f"Skipping data acquisition at point {stage1_pos, stage2_pos, rotary1_pos, rotary2_pos} due to movement error.")
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
                        time.sleep(wait_time2_s)  # wait before acquisition, for timeconstant settling
                        l2x = self.lockin2.get_x() if self.lockin2 else 0.0
                        time.sleep(0.05)
                        l2y = self.lockin2.get_y() if self.lockin2 else 0.0
                except Exception as e:
                    print(f"Error acquiring data from lockin2: {e}")
                    l2x, l2y = 0.0, 0.0  # assign default values on error
                
                # Store acquired data into h5py datasets, according to 'position indexes' and scan mode
                # Choose dataset indexes based on scan mode
                scanMode_box = getattr(self.ui, 'scanMode', None) 
                scanMode_idx = scanMode_box.currentIndex() if scanMode_box else None

                if scanMode_idx == 0 or scanMode_idx == 1:  # 1D and 2D Scan mode
                    self.ds_lockin1_X[stage1_idx, rotary2_idx, rep] = l1x
                    self.ds_lockin1_Y[stage1_idx, rotary2_idx, rep] = l1y
                    self.ds_lockin2_X[stage1_idx, rotary2_idx, rep] = l2x
                    self.ds_lockin2_Y[stage1_idx, rotary2_idx, rep] = l2y
                elif scanMode_idx == 2:  # TDS Scan mode
                    self.ds_lockin1_X[stage2_idx, rotary2_idx, rep] = l1x
                    self.ds_lockin1_Y[stage2_idx, rotary2_idx, rep] = l1y
                    self.ds_lockin2_X[stage2_idx, rotary2_idx, rep] = l2x
                    self.ds_lockin2_Y[stage2_idx, rotary2_idx, rep] = l2y
                else:
                    print(f"Warning: Unknown scan mode index {scanMode_idx}. Data not saved.")
                    continue
                
                # emit lockin readings to update lockin 1 and 2 charts
                lockin_readings = {
                    'l1x': l1x,
                    'l1y': l1y,
                    'l2x': l2x,
                    'l2y': l2y
                }
                thread.lockin_update.emit(lockin_readings) # emit lockin data update signal if needed
                
                # emit lockin readings to update polar chart
                enable_pol_chart = (rotary2_NO >= 2)
                
                if enable_pol_chart:
                    pol_data = {
                        'Angle': rotary2_pos,
                        'l2x': l2x,
                        'rotary2_NO': rotary2_NO,
                        'rotary2_idx': rotary2_idx 
                    }
                    thread.pol_update.emit(pol_data)  # emit polar chart update signal
                
                
                self.h5_file.flush(),  # write to file for avoiding data loss

                print(f"Acquired data point {stage1_idx+1}|{stage2_idx+1}|{rotary2_idx+1}|{rep+1}: "
                    f"Lockin1 X={l1x:.4e}, Y={l1y:.4e}; " f"Lockin2 X={l2x:.4e}, Y={l2y:.4e}")
                #endregion
                
                #region check stop flag at the beginning of each repeat
                if self.stop_flag or thread.stop_flag:
                    print(f"Scan stop flag detected at point {stage1_pos, stage2_pos, rotary1_pos, rotary2_pos}. Exiting scan loop.")
                    print("============================Scan stopped by user============================") 
                    break  # exit the scan loop if stop flag is set
                #endregion
                
            #region Emit "stage_pos: lockin1_X"" data signal after each repeat for TDS chart update
            rotary2_target_idx = 0  # choose first rotary2 position for TDS chart update 
            
            if scanMode_idx == 0 or scanMode_idx == 1:
                tds_x_data = stage1_pos_sequence.copy()
                tds_y_data = []
                
                for s1_idx in range(stage1_NO):
                    # read data from HDF5 dataset for current repeat
                    y_value = self.ds_lockin1_X[s1_idx, rotary2_target_idx, rep]
                    tds_y_data.append(float(y_value))
            elif scanMode_idx == 2:  # TDS Scan mode, position x is stage2
                tds_x_data = stage2_pos_sequence.copy()
                tds_y_data = []
                
                for s2_idx in range(stage2_NO):
                    # read data from HDF5 dataset for current repeat
                    y_value = self.ds_lockin1_X[s2_idx, rotary2_target_idx, rep]
                    tds_y_data.append(float(y_value))
                     
            # emit TDS data update signal
            print({"tds_x_data": tds_x_data, "tds_y_data": tds_y_data})
            tds_data = {
                'tds_x': tds_x_data,
                'tds_y': tds_y_data
            }
            thread.tds_update.emit(tds_data)  # emit TDS data update signal if needed
            print(f"TDS data updated for repeat {rep + 1}.")
            #endregion
        #endregion
        
        if self.h5_file:
            self.h5_file.close()  # close HDF5 file after scan
            print(f"HDF5 file closed and data saved to {self.fullFilePath}.")
              
    #endregion
    
    #region set_ControlsEnabledDuringScan function
    def set_ControlsEnabledDuringScan(self, scanning: bool):
        # Disable all controls during scan except stop and exit button
        input_type = (QPushButton, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QLineEdit)
        always_enabled = [self.ui.stopButton, self.ui.exitApp]
        
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

    #region update current scan parameters in UI
    """ The following functions are slots connected to signals emitted from ScanThread to update the UI in real-time during the scan process."""
    def update_curr_repeat(self, rep_num: int):
        self.ui.stage1CurrScan.setValue(rep_num)
        self.ui.stage2CurrScan.setValue(rep_num)
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
        y = pol_data.get('l2x', [])
        rotary2_NO = pol_data.get('rotary2_NO', 1)
        rotary2_idx = pol_data.get('rotary2_idx', 0)
        
        if 'rotary2_idx' in pol_data and pol_data['rotary2_idx'] is not None:
            if rotary2_idx == 0:
                self.curves['polChart'].clear()  # clear previous data for new scan
                self.buffers['polChart'].clear()  # clear buffer as well
                self.indices['polChart'] = -1  # reset index
                QApplication.processEvents()   # force execute events to update UI immediately
        
            if 'l2x' in pol_data and pol_data['l2x'] is not None:
                self.chart_updaters['polChart'].update(update_single_shot=True, lockin_reading=pol_data['l2x'])
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
    
        c = 3e8  # speed of light in m/s
        time_ps = 2 * position_mm * 1e-3 / c * 1e12  # convert position in mm to time in ps (round-trip)
        time_step_min = np.min(np.diff(time_ps))  # find the minimum time step in ps
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
    repeat_update = Signal(int)     # signal to update progress bar
    position_update = Signal(dict)  # signal to update current position display
    step_update = Signal(dict)      # signal to update current step size display
    stepNO_update = Signal(dict)    # signal to update current step number display
    lockin_update = Signal(dict)    # signal to update lockin readings display
    tds_update = Signal(dict)       # signal to update TDS readings display
    pol_update = Signal(dict)       # signal to update polarimeter readings display
    scan_finished = Signal()        # signal to be emitted when scan is finished
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


    # region Scanned data preprocessing and plotting functions
    # set a connect get single of scan finished signal, then run data processing function, then plot data in blue and red channels
    # to be implemented later


app = QApplication()
# load icon for mainwindow
app.setWindowIcon(QIcon('mo_icon.png'))
mosys = moSys()
mosys.ui.show()
app.exec()