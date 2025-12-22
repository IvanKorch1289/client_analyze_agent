"""
Pagination helpers for API responses.

Provides reusable pagination models and utilities.
"""

from typing import Any, Generic, List, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Pagination parameters for list endpoints."""
    
    limit: int = Field(default=50, ge=1, le=500, description="Number of items per page")
    offset: int = Field(default=0, ge=0, description="Number of items to skip")


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Generic paginated response model.
    
    Usage:
    ```python
    class UserResponse(BaseModel):
        id: int
        name: str
    
    @router.get("/users", response_model=PaginatedResponse[UserResponse])
    async def list_users(pagination: PaginationParams = Depends()):
        users = get_users(limit=pagination.limit, offset=pagination.offset)
        return PaginatedResponse(
            items=users,
            total=count_users(),
            limit=pagination.limit,
            offset=pagination.offset
        )
    ```
    """
    
    items: List[T] = Field(..., description="List of items for current page")
    total: int = Field(..., ge=0, description="Total number of items across all pages")
    limit: int = Field(..., ge=1, description="Items per page")
    offset: int = Field(..., ge=0, description="Number of items skipped")
    has_more: bool = Field(..., description="Whether there are more items available")
    
    def __init__(self, **data):
        # Calculate has_more if not provided
        if "has_more" not in data:
            items_count = len(data.get("items", []))
            total = data.get("total", 0)
            offset = data.get("offset", 0)
            data["has_more"] = (offset + items_count) < total
        
        super().__init__(**data)
    
    @property
    def current_page(self) -> int:
        """Calculate current page number (1-based)."""
        if self.limit == 0:
            return 1
        return (self.offset // self.limit) + 1
    
    @property
    def total_pages(self) -> int:
        """Calculate total number of pages."""
        if self.limit == 0:
            return 1
        return (self.total + self.limit - 1) // self.limit


class CursorPaginationParams(BaseModel):
    """Cursor-based pagination parameters."""
    
    limit: int = Field(default=50, ge=1, le=500)
    cursor: str | None = Field(default=None, description="Cursor for next page")


class CursorPaginatedResponse(BaseModel, Generic[T]):
    """
    Cursor-based paginated response.
    
    More efficient for large datasets than offset pagination.
    """
    
    items: List[T]
    next_cursor: str | None = Field(None, description="Cursor for next page")
    has_more: bool = Field(..., description="Whether there are more items")
    limit: int


def paginate_list(
    items: List[Any],
    total: int,
    limit: int,
    offset: int
) -> dict:
    """
    Helper to create paginated response dict.
    
    Args:
        items: List of items for current page
        total: Total count of all items
        limit: Items per page
        offset: Items to skip
        
    Returns:
        Dict with pagination metadata
    """
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + len(items)) < total,
    }


__all__ = [
    "PaginationParams",
    "PaginatedResponse",
    "CursorPaginationParams",
    "CursorPaginatedResponse",
    "paginate_list",
]
