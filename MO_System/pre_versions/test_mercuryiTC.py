# test_mercury_simple.py
"""
Mercury iTC 测试 - 使用USB连接（显示为COM3/ASRL3）
执行 10 次测试循环
"""

from Oxford_mercuryiTC import MercuryiTC, MercuryiTCError  
import time 

# 您的设备地址（从NI-MAX中看到的）
RESOURCE = "ASRL3::INSTR"  # COM3

print("=" * 50)
print("Mercury iTC 测试 - 10 次循环")
print("=" * 50)

# 执行 10 次测试

print(f"\n{'='*50}")
print(f"测试")
print(f"{'='*50}")

    # 连接设备
print("\n[1] 连接设备...")
itc = MercuryiTC(RESOURCE, timeout_ms=5000)
itc.open()
print("✓ 连接成功")


itc.query('*IDN?')
time.sleep(0.1)  # 给设备一点响应时间
while True:
    try:
        byte = itc.read_bytes(1)
        print(repr(byte))  # 打印每个字节的十六进制表示
    except:
        break
    
    


    # try:
       
        
    #     #time.sleep(0.5)  # Wait a moment after connection

    #     # 读取设备信息
    #     print("\n[2] 读取设备信息...")
    #     idn = itc.idn()
    #     print(f"设备: {idn}")
        
        
    #     device = itc.get_system_catalog()
    #     print("系统目录:")  
    #     for uid, types in device.items():
    #         print(f"  {uid}: {', '.join(types)}")
            
        
    #     response = itc.set_heater_voltage_limit("MB0.H1", 22)
    #     heater_new = itc.get_heater_voltage_limit("MB0.H1")
    #     print(f"New Heater 电压限制: {heater_new:.3f} V")
        
        
    #     # 读取温度
    #     print("\n[3] 读取温度...")
    #     temp = itc.read_temperature("MB1.T1")
    #     print(f"温度: {temp:.3f} K")
        
# 设置温度设定点
# response = itc.set_temp_point("MB1.T1", 50.0)
# setpoint = itc.get_temperature_setpoint("MB1.T1")
#response = itc.enable_pid_control("MB1.T1", False)
response = itc.enable_auto_pid_table("MB1.T1", True)
print(f"PID 控制启用: {response}")
        
        
        
    # except Exception as e:
    #     print(f"\n❌ 第 {iteration} 次测试错误: {e}")
    #     try:
    #         itc.close()
    #     except:
    #         pass
    
    # # 在下一次测试前等待
    # if iteration < 10:
    #     print(f"\n等待 2 秒后开始下一次测试...")
    #     time.sleep(2)
    
success = itc.set_heater_voltage("MB0.H1",  0.0)
print(f"PID 控制启用: {success}")

time.sleep(1)
# 关闭连接
print("\n[4] 关闭连接...")
itc.close()

        
        
print("\n" + "=" * 50)
print("所有测试完成")
print("=" * 50)
