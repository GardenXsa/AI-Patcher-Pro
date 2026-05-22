"""
Сканер структуры проекта для генерации контекста ИИ.

Возможности:
- Рекурсивное сканирование директории проекта
- Поддержка .gitignore (автозагрузка + пользовательские паттерны)
- Выборочное сканирование: по расширениям, языкам, размеру, regex
- Пользовательские исключения (glob и regex)
- Нумерация строк в генерируемом контексте
- Оценка токенов с учётом лимитов
- Гибкая генерация контекста: дерево, содержимое, выбор файлов
"""

import os
import re
import fnmatch
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field


# ─────────────────────────── Расширения по языкам ───────────────────────────

LANG_CATEGORIES: Dict[str, str] = {
    # Python
    ".py": "Python", ".pyw": "Python", ".pyi": "Python",
    # JavaScript / TypeScript
    ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".mjs": "JavaScript", ".cjs": "JavaScript",
    # Web
    ".html": "HTML", ".htm": "HTML",
    ".css": "CSS", ".scss": "SCSS", ".sass": "SASS", ".less": "LESS",
    ".vue": "Vue", ".svelte": "Svelte",
    # Java / JVM
    ".java": "Java", ".kt": "Kotlin", ".scala": "Scala", ".groovy": "Groovy",
    # C / C++
    ".c": "C", ".h": "C/C++ Header",
    ".cpp": "C++", ".hpp": "C++ Header", ".cc": "C++", ".cxx": "C++",
    # C#
    ".cs": "C#",
    # Go
    ".go": "Go",
    # Rust
    ".rs": "Rust",
    # Ruby
    ".rb": "Ruby", ".erb": "Ruby Template",
    # PHP
    ".php": "PHP",
    # Swift
    ".swift": "Swift",
    # Shell
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
    ".bat": "Batch", ".ps1": "PowerShell", ".cmd": "Batch",
    # Config / Data
    ".json": "JSON", ".json5": "JSON5",
    ".yaml": "YAML", ".yml": "YAML",
    ".toml": "TOML", ".ini": "INI", ".cfg": "Config",
    ".env": "Environment", ".xml": "XML", ".csv": "CSV",
    ".properties": "Properties",
    # Markup / Docs
    ".md": "Markdown", ".mdx": "MDX",
    ".rst": "reStructuredText", ".txt": "Text", ".tex": "LaTeX",
    ".adoc": "AsciiDoc",
    # Database
    ".sql": "SQL",
    # Docker / CI
    ".dockerfile": "Docker", ".containerfile": "Docker",
    # Other languages
    ".lua": "Lua", ".r": "R", ".dart": "Dart",
    ".ex": "Elixir", ".exs": "Elixir",
    ".erl": "Erlang", ".hrl": "Erlang",
    ".hs": "Haskell", ".ml": "OCaml",
    ".clj": "Clojure", ".cljs": "ClojureScript",
    ".jl": "Julia", ".nim": "Nim",
    ".zig": "Zig", ".v": "V",
    ".proto": "Protocol Buffers", ".graphql": "GraphQL",
    ".tf": "Terraform", ".hcl": "HCL",
}

# Все расширения, которые считаются текстовыми и могут быть прочитаны
TEXT_EXTENSIONS: Set[str] = set(LANG_CATEGORIES.keys()) | {
    ".gitignore", ".editorconfig", ".eslintrc", ".prettierrc",
    ".babelrc", ".stylelintrc", ".npmrc", ".nvmrc",
    ".flake8", ".pylintrc", ".isort.cfg",
    ".makefile", ".cmake",
    ".dockerignore", ".envrc", ".tool-versions",
    ".lock", ".log",
}

# Директории, игнорируемые всегда (без возможности отключения)
HARDCODED_IGNORE_DIRS: Set[str] = {
    "__pycache__", ".git", ".svn", ".hg",
}

# Директории, игнорируемые по умолчанию (можно отключить)
DEFAULT_IGNORE_DIRS: Set[str] = {
    "node_modules", ".venv", "venv", "env",
    ".idea", ".vscode", ".vs",
    "dist", "build", "egg-info", ".eggs", ".tox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "target", "bin", "obj", "out", ".next", ".nuxt",
    "coverage", ".coverage", "htmlcov", ".sass-cache",
    ".gradle", ".mvn", ".cargo", ".cache",
    "vendor", "Pods", ".gradle",
}

