# test_kdc101.py
from thorlabs_RotaryStage import RotaryStage

SERIAL = "27256338"  # replace with your KDC101 serial

stage = RotaryStage(SERIAL, poll_ms = 250, use_sim = True)
try:
    stage.home()
    print("Velocity(before):", stage.get_velocity())
    stage.set_velocity(5.0, 10.0)
    print("Velocity(after): ", stage.get_velocity())

    stage.move_to(359.0)
    print("Pos:", stage.position())

    stage.move_by(2.0)
    print("Pos:", stage.position())
finally:
    stage.close()
    print("Device closed.")
