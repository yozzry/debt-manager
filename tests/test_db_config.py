import os

from app import create_app, limiter
from app.models import db as _db, User


def test_database_url_env_is_respected(tmp_path):
    db_file = tmp_path / 'custom.db'
    os.environ['DATABASE_URL'] = f"sqlite:///{db_file.as_posix()}"
    try:
        app = create_app(testing=False)
        limiter.enabled = False
        with app.app_context():
            assert db_file.exists()
            assert User.query.filter_by(username='admin').first() is not None
    finally:
        os.environ.pop('DATABASE_URL', None)


def test_testing_mode_forces_memory_sqlite():
    os.environ['DATABASE_URL'] = 'postgresql://user:pass@localhost/db'
    try:
        app = create_app(testing=True)
        assert app.config['SQLALCHEMY_DATABASE_URI'] == 'sqlite:///:memory:'
    finally:
        os.environ.pop('DATABASE_URL', None)


def test_sqlite_only_routes_reject_non_sqlite(monkeypatch, app, client):
    import app.database as database_mod
    monkeypatch.setattr(database_mod, '_is_sqlite', lambda: False)
    client.post('/login', data={'username': 'admin', 'password': 'admin123'})
    for url in ('/api/database/backup', '/api/database/integrity', '/api/database/optimize'):
        resp = client.post(url) if 'backup' in url or 'optimize' in url else client.get(url)
        data = resp.get_json() or {}
        assert data.get('ok') is False
        assert 'SQLite' in data.get('msg', '')
