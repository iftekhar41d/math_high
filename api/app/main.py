import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, content, meta, profile

# Only needed for local dev where the web dev server runs on a different
# origin/port. In production, nginx proxies /api on the same origin as the
# web app, so no CORS is required there.
DEV_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

app = FastAPI(title="MentisQ API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(content.router)


@app.get("/health")
def health():
    """Liveness probe — no dependencies, no DB. See `/meta` for a real round trip."""
    return {"status": "ok"}