# Файлы, игнорируемые по умолчанию (glob-шаблоны)
DEFAULT_IGNORE_PATTERNS: List[str] = [
    "*.pyc", "*.pyo", "*.so", "*.dll", "*.exe", "*.dylib",
    "*.class", "*.jar", "*.war", "*.egg", "*.whl",
    "*.min.js", "*.min.css", "*.map",
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.bmp", "*.ico", "*.svg",
    "*.webp", "*.avif", "*.tiff", "*.tif",
    "*.mp3", "*.mp4", "*.wav", "*.avi", "*.mov", "*.mkv", "*.flac",
    "*.zip", "*.tar", "*.gz", "*.rar", "*.7z", "*.bz2", "*.xz",
    "*.pdf", "*.doc", "*.docx", "*.xls", "*.xlsx", "*.ppt", "*.pptx",
    "*.odt", "*.ods", "*.odp",
    "*.db", "*.sqlite", "*.sqlite3",
    "*.woff", "*.woff2", "*.ttf", "*.eot", "*.otf",
    "*.pkl", "*.pickle", "*.npy", "*.npz",
    ".DS_Store", "Thumbs.db", "desktop.ini",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Cargo.lock", "Gemfile.lock",
]


# ─────────────────────────── .gitignore парсер ───────────────────────────

