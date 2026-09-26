# test_pi_stage.py
"""
测试 physik_E861.LinearStage 驱动 PI N-565.360 (E-861 控制器) 是否正常：
1. 只读信息：IDN、轴号、stage 型号、行程限位、是否已参考、当前位置、速度
2. 参考(reference)功能：home_with_guard()，已参考的轴会跳过参考移动
3. 移动功能：相对 +/-step、绝对回到起点，每步核对实际到位位置

用法（默认只做只读检查，不会让台子动）：
    python test_pi_stage.py           # 只读信息
    python test_pi_stage.py --move    # 只读信息 + 参考 + 移动测试
    python test_pi_stage.py --move --force-ref   # 额外强制重新参考(台子会跑到参考开关)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # 可从任意目录运行本脚本
from physik_E861 import LinearStage

SERIAL = "0119001337"   # E-861 控制器序列号，印在机箱上
AXIS = "1"              # GCS 轴号
STEP_MM = 0.1           # 移动测试的步长，按实际光路空间调整


def test_info(stage: LinearStage):
    print("\n===== 只读信息 =====")
    print(f"行程限位  : {stage.min_pos} .. {stage.max_pos} mm")
    print(f"是否已参考: {stage.is_homed()}")
    print(f"当前位置  : {stage.position():.6f} mm")
    vel, acc = stage.get_velocity()
    print(f"速度/加速度: {vel:.3f} mm/s, {acc:.3f} mm/s^2")


def test_reference(stage: LinearStage, force: bool = False):
    print("\n===== 参考(reference)测试 =====")
    if force:
        # 绕过“已参考就跳过”的逻辑，强制重新跑一次 FRF
        print("强制重新参考，台子会移动到参考开关 ...")
        stage._dev.FRF(stage.axis)
        from pipython.pitools import waitonreferencing
        waitonreferencing(stage._dev, axes=stage.axis, timeout=60)
        print(f"参考完成，当前位置: {stage.position():.6f} mm")
    else:
        stage.home_with_guard(60000)
    print(f"is_homed = {stage.is_homed()}, 位置 = {stage.position():.6f} mm")


def test_move(stage: LinearStage):
    print("\n===== 移动测试 =====")
    start = stage.position()
    print(f"起点: {start:.6f} mm")

    stage.move_by(STEP_MM)
    print(f"相对 +{STEP_MM} mm -> {stage.position():.6f} mm (期望 {start + STEP_MM:.6f})")

    stage.move_by(-2 * STEP_MM)
    print(f"相对 -{2 * STEP_MM} mm -> {stage.position():.6f} mm (期望 {start - STEP_MM:.6f})")

    stage.move_to(start)
    print(f"绝对回到起点   -> {stage.position():.6f} mm (期望 {start:.6f})")

    # 超程保护应当在发指令之前就拦下来
    try:
        stage.move_to(stage.max_pos + 1.0)
        print("超程保护失效：超出行程的目标没有被拒绝！")
    except ValueError as e:
        print(f"超程保护正常: {e}")


if __name__ == "__main__":
    do_move = "--move" in sys.argv
    force_ref = "--force-ref" in sys.argv

    # 连接时不自动参考，交给 test_reference 显式测试
    stage = LinearStage(SERIAL, axis=AXIS, servo_on=True, reference_if_needed=False)
    try:
        test_info(stage)
        if do_move:
            test_reference(stage, force=force_ref)
            test_move(stage)
        else:
            print("\n(只读模式，未做任何移动。加 --move 参数可测试参考和移动功能)")
    finally:
        stage.close()
