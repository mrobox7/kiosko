from pydantic import BaseModel, Field


class MenuItem(BaseModel):
    id: int
    name: str
    description: str
    price: float
    tags: list[str]
    category: str
    available: bool


class MenuFilters(BaseModel):
    category: str | None = None
    tags_any: list[str] = Field(default_factory=list)
    tags_all: list[str] = Field(default_factory=list)
    exclude_tags: list[str] = Field(default_factory=list)
    max_price: float | None = None
    available_only: bool = True
