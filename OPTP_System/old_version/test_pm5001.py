# test_pm500_min.py
# Minimal test for Newport PM500-C using the PM500 class (no GUI, no argparse).

from newport_PM500 import PM500, PM500Error
import time    

# ======== CONFIGURE HERE ========
RESOURCE   = "GPIB0::4::INSTR"   # e.g. "GPIB0::1::INSTR" or "ASRL3::INSTR"
AXIS       = "X"                 # "X", "Y", "Z", "A", "B", or "C"

USE_COMOPT3 = False              # True if using RS-232 (recommended); False for GPIB

V_MM_S     = 10.0                 # high-speed velocity (mm/s)
ACC_MM_S2  = 100.0                # high-speed acceleration (mm/s^2)
DEC_MM_S2  = 100.0                # high-speed deceleration (mm/s^2)

TARGET_ABS_MM = -10         # absolute position to go (mm)
REL_MOVE_MM   = -3           # then move relative by this (mm)
MOVE_NO = 10
TIMEOUT_S  = 60.0                # wait_done timeout (s)
Wait_time = 2               # wait time between moves (s)
# =================================

try:
    with PM500(RESOURCE).connect() as pm:
        print("[Connect] OK")
        print("[ID]      ", pm.idn())

        if USE_COMOPT3:
            pm.comopt3()
            print("[COMOPT3] echo + done responses enabled")

        # Make sure motor is enabled
        pm.motor_on(AXIS)
        
        
        # auto zero calibration
        # pm.motor_auto_zero(AXIS)
        # pm.wait_done(AXIS, timeout=TIMEOUT_S)
        # print(f"[AutoZero] {AXIS} axis auto zeroed.")
        # pm.save_to_nvm(AXIS)
        # print(f"[SaveNVM]  {AXIS} axis settings saved to NVM.")
        
        # # Move to fiducial center
        # pm.fiducial_center(AXIS)
        # pm.wait_done(AXIS, timeout=TIMEOUT_S)
        # print(f"[Fiducial] {AXIS} axis set to center position.")
        

        # # Set high-speed parameters
        # pm.set_high_speed(AXIS, v_mm_s=V_MM_S, accel_mm_s2=ACC_MM_S2, decel_mm_s2=DEC_MM_S2)
        # print(f"[Speed]   V={V_MM_S} mm/s  ACC={ACC_MM_S2}  DEC={DEC_MM_S2}")

        # Read current position
        pos0 = pm.read_pos(AXIS)
        pm.wait_done(AXIS, timeout=TIMEOUT_S)
        print(f"[Pos]     before move: {pos0:.6f} um")

        # Absolute move
        print(f"[MoveAbs] {TARGET_ABS_MM:.3f} mm ...")
        pm.go_and_wait_abs(AXIS, TARGET_ABS_MM, timeout=TIMEOUT_S)
        pos1 = pm.read_pos(AXIS)
        print(f"[Pos]     after abs:   {pos1:.6f} um")

        # Relative move
        print(f"[MoveRel] {REL_MOVE_MM:+.3f} um ...")
        for i in range(1, MOVE_NO + 1):
            pm.go_and_wait_rel(AXIS, REL_MOVE_MM, timeout=TIMEOUT_S)
            #time.sleep(Wait_time)   # wait time in unit of seconds
            pos2 = pm.read_pos(AXIS)
            print(f"[Pos]     after rel:   {pos2:.6f} mm")

        print("[Done] test completed.")

except PM500Error as e:
    print("PM500Error:", e)
except Exception as e:
    print("Unexpected error:", e)
