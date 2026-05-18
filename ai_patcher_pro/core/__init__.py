"""Ядро приложения: поиск, парсинг, патчинг, бэкапы, безопасность."""

from ai_patcher_pro.core.search import SearchEngine
from ai_patcher_pro.core.json_parser import extract_all_json
from ai_patcher_pro.core.patcher import apply_single_operation, replace_first_occurrence
from ai_patcher_pro.core.backup import BackupManager
from ai_patcher_pro.core.security import secure_path_join
from ai_patcher_pro.core.processor import ProcessorThread

__all__ = [
    "SearchEngine",
    "extract_all_json",
    "apply_single_operation",
    "replace_first_occurrence",
    "BackupManager",
    "secure_path_join",
    "ProcessorThread",
]
