import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.storage import media_root
from app.routers import (
    admin,
    auth,
    content,
    content_admin,
    dashboard,
    mentisq,
    meta,
    practice,
    profile,
)

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
app.include_router(content_admin.router)
app.include_router(practice.router)
app.include_router(mentisq.router)
app.include_router(dashboard.router)
app.include_router(admin.router)

# Serve uploaded media (lecture images, animation videos + transcripts) straight
# from the store. In production nginx's `location /media/` matches first and
# these requests never reach the API (deploy/nginx.conf) — this mount is what
# makes media resolve in local dev, where the Vite proxy only forwards `/api`.
# `check_dir=False` so import never depends on the directory existing yet.
app.mount("/media", StaticFiles(directory=media_root(), check_dir=False), name="media")


@app.get("/health")
def health():
    """Liveness probe — no dependencies, no DB. See `/meta` for a real round trip."""
    return {"status": "ok"}
