import datetime
from typing import Optional, Type
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from database import get_db
from database.models import (
    MovieModel,
    CountryModel,
    GenreModel,
    ActorModel,
    LanguageModel,
    MovieStatusEnum,
)

from schemas.movies import (
    MovieListResponseSchema,
    MovieDetailResponseSchema,
    MovieCreateRequestSchema,
    MovieUpdateRequestSchema,
    MessageResponseSchema,
)

router = APIRouter(prefix="/movies")


def _is_valid_status(value: str) -> bool:
    return value in {e.value for e in MovieStatusEnum}


def _validate_create_payload(payload: MovieCreateRequestSchema) -> Optional[str]:
    today = datetime.date.today()

    if payload.date > today + datetime.timedelta(days=365):
        return "Invalid input data."

    if not _is_valid_status(payload.status):
        return "Invalid input data."

    return None


def _validate_update_payload(payload: MovieUpdateRequestSchema) -> Optional[str]:
    if all(
        getattr(payload, field) is None
        for field in ("name", "date", "score", "overview", "status", "budget", "revenue")
    ):
        return "Invalid input data."

    if payload.date:
        today = datetime.date.today()
        if payload.date > today + datetime.timedelta(days=365):
            return "Invalid input data."

    if payload.status and not _is_valid_status(payload.status):
        return "Invalid input data."

    return None


async def _get_or_create_by_unique_str(
    db: AsyncSession,
    model: Type,
    field_name: str,
    value: str,
):
    stmt = select(model).where(getattr(model, field_name) == value)
    result = await db.execute(stmt)
    obj = result.scalars().first()
    if obj:
        return obj

    obj = model(**{field_name: value})
    db.add(obj)
    await db.flush()
    return obj


async def _get_or_create_country(db: AsyncSession, code: str) -> CountryModel:
    stmt = select(CountryModel).where(CountryModel.code == code)
    result = await db.execute(stmt)
    country = result.scalars().first()
    if country:
        return country

    country = CountryModel(code=code, name=None)
    db.add(country)
    await db.flush()
    return country


@router.get("/", response_model=MovieListResponseSchema)
async def get_movies(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    total_items = await db.scalar(select(func.count(MovieModel.id))) or 0
    if total_items == 0:
        raise HTTPException(status_code=404, detail="No movies found.")

    offset = (page - 1) * per_page

    stmt = (
        select(MovieModel)
        .order_by(MovieModel.id.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await db.execute(stmt)
    movies = result.scalars().all()

    if not movies:
        raise HTTPException(status_code=404, detail="No movies found.")

    total_pages = (total_items + per_page - 1) // per_page
    base_path = "/theater/movies/"

    return {
        "movies": movies,
        "prev_page": f"{base_path}?page={page - 1}&per_page={per_page}" if page > 1 else None,
        "next_page": f"{base_path}?page={page + 1}&per_page={per_page}" if page < total_pages else None,
        "total_pages": total_pages,
        "total_items": total_items,
    }


@router.get("/{movie_id}/", response_model=MovieDetailResponseSchema)
async def get_movie_by_id(movie_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(MovieModel)
        .where(MovieModel.id == movie_id)
        .options(
            joinedload(MovieModel.country),
            joinedload(MovieModel.genres),
            joinedload(MovieModel.actors),
            joinedload(MovieModel.languages),
        )
    )
    result = await db.execute(stmt)
    movie = result.scalars().first()

    if not movie:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")

    return movie


@router.post("/", status_code=201, response_model=MovieDetailResponseSchema)
async def create_movie(payload: MovieCreateRequestSchema, db: AsyncSession = Depends(get_db)):
    err = _validate_create_payload(payload)
    if err:
        raise HTTPException(status_code=400, detail=err)

    try:
        country = await _get_or_create_country(db, payload.country)

        genres = [
            await _get_or_create_by_unique_str(db, GenreModel, "name", g)
            for g in payload.genres
        ]
        actors = [
            await _get_or_create_by_unique_str(db, ActorModel, "name", a)
            for a in payload.actors
        ]
        languages = [
            await _get_or_create_by_unique_str(db, LanguageModel, "name", l)
            for l in payload.languages
        ]

        movie = MovieModel(
            name=payload.name,
            date=payload.date,
            score=payload.score,
            overview=payload.overview,
            status=MovieStatusEnum(payload.status),
            budget=payload.budget,
            revenue=payload.revenue,
            country=country,
            genres=genres,
            actors=actors,
            languages=languages,
        )

        db.add(movie)
        await db.commit()

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"A movie with the name '{payload.name}' and release date '{payload.date}' already exists.",
        )

    stmt = (
        select(MovieModel)
        .where(MovieModel.id == movie.id)
        .options(
            joinedload(MovieModel.country),
            joinedload(MovieModel.genres),
            joinedload(MovieModel.actors),
            joinedload(MovieModel.languages),
        )
    )
    result = await db.execute(stmt)
    return result.scalars().first()


@router.delete("/{movie_id}/", status_code=204)
async def delete_movie(movie_id: int, db: AsyncSession = Depends(get_db)):
    movie = await db.get(MovieModel, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")

    await db.delete(movie)
    await db.commit()
    return None


@router.patch("/{movie_id}/", response_model=MessageResponseSchema)
async def update_movie(
    movie_id: int,
    payload: MovieUpdateRequestSchema,
    db: AsyncSession = Depends(get_db),
):
    movie = await db.get(MovieModel, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")

    err = _validate_update_payload(payload)
    if err:
        raise HTTPException(status_code=400, detail=err)

    for field, value in payload.model_dump(exclude_none=True).items():
        if field == "status":
            value = MovieStatusEnum(value)
        setattr(movie, field, value)

    await db.commit()
    return {"detail": "Movie updated successfully."}
