from thorlabs_MFF02 import FilterFlipper


serial = "37872830"  # TODO: replace with your MFF01 serial

flipper = FilterFlipper(serial)
try:
    print("Connected:", serial)
    print("Position:", flipper.position())
    print("Upright:", flipper.is_upright())
    print(f"Status bits: 0x{flipper.get_status_bits():X}")
    input("Press Enter to toggle...")
    target = flipper.toggle()
    print("Moved to:", target)
    print("Position:", flipper.position())
    desired = input("Move to position (1/2, blank to skip): ").strip()
    if desired in ("1", "2"):
        flipper.move_to(int(desired))
        print("Moved to:", desired)
        print("Position:", flipper.position())
finally:
    flipper.close()
