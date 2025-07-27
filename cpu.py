import os
import psutil

#print number of physical cores
physical_cores = os.cpu_count()
print(f"Cpu core: {physical_cores or 'Unable to detect how many cores'}")


#print logical & physical cores
logical_core = psutil.cpu_count(logical = True)
phys_core = psutil.cpu_count(logical= False)

print(f"""Logical cores (threads): {logical_core}""")
print(f"""Physical cores: {phys_core}""")
