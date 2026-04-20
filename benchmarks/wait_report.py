import os
import time

while not os.path.exists('benchmark_final_report.json'):
    time.sleep(5)
    
print("REPORT READY")
