from __future__ import annotations
import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

try:
    from pydantic import ConfigDict
except Exception:
    ConfigDict = None


class _BaseSchema(BaseModel):
    if ConfigDict:
        model_config = ConfigDict(from_attributes=True)
    else:
        class Config:
            orm_mode = True


class GenreSchema(_BaseSchema):
    id: int
    name: str


class ActorSchema(_BaseSchema):
    id: int
    name: str


class LanguageSchema(_BaseSchema):
    id: int
    name: str


class CountrySchema(_BaseSchema):
    id: int
    code: str
    name: Optional[str] = None


class MovieListItemSchema(_BaseSchema):
    id: int
    name: str
    date: datetime.date
    score: float
    overview: str


class MovieListResponseSchema(_BaseSchema):
    movies: List[MovieListItemSchema]
    prev_page: Optional[str]
    next_page: Optional[str]
    total_pages: int
    total_items: int


class MovieDetailResponseSchema(_BaseSchema):
    id: int
    name: str
    date: datetime.date
    score: float
    overview: str
    status: str
    budget: float
    revenue: float
    country: CountrySchema
    genres: List[GenreSchema]
    actors: List[ActorSchema]
    languages: List[LanguageSchema]


class MovieCreateRequestSchema(_BaseSchema):
    name: str = Field(max_length=255)
    date: datetime.date
    score: float = Field(ge=0, le=100)
    overview: str
    status: str
    budget: float = Field(ge=0)
    revenue: float = Field(ge=0)
    country: str
    genres: List[str]
    actors: List[str]
    languages: List[str]


class MovieUpdateRequestSchema(_BaseSchema):
    name: Optional[str] = None
    date: Optional[datetime.date] = None
    score: Optional[float] = None
    overview: Optional[str] = None
    status: Optional[str] = None
    budget: Optional[float] = None
    revenue: Optional[float] = None


class MessageResponseSchema(_BaseSchema):
    detail: str
