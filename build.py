"""
Скрипт сборки exe-файла с помощью PyInstaller.

Использование:
    py build.py

Важно:
- Перед сборкой всегда выполняется compileall.
- Если в проекте есть синтаксические ошибки, сборка EXE останавливается.
- Это защищает от ситуации, когда старый/битый EXE остаётся в dist/ и кажется, будто сборка успешна.
"""

import os
import subprocess
import sys


APP_NAME = "AI-Patcher-Pro"


def run_preflight(project_root: str) -> int:
    """Проверяет синтаксис проекта перед сборкой."""
    print("\n" + "=" * 60)
    print("  Preflight: проверка синтаксиса")
    print("=" * 60)

    result = subprocess.run(
        [sys.executable, "-m", "compileall", "ai_patcher_pro", "tests"],
        cwd=project_root,
    )

    if result.returncode != 0:
        print("\n" + "=" * 60)
        print("  СБОРКА ОСТАНОВЛЕНА")
        print("  В проекте есть синтаксические ошибки.")
        print("  EXE не будет пересобран, чтобы не создать битый файл.")
        print("=" * 60)

    return result.returncode


def ensure_pyinstaller() -> None:
    """Устанавливает PyInstaller, если он отсутствует."""
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller не найден. Устанавливаю pyinstaller>=6.0...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyinstaller>=6.0"]
        )


def build_exe() -> int:
    """Собирает exe-файл AI Patcher Pro."""
    print("=" * 60)
    print("  AI Patcher Pro - Сборка exe")
    print("=" * 60)

    project_root = os.path.dirname(os.path.abspath(__file__))

    preflight_code = run_preflight(project_root)
    if preflight_code != 0:
        return preflight_code

    ensure_pyinstaller()

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        f"--name={APP_NAME}",
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
        exe_path = os.path.join(project_root, "dist", f"{APP_NAME}.exe")
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"\n{'=' * 60}")
            print("  Сборка завершена успешно!")
            print(f"  Файл: {exe_path}")
            print(f"  Размер: {size_mb:.1f} MB")
            print("=" * 60)
        else:
            print("\nСборка завершилась без ошибки, но EXE не найден в dist/.")
            return 1
    else:
        print("\n" + "=" * 60)
        print("  СБОРКА ЗАВЕРШИЛАСЬ С ОШИБКОЙ")
        print("  Старый EXE мог остаться в dist/, но новый успешно не собран.")
        print("=" * 60)

    return result.returncode


if __name__ == "__main__":
    sys.exit(build_exe())
