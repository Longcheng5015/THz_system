# test_dds220_multichannel.py
"""
测试 dds220_stage.LinearStage 在 BBD202 上多通道是否能正常工作：
1. 先单独测试 ch1
2. 再单独测试 ch2
3. 最后同时连 ch1 + ch2，看能否共存、都能 home 和移动
"""

import time

from proj_tools import ProjectTools
ProjectTools.inject_inst_libs(__file__)

from thorlabs_LinearStage_BBD202 import LinearStage

SERIAL = "73844983"   # 换成你的控制器序列号


def test_single_channel(chan: int):
    print(f"\n===== 单通道测试：channel {chan} =====")
    stage = LinearStage(
        SERIAL,
        channel=chan,
        poll_ms=250,
        enable_state_guard=True,
        enable_wait_timeout_ms=5000,
        enable_retry_count=2,
        enable_poll_interval_ms=100,
    )
    try:
        print(f"[CH{chan}] 开始 homing ...")
        stage.home_with_guard(60000)
        print(f"[CH{chan}] Homed, 当前位置: {stage.position():.4f} mm")

        v_before = stage.get_velocity()
        print(f"[CH{chan}] 速度参数(之前): vmax={v_before[0]:.3f} mm/s, acc={v_before[1]:.3f} mm/s^2")

        # 这里的速度可以按你实际需求改小一点
        stage.set_velocity(5.0, 20.0)
        v_after = stage.get_velocity()
        print(f"[CH{chan}] 速度参数(之后): vmax={v_after[0]:.3f} mm/s, acc={v_after[1]:.3f} mm/s^2")

        # 小幅移动，避免撞行程，按你实际行程自己调整
        print(f"[CH{chan}] 相对移动 +1.0 mm ...")
        stage.move_by(1.0, 60000)
        print(f"[CH{chan}] 当前位置: {stage.position():.4f} mm")

        print(f"[CH{chan}] 相对移动 -1.0 mm ...")
        stage.move_by(-1.0, 60000)
        print(f"[CH{chan}] 当前位置: {stage.position():.4f} mm")

    finally:
        stage.close()
        print(f"[CH{chan}] 已关闭。")


def test_two_channels():
    print("\n===== 双通道同时测试：channel 1 + channel 2 =====")
    stage1 = LinearStage(
        SERIAL,
        channel=1,
        poll_ms=250,
        enable_state_guard=True,
        enable_wait_timeout_ms=5000,
        enable_retry_count=2,
        enable_poll_interval_ms=100,
    )
    stage2 = LinearStage(
        SERIAL,
        channel=2,
        poll_ms=250,
        enable_state_guard=True,
        enable_wait_timeout_ms=5000,
        enable_retry_count=2,
        enable_poll_interval_ms=100,
    )

    try:
        print("[BOTH] 开始同时 homing ch1 和 ch2 ...")
        stage1.home_with_guard(60000)
        stage2.home_with_guard(60000)
        print(f"[BOTH] Homed 后位置：ch1={stage1.position():.4f} mm, ch2={stage2.position():.4f} mm")

        print("[BOTH] ch1 相对移动 +0.5 mm，ch2 相对移动 -0.5 mm ...")
        stage1.move_by(0.5, 60000)
        stage2.move_by(-0.5, 60000)
        print(f"[BOTH] 移动后位置：ch1={stage1.position():.4f} mm, ch2={stage2.position():.4f} mm")

    finally:
        stage1.close()
        stage2.close()
        print("[BOTH] 两个通道都已关闭。")


if __name__ == "__main__":
    # 1) 单独测 ch1
    test_single_channel(1)

    # 2) 单独测 ch2
    test_single_channel(2)

    # 3) 同时测 ch1 + ch2（关键）
    test_two_channels()
