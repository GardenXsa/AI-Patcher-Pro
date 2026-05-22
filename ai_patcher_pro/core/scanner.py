"""
Сканер структуры проекта для генерации контекста ИИ.

Рекурсивно обходит директорию проекта, собирает дерево файлов,
оценивает количество токенов и генерирует компактный контекст
для системного промпта нейросети.
"""

import os
import fnmatch
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


# Расширения файлов по категориям
LANG_CATEGORIES: Dict[str, str] = {
    # Python
    ".py": "Python",
    ".pyw": "Python",
    # JavaScript / TypeScript
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    # Web
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
    ".sass": "CSS",
    ".less": "CSS",
    # Java / JVM
    ".java": "Java",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".groovy": "Groovy",
    # C / C++
    ".c": "C",
    ".h": "C/C++ Header",
    ".cpp": "C++",
    ".hpp": "C++ Header",
    ".cc": "C++",
    ".cxx": "C++",
    # C#
    ".cs": "C#",
    # Go
    ".go": "Go",
    # Rust
    ".rs": "Rust",
    # Ruby
    ".rb": "Ruby",
    # PHP
    ".php": "PHP",
    # Swift
    ".swift": "Swift",
    # Shell
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".bat": "Batch",
    ".ps1": "PowerShell",
    # Config / Data
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".ini": "INI",
    ".cfg": "Config",
    ".env": "Environment",
    ".xml": "XML",
    ".csv": "CSV",
    # Markup / Docs
    ".md": "Markdown",
    ".rst": "reStructuredText",
    ".txt": "Text",
    ".tex": "LaTeX",
    # Database
    ".sql": "SQL",
    # Docker
    ".dockerfile": "Docker",
    # Other
    ".lua": "Lua",
    ".r": "R",
    ".dart": "Dart",
    ".vue": "Vue",
    ".svelte": "Svelte",
}

# Директории, игнорируемые по умолчанию
DEFAULT_IGNORE_DIRS: List[str] = [
    "__pycache__", ".git", ".svn", ".hg", "node_modules",
    ".venv", "venv", "env", ".env", ".idea", ".vscode",
    "dist", "build", "egg-info", ".eggs", ".tox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "target", "bin", "obj", "out", ".next", ".nuxt",
    "coverage", ".coverage", "htmlcov", ".sass-cache",
    ".gradle", ".mvn", ".cargo",
]

# Файлы, игнорируемые по умолчанию (glob-шаблоны)
DEFAULT_IGNORE_FILES: List[str] = [
    "*.pyc", "*.pyo", "*.so", "*.dll", "*.exe", "*.dylib",
    "*.class", "*.jar", "*.war", "*.egg", "*.whl",
    "*.min.js", "*.min.css", "*.map",
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.bmp", "*.ico", "*.svg",
    "*.mp3", "*.mp4", "*.wav", "*.avi", "*.mov",
    "*.zip", "*.tar", "*.gz", "*.rar", "*.7z",
    "*.pdf", "*.doc", "*.docx", "*.xls", "*.xlsx", "*.ppt", "*.pptx",
    "*.db", "*.sqlite", "*.sqlite3",
    ".DS_Store", "Thumbs.db",
]


@dataclass
class FileInfo:
    """Информация о файле в проекте."""
    rel_path: str
    abs_path: str
    extension: str
    language: str
    size_bytes: int
    line_count: int
    token_estimate: int


@dataclass
class ScanResult:
    """Результат сканирования проекта."""
    root_path: str
    files: List[FileInfo] = field(default_factory=list)
    total_files: int = 0
    total_lines: int = 0
    total_tokens: int = 0
    total_size: int = 0
    languages: Dict[str, int] = field(default_factory=dict)  # lang -> file count
    directory_tree: str = ""


