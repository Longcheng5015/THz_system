from inst_tools import InstrumentTools

resources = InstrumentTools.list_visa_resources()
print(resources)


info = InstrumentTools.list_visa_resource_info()
for item in info:
    print(item)
