# quick_test_sr830_min.py
# 极简：连通/读参数/设参数/再读/循环读数值

import time
from stanford_SR830 import SR830, SR830Error

# ======= 修改这里 =======
RESOURCE    = "GPIB0::10::INSTR"  # 你的 GPIB 资源地址

# 是否同时设置参考源/频率（如不需要就设为 False）
SET_REF     = False
REF_MODE    = 1          # 1=internal, 0=external
REF_FREQ_HZ = 1000.0     # 仅当 REF_MODE=1 时有效

# 要设置的索引（见 SR830 手册）
SENS_IDX    = 10         # 灵敏度索引 0..26（例：10 ≈ 5 µV）
TC_IDX      = 10         # 时间常数索引 0..19（例：12 = 10 s）
SRAT_IDX    = 12         # 采样率索引 0..14（例：12 = 256 Hz）

READ_TIMES  = 3          # 循环读取次数
INTERVAL_S  = 2        # 读取间隔（秒）
# ========================

try:
    with SR830(RESOURCE).connect() as sr:
        time.sleep(0.2)  # wait device to be ready for next command
        
        print("Connected:", sr.idn())
        sr.reset_buffers()  # 清除状态寄存器
        time.sleep(1)  # wait device to be ready for next command
        sr.clear_status()  # 清除错误寄存器
        time.sleep(1)  # wait device to be ready for next command

        # ---- 设置前：读取并显示当前参数 ----
        print("\n[Before]")
        time.sleep(0.2)  # wait device to be ready for next command
        si = sr.get_sensitivity_index()
        time.sleep(0.2)  # wait device to be ready for next command
        sv = sr.get_sensitivity_volts()
        time.sleep(0.2)  # wait device to be ready for next command
        ti = sr.get_time_constant_index()
        time.sleep(0.1)  # wait device to be ready for next command
        ts = sr.get_time_constant_seconds()
        time.sleep(0.1)  # wait device to be ready for next command
        ri = sr.get_sample_rate_index()
        time.sleep(0.1)  # wait device to be ready for next command
        rv = sr.get_sample_rate()
        print(f"Sensitivity : idx {si}  ~ {sv:.6g} V")
        print(f"Time const. : idx {ti}  ~ {ts:.6g} s")
        if rv == "Trigger":
            print(f"Sample rate : idx {ri}  (Trigger)")
        else:
            print(f"Sample rate : idx {ri}  ~ {float(rv):.6g} Hz")

        # ---- 可选：设置参考源/频率 ----
        if SET_REF:
            sr.set_ref_mode(REF_MODE)
            print("Set ref mode ->", sr.get_ref_mode())
            if REF_MODE == 1:
                sr.set_ref_freq(REF_FREQ_HZ)
                print("Set ref freq ->", sr.get_ref_freq(), "Hz")

        # ---- 设置灵敏度/时间常数/采样率 ----
        sr.set_sensitivity(SENS_IDX)
        sr.set_time_constant(TC_IDX)
        sr.set_sample_rate(SRAT_IDX)

        # ---- 设置后：再次读取并显示 ----
        print("\n[After]")
        si = sr.get_sensitivity_index()
        sv = sr.get_sensitivity_volts()
        ti = sr.get_time_constant_index()
        ts = sr.get_time_constant_seconds()
        ri = sr.get_sample_rate_index()
        rv = sr.get_sample_rate()
        print(f"Sensitivity : idx {si}  ~ {sv:.6g} V")
        print(f"Time const. : idx {ti}  ~ {ts:.6g} s")
        if rv == "Trigger":
            print(f"Sample rate : idx {ri}  (Trigger)")
        else:
            print(f"Sample rate : idx {ri}  ~ {float(rv):.6g} Hz")

        # ---- 循环读取数值 ----
        print("\nReading X/Y/R/θ ...")
        for i in range(1, READ_TIMES + 1):
            x = sr.get_x()
            y = sr.get_y()
            r = sr.get_r()
            th = sr.get_theta()
            all = sr.snap(1, 2, 3, 4)  # 一次性读 X,Y,R,θ
            print(f"[{i}/{READ_TIMES}] X={x:.6g} V, Y={y:.6g} V, R={r:.6g} V, θ={th:.3f}°")
            time.sleep(INTERVAL_S)   # wait time in unit of seconds

        # ----（可选）一次 SNAP：同时读 X、Y、Ref Freq ----
        snap_vals = sr.snap(1, 2, 9)
        print("\nSNAP? 1,2,3 -> [X, Y, RefFreq]:", snap_vals)

        print("\nDone.")

except SR830Error as e:
    print("SR830Error:", e)
except Exception as e:
    print("Unexpected error:", e)
