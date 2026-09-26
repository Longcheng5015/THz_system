# mercury_itc.py
"""
Oxford Instruments Mercury iTC Temperature Controller
SCPI command interface via PyVISA
Add thread-safe operations with locking mechanism
"""

from __future__ import annotations # for Python 3.7+, to allow class methods to return instance of the class
from typing import Optional, Literal, Dict, List, Tuple
import time
import pyvisa
import threading


class MercuryiTCError(Exception):
    """Exception for Mercury iTC operations."""
    pass


class MercuryiTC:
    """
    Oxford Instruments Mercury iTC temperature controller interface.
    
    Supports RS232, GPIB, Ethernet, and USB connections via PyVISA.
    Uses SCPI command protocol.
    
    Example:
        # Ethernet connection
        itc = MercuryiTC("TCPIP::192.168.1.100::7020::SOCKET")
        
        # GPIB connection
        itc = MercuryiTC("GPIB0::12::INSTR")
        
        # RS232 connection
        itc = MercuryiTC("ASRL3::INSTR")
        
        with itc.connect():
            print(itc.idn())
            
            # Read temperature from motherboard sensor
            temp = itc.read_temperature("MB1.T1")
            print(f"Temperature: {temp} K")
            
            # Set temperature setpoint
            itc.set_temp_point("MB1.T1", 300.0)
            
            # Enable PID control
            itc.enable_pid_control("MB1.T1", True)
            
            # Set PID parameters
            itc.set_pid_params("MB1.T1", p=50, i=20, d=5)
            
            # Read heater power
            power = itc.read_heater_power("MB0.H1")
            print(f"Heater power: {power} W")
    """

    def __init__(self, resource: str, timeout_ms: int = 5000):
        """
        Initialize Mercury iTC controller.
        
        Args:
            resource: VISA resource string
                - Ethernet: "TCPIP::192.168.1.100::7020::SOCKET"
                - GPIB: "GPIB0::12::INSTR"  (default address 12)
                - RS232: "ASRL3::INSTR"
                - USB: "USB0::0x0699::0x XXXX::SERIAL::INSTR"
            timeout_ms: Communication timeout in milliseconds
        """
        self._io_lock = threading.RLock() # Reentrant lock for thread-safe operations
        self.resource = resource
        self.timeout_ms = timeout_ms
        self._rm: Optional[pyvisa.ResourceManager] = None
        self._inst: Optional[pyvisa.resources.MessageBasedResource] = None
        
    @property
    def io_lock(self):
        """Get the I/O lock for thread-safe operations."""
        return self._io_lock
    # ==================== Connection Management ====================
    
    
    
    def open(self) -> None:
        """Open connection to instrument."""
        if self._inst is not None:
            return
            
        self._rm = pyvisa.ResourceManager()
        self._inst = self._rm.open_resource(self.resource)
        self._inst.timeout = self.timeout_ms
        
        
        # Set terminators according to manual (page 107)
        self._inst.read_termination = '\n'   # LF (0x0A)
        self._inst.write_termination = '\n'  # LF (0x0A)
        
        self._inst.encoding = 'ascii'
        
        # For RS232, configure parameters if needed
        if 'ASRL' in self.resource:
            # Default RS232 settings (configurable on device)
            try:
                self._inst.baud_rate = 9600  # Adjust as configured on device
                self._inst.data_bits = 8
                self._inst.parity = pyvisa.constants.Parity.none
                self._inst.stop_bits = pyvisa.constants.StopBits.one
            except:
                pass  # Some parameters may not be settable
        
        # For Ethernet SOCKET connection, may need additional config
        if 'SOCKET' in self.resource:
            self._inst.read_termination = '\n'
            self._inst.write_termination = '\n'
        
        # Clear any pending data
        try:
            self._inst.clear()
        except:
            pass
        
        # Flush input buffer
        # old_timeout = self._inst.timeout
        # self._inst.timeout = 100  # 短超时
        # try:
        #     while True:
        #         self._inst.read_raw()  # 读取并丢弃所有残留数据
        # except pyvisa.errors.VisaIOError:
        #     pass  # 超时表示缓冲区已空
        # finally:
        #     self._inst.timeout = old_timeout
            
        time.sleep(0.3)  # Wait for instrument to be ready
        
    def close(self) -> None:
        """Close this instrument's VISA session.

        The ResourceManager is deliberately NOT closed here. pyvisa.ResourceManager() is a
        process-wide singleton, so every instrument in the application holds the same object;
        closing it would invalidate the sessions of all the other instruments (and raise
        VI_ERROR_INV_OBJECT while walking resources that are already dead). It is released at
        interpreter exit.
        """
        try:
            if self._inst is not None:
                self._inst.close()
        finally:
            self._inst = None
            self._rm = None   # drop our reference only; the shared manager stays alive
    
    def __enter__(self) -> "MercuryiTC":
        self.open()
        return self
    
    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
    
    def connect(self) -> "MercuryiTC":
        """Context manager alias."""
        self.open()
        return self
    
    # ==================== Low-Level Communication ====================
    
    def write(self, cmd: str) -> None:
        """Send command to instrument."""
        if self._inst is None:
            raise MercuryiTCError("Not connected. Call open() first.")
        with self._io_lock:
            self._inst.write(cmd)
    
    def query(self, cmd: str) -> str:
        """Send query and return response."""
        if self._inst is None:
            raise MercuryiTCError("Not connected. Call open() first.")
        with self._io_lock:
            response = self._inst.query(cmd).strip()
        
        # Check for error responses (page 121)
        if 'INVALID' in response:
            raise MercuryiTCError(f"Invalid command: {response}")
        if 'NOTFOUND' in response:
            raise MercuryiTCError(f"UID not found: {response}")
        if 'DENIED' in response:
            raise MercuryiTCError(f"Access denied: {response}")
            
        return response
    
    def read(self) -> str:
        """Read response from instrument."""
        if self._inst is None:
            raise MercuryiTCError("Not connected. Call open() first.")
        with self._io_lock:
            return self._inst.read().strip()
    
    # ==================== System Commands ====================
    
    def idn(self) -> str:
        """
        Get instrument identification.
        Returns: String like "OXFORD INSTRUMENTS:MERCURY iTC:TC12345:2.3.0.0"
        """
        return self.query("*IDN?")
    
    def get_system_catalog(self) -> Dict[str, List[str]]:
        """
        Get list of available devices (page 110).
        Returns: Dictionary mapping device UIDs to device types
        """
        response = self.query("READ:SYS:CAT")
        # Parse response like "STAT:DEV:MB0:TEMP:DEV:MB1:HTR:DEV:DB1:TEMP:..."
        devices = {}
        parts = response.split(':')
        i = 0
        while i < len(parts):
            if parts[i] == 'DEV':
                uid = parts[i+1]
                dev_type = parts[i+2]
                if uid not in devices:
                    devices[uid] = []
                devices[uid].append(dev_type)
                i += 3
            else:
                i += 1
        return devices
    
    def set_remote_mode(self, enable: bool = True) -> bool:
        """Enable or disable remote control mode."""
        # This sets the user level (page 110)
        if enable:
            response = self.query("SET:SYS:LOCK:ON")  # Normal remote access
        else:
            response = self.query("SET:SYS:LOCK:OFF")  # Local control
        value = self._parse_value(response)
        return (value == 'VALID')

    def set_user_mode(self, enable: bool = True) -> bool:
        """Enable or disable user control mode."""
        # This sets the user level (page 110)
        if enable:
            response = self.query("SET:SYS:USER:PRIV")  # Local control
        else:
            response = self.query("SET:SYS:USER:NORM")  # Normal user access
        value = self._parse_value(response)
        return (value == 'VALID')
    
    def get_alarms(self) -> str:
        """Get current system alarms."""
        return self.query("READ:SYS:ALRM")
    
    # ==================== Temperature Sensor Commands ====================
    
    def read_temperature(self, uid: str = "MB1.T1") -> float:
        """
        Read temperature from sensor (page 112).
        
        Args:
            uid: Device UID (e.g., "MB1.T1" for motherboard sensor,
                              "DB1.T1" for daughter board sensor)
        Returns: Temperature in Kelvin
        """
        response = self.query(f"READ:DEV:{uid}:TEMP:SIG:TEMP")
        # Response format: "STAT:DEV:MB1.T1:TEMP:SIG:TEMP:4.321K"
        value = self._parse_value(response)
        T_value = round(float(value.rstrip('K')), 3)
        return T_value
    
    def read_sensor_voltage(self, uid: str = "MB1.T1") -> float:
        """Read sensor voltage in volts."""
        response = self.query(f"READ:DEV:{uid}:TEMP:SIG:VOLT")
        value = self._parse_value(response)
        return self._parse_unit_value(value)
    
    def read_sensor_resistance(self, uid: str = "MB1.T1") -> float:
        """Read sensor resistance in ohms."""
        response = self.query(f"READ:DEV:{uid}:TEMP:SIG:RES")
        value = self._parse_value(response)
        return self._parse_unit_value(value)
    
    def configure_sensor(self, uid: str, sensor_type: str, 
                        excitation_type: str = "UNIP",
                        excitation_mag: float = 10.0,
                        cal_file: str = "RuO2.dat") -> bool:
        """
        Configure temperature sensor (page 112).
        
        Args:
            uid: Device UID
            sensor_type: "PTC", "NTC", "DE", "TC", etc.
            excitation_type: "UNIP", "BIP", "SOFT"
            excitation_mag: Excitation current in µA (0-1000)
            cal_file: Calibration file name
        """
        cmd = (f"SET:DEV:{uid}:TEMP:TYPE:{sensor_type}:"
               f"EXCT:TYPE:{excitation_type}:MAG:{excitation_mag}uA:"
               f"CAL:{cal_file}")
        response = self.query(cmd)
        value = self._parse_value(response)
        if value != 'VALID':
            raise MercuryiTCError(f"Failed to configure sensor: {response}")
        return (value == 'VALID')
    
    # ==================== Temperature Control Loop ====================
    
    def set_temp_point(self, uid: str, temp_k: float) -> bool:
        """
        Set temperature setpoint (page 113).
        
        Args:
            uid: Temperature sensor UID
            temp_k: Setpoint temperature in Kelvin
        """
        response = self.query(f"SET:DEV:{uid}:TEMP:LOOP:TSET:{temp_k}")
        value = self._parse_value(response)
        
        success = (value == 'VALID')
        if not success:
            raise MercuryiTCError(f"Failed to set temperature setpoint: {response}")
        return success
    
    def get_temperature_setpoint(self, uid: str) -> float:
        """Get current temperature setpoint."""
        response = self.query(f"READ:DEV:{uid}:TEMP:LOOP:TSET")
        value = self._parse_value(response)
        return float(value.rstrip('K'))
    
    def set_pid_params(self, uid: str, p: float, i: float, d: float) -> bool:
        """
        Set PID parameters (page 113).
        
        Args:
            uid: Temperature sensor UID
            p: Proportional gain
            i: Integral time
            d: Derivative time
        """
        response1 = self.query(f"SET:DEV:{uid}:TEMP:LOOP:P:{p}")
        response2 = self.query(f"SET:DEV:{uid}:TEMP:LOOP:I:{i}")
        response3 = self.query(f"SET:DEV:{uid}:TEMP:LOOP:D:{d}")
        value1 = self._parse_value(response1)
        value2 = self._parse_value(response2)   
        value3 = self._parse_value(response3)
        success = (value1 == 'VALID' and value2 == 'VALID' and value3 == 'VALID')
        if not success:
            raise MercuryiTCError(f"Failed to set PID parameters: {response1}, {response2}, {response3}")
        return success
    
    def get_pid_params(self, uid: str) -> Tuple[float, float, float]:
        """Get PID parameters."""
        p_resp = self.query(f"READ:DEV:{uid}:TEMP:LOOP:P")
        i_resp = self.query(f"READ:DEV:{uid}:TEMP:LOOP:I")
        d_resp = self.query(f"READ:DEV:{uid}:TEMP:LOOP:D")
        
        p = float(self._parse_value(p_resp))
        i = float(self._parse_value(i_resp))
        d = float(self._parse_value(d_resp))
        
        return (p, i, d)
    
    def enable_pid_control(self, uid: str, enable: bool = True) -> bool:
        """Enable or disable automatic PID control."""
        uid = uid
        state = "ON" if enable else "OFF"
        response = self.query(f"SET:DEV:{uid}:TEMP:LOOP:ENAB:{state}")
        value = self._parse_value(response)
        success = (value == 'VALID')
        
        if not success:
            raise MercuryiTCError(f"Failed to set PID control state: {response}")
        
        return success
    
    def get_pid_control_state(self, uid: str) -> bool:
        """Read whether the loop's automatic PID control is currently enabled."""
        response = self.query(f"READ:DEV:{uid}:TEMP:LOOP:ENAB")
        return self._parse_value(response).upper() == "ON"

    def enable_auto_pid_table(self, uid: str, enable: bool = True) -> bool:
        """Enable or disable automatic PID parameters set from table."""
        state = "ON" if enable else "OFF"
        response = self.query(f"SET:DEV:{uid}:TEMP:LOOP:PIDT:{state}")
        value = self._parse_value(response)
        success = (value == 'VALID')
        
        if not success:
            raise MercuryiTCError(f"Failed to set PID table state: {response}")
        
        return success
    
    def assign_heater_to_loop(self, temp_uid: str, heater_uid: str) -> bool:
        """
        Assign a heater to a temperature control loop.
        
        Args:
            temp_uid: Temperature sensor UID
            heater_uid: Heater UID (e.g., "MB0.H1", "DB1.H1")
        """
        response = self.query(f"SET:DEV:{temp_uid}:TEMP:LOOP:HTR:{heater_uid}")
        value = self._parse_value(response)
        success = (value == 'VALID')
        
        if not success:
            raise MercuryiTCError(f"Failed to assign heater to loop: {response}")
        
        return success
    
    # ==================== Heater Commands ====================
    
    def set_heater_voltage(self, uid: str, voltage: float) -> bool:
        """
        Set heater output voltage directly (page 114-115).
        
        Args:
            uid: Heater UID (e.g., "MB0.H1", "DB1.H1")
            voltage: Output voltage in volts (0 to voltage_limit)
            
        Warning:
            This directly sets the heater voltage. Make sure this is within
            the configured voltage limit (VLIM) for safety.
            
        Example:
            # Set voltage limit first for safety
            itc.set_heater_voltage_limit("MB0.H1", 40.0)
            # Then set actual output voltage
            itc.set_heater_voltage("MB0.H1", 10.0)  # Set to 10V
        """
        # Optionally check against voltage limit
        vlim = self.get_heater_voltage_limit(uid)
        if voltage > vlim:
            raise MercuryiTCError(
                f"Requested voltage {voltage}V exceeds limit {vlim}V"
            )
        
        response = self.query(f"SET:DEV:{uid}:HTR:SIG:VOLT:{voltage}")
        value = self._parse_value(response)
        success = (value == 'VALID')
        
        if not success:
            raise MercuryiTCError(f"Failed to set heater voltage: {response}")
        
        return success

    
    def read_heater_power(self, uid: str = "MB0.H1") -> float:
        """
        Read heater power in watts (page 114).
        
        Args:
            uid: Heater UID (e.g., "MB0.H1", "DB1.H1")
        """
        response = self.query(f"READ:DEV:{uid}:HTR:SIG:POWR")
        value = self._parse_value(response)
        return self._parse_unit_value(value)
    
    def read_heater_voltage(self, uid: str = "MB0.H1") -> float:
        """Read heater voltage in volts."""
        response = self.query(f"READ:DEV:{uid}:HTR:SIG:VOLT")
        value = self._parse_value(response)
        return self._parse_unit_value(value)
    
    def read_heater_current(self, uid: str = "MB0.H1") -> float:
        """Read heater current in amps."""
        response = self.query(f"READ:DEV:{uid}:HTR:SIG:CURR")
        value = self._parse_value(response)
        return self._parse_unit_value(value)
    
    def set_heater_voltage_limit(self, uid: str, voltage: float) -> bool:
        """
        Set heater maximum voltage limit (page 41, 114).
        
        Args:
            uid: Heater UID (e.g., "MB0.H1", "DB1.H1")
            voltage: Maximum voltage limit in volts (0-40V)
            
        Example:
            itc.set_heater_voltage_limit("MB0.H1", 25.0)  # Set max voltage to 25V
        """
        success = None
        if not (0 <= voltage <= 40):
            success = False
            raise MercuryiTCError(f"Voltage limit must be between 0 and 40V, got {voltage}V")
        response = self.query(f"SET:DEV:{uid}:HTR:VLIM:{voltage}")
        value = self._parse_value(response)
        success = (value == 'VALID')
        
        if not success:
            raise MercuryiTCError(f"Failed to set voltage limit: {response}")
        
        return success
    
    def get_heater_voltage_limit(self, uid: str = "MB0.H1") -> float:
        """Read heater maximum voltage limit setting."""
        response = self.query(f"READ:DEV:{uid}:HTR:VLIM")
        value = self._parse_value(response)
        return float(value.rstrip('V'))
    
    def set_heater_manual(self, temp_uid: str, percent: float) -> bool:
        """
        Set heater output manually as a percentage of full power (manual control mode).

        HSET belongs to the temperature control LOOP, not to the heater device, so it is
        addressed by the *temperature sensor* UID - the same UID used by TSET / P / I / D /
        ENAB / PIDT above. The previous "SET:DEV:<heater uid>:HTR:SIG:HSET" form mixed the
        two subsystems; it had no callers anywhere in the project, so correcting it here
        cannot regress existing behaviour.
        
        Args:
            temp_uid: Temperature sensor UID owning the loop (e.g. "MB1.T1")
            percent: Heater output as a percentage of full power (0-100)
        """
        response = self.query(f"SET:DEV:{temp_uid}:TEMP:LOOP:HSET:{percent}")
        value = self._parse_value(response)
        success = (value == 'VALID')
        
        if not success:
            raise MercuryiTCError(f"Failed to set heater manual output: {response}")
        
        return success
    
    def get_heater_manual(self, temp_uid: str) -> float:
        """Read the loop's manual heater setting, as a percentage of full power."""
        response = self.query(f"READ:DEV:{temp_uid}:TEMP:LOOP:HSET")
        value = self._parse_value(response)
        return self._parse_unit_value(value)

    # ==================== Auxiliary I/O Commands ====================
    
    def read_gas_flow(self, uid: str = "DB4.G1") -> float:
        """Read gas flow valve position as percentage."""
        response = self.query(f"READ:DEV:{uid}:AUX:SIG:PERC")
        value = self._parse_value(response)
        return float(value.rstrip('%'))
    
    def set_gas_flow_manual(self, uid: str, percent: float) -> bool:
        """Set gas flow valve position manually (0-100%)."""
        response = self.query(f"SET:DEV:{uid}:AUX:SIG:PERC:{percent}")
        value = self._parse_value(response)
        success = (value == 'VALID')
        
        if not success:
            raise MercuryiTCError(f"Failed to set gas flow manual output: {response}")
        
        return success
    
    # ==================== Helper Methods ====================
    
    def _parse_value(self, response: str) -> str:
        """
        Parse value from SCPI response.
        Example: "STAT:DEV:MB1.T1:TEMP:SIG:TEMP:4.321K" -> "4.321K"
        """
        parts = response.split(':')
        # if len(parts) > 0 and parts[-1] == 'VALID': # handle VALID suffix
        #     if len(parts) > 1:
        #         return parts[-2]
            
        if len(parts) > 0:
            return parts[-1]
        return ""
    
    def _parse_unit_value(self, value_str: str) -> float:
        """
        Parse value with SI prefix.
        Examples: "12.345mV" -> 0.012345, "1.5A" -> 1.5
        """
        import re
        match = re.match(r'([+-]?\d+\.?\d*)\s*([nuµmkMG]?)([A-Za-z]*)', value_str)
        if not match:
            return float(value_str)
        
        num = float(match.group(1))
        prefix = match.group(2)
        
        # SI prefixes (page 109-110)
        multipliers = {
            'n': 1e-9,  # nano
            'u': 1e-6,  # micro
            'µ': 1e-6,  # micro
            'm': 1e-3,  # milli
            '': 1.0,
            'k': 1e3,   # kilo
            'M': 1e6,   # mega
            'G': 1e9,   # giga
        }
        
        return num * multipliers.get(prefix, 1.0)


# # ==================== Usage Example ====================

# if __name__ == "__main__":
#     # Example usage
#     itc = MercuryiTC("TCPIP::192.168.1.100::7020::SOCKET")
    
#     try:
#         with itc.connect():
#             print("Connected to:", itc.idn())
            
#             # Get system catalog
#             devices = itc.get_system_catalog()
#             print("Available devices:", devices)
            
#             # Read temperature
#             temp = itc.read_temperature("MB1.T1")
#             print(f"Current temperature: {temp:.3f} K")
            
#             # Set temperature control
#             itc.assign_heater_to_loop("MB1.T1", "MB0.H1")
#             itc.set_pid_params("MB1.T1", p=50, i=20, d=5)
#             itc.set_temperature_setpoint("MB1.T1", 300.0)
#             itc.enable_pid_control("MB1.T1", True)
            
#             # Monitor
#             for i in range(10):
#                 temp = itc.read_temperature("MB1.T1")
#                 power = itc.read_heater_power("MB0.H1")
#                 print(f"T={temp:.3f}K, P={power:.2f}W")
#                 time.sleep(1)
                
#     except MercuryiTCError as e:
#         print(f"Error: {e}")
