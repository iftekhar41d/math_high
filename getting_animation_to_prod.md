Getting the animation to prod
The .mp4/.vtt do NOT travel through git or the deploy pipeline. What you just committed (scenes/equivalent-fractions/) is only the re-renderable source. The video and the DB row are created by uploading through the live admin screen on the production site.

1. Deploy the Phase 2 code
Push main → .github/workflows/deploy.yml SSHes to the VPS and runs git reset --hard origin/main → alembic upgrade head → python -m app.ingest → npm build → restart. This ships:

the /admin/animations screen + API
the animations / animation_topics tables (Phase 2 migrations)
tools/anim/scenes/equivalent-fractions/ (source only)
app.ingest loads the text manifest only — it never creates Animation rows. So nothing about the video itself is deployed.

2. Make sure a prod ContentAdmin exists
Roles have no admin UI (that's Phase 3), and the dev role changes I made do not carry to prod — prod has its own api/data/app.db. Someone with SSH sets it directly:


ssh deploy@math.mentisq.com
cd /home/deploy/math-high/api
sqlite3 data/app.db "UPDATE users SET role='content_admin' WHERE email='<prod-admin-email>';"
No restart needed — the role is read from the DB on every request.

3. Upload on prod
Log into https://math.mentisq.com as that ContentAdmin → /admin/animations:

New animation, slug equivalent-fractions
Upload the local tools/anim/out/equivalent-fractions/equivalent-fractions.mp4 + .vtt
Title / description / duration (26 s) → tick Equivalent Fractions → Save → Publish

4. Where it lands on the VPS
The upload goes through the MediaStorage seam → LocalMediaStorage writes to
MEDIA_ROOT = /home/deploy/math-high/api/data/media/animations/equivalent-fractions/ (video.mp4, transcript.vtt).
nginx location /media/ serves it straight off disk; the Animation row + topic link live in prod's app.db.

Persistence
api/data/ (both *.db and media/) is gitignored, so git reset --hard on every future deploy leaves the uploaded media and the DB untouched — the animation survives redeploys. It lives only on the VPS local disk, so it's only as safe as your backup of /home/deploy/math-high/api/data/. If that disk is lost, recovery = re-render from the committed scene.py and re-upload (which is exactly why the source is committed).