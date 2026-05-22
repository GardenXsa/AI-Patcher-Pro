"""
Скрипт сборки exe-файла с помощью PyInstaller.

Использование:
    python build.py
"""

import subprocess
import sys
import os


def build_exe():
    """Собирает exe-файл AI Patcher Pro."""
    print("=" * 60)
    print("  AI Patcher Pro - Сборка exe")
    print("=" * 60)

    # Проверяем PyInstaller
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Установка PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0"])

    project_root = os.path.dirname(os.path.abspath(__file__))

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=AI-Patcher-Pro",
        "--onefile",
        "--windowed",
        "--noconfirm",
        "--clean",
        f"--add-data={os.path.join(project_root, 'ai_patcher_pro')}:ai_patcher_pro",
        "--hidden-import=PyQt6",
        "--hidden-import=PyQt6.QtWidgets",
        "--hidden-import=PyQt6.QtCore",
        "--hidden-import=PyQt6.QtGui",
        os.path.join(project_root, "ai_patcher_pro", "__main__.py"),
    ]

    print(f"\nКоманда: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=project_root)

    if result.returncode == 0:
        exe_path = os.path.join(project_root, "dist", "AI-Patcher-Pro.exe")
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"\n{'=' * 60}")
            print(f"  Сборка завершена успешно!")
            print(f"  Файл: {exe_path}")
            print(f"  Размер: {size_mb:.1f} MB")
            print(f"{'=' * 60}")
        else:
            print("\nПредупреждение: exe-файл не найден в dist/")
    else:
        print(f"\nОшибка сборки (код {result.returncode})")
        sys.exit(1)


if __name__ == "__main__":
    build_exe()