class ScannerEngine:
    """
    Движок сканирования структуры проекта.

    Рекурсивно обходит директорию, фильтрует файлы по расширениям,
    подсчитывает строки, оценивает токены и генерирует контекст для ИИ.
    """

    def __init__(
        self,
        ignore_dirs: Optional[List[str]] = None,
        ignore_files: Optional[List[str]] = None,
        max_file_size: int = 512 * 1024,  # 512 KB
        max_total_tokens: int = 200_000,
    ):
        """
        Args:
            ignore_dirs: Список игнорируемых директорий (добавляются к дефолтным).
            ignore_files: Список glob-шаблонов игнорируемых файлов (добавляются к дефолтным).
            max_file_size: Максимальный размер файла для включения (байты).
            max_total_tokens: Максимальное суммарное количество токенов.
        """
        self.ignore_dirs = set(DEFAULT_IGNORE_DIRS)
        if ignore_dirs:
            self.ignore_dirs.update(ignore_dirs)

        self.ignore_patterns = list(DEFAULT_IGNORE_FILES)
        if ignore_files:
            self.ignore_patterns.extend(ignore_files)

        self.max_file_size = max_file_size
        self.max_total_tokens = max_total_tokens

    def scan(self, root_path: str) -> ScanResult:
        """
        Сканирует директорию проекта.

        Args:
            root_path: Абсолютный путь к корню проекта.

        Returns:
            ScanResult с полной информацией о проекте.
        """
        root_path = os.path.abspath(root_path)
        if not os.path.isdir(root_path):
            return ScanResult(root_path=root_path)

        result = ScanResult(root_path=root_path)
        languages: Dict[str, int] = {}

        for dirpath, dirnames, filenames in os.walk(root_path):
            # Фильтрация директорий на месте (os.walk не зайдёт в них)
            dirnames[:] = [
                d for d in dirnames
                if d not in self.ignore_dirs and not d.startswith(".")
            ]

            for filename in filenames:
                # Проверка glob-шаблонов
                if any(fnmatch.fnmatch(filename, pat) for pat in self.ignore_patterns):
                    continue

                abs_path = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(abs_path, root_path)

                # Нормализация пути для Windows
                rel_path = rel_path.replace("\\", "/")

                try:
                    stat = os.stat(abs_path)
                except OSError:
                    continue

                if stat.st_size > self.max_file_size:
                    continue

                ext = os.path.splitext(filename)[1].lower()
                language = LANG_CATEGORIES.get(ext, "Other")

                # Подсчёт строк и оценка токенов
                line_count = 0
                token_estimate = 0
                if ext in LANG_CATEGORIES or ext in (".txt", ".md", ".rst", ".env"):
                    try:
                        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read()
                        line_count = content.count("\n") + 1
                        # Грубая оценка: ~4 символа на токен для кода
                        token_estimate = max(1, len(content) // 4)
                    except OSError:
                        continue

                file_info = FileInfo(
                    rel_path=rel_path,
                    abs_path=abs_path,
                    extension=ext,
                    language=language,
                    size_bytes=stat.st_size,
                    line_count=line_count,
                    token_estimate=token_estimate,
                )

                result.files.append(file_info)
                result.total_lines += line_count
                result.total_tokens += token_estimate
                result.total_size += stat.st_size

                languages[language] = languages.get(language, 0) + 1

        result.total_files = len(result.files)
        result.languages = dict(
            sorted(languages.items(), key=lambda x: x[1], reverse=True)
        )
        result.directory_tree = self._build_tree(root_path, result.files)

        return result

    def generate_context(
        self,
        scan_result: ScanResult,
        include_tree: bool = True,
        include_contents: bool = False,
        selected_files: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Генерирует текстовый контекст проекта для промпта ИИ.

        Args:
            scan_result: Результат сканирования.
            include_tree: Включить дерево файлов.
            include_contents: Включить содержимое файлов.
            selected_files: Список относительных путей файлов для включения.
                Если None — включаются все файлы.
            max_tokens: Ограничение токенов (переопределяет self.max_total_tokens).

        Returns:
            Строка с контекстом проекта.
        """
        limit = max_tokens or self.max_total_tokens
        parts: List[str] = []
        current_tokens = 0

        # Заголовок
        header = (
            f"Project: {os.path.basename(scan_result.root_path)}\n"
            f"Files: {scan_result.total_files} | "
            f"Lines: {scan_result.total_lines} | "
            f"Tokens (est): {scan_result.total_tokens}\n"
        )
        if scan_result.languages:
            lang_str = ", ".join(
                f"{lang} ({count})" for lang, count in scan_result.languages.items()
            )
            header += f"Languages: {lang_str}\n"

        parts.append(header)
        current_tokens += len(header) // 4

        # Дерево файлов
        if include_tree and scan_result.directory_tree:
            tree_section = f"\n--- File Tree ---\n{scan_result.directory_tree}\n"
            parts.append(tree_section)
            current_tokens += len(tree_section) // 4

        # Содержимое файлов
        if include_contents:
            files_to_include = scan_result.files
            if selected_files is not None:
                selected_set = set(selected_files)
                files_to_include = [
                    f for f in scan_result.files if f.rel_path in selected_set
                ]

            # Сортируем по размеру токенов — сначала маленькие
            files_to_include = sorted(files_to_include, key=lambda f: f.token_estimate)

            for fi in files_to_include:
                if current_tokens >= limit:
                    parts.append(f"\n... (обрезано по лимиту токенов: {limit})")
                    break

                try:
                    with open(fi.abs_path, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read()
                except OSError:
                    continue

                file_section = (
                    f"\n--- {fi.rel_path} ({fi.language}, {fi.line_count} lines) ---\n"
                    f"{content}\n"
                )
                est_tokens = len(file_section) // 4

                if current_tokens + est_tokens > limit:
                    # Включаем сколько влезет
                    remaining = limit - current_tokens
                    remaining_chars = remaining * 4
                    if remaining_chars > 200:
                        truncated = content[:remaining_chars - 200]
                        file_section = (
                            f"\n--- {fi.rel_path} ({fi.language}, {fi.line_count} lines) [TRUNCATED] ---\n"
                            f"{truncated}\n... (обрезано)\n"
                        )
                        parts.append(file_section)
                    break

                parts.append(file_section)
                current_tokens += est_tokens

        return "".join(parts)

    @staticmethod
    def _build_tree(root_path: str, files: List[FileInfo]) -> str:
        """
        Строит текстовое дерево файлов проекта.

        Args:
            root_path: Корневой путь проекта.
            files: Список FileInfo.

        Returns:
            Строка с деревом файлов в формате:
            root/
            ├── dir/
            │   ├── file1.py
            │   └── file2.py
            └── file3.py
        """
        if not files:
            return ""

        # Строим вложенную структуру
        tree: Dict = {}
        for fi in files:
            parts = fi.rel_path.split("/")
            current = tree
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = None  # None = файл

        def _render(node: Dict, prefix: str = "", is_last: bool = True) -> List[str]:
            lines = []
            items = sorted(node.items(), key=lambda x: (x[1] is None, x[0]))
            for idx, (name, value) in enumerate(items):
                last = idx == len(items) - 1
                connector = "└── " if last else "├── "
                if value is None:
                    # Файл
                    lines.append(f"{prefix}{connector}{name}")
                else:
                    # Директория
                    lines.append(f"{prefix}{connector}{name}/")
                    extension = "    " if last else "│   "
                    lines.extend(_render(value, prefix + extension, last))
            return lines

        root_name = os.path.basename(root_path) or root_path
        result_lines = [f"{root_name}/"]
        result_lines.extend(_render(tree))

        return "\n".join(result_lines)

    def get_files_by_language(self, scan_result: ScanResult) -> Dict[str, List[FileInfo]]:
        """
        Группирует файлы по языку программирования.

        Args:
            scan_result: Результат сканирования.

        Returns:
            Словарь {язык: [список FileInfo]}.
        """
        grouped: Dict[str, List[FileInfo]] = {}
        for fi in scan_result.files:
            grouped.setdefault(fi.language, []).append(fi)
        return grouped

    def estimate_tokens_for_files(
        self, file_paths: List[str], root_path: str
    ) -> int:
        """
        Оценивает количество токенов для указанных файлов.

        Args:
            file_paths: Список относительных путей файлов.
            root_path: Корневой путь проекта.

        Returns:
            Оценка общего количества токенов.
        """
        total = 0
        for rel_path in file_paths:
            abs_path = os.path.join(root_path, rel_path)
            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                total += max(1, len(content) // 4)
            except OSError:
                continue
        return total
