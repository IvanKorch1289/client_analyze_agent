"""
File operation tools (read-only, safe).

All file operations are restricted to MCP_FILES_ROOT for security.
"""

import os
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator

from app.shared.config import settings
from app.shared.exceptions import ValidationError
from app.shared.logger import get_logger
from app.shared.security import sanitize_filename

logger = get_logger(__name__)

# File operation limits (security)
MCP_FILES_ROOT = Path(os.getenv("MCP_FILES_ROOT", settings.REPORTS_DIR)).resolve()
MCP_MAX_FILE_BYTES = int(os.getenv("MCP_MAX_FILE_BYTES", "1048576"))  # 1MB


def _resolve_under_root(relative_path: str) -> Path:
    """
    Safely resolve path relative to MCP_FILES_ROOT.

    Protection against path traversal: final path must be inside MCP_FILES_ROOT.

    Args:
        relative_path: Relative path

    Returns:
        Resolved absolute path

    Raises:
        ValidationError: If path is outside root
    """
    rel = (relative_path or "").lstrip("/").strip()
    p = (MCP_FILES_ROOT / rel).resolve()

    if MCP_FILES_ROOT not in p.parents and p != MCP_FILES_ROOT:
        raise ValidationError(
            "Path is outside MCP_FILES_ROOT",
            details={"path": str(p), "root": str(MCP_FILES_ROOT)},
        )

    return p


# ============================================================================
# Request Models
# ============================================================================


class ReadFileRequest(BaseModel):
    """Request to read a file."""

    path: str = Field(..., max_length=500, description="Relative file path")

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate path doesn't contain dangerous patterns."""
        if ".." in v or v.startswith("/"):
            raise ValueError("Path must be relative and not contain '..'")
        return v.strip()


class ListFilesRequest(BaseModel):
    """Request to list files in directory."""

    path: str = Field(default="", max_length=500, description="Relative directory path")
    pattern: str = Field(default="*", max_length=50, description="Glob pattern")

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate path."""
        if ".." in v:
            raise ValueError("Path must not contain '..'")
        return v.strip()


# ============================================================================
# Tool Functions
# ============================================================================


async def read_file_tool(request: ReadFileRequest) -> Dict[str, Any]:
    """
    Read file contents (read-only, safe).

    Only files inside MCP_FILES_ROOT can be read.
    File size is limited to MCP_MAX_FILE_BYTES.

    Args:
        request: Validated request

    Returns:
        File contents and metadata

    Raises:
        ValidationError: If path is invalid or file too large
        FileNotFoundError: If file doesn't exist

    Examples:
        >>> result = await read_file_tool(
        ...     ReadFileRequest(path="reports/report_123.json")
        ... )
        >>> result['content']
        '{"client": "...", "risk_score": 67}'
    """
    logger.log_action("read_file_start", path=request.path)

    try:
        file_path = _resolve_under_root(request.path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {request.path}")

        if not file_path.is_file():
            raise ValidationError(f"Path is not a file: {request.path}")

        file_size = file_path.stat().st_size

        if file_size > MCP_MAX_FILE_BYTES:
            raise ValidationError(
                f"File too large: {file_size} bytes (max: {MCP_MAX_FILE_BYTES})",
                details={
                    "file_size": file_size,
                    "max_size": MCP_MAX_FILE_BYTES,
                    "path": request.path,
                },
            )

        # Read file
        content = file_path.read_text(encoding="utf-8")

        logger.log_action(
            "read_file_success",
            path=request.path,
            size_bytes=file_size,
        )

        return {
            "path": request.path,
            "content": content,
            "size_bytes": file_size,
            "encoding": "utf-8",
        }

    except Exception as e:
        logger.error("read_file_failed", exc=e, path=request.path)
        raise


async def list_files_tool(request: ListFilesRequest) -> Dict[str, Any]:
    """
    List files in directory (read-only, safe).

    Only directories inside MCP_FILES_ROOT can be listed.

    Args:
        request: Validated request

    Returns:
        List of files with metadata

    Raises:
        ValidationError: If path is invalid
        FileNotFoundError: If directory doesn't exist

    Examples:
        >>> result = await list_files_tool(
        ...     ListFilesRequest(path="reports", pattern="*.json")
        ... )
        >>> result['files']
        [
            {'name': 'report_123.json', 'size': 5432},
            {'name': 'report_456.json', 'size': 7890}
        ]
    """
    logger.log_action("list_files_start", path=request.path, pattern=request.pattern)

    try:
        dir_path = _resolve_under_root(request.path)

        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {request.path}")

        if not dir_path.is_dir():
            raise ValidationError(f"Path is not a directory: {request.path}")

        # List files matching pattern
        files = []
        for file_path in dir_path.glob(request.pattern):
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "path": str(file_path.relative_to(MCP_FILES_ROOT)),
                    "size_bytes": stat.st_size,
                    "modified": stat.st_mtime,
                })

        logger.log_action(
            "list_files_success",
            path=request.path,
            pattern=request.pattern,
            count=len(files),
        )

        return {
            "path": request.path,
            "pattern": request.pattern,
            "files": files,
            "count": len(files),
        }

    except Exception as e:
        logger.error("list_files_failed", exc=e, path=request.path)
        raise


__all__ = [
    "ReadFileRequest",
    "ListFilesRequest",
    "read_file_tool",
    "list_files_tool",
]

