from thorlabs_PM100D import PM100D

resources = PM100D.list_resources_with_idn()
if not resources:
    raise RuntimeError("No Thorlabs PM100D was found by the TLPM driver.")

for index, (resource, identity) in enumerate(resources):
    print(index, resource, identity)

if len(resources) != 1:
    raise RuntimeError("More than one PM100D was found; select its resource explicitly.")

resource = resources[0][0]
print("Using PM100D resource:", resource)

pm = PM100D(
    resource,
    timeout_ms=10000,
    query_delay_s=0.1,
    retry_count=2,
    retry_delay_s=0.2,
)
with pm.connect():
    print("ID:", pm.idn())
    print("Wavelength (nm):", pm.get_wavelength_nm())
    print("Power (W):", pm.measure_power())
