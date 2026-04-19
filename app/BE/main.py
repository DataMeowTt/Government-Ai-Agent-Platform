from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from api.tax import router as tax_router

app = FastAPI(title="Government AI Agent Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(tax_router, prefix="/api")

FE_DIR = os.path.join(os.path.dirname(__file__), "..", "FE")
app.mount("/static", StaticFiles(directory=os.path.join(FE_DIR, "static")), name="static")


@app.get("/")
def serve_dashboard():
    return FileResponse(os.path.join(FE_DIR, "index.html"))


@app.get("/map")
def serve_map():
    return FileResponse(os.path.join(FE_DIR, "map.html"))
