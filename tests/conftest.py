import os
import sys
import pytest

os.environ['RATELIMIT_ENABLED'] = 'false'
os.environ['TESTING'] = '1'

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, limiter
from app.models import db as _db, User


@pytest.fixture(scope='session')
def app():
    app = create_app(testing=True)
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SERVER_NAME'] = 'localhost'
    limiter.enabled = False

    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture(autouse=True)
def reset_db(app):
    with app.app_context():
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()

        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', role='admin')
            admin.set_password('admin123')
            _db.session.add(admin)
            _db.session.commit()
        yield
        _db.session.remove()


@pytest.fixture
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture
def auth_client(client):
    client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
    return client
