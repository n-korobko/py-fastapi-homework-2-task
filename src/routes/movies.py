from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from database.session_sqlite import get_sqlite_db as get_db
from database.models import (
    MovieModel,
    CountryModel,
    GenreModel,
    ActorModel,
    LanguageModel,
)
from schemas.movies import (
    MovieListResponseSchema,
    MovieCreateSchema,
    MovieDetailResponseSchema,
    MovieUpdateSchema,
)

router = APIRouter()


async def get_or_create(db: AsyncSession, model, field: str, value: str):
    result = await db.execute(select(model).where(getattr(model, field) == value))
    instance = result.scalar_one_or_none()
    if instance is None:
        instance = model(**{field: value})
        db.add(instance)
        await db.flush()
    return instance


@router.get("/movies/", response_model=MovieListResponseSchema)
async def get_movies(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=20),
):
    total_items = await db.scalar(select(func.count(MovieModel.id)))
    if total_items == 0:
        raise HTTPException(status_code=404, detail="No movies found.")

    total_pages = (total_items + per_page - 1) // per_page
    if page > total_pages:
        raise HTTPException(status_code=404, detail="No movies found.")

    offset = (page - 1) * per_page

    result = await db.execute(
        select(MovieModel)
        .order_by(MovieModel.id.desc())
        .offset(offset)
        .limit(per_page)
    )
    movies = result.scalars().all()

    base = "/theater/movies/"
    prev_page = f"{base}?page={page - 1}&per_page={per_page}" if page > 1 else None
    next_page = f"{base}?page={page + 1}&per_page={per_page}" if page < total_pages else None

    return {
        "movies": movies,
        "prev_page": prev_page,
        "next_page": next_page,
        "total_pages": total_pages,
        "total_items": total_items,
    }


@router.get("/movies/{movie_id}/", response_model=MovieDetailResponseSchema)
async def get_movie(movie_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MovieModel)
        .options(
            joinedload(MovieModel.country),
            joinedload(MovieModel.genres),
            joinedload(MovieModel.actors),
            joinedload(MovieModel.languages),
        )
        .where(MovieModel.id == movie_id)
    )
    movie = result.unique().scalar_one_or_none()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")
    return movie


@router.post("/movies/", response_model=MovieDetailResponseSchema, status_code=201)
async def create_movie(movie: MovieCreateSchema, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MovieModel).where(
            MovieModel.name == movie.name,
            MovieModel.date == movie.date,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"A movie with the name '{movie.name}' and release date '{movie.date}' already exists.",
        )

    country = await get_or_create(db, CountryModel, "code", movie.country)

    new_movie = MovieModel(
        **movie.model_dump(exclude={"genres", "actors", "languages", "country"}),
        country=country,
    )
    db.add(new_movie)
    await db.flush()

    for name in movie.genres:
        new_movie.genres.append(await get_or_create(db, GenreModel, "name", name))
    for name in movie.actors:
        new_movie.actors.append(await get_or_create(db, ActorModel, "name", name))
    for name in movie.languages:
        new_movie.languages.append(await get_or_create(db, LanguageModel, "name", name))

    await db.commit()

    result = await db.execute(
        select(MovieModel)
        .options(
            joinedload(MovieModel.country),
            joinedload(MovieModel.genres),
            joinedload(MovieModel.actors),
            joinedload(MovieModel.languages),
        )
        .where(MovieModel.id == new_movie.id)
    )

    return result.unique().scalar_one()


@router.delete("/movies/{movie_id}/", status_code=204)
async def delete_movie(movie_id: int, db: AsyncSession = Depends(get_db)):
    movie = await db.get(MovieModel, movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")
    await db.delete(movie)
    await db.commit()


@router.patch(
    "/movies/{movie_id}/",
    response_model=MovieDetailResponseSchema,
)
async def update_movie(movie_id: int, movie: MovieUpdateSchema, db: AsyncSession = Depends(get_db)):
    db_movie = await db.get(MovieModel, movie_id)
    if not db_movie:
        raise HTTPException(status_code=404, detail="Movie with the given ID was not found.")

    data = movie.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Invalid input data.")

    for k, v in data.items():
        setattr(db_movie, k, v)

    await db.commit()

    result = await db.execute(
        select(MovieModel)
        .options(
            joinedload(MovieModel.country),
            joinedload(MovieModel.genres),
            joinedload(MovieModel.actors),
            joinedload(MovieModel.languages),
        )
        .where(MovieModel.id == db_movie.id)
    )

    return result.unique().scalar_one()
