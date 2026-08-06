# test_linear_stage.py
from thorlabs_LinearStage import LinearStage

SERIAL = "73844983"  # Replace with your controller serial
CHAN = 1

stage = LinearStage(SERIAL, CHAN, poll_ms=250)
try:
    hp = stage.get_homing_params()
    print(f"Homing Velocity: {hp.Velocity}, Direction: {hp.Direction}")

    stage.home(60000)

    print("Velocity(before):", stage.get_velocity())
    stage.set_velocity(50.0, 500.0)
    print("Velocity(after):", stage.get_velocity())

    stage.move_to(10.0, 60000)
    print("Position:", stage.position())

    stage.move_by(-2.0, 60000)
    print("Position:", stage.position())
    
    stage.move_by(5.0, 60000)
    print("Position:", stage.position())
finally:
    stage.close()
    print("Device closed.")