def parse_gitignore(gitignore_path: str) -> Tuple[List[str], List[str]]:
    """
    Парсит .gitignore и возвращает два списка паттернов.

    Args:
        gitignore_path: Путь к файлу .gitignore.

    Returns:
        Кортеж (dir_patterns, file_patterns) — паттерны для директорий и файлов.
    """
    dir_patterns: List[str] = []
    file_patterns: List[str] = []

    if not os.path.isfile(gitignore_path):
        return dir_patterns, file_patterns

    try:
        with open(gitignore_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                # Пропускаем пустые строки и комментарии
                if not line or line.startswith("#"):
                    continue
                # Убираем отрицание (пока не поддерживаем !pattern)
                if line.startswith("!"):
                    continue
                # Паттерн, заканчивающийся на / — только директории
                if line.endswith("/"):
                    dir_patterns.append(line.rstrip("/"))
                else:
                    file_patterns.append(line)
                    # Если без /, может быть и директорией
                    if "/" not in line and not line.startswith("*"):
                        dir_patterns.append(line)
    except OSError:
        pass

    return dir_patterns, file_patterns


# ─────────────────────────── Data Classes ───────────────────────────

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
    is_text: bool = True


@dataclass
class ScanResult:
    """Результат сканирования проекта."""
    root_path: str
    files: List[FileInfo] = field(default_factory=list)
    total_files: int = 0
    total_lines: int = 0
    total_tokens: int = 0
    total_size: int = 0
    languages: Dict[str, int] = field(default_factory=dict)
    extensions: Dict[str, int] = field(default_factory=dict)
    directory_tree: str = ""
    ignored_dirs: List[str] = field(default_factory=list)
    ignored_patterns: List[str] = field(default_factory=list)
    gitignore_loaded: bool = False


@dataclass
class ScanFilter:
    """Фильтры для выборочного сканирования."""
    # Включаемые расширения (None = все)
    include_extensions: Optional[Set[str]] = None
    # Исключаемые расширения
    exclude_extensions: Optional[Set[str]] = None
    # Включаемые языки (None = все)
    include_languages: Optional[Set[str]] = None
    # Исключаемые языки
    exclude_languages: Optional[Set[str]] = None
    # Минимальный размер файла (байты)
    min_file_size: int = 0
    # Максимальный размер файла (байты)
    max_file_size: int = 512 * 1024
    # Regex для включения путей
    include_regex: Optional[str] = None
    # Regex для исключения путей
    exclude_regex: Optional[str] = None
    # Пользовательские glob-исключения файлов
    user_ignore_patterns: Optional[List[str]] = None
    # Пользовательские исключения директорий
    user_ignore_dirs: Optional[List[str]] = None
    # Использовать .gitignore
    use_gitignore: bool = True
    # Использовать дефолтные игноры
    use_default_ignores: bool = True


@dataclass
class ContextOptions:
    """Опции генерации контекста."""
    include_tree: bool = True
    include_contents: bool = False
    line_numbers: bool = True
    line_number_width: int = 4
    show_file_stats: bool = True
    max_tokens: int = 200_000
    separator: str = "---"
    truncate_marker: str = "... (обрезано по лимиту токенов: {limit})"
    sort_by: str = "path"  # path | size | tokens


# ─────────────────────────── ScannerEngine ───────────────────────────

class ScannerEngine:
    """
    Полнофункциональный движок сканирования структуры проекта.

    Поддерживает:
    - .gitignore (автозагрузка + пользовательские паттерны)
    - Выборочное сканирование: по расширениям, языкам, размеру, regex
    - Пользовательские исключения (glob и regex)
    - Нумерация строк в генерируемом контексте
    - Гибкую генерацию контекста с лимитом токенов
    """

    def __init__(self, max_total_tokens: int = 200_000):
        self.max_total_tokens = max_total_tokens

    def scan(
        self,
        root_path: str,
        scan_filter: Optional[ScanFilter] = None,
    ) -> ScanResult:
        """
        Сканирует директорию проекта с применением фильтров.

        Args:
            root_path: Абсолютный путь к корню проекта.
            scan_filter: Фильтры сканирования (None = дефолтные).

        Returns:
            ScanResult с полной информацией о проекте.
        """
        root_path = os.path.abspath(root_path)
        if not os.path.isdir(root_path):
            return ScanResult(root_path=root_path)

        if scan_filter is None:
            scan_filter = ScanFilter()

        result = ScanResult(root_path=root_path)

        # Собираем игнор-наборы
        ignore_dirs = set(HARDCODED_IGNORE_DIRS)
        ignore_patterns = list(DEFAULT_IGNORE_PATTERNS)

        if scan_filter.use_default_ignores:
            ignore_dirs.update(DEFAULT_IGNORE_DIRS)

        if scan_filter.user_ignore_dirs:
            ignore_dirs.update(scan_filter.user_ignore_dirs)

        if scan_filter.user_ignore_patterns:
            ignore_patterns.extend(scan_filter.user_ignore_patterns)

        # .gitignore
        gitignore_dir_patterns: List[str] = []
        gitignore_file_patterns: List[str] = []

        if scan_filter.use_gitignore:
            gitignore_path = os.path.join(root_path, ".gitignore")
            if os.path.isfile(gitignore_path):
                gitignore_dir_patterns, gitignore_file_patterns = parse_gitignore(gitignore_path)
                ignore_dirs.update(gitignore_dir_patterns)
                ignore_patterns.extend(gitignore_file_patterns)
                result.gitignore_loaded = True

        result.ignored_dirs = sorted(ignore_dirs)
        result.ignored_patterns = sorted(set(ignore_patterns))

        # Компилируем regex фильтры
        include_re = None
        exclude_re = None
        if scan_filter.include_regex:
            try:
                include_re = re.compile(scan_filter.include_regex)
            except re.error:
                pass
        if scan_filter.exclude_regex:
            try:
                exclude_re = re.compile(scan_filter.exclude_regex)
            except re.error:
                pass

        languages: Dict[str, int] = {}
        extensions: Dict[str, int] = {}

        for dirpath, dirnames, filenames in os.walk(root_path):
            # Фильтрация директорий
            dirnames[:] = [
                d for d in dirnames
                if d not in ignore_dirs
                and not d.startswith(".")
                and not any(fnmatch.fnmatch(d, p) for p in gitignore_dir_patterns)
            ]
            # Сортировка для стабильного обхода
            dirnames.sort()

            for filename in sorted(filenames):
                # Проверка glob-шаблонов
                if any(fnmatch.fnmatch(filename, pat) for pat in ignore_patterns):
                    continue

                abs_path = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(abs_path, root_path).replace("\\", "/")

                # .gitignore проверка по полному пути
                if any(fnmatch.fnmatch(rel_path, p) for p in gitignore_file_patterns):
                    continue

                # Regex фильтры
                if include_re and not include_re.search(rel_path):
                    continue
                if exclude_re and exclude_re.search(rel_path):
                    continue

                try:
                    stat = os.stat(abs_path)
                except OSError:
                    continue

                # Фильтр по размеру
                if stat.st_size < scan_filter.min_file_size:
                    continue
                if stat.st_size > scan_filter.max_file_size:
                    continue

                ext = os.path.splitext(filename)[1].lower()
                language = LANG_CATEGORIES.get(ext, "Other")
                is_text = ext in TEXT_EXTENSIONS or (not ext and stat.st_size < 100_000)

                # Фильтр по расширениям
                if scan_filter.include_extensions is not None:
                    if ext not in scan_filter.include_extensions:
                        continue
                if scan_filter.exclude_extensions is not None:
                    if ext in scan_filter.exclude_extensions:
                        continue

                # Фильтр по языкам
                if scan_filter.include_languages is not None:
                    if language not in scan_filter.include_languages:
                        continue
                if scan_filter.exclude_languages is not None:
                    if language in scan_filter.exclude_languages:
                        continue

                # Подсчёт строк и токенов
                line_count = 0
                token_estimate = 0

                if is_text:
                    try:
                        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read()
                        line_count = content.count("\n") + (1 if content else 0)
                        token_estimate = self._estimate_tokens(content)
                    except OSError:
                        is_text = False

                fi = FileInfo(
                    rel_path=rel_path,
                    abs_path=abs_path,
                    extension=ext,
                    language=language,
                    size_bytes=stat.st_size,
                    line_count=line_count,
                    token_estimate=token_estimate,
                    is_text=is_text,
                )

                result.files.append(fi)
                result.total_lines += line_count
                result.total_tokens += token_estimate
                result.total_size += stat.st_size

                languages[language] = languages.get(language, 0) + 1
                extensions[ext] = extensions.get(ext, 0) + 1

        result.total_files = len(result.files)
        result.languages = dict(
            sorted(languages.items(), key=lambda x: x[1], reverse=True)
        )
        result.extensions = dict(
            sorted(extensions.items(), key=lambda x: x[1], reverse=True)
        )
        result.directory_tree = self._build_tree(root_path, result.files)

        return result

    def generate_context(
        self,
        scan_result: ScanResult,
        selected_files: Optional[List[str]] = None,
        options: Optional[ContextOptions] = None,
    ) -> str:
        """
        Генерирует текстовый контекст проекта для промпта ИИ.

        Args:
            scan_result: Результат сканирования.
            selected_files: Список относительных путей файлов.
                Если None — включаются все файлы.
            options: Опции генерации контекста.

        Returns:
            Строка с контекстом проекта (с нумерацией строк).
        """
        if options is None:
            options = ContextOptions()

        limit = options.max_tokens
        parts: List[str] = []
        current_tokens = 0

        # ── Заголовок ──
        header = f"Project: {os.path.basename(scan_result.root_path)}\n"
        header += f"Files: {scan_result.total_files} | "
        header += f"Lines: {scan_result.total_lines} | "
        header += f"Tokens (est): {scan_result.total_tokens:,}\n"

        if scan_result.languages:
            lang_str = ", ".join(
                f"{lang} ({count})" for lang, count in scan_result.languages.items()
            )
            header += f"Languages: {lang_str}\n"

        parts.append(header)
        current_tokens += len(header) // 4

        # ── Дерево файлов ──
        if options.include_tree and scan_result.directory_tree:
            tree_section = f"\n{options.separator} File Tree {options.separator}\n"
            tree_section += scan_result.directory_tree + "\n"
            parts.append(tree_section)
            current_tokens += len(tree_section) // 4

        # ── Содержимое файлов ──
        if options.include_contents:
            files_to_include = scan_result.files
            if selected_files is not None:
                selected_set = set(selected_files)
                files_to_include = [
                    f for f in scan_result.files if f.rel_path in selected_set
                ]

            # Сортировка
            if options.sort_by == "size":
                files_to_include = sorted(files_to_include, key=lambda f: f.size_bytes)
            elif options.sort_by == "tokens":
                files_to_include = sorted(files_to_include, key=lambda f: f.token_estimate)
            else:
                files_to_include = sorted(files_to_include, key=lambda f: f.rel_path)

            for fi in files_to_include:
                if not fi.is_text:
                    continue

                if current_tokens >= limit:
                    marker = options.truncate_marker.format(limit=limit)
                    parts.append(f"\n{marker}\n")
                    break

                try:
                    with open(fi.abs_path, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read()
                except OSError:
                    continue

                # Формируем заголовок файла
                file_header = f"\n{options.separator} {fi.rel_path} "
                if options.show_file_stats:
                    file_header += f"({fi.language}, {fi.line_count} lines, ~{fi.token_estimate:,} tokens) "
                file_header += f"{options.separator}\n"

                # Нумерация строк
                if options.line_numbers and content:
                    numbered_content = self._add_line_numbers(
                        content, width=options.line_number_width
                    )
                else:
                    numbered_content = content

                file_section = file_header + numbered_content + "\n"
                est_tokens = len(file_section) // 4

                if current_tokens + est_tokens > limit:
                    # Обрезаем файл
                    remaining_tokens = limit - current_tokens
                    remaining_chars = remaining_tokens * 4 - len(file_header) - 100
                    if remaining_chars > 200:
                        truncated = content[:remaining_chars]
                        # Обрезаем по последней полной строке
                        last_newline = truncated.rfind("\n")
                        if last_newline > 0:
                            truncated = truncated[:last_newline]

                        if options.line_numbers:
                            truncated = self._add_line_numbers(
                                truncated, width=options.line_number_width
                            )

                        file_section = (
                            file_header + truncated + "\n"
                            + f"... (обрезано: показано {content[:remaining_chars].count(chr(10)) + 1}"
                            f" из {fi.line_count} строк)\n"
                        )
                        parts.append(file_section)
                    break
                else:
                    parts.append(file_section)
                    current_tokens += est_tokens

        return "".join(parts)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """
        Оценивает количество токенов в тексте.

        Использует эвристику: код ~3.5 символа/токен, текст ~4 символа/токен.
        """
        if not text:
            return 0
        # Более точная оценка для кода
        char_count = len(text)
        # Код обычно плотнее, чем обычный текст
        ratio = 3.5 if text.count("\n") > 5 else 4.0
        return max(1, int(char_count / ratio))

    @staticmethod
    def _add_line_numbers(text: str, width: int = 4) -> str:
        """
        Добавляет нумерацию строк к тексту.

        Args:
            text: Исходный текст.
            width: Ширина поля номера строки.

        Returns:
            Текст с номерами строк вида "  1 | content".
        """
        lines = text.split("\n")
        # Убираем последнюю пустую строку если файл кончался на \n
        if lines and lines[-1] == "":
            lines = lines[:-1]

        total = len(lines)
        # Автоматически подгоняем ширину под количество строк
        auto_width = max(width, len(str(total)))

        numbered = []
        for i, line in enumerate(lines, 1):
            numbered.append(f"{i:>{auto_width}} | {line}")
        return "\n".join(numbered)

    @staticmethod
    def _build_tree(root_path: str, files: List[FileInfo]) -> str:
        """Строит текстовое дерево файлов проекта."""
        if not files:
            return ""

        tree: Dict = {}
        for fi in files:
            parts = fi.rel_path.split("/")
            current = tree
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = None

        def _render(node: Dict, prefix: str = "") -> List[str]:
            lines = []
            items = sorted(node.items(), key=lambda x: (x[1] is None, x[0]))
            for idx, (name, value) in enumerate(items):
                last = idx == len(items) - 1
                connector = "└── " if last else "├── "
                if value is None:
                    lines.append(f"{prefix}{connector}{name}")
                else:
                    lines.append(f"{prefix}{connector}{name}/")
                    extension = "    " if last else "│   "
                    lines.extend(_render(value, prefix + extension))
            return lines

        root_name = os.path.basename(root_path) or root_path
        result_lines = [f"{root_name}/"]
        result_lines.extend(_render(tree))
        return "\n".join(result_lines)

    def get_files_by_language(self, scan_result: ScanResult) -> Dict[str, List[FileInfo]]:
        """Группирует файлы по языку программирования."""
        grouped: Dict[str, List[FileInfo]] = {}
        for fi in scan_result.files:
            grouped.setdefault(fi.language, []).append(fi)
        return grouped

    def estimate_tokens_for_files(
        self, file_paths: List[str], root_path: str
    ) -> int:
        """Оценивает количество токенов для указанных файлов."""
        total = 0
        for rel_path in file_paths:
            abs_path = os.path.join(root_path, rel_path)
            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                total += self._estimate_tokens(content)
            except OSError:
                continue
        return total

    @staticmethod
    def get_all_known_extensions() -> Set[str]:
        """Возвращает все известные расширения файлов."""
        return set(LANG_CATEGORIES.keys())

    @staticmethod
    def get_all_known_languages() -> Set[str]:
        """Возвращает все известные языки программирования."""
        return set(LANG_CATEGORIES.values())
