from fastapi import FastAPI
from contextlib import asynccontextmanager
from db import engine
from api import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title="AI SMS Guard", lifespan=lifespan)
app.include_router(router)