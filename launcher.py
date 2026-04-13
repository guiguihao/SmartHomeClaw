#!/usr/bin/env python3
"""
Launcher Script / 统一启动器
Reads config/services.yaml and starts all enabled services.
"""
import subprocess
import yaml
import sys
import os

# 彻底禁用 __pycache__ 生成（对当前进程及所有子进程生效）
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import time
import socket
import signal
from pathlib import Path

ROOT = Path(__file__).parent
os.chdir(ROOT)

CONFIG_PATH = ROOT / "config" / "services.yaml"
PID_FILE = ROOT / "logs" / "launcher.pids"

def is_port_in_use(port: int) -> bool:
    """Check if a local port is already occupied."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def get_pids_from_port(port: int) -> list[int]:
    """Get PIDs of processes using a specific port (Darwin/Linux)."""
    try:
        output = subprocess.check_output(["lsof", "-t", f"-i:{port}"]).decode().strip()
        if output:
            return [int(pid) for pid in output.split("\n")]
    except Exception:
        pass
    return []

def stop_services():
    """Find and kill processes from previous run."""
    print("🛑 Stopping existing services...")
    
    # 1. Kill by port 8000
    pids = get_pids_from_port(8000)
    
    # 2. Kill by recorded PIDs
    if PID_FILE.exists():
        with open(PID_FILE, "r") as f:
            for line in f:
                try:
                    pids.append(int(line.strip()))
                except ValueError:
                    continue
    # 1. 首先尝试通过 PID 文件优雅停止
    if PID_FILE.exists():
        try:
            with open(PID_FILE, "r") as f:
                pids = f.read().splitlines()
            for pid in pids:
                try:
                    # 尝试杀掉整个进程组
                    os.killpg(int(pid), signal.SIGTERM)
                    print(f"  -> Sent SIGTERM to process group {pid}")
                except ProcessLookupError:
                    pass
                except Exception as e:
                    print(f"  -> Error stopping {pid}: {e}")
            PID_FILE.unlink()
        except Exception:
            pass

    # 2. 强力清理模式：根据进程特征词进行二次清理，防止残留
    # 搜索包含模块路径的关键进程名
    keywords = ["src.server.main", "services.feishu.main", "launcher.py start"]
    
    import subprocess
    try:
        # 给 2 秒缓冲时间让 SIGTERM 生效
        time.sleep(1.5)
        for kw in keywords:
            # 使用 pkill -9 强制清理所有符合特征的 Python 进程
            # -f 表示匹配完整的命令行
            subprocess.run(["pkill", "-9", "-f", kw], stderr=subprocess.DEVNULL)
        print("  -> Cleanup complete (Forcefully killed residuals).")
    except Exception:
        pass
    if PID_FILE.exists():
        PID_FILE.unlink()
    
    time.sleep(1) # Wait for cleanup

def load_services():
    if not CONFIG_PATH.exists():
        print(f"❌ config/services.yaml not found at {CONFIG_PATH}")
        sys.exit(1)
    
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f).get("services", {})

def start_services():
    # Safety Check: Avoid duplicated launches
    if is_port_in_use(8000):
        print("\n⚠️  [Conflict] Port 8000 is already in use!")
        print("   Please run 'python launcher.py restart' if you want to reboot.")
        sys.exit(1)

    services = load_services()
    processes = []
    
    print("🚀 Starting SmartHome Services...")
    
    # Ensure logs dir exists
    (ROOT / "logs").mkdir(exist_ok=True)

    # 所有服务的输出都重定向到这个文件
    log_file = open(ROOT / "logs" / "serve.out", "a", encoding="utf-8")

    # 1. 首先启动 agent_core
    if services.get("agent_core", {}).get("enabled"):
        cmd_parts = services["agent_core"]["command"].split()
        # 兼容性修复：将 'python' 替换为当前系统的 Python 解释器路径
        if cmd_parts[0] == "python":
            cmd_parts[0] = sys.executable
            
        print(f"  -> Starting agent_core: {' '.join(cmd_parts)}")
        p = subprocess.Popen(cmd_parts, preexec_fn=os.setsid, stdout=log_file, stderr=log_file)
        processes.append(("agent_core", p))
        time.sleep(2) 
        
    # 2. 启动其他服务
    for name, svc in services.items():
        if name == "agent_core": continue
        if svc.get("enabled"):
            cmd_parts = svc["command"].split()
            # 兼容性修复：将 'python' 替换为当前系统的 Python 解释器路径
            if cmd_parts[0] == "python":
                cmd_parts[0] = sys.executable
                
            print(f"  -> Starting {name}: {' '.join(cmd_parts)}")
            p = subprocess.Popen(cmd_parts, preexec_fn=os.setsid, stdout=log_file, stderr=log_file)
            processes.append((name, p))

    if not processes:
        print("❌ No services enabled.")
        return

    # Record PIDs
    with open(PID_FILE, "w") as f:
        for name, p in processes:
            f.write(f"{p.pid}\n")

    print("\n✅ All services started. Press Ctrl+C to stop all.")
    
    try:
        while True:
            for name, p in processes:
                if p.poll() is not None:
                    print(f"⚠️ Service '{name}' exited with code {p.returncode}")
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        for name, p in processes:
            p.terminate()
        if PID_FILE.exists(): PID_FILE.unlink()

def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "start"
    
    if arg == "stop":
        stop_services()
    elif arg == "restart":
        stop_services()
        start_services()
    elif arg in ("start", "up"):
        start_services()
    else:
        print("Usage: python launcher.py [start|stop|restart]")

if __name__ == "__main__":
    main()
