# Alembic migrations

Run from the backend container (so the Python deps are available):

    docker compose run --rm adsb-backend alembic upgrade head

Generate a new migration after changing models:

    docker compose run --rm adsb-backend alembic revision --autogenerate -m "change description"
