"""Tests for app/user.py — User model."""

import pytest
from unittest.mock import MagicMock, call
from datetime import datetime, timedelta

from tests.conftest import make_character_doc
from app.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mongo(doc):
    m = MagicMock()
    m.db.characters.find_one.return_value = doc
    m.db.characters.find_one_and_update.return_value = doc
    return m


def _auth_response(expires_in=1199):
    return {
        'access_token': 'access-token-abc',
        'refresh_token': 'refresh-token-xyz',
        'expires_in': expires_in,
    }


# ---------------------------------------------------------------------------
# __init__ — load by character_id
# ---------------------------------------------------------------------------

class TestUserInitById:
    def test_loads_from_mongo(self):
        doc = make_character_doc()
        user = User(character_id=12345, mongo=_make_mongo(doc))
        assert user.character_id == 12345
        assert user.character_name == 'Test Pilot'

    def test_access_token_set_from_doc(self):
        doc = make_character_doc()
        user = User(character_id=12345, mongo=_make_mongo(doc))
        assert user.access_token == 'access-token-abc'

    def test_refresh_token_set_from_doc(self):
        doc = make_character_doc()
        user = User(character_id=12345, mongo=_make_mongo(doc))
        assert user.refresh_token == 'refresh-token-xyz'

    def test_raises_when_character_not_found(self):
        mongo = MagicMock()
        mongo.db.characters.find_one.return_value = None
        with pytest.raises(Exception):
            User(character_id=99999, mongo=mongo)

    def test_fleet_id_defaults_to_none_when_absent(self):
        doc = make_character_doc()  # no fleet_id key
        doc.pop('fleet_id', None)
        user = User(character_id=12345, mongo=_make_mongo(doc))
        assert user.fleet_id is None


# ---------------------------------------------------------------------------
# __init__ — create/update from character_data + auth_response
# ---------------------------------------------------------------------------

class TestUserInitFromCharacterData:
    def _character_data(self, scopes='esi-fleets.read_fleet.v1'):
        return {'CharacterID': 12345, 'CharacterName': 'Test Pilot', 'Scopes': scopes}

    def test_upserts_character_to_mongo(self):
        doc = make_character_doc()
        mongo = MagicMock()
        mongo.db.characters.find_one_and_update.return_value = doc

        User(character_data=self._character_data(), auth_response=_auth_response(), mongo=mongo)

        mongo.db.characters.find_one_and_update.assert_called_once()

    def test_scopes_split_into_list(self):
        doc = make_character_doc()
        mongo = MagicMock()
        mongo.db.characters.find_one_and_update.return_value = doc

        User(
            character_data=self._character_data('scope-a scope-b'),
            auth_response=_auth_response(),
            mongo=mongo,
        )

        update_arg = mongo.db.characters.find_one_and_update.call_args[0][1]
        assert update_arg['$set']['scopes'] == ['scope-a', 'scope-b']

    def test_expiry_stored_as_datetime(self):
        doc = make_character_doc()
        mongo = MagicMock()
        mongo.db.characters.find_one_and_update.return_value = doc

        User(character_data=self._character_data(), auth_response=_auth_response(600), mongo=mongo)

        update_arg = mongo.db.characters.find_one_and_update.call_args[0][1]
        expires = update_arg['$set']['tokens']['access_token_expires']
        assert isinstance(expires, datetime)
        # Should be ~600 seconds in the future
        delta = (expires - datetime.utcnow()).total_seconds()
        assert 595 < delta < 605

    def test_empty_scopes_when_missing_from_data(self):
        cdata = {'CharacterID': 12345, 'CharacterName': 'Test Pilot'}  # no 'Scopes'
        doc = make_character_doc({'scopes': ''})
        mongo = MagicMock()
        mongo.db.characters.find_one_and_update.return_value = doc

        User(character_data=cdata, auth_response=_auth_response(), mongo=mongo)

        update_arg = mongo.db.characters.find_one_and_update.call_args[0][1]
        assert update_arg['$set']['scopes'] == ''


