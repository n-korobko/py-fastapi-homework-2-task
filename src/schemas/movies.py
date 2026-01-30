from datetime import date, timedelta
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, field_validator
from database.models import MovieStatusEnum


class MovieBase(BaseModel):
    name: str = Field(max_length=255)
    date: date
    score: float = Field(ge=0, le=100)
    overview: Optional[str] = None
    status: MovieStatusEnum
    budget: float = Field(ge=0)
    revenue: float = Field(ge=0)

    @field_validator("date")
    @classmethod
    def check_future_date(cls, v: date) -> date:
        if v > date.today() + timedelta(days=365):
            raise ValueError("The date must not be more than one year in the future.")
        return v


class MovieShortResponse(BaseModel):
    id: int
    name: str
    date: date
    score: float
    overview: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class MovieListResponseSchema(BaseModel):
    movies: List[MovieShortResponse]
    prev_page: Optional[str]
    next_page: Optional[str]
    total_pages: int
    total_items: int

    model_config = ConfigDict(from_attributes=True)


class MovieCreateSchema(MovieBase):
    country: str = Field(max_length=3)
    genres: List[str]
    actors: List[str]
    languages: List[str]


class MovieCountrySchema(BaseModel):
    id: int
    code: str
    name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AdditionalInfoSchema(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class MovieGenresSchema(AdditionalInfoSchema):
    pass


class MovieActorsSchema(AdditionalInfoSchema):
    pass


class MovieLanguagesSchema(AdditionalInfoSchema):
    pass


class MovieDetailResponseSchema(MovieBase):
    id: int
    country: MovieCountrySchema
    genres: List[MovieGenresSchema]
    actors: List[MovieActorsSchema]
    languages: List[MovieLanguagesSchema]

    model_config = ConfigDict(from_attributes=True)


class MovieUpdateSchema(BaseModel):
    name: Optional[str]
    date: Optional[date]
    score: Optional[float]
    overview: Optional[str]
    status: Optional[MovieStatusEnum]
    budget: Optional[float]
    revenue: Optional[float]
