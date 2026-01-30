from math import ceil
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    MovieDetailSchema,
    MovieUpdateSchema,
)

router = APIRouter(prefix="/movies")


# -----------------------
# helpers
# -----------------------

def _page_link(page: int, per_page: int) -> str:
    # ВАЖЛИВО: тести очікують лінки без "/api/v1"
    # саме так: "/theater/movies/?page=2&per_page=10"
    return f"/theater/movies/?page={page}&per_page={per_page}"


async def _get_movie_or_404(db: AsyncSession, movie_id: int) -> MovieModel:
    stmt = (
        select(MovieModel)
        .where(MovieModel.id == movie_id)
        .options(
            selectinload(MovieModel.country),
            selectinload(MovieModel.genres),
            selectinload(MovieModel.actors),
            selectinload(MovieModel.languages),
        )
    )
    movie = await db.scalar(stmt)
    if not movie:
        raise HTTPException(
            status_code=404,
            detail="Movie with the given ID was not found.",
        )
    return movie


# -----------------------
# GET /movies/
# -----------------------

@router.get("/", response_model=MovieListResponseSchema)
async def get_movies(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    total_items = await db.scalar(select(func.count(MovieModel.id)))

    if not total_items or total_items == 0:
        raise HTTPException(status_code=404, detail="No movies found.")

    total_pages = ceil(total_items / per_page)

    if page > total_pages:
        raise HTTPException(status_code=404, detail="No movies found.")

    stmt = (
        select(MovieModel)
        .options(selectinload(MovieModel.country))
        .order_by(MovieModel.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(stmt)
    movies = result.scalars().all()

    # Якщо сторінка пуста — теж 404 (по ТЗ)
    if not movies:
        raise HTTPException(status_code=404, detail="No movies found.")

    prev_page = _page_link(page - 1, per_page) if page > 1 else None
    next_page = _page_link(page + 1, per_page) if page < total_pages else None

    return MovieListResponseSchema(
        movies=movies,                 # schema повинна брати поля id/name/date/score/overview
        prev_page=prev_page,
        next_page=next_page,
        total_pages=total_pages,
        total_items=total_items,
    )


# -----------------------
# GET /movies/{movie_id}/
# -----------------------

@router.get("/{movie_id}/", response_model=MovieDetailSchema)
async def get_movie_by_id(
    movie_id: int,
    db: AsyncSession = Depends(get_db),
):
    movie = await _get_movie_or_404(db, movie_id)
    return movie


# -----------------------
# POST /movies/
# -----------------------

@router.post("/", response_model=MovieDetailSchema, status_code=status.HTTP_201_CREATED)
async def create_movie(
    movie_data: MovieCreateSchema,
    db: AsyncSession = Depends(get_db),
):
    # validation: date не більше ніж +1 рік (як у ТЗ)
    if movie_data.date > date.today() + timedelta(days=365):
        raise HTTPException(status_code=400, detail="Invalid input data.")

    # duplicate check (до INSERT, щоб не ловити sqlite IntegrityError)
    existing = await db.scalar(
        select(MovieModel).where(
            MovieModel.name == movie_data.name,
            MovieModel.date == movie_data.date,
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=(
                f"A movie with the name '{movie_data.name}' and release date "
                f"'{movie_data.date}' already exists."
            ),
        )

    # country: code
    country = await db.scalar(
        select(CountryModel).where(CountryModel.code == movie_data.country)
    )
    if not country:
        country = CountryModel(code=movie_data.country)
        db.add(country)
        await db.flush()

    movie = MovieModel(
        name=movie_data.name,
        date=movie_data.date,
        score=movie_data.score,
        overview=movie_data.overview,
        status=movie_data.status,
        budget=movie_data.budget,
        revenue=movie_data.revenue,
        country=country,
    )
    db.add(movie)
    await db.flush()

    # genres
    for g_name in movie_data.genres:
        genre = await db.scalar(select(GenreModel).where(GenreModel.name == g_name))
        if not genre:
            genre = GenreModel(name=g_name)
            db.add(genre)
            await db.flush()
        movie.genres.append(genre)

    # actors
    for a_name in movie_data.actors:
        actor = await db.scalar(select(ActorModel).where(ActorModel.name == a_name))
        if not actor:
            actor = ActorModel(name=a_name)
            db.add(actor)
            await db.flush()
        movie.actors.append(actor)

    # languages
    for l_name in movie_data.languages:
        lang = await db.scalar(select(LanguageModel).where(LanguageModel.name == l_name))
        if not lang:
            lang = LanguageModel(name=l_name)
            db.add(lang)
            await db.flush()
        movie.languages.append(lang)

    await db.commit()

    # КЛЮЧОВЕ: перечитати movie з eager-load, щоб НЕ було MissingGreenlet у response_model
    movie = await _get_movie_or_404(db, movie.id)
    return movie


# -----------------------
# PATCH /movies/{movie_id}/
# -----------------------

@router.patch("/{movie_id}/")
async def update_movie(
    movie_id: int,
    movie_data: MovieUpdateSchema,
    db: AsyncSession = Depends(get_db),
):
    movie = await db.get(MovieModel, movie_id)
    if not movie:
        raise HTTPException(
            status_code=404,
            detail="Movie with the given ID was not found.",
        )

    data = movie_data.model_dump(exclude_unset=True)

    # базова валідація (як в ТЗ)
    if "score" in data and not (0 <= data["score"] <= 100):
        raise HTTPException(status_code=400, detail="Invalid input data.")
    if "budget" in data and data["budget"] < 0:
        raise HTTPException(status_code=400, detail="Invalid input data.")
    if "revenue" in data and data["revenue"] < 0:
        raise HTTPException(status_code=400, detail="Invalid input data.")
    if "date" in data and data["date"] > date.today() + timedelta(days=365):
        raise HTTPException(status_code=400, detail="Invalid input data.")

    for field, value in data.items():
        setattr(movie, field, value)

    await db.commit()

    return {"detail": "Movie updated successfully."}


# -----------------------
# DELETE /movies/{movie_id}/
# -----------------------

@router.delete("/{movie_id}/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_movie(
    movie_id: int,
    db: AsyncSession = Depends(get_db),
):
    movie = await db.get(MovieModel, movie_id)
    if not movie:
        raise HTTPException(
            status_code=404,
            detail="Movie with the given ID was not found.",
        )

    await db.delete(movie)
    await db.commit()
    return None
