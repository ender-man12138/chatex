import subprocess
import sys
import os

def main():
    # 获取 exe 所在目录（用户解压后的项目根目录）
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 虚拟环境中的 python（优先用 pythonw，避免弹出控制台）
    python_exe = os.path.join(base_dir, "venv", "Scripts", "python.exe")
    pythonw_exe = os.path.join(base_dir, "venv", "Scripts", "pythonw.exe")
    if os.path.exists(pythonw_exe):
        python_exe = pythonw_exe
    main_py = os.path.join(base_dir, "main.py")
    
    # 检查文件是否存在
    if not os.path.exists(python_exe):
        print(f"[错误] 未找到虚拟环境: {python_exe}")
        input("按回车键退出...")
        sys.exit(1)
    
    if not os.path.exists(main_py):
        print(f"[错误] 未找到主程序: {main_py}")
        input("按回车键退出...")
        sys.exit(1)
    
    # 设置环境变量，确保 venv 环境正确
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = os.path.join(base_dir, "venv")
    env["PATH"] = os.path.join(base_dir, "venv", "Scripts") + os.pathsep + env.get("PATH", "")
    
    # 启动 main.py，不等待，隐藏控制台窗口
    creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    process = subprocess.Popen(
        [python_exe, main_py],
        cwd=base_dir,
        env=env,
        creationflags=creationflags
    )
    print(f"[启动器] 已启动 main.py，PID: {process.pid}")
    print(f"[启动器] 启动器即将退出...")
    sys.exit(0)

if __name__ == "__main__":
    main()
