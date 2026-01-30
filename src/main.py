from fastapi import FastAPI
from routes.movies import router as movie_router

app = FastAPI()

app.include_router(movie_router, prefix="/api/v1/theater")
