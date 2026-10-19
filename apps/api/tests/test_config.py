import pytest

from app.config import normalize_database_url


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@db:5432/pulse", "postgresql+psycopg://u:p@db:5432/pulse"),
        ("postgresql://u:p@db:5432/pulse?sslmode=require", "postgresql+psycopg://u:p@db:5432/pulse?sslmode=require"),
        ("postgresql+psycopg://u:p@db/pulse", "postgresql+psycopg://u:p@db/pulse"),
        ("  postgres://u:p@db/pulse\n", "postgresql+psycopg://u:p@db/pulse"),
    ],
)
def test_platform_database_urls_use_the_psycopg_driver(given, expected):
    assert normalize_database_url(given) == expected
