"""Configurable context loading with task-specific strategies."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class LoadingStrategy:
    """Defines how to prioritize and load files based on task needs."""

    name: str
    description: str

    # File prioritization rules
    priority_patterns: Dict[str, int] = field(default_factory=dict)
    # filename_pattern -> priority_score

    extension_priorities: Dict[str, int] = field(default_factory=dict)
    # .ext -> priority_score

    # Filters
    required_patterns: List[str] = field(default_factory=list)
    # Must include files matching these patterns

    exclude_patterns: List[str] = field(default_factory=list)
    # Must exclude files matching these patterns

    # Size limits
    max_file_size: int = 100 * 1024  # 100KB default
    max_total_size: int = 500 * 1024  # 500KB total default

    # Modifiers
    depth_penalty: int = 5  # Penalty per directory level
    small_file_boost: int = 10  # Boost for files < 10KB

    # Custom scoring function (optional)
    custom_scorer: Optional[Callable[[Path], int]] = None


# Pre-defined strategies for common tasks
LOADING_STRATEGIES = {
    "agent_evaluation": LoadingStrategy(
        name="agent_evaluation",
        description="Load agent instructions, capabilities, and behavior rules",
        priority_patterns={
            "power.md": 100,
            "claude.md": 100,
            "instructions.md": 90,
            "readme.md": 80,
            "capabilities.md": 85,
            "rules.md": 85,
        },
        extension_priorities={
            ".md": 50,
            ".txt": 45,
            ".rst": 40,
            ".yaml": 30,
            ".yml": 30,
            ".json": 25,
            ".toml": 25,
            ".py": 20,
            ".js": 15,
        },
        required_patterns=["*.md"],  # Must have at least one markdown file
    ),

    "api_analysis": LoadingStrategy(
        name="api_analysis",
        description="Load API definitions, schemas, and configuration",
        priority_patterns={
            "openapi.yaml": 100,
            "swagger.yaml": 100,
            "api.yaml": 90,
            "schema.json": 85,
            "endpoints.md": 80,
        },
        extension_priorities={
            ".yaml": 60,
            ".yml": 60,
            ".json": 55,
            ".md": 40,
            ".py": 30,
            ".js": 30,
        },
    ),

    "code_understanding": LoadingStrategy(
        name="code_understanding",
        description="Load source code, with docs as context",
        priority_patterns={
            "main.py": 90,
            "app.py": 90,
            "index.js": 90,
            "readme.md": 70,
        },
        extension_priorities={
            ".py": 60,
            ".js": 55,
            ".ts": 55,
            ".go": 50,
            ".rs": 50,
            ".java": 45,
            ".md": 40,
            ".yaml": 30,
        },
    ),

    "architecture_review": LoadingStrategy(
        name="architecture_review",
        description="Load architecture docs, design decisions, and diagrams",
        priority_patterns={
            "architecture.md": 100,
            "design.md": 95,
            "adr.md": 90,  # Architecture Decision Records
            "decisions.md": 90,
            "system-design.md": 85,
        },
        extension_priorities={
            ".md": 60,
            ".txt": 50,
            ".mmd": 55,  # Mermaid diagrams
            ".puml": 55,  # PlantUML
            ".drawio": 45,
            ".yaml": 30,
        },
    ),

    "configuration_audit": LoadingStrategy(
        name="configuration_audit",
        description="Load configuration files and settings",
        priority_patterns={
            "config.yaml": 100,
            "settings.yaml": 95,
            ".env.example": 90,
            "defaults.yaml": 85,
        },
        extension_priorities={
            ".yaml": 70,
            ".yml": 70,
            ".toml": 65,
            ".ini": 60,
            ".env": 60,
            ".json": 55,
            ".conf": 50,
            ".md": 30,
        },
    ),

    "generic": LoadingStrategy(
        name="generic",
        description="Balanced loading for general analysis (default)",
        priority_patterns={
            "readme.md": 80,
            "index.md": 75,
            "main.py": 60,
            "config.yaml": 60,
        },
        extension_priorities={
            ".md": 50,
            ".txt": 45,
            ".yaml": 40,
            ".yml": 40,
            ".json": 35,
            ".toml": 35,
            ".py": 30,
            ".js": 25,
            ".ts": 25,
        },
    ),
}


class ContextLoader:
    """Load source context with configurable strategies."""

    def __init__(
        self,
        strategy: str = "generic",
        custom_strategy: Optional[LoadingStrategy] = None
    ):
        """Initialize context loader.

        Args:
            strategy: Name of pre-defined strategy, or "custom"
            custom_strategy: Custom LoadingStrategy if strategy="custom"
        """
        if custom_strategy:
            self.strategy = custom_strategy
        elif strategy in LOADING_STRATEGIES:
            self.strategy = LOADING_STRATEGIES[strategy]
        else:
            logger.warning(f"Unknown strategy '{strategy}', using 'generic'")
            self.strategy = LOADING_STRATEGIES["generic"]

        logger.info(f"Using loading strategy: {self.strategy.name}")

    def load(self, path: str) -> Optional[str]:
        """Load context from path using configured strategy.

        Args:
            path: File or directory path

        Returns:
            Combined context string, or None if nothing loaded
        """
        if not path:
            return None

        path_obj = Path(path)
        if not path_obj.exists():
            logger.warning(f"Path not found: {path}")
            return None

        if path_obj.is_file():
            return self._load_single_file(path_obj)
        elif path_obj.is_dir():
            return self._load_directory(path_obj)

        return None

    def _load_single_file(self, file_path: Path) -> Optional[str]:
        """Load a single file."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            logger.info(f"Loaded {file_path.name} ({len(content)} chars)")
            return content
        except Exception as e:
            logger.warning(f"Failed to load {file_path}: {e}")
            return None

    def _load_directory(self, dir_path: Path) -> Optional[str]:
        """Load files from directory using strategy."""

        # Common directories to skip
        SKIP_DIRS = {
            '.git', '__pycache__', 'node_modules', '.venv', 'venv',
            'build', 'dist', 'target', '.pytest_cache', '.mypy_cache',
            'coverage', '.tox', '.eggs'
        }

        # Known binary extensions to skip
        BINARY_EXTS = {
            '.pyc', '.so', '.dll', '.exe', '.bin', '.obj', '.o',
            '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z',
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico',
            '.pdf', '.mp3', '.mp4', '.avi', '.mov', '.wav',
            '.whl', '.jar', '.class'
        }

        # Collect files with priority scores
        file_scores = []

        for file_path in dir_path.rglob('*'):
            if not file_path.is_file():
                continue

            # Apply filters
            if any(skip in file_path.parts for skip in SKIP_DIRS):
                continue

            if file_path.suffix.lower() in BINARY_EXTS:
                continue

            # Check file size
            try:
                file_size = file_path.stat().st_size
                if file_size > self.strategy.max_file_size:
                    continue
                if file_size == 0:
                    continue
            except Exception:
                continue

            # Check if text file
            if not self._is_text_file(file_path):
                continue

            # Calculate priority score
            score = self._calculate_score(file_path, file_size, dir_path)
            file_scores.append((score, file_path, file_size))

        # Sort by score (highest first)
        file_scores.sort(key=lambda x: x[0], reverse=True)

        # Load files up to max total size
        contents = []
        total_size = 0

        for score, file_path, file_size in file_scores:
            if total_size + file_size > self.strategy.max_total_size:
                logger.info(f"Reached max total size ({self.strategy.max_total_size} bytes)")
                break

            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                if not content.strip():
                    continue

                rel_path = file_path.relative_to(dir_path)
                contents.append(f"# File: {rel_path}\n\n{content}")
                logger.info(f"  - Loaded {rel_path} (score: {score}, {file_size} bytes)")

                total_size += file_size

            except Exception as e:
                logger.warning(f"Failed to load {file_path}: {e}")

        if not contents:
            logger.warning(f"No files loaded from {dir_path}")
            return None

        combined = "\n\n" + "="*80 + "\n\n".join(contents)
        logger.info(f"Loaded {len(contents)} files ({total_size} bytes total)")

        return combined

    def _calculate_score(
        self,
        file_path: Path,
        file_size: int,
        base_path: Path
    ) -> int:
        """Calculate priority score for a file."""
        score = 0

        # Use custom scorer if provided
        if self.strategy.custom_scorer:
            return self.strategy.custom_scorer(file_path)

        # Check priority patterns (filename matches)
        filename_lower = file_path.name.lower()
        for pattern, priority in self.strategy.priority_patterns.items():
            if pattern.lower() == filename_lower:
                score += priority
                break

        # Check extension priorities
        ext_lower = file_path.suffix.lower()
        if ext_lower in self.strategy.extension_priorities:
            score += self.strategy.extension_priorities[ext_lower]

        # Depth penalty (prefer root-level files)
        depth = len(file_path.relative_to(base_path).parts) - 1
        score -= depth * self.strategy.depth_penalty

        # Small file boost
        if file_size < 10 * 1024:
            score += self.strategy.small_file_boost

        return score

    def _is_text_file(self, file_path: Path) -> bool:
        """Check if file is text by looking for null bytes."""
        try:
            with open(file_path, 'rb') as f:
                sample = f.read(512)
            return b'\x00' not in sample
        except Exception:
            return False


def create_custom_strategy(
    name: str,
    description: str,
    **kwargs
) -> LoadingStrategy:
    """Helper to create custom loading strategies.

    Example:
        strategy = create_custom_strategy(
            name="my_task",
            description="Load files for my specific task",
            priority_patterns={"important.md": 100},
            extension_priorities={".py": 70, ".md": 50}
        )
    """
    return LoadingStrategy(
        name=name,
        description=description,
        **kwargs
    )


# Convenience function for backward compatibility
def load_source_context(
    path: str,
    strategy: str = "agent_evaluation"
) -> Optional[str]:
    """Load source context using specified strategy.

    Args:
        path: File or directory path
        strategy: Loading strategy name

    Returns:
        Loaded context string
    """
    loader = ContextLoader(strategy=strategy)
    return loader.load(path)
