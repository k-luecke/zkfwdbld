import psutil
import time

def monitor_site_vitals(duration_seconds=10):
    print(f"Monitoring Beelink SER5 Vitals for {duration_seconds}s...")
    for _ in range(duration_seconds):
        cpu_percent = psutil.cpu_percent(interval=1)
        mem_percent = psutil.virtual_memory().percent
        # Note: Thermal sensors vary by driver; this is a generic check
        print(f"Load: {cpu_percent}% | RAM: {mem_percent}%")

if __name__ == "__main__":
    monitor_site_vitals()
