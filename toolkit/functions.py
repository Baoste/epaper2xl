import os, time
import subprocess
import re

def search_existing_display_scripts():
    output = subprocess.check_output(["ps", "aux"], text=True)
    current_pid = os.getpid()

    for line in output.splitlines():
        # 过滤出 display_*.py 的进程
        if re.search(r"python.*display_.*\.py", line):
            parts = line.split()
            pid = int(parts[1])
            if pid != current_pid:
                return pid
            
    return None
        

def kill_existing_display_scripts(logger):
    try:
        pid = search_existing_display_scripts()
        if pid:
            logger.info(f"检测到旧进程：{pid}")
            os.system(f"sudo kill {pid}")
            time.sleep(5)
            logger.info(f"已结束进程 PID {pid}")
    except Exception as e:
        logger.error(f"杀进程时出错: {e}")