# ---------------------------------------------------------------------------
# get_id
# ---------------------------------------------------------------------------

class TestGetId:
    def test_returns_character_id(self):
        doc = make_character_doc()
        user = User(character_id=12345, mongo=_make_mongo(doc))
        assert user.get_id() == 12345


# ---------------------------------------------------------------------------
# get_sso_data
# ---------------------------------------------------------------------------

class TestGetSsoData:
    def test_returns_correct_keys(self):
        doc = make_character_doc()
        user = User(character_id=12345, mongo=_make_mongo(doc))
        data = user.get_sso_data()
        assert set(data.keys()) == {'access_token', 'refresh_token', 'expires_in'}

    def test_expires_in_is_approximate_seconds(self):
        future = datetime.utcnow() + timedelta(seconds=300)
        doc = make_character_doc({'tokens': {
            'access_token': 'at',
            'refresh_token': 'rt',
            'access_token_expires': future,
        }})
        user = User(character_id=12345, mongo=_make_mongo(doc))
        sso = user.get_sso_data()
        assert 290 < sso['expires_in'] <= 300

    def test_negative_expires_in_when_expired(self):
        past = datetime.utcnow() - timedelta(seconds=60)
        doc = make_character_doc({'tokens': {
            'access_token': 'at',
            'refresh_token': 'rt',
            'access_token_expires': past,
        }})
        user = User(character_id=12345, mongo=_make_mongo(doc))
        assert user.get_sso_data()['expires_in'] < 0


# ---------------------------------------------------------------------------
# get_fleet_id / set_fleet_id
# ---------------------------------------------------------------------------

class TestFleetId:
    def test_get_fleet_id_reads_from_db(self):
        doc = make_character_doc({'fleet_id': 7654321})
        user = User(character_id=12345, mongo=_make_mongo(doc))
        assert user.get_fleet_id() == 7654321

    def test_get_fleet_id_defaults_to_zero_when_absent(self):
        doc = make_character_doc()
        doc.pop('fleet_id', None)
        user = User(character_id=12345, mongo=_make_mongo(doc))
        assert user.get_fleet_id() == 0

    def test_set_fleet_id_updates_db(self):
        doc = make_character_doc()
        mongo = _make_mongo(doc)
        user = User(character_id=12345, mongo=mongo)

        user.set_fleet_id(9999)

        assert user.fleet_id == 9999
        update_call = mongo.db.characters.find_one_and_update.call_args
        assert update_call[0][1]['$set']['fleet_id'] == 9999


# ---------------------------------------------------------------------------
# update_token
# ---------------------------------------------------------------------------

class TestUpdateToken:
    def test_updates_in_memory_access_token(self):
        doc = make_character_doc()
        user = User(character_id=12345, mongo=_make_mongo(doc))
        user.update_token({'access_token': 'new-at', 'refresh_token': 'new-rt', 'expires_in': 1199})
        assert user.access_token == 'new-at'

    def test_updates_in_memory_refresh_token(self):
        doc = make_character_doc()
        user = User(character_id=12345, mongo=_make_mongo(doc))
        user.update_token({'access_token': 'new-at', 'refresh_token': 'new-rt', 'expires_in': 1199})
        assert user.refresh_token == 'new-rt'

    def test_persists_tokens_to_mongo(self):
        doc = make_character_doc()
        mongo = _make_mongo(doc)
        user = User(character_id=12345, mongo=mongo)

        user.update_token({'access_token': 'new-at', 'refresh_token': 'new-rt', 'expires_in': 600})

        mongo.db.characters.find_one_and_update.assert_called()
        update_arg = mongo.db.characters.find_one_and_update.call_args[0][1]
        assert update_arg['$set']['tokens']['access_token'] == 'new-at'
        assert update_arg['$set']['tokens']['refresh_token'] == 'new-rt'
