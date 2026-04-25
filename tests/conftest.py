import os

# Must be set before any app module imports config
os.environ.setdefault('SECRET_KEY', 'a' * 32)
os.environ.setdefault('SERVER_NAME', 'testserver')
os.environ.setdefault('ESI_CLIENT_ID', 'test-client-id')
os.environ.setdefault('ESI_SECRET_KEY', 'test-esi-secret')

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta


@pytest.fixture
def mock_mongo():
    return MagicMock()


def make_character_doc(overrides=None):
    """Return a minimal character document suitable for User construction."""
    doc = {
        'id': 12345,
        'name': 'Test Pilot',
        'scopes': ['esi-fleets.read_fleet.v1'],
        'tokens': {
            'access_token': 'access-token-abc',
            'refresh_token': 'refresh-token-xyz',
            'access_token_expires': datetime.utcnow() + timedelta(seconds=600),
        },
        'sid': [],
    }
    if overrides:
        doc.update(overrides)
    return doc
