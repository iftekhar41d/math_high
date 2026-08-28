"""Authentication: registration, email verification, login/refresh sessions,
password recovery, and login rate limiting.

The HTTP layer is `app.routers.auth` / `app.routers.profile`; the reusable core
is `app.auth.service`. Time is always read through the injected `Clock` so the
test suite can drive expiry, rotation, and lockout windows with a fake.
"""
