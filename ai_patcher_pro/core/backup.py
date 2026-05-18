"""
Система бэкапов (Машина Времени).

Создаёт бэкапы файлов перед применением патчей,
позволяет просматривать и восстанавливать предыдущие версии.
"""

import os
import json
import shutil
import datetime
from typing import List, Dict, Optional


BACKUP_DIR = ".ai_backups"


class BackupManager:
    """Менеджер бэкапов: создание, просмотр, восстановление."""

    def __init__(self, workspace: str, backup_dir: str = BACKUP_DIR):
        """
        Args:
            workspace: Рабочая директория проекта.
            backup_dir: Имя директории для бэкапов (относительно workspace).
        """
        self.workspace = workspace
        self.backup_dir = os.path.join(workspace, backup_dir)

    def init_backup_dir(self) -> None:
        """Создаёт директорию бэкапов и .gitignore."""
        os.makedirs(self.backup_dir, exist_ok=True)
        git_ignore = os.path.join(self.backup_dir, ".gitignore")
        if not os.path.exists(git_ignore):
            with open(git_ignore, "w", encoding="utf-8") as f:
                f.write("*\n")

    def create_backup(self, patch_name: str, affected_files: Dict[str, str]) -> str:
        """
        Создаёт бэкап затронутых файлов.

        Args:
            patch_name: Имя патча для метаданных.
            affected_files: Словарь {абсолютный_путь: содержимое_в_кэше}
                файлов, которые будут изменены.

        Returns:
            Путь к созданному бэкапу.
        """
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        b_path = os.path.join(self.backup_dir, f"backup_{ts}")
        os.makedirs(b_path, exist_ok=True)

        # Сохраняем метаданные
        meta_path = os.path.join(b_path, "patch_meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(
                {"timestamp": ts, "patch_name": patch_name}, f, ensure_ascii=False
            )

        # Копируем файлы
        for abs_p in affected_files:
            if os.path.exists(abs_p):
                rel = os.path.relpath(abs_p, self.workspace)
                bp = os.path.join(b_path, rel)
                os.makedirs(os.path.dirname(bp), exist_ok=True)
                shutil.copy2(abs_p, bp)

        return b_path

    def list_backups(self) -> List[str]:
        """
        Возвращает список имён бэкапов (от новых к старым).

        Returns:
            Список имён директорий бэкапов.
        """
        if not os.path.exists(self.backup_dir):
            return []

        items = os.listdir(self.backup_dir)
        dirs = [
            d
            for d in items
            if os.path.isdir(os.path.join(self.backup_dir, d))
        ]
        return sorted(dirs, reverse=True)

    def get_backup_meta(self, backup_name: str) -> Optional[Dict]:
        """
        Читает метаданные бэкапа.

        Args:
            backup_name: Имя директории бэкапа.

        Returns:
            Словарь метаданных или None при ошибке.
        """
        meta_path = os.path.join(self.backup_dir, backup_name, "patch_meta.json")
        if not os.path.exists(meta_path):
            return None

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def get_backup_path(self, backup_name: str) -> str:
        """Возвращает полный путь к директории бэкапа."""
        return os.path.join(self.backup_dir, backup_name)

    def restore_backup(self, backup_path: str, workspace: str) -> None:
        """
        Восстанавливает файлы из бэкапа.

        Args:
            backup_path: Полный путь к директории бэкапа.
            workspace: Рабочая директория для восстановления.
        """
        for root, _, files in os.walk(backup_path):
            for f in files:
                if f == "patch_meta.json":
                    continue
                src = os.path.join(root, f)
                dst = os.path.join(workspace, os.path.relpath(src, backup_path))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
