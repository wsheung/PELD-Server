"""Tests for app/routes_helpers.py — entity lookup, token refresh, sid management."""

import pytest
from unittest.mock import MagicMock, patch, call
from datetime import timedelta

from app.esi import EsiError, EsiException


# ---------------------------------------------------------------------------
# id_from_name
# ---------------------------------------------------------------------------

class TestIdFromName:
    def test_cache_hit_returns_cached_id(self):
        mock_mongo = MagicMock()
        mock_mongo.db.entities.find_one.return_value = {'id': 587, 'name': 'Rifter'}

        with patch('app.routes_helpers.mongo', mock_mongo):
            from app.routes_helpers import id_from_name
            result = id_from_name('Rifter')

        assert result == 587
        mock_mongo.db.entities.find_one.assert_called_once_with({'name': 'Rifter'})

    def test_cache_miss_calls_esi_and_returns_id(self):
        mock_mongo = MagicMock()
        mock_mongo.db.entities.find_one.return_value = None
        mock_esi = MagicMock()
        mock_esi.get_universe_ids.return_value = {
            'inventory_types': [{'id': 587, 'name': 'Rifter'}]
        }

        with patch('app.routes_helpers.mongo', mock_mongo), \
             patch('app.routes_helpers.esi', mock_esi):
            from app.routes_helpers import id_from_name
            result = id_from_name('Rifter')

        assert result == 587

    def test_cache_miss_stores_entity_in_db(self):
        mock_mongo = MagicMock()
        mock_mongo.db.entities.find_one.return_value = None
        mock_esi = MagicMock()
        mock_esi.get_universe_ids.return_value = {
            'inventory_types': [{'id': 587, 'name': 'Rifter'}]
        }

        with patch('app.routes_helpers.mongo', mock_mongo), \
             patch('app.routes_helpers.esi', mock_esi):
            from app.routes_helpers import id_from_name
            id_from_name('Rifter')

        mock_mongo.db.entities.find_one_and_update.assert_called()

    def test_returns_negative_one_when_esi_has_no_inventory_types(self):
        mock_mongo = MagicMock()
        mock_mongo.db.entities.find_one.return_value = None
        mock_esi = MagicMock()
        mock_esi.get_universe_ids.return_value = {}

        with patch('app.routes_helpers.mongo', mock_mongo), \
             patch('app.routes_helpers.esi', mock_esi):
            from app.routes_helpers import id_from_name
            result = id_from_name('UnknownItem')

        assert result == -1

    def test_returns_zero_when_esi_raises_error(self):
        mock_mongo = MagicMock()
        mock_mongo.db.entities.find_one.return_value = None
        mock_esi = MagicMock()
        mock_esi.get_universe_ids.side_effect = EsiError('esi down')

        with patch('app.routes_helpers.mongo', mock_mongo), \
             patch('app.routes_helpers.esi', mock_esi):
            from app.routes_helpers import id_from_name
            result = id_from_name('Whatever')

        assert result == 0


# ---------------------------------------------------------------------------
# decode_character_id / decode_ship_id / decode_system_id
# (all three share the same cache-then-ESI pattern)
# ---------------------------------------------------------------------------

class TestDecodeCharacterId:
    def test_cache_hit(self):
        mock_mongo = MagicMock()
        mock_mongo.db.entities.find_one.return_value = {'id': 12345, 'name': 'Test Pilot'}

        with patch('app.routes_helpers.mongo', mock_mongo):
            from app.routes_helpers import decode_character_id
            assert decode_character_id(12345) == 'Test Pilot'

    def test_esi_lookup_on_cache_miss(self):
        mock_mongo = MagicMock()
        mock_mongo.db.entities.find_one.return_value = None
        mock_esi = MagicMock()
        mock_esi.get_universe_names.return_value = [
            {'id': 12345, 'name': 'Test Pilot', 'category': 'character'}
        ]

        with patch('app.routes_helpers.mongo', mock_mongo), \
             patch('app.routes_helpers.esi', mock_esi):
            from app.routes_helpers import decode_character_id
            assert decode_character_id(12345) == 'Test Pilot'

    def test_returns_string_id_on_esi_error(self):
        mock_mongo = MagicMock()
        mock_mongo.db.entities.find_one.return_value = None
        mock_esi = MagicMock()
        mock_esi.get_universe_names.side_effect = EsiError('error')

        with patch('app.routes_helpers.mongo', mock_mongo), \
             patch('app.routes_helpers.esi', mock_esi):
            from app.routes_helpers import decode_character_id
            assert decode_character_id(12345) == '12345'

    def test_returns_string_id_on_empty_esi_response(self):
        mock_mongo = MagicMock()
        mock_mongo.db.entities.find_one.return_value = None
        mock_esi = MagicMock()
        mock_esi.get_universe_names.return_value = []  # empty list → IndexError

        with patch('app.routes_helpers.mongo', mock_mongo), \
             patch('app.routes_helpers.esi', mock_esi):
            from app.routes_helpers import decode_character_id
            assert decode_character_id(12345) == '12345'


class TestDecodeShipId:
    def test_cache_hit(self):
        mock_mongo = MagicMock()
        mock_mongo.db.entities.find_one.return_value = {'id': 587, 'name': 'Rifter'}

        with patch('app.routes_helpers.mongo', mock_mongo):
            from app.routes_helpers import decode_ship_id
            assert decode_ship_id(587) == 'Rifter'


class TestDecodeSystemId:
    def test_cache_hit(self):
        mock_mongo = MagicMock()
        mock_mongo.db.entities.find_one.return_value = {'id': 30000142, 'name': 'Jita'}

        with patch('app.routes_helpers.mongo', mock_mongo):
            from app.routes_helpers import decode_system_id
            assert decode_system_id(30000142) == 'Jita'


# ---------------------------------------------------------------------------
# update_token
# ---------------------------------------------------------------------------

class TestUpdateToken:
    def _make_user(self, expires_in):
        user = MagicMock()
        user.get_sso_data.return_value = {
            'expires_in': expires_in,
            'access_token': 'old-at',
            'refresh_token': 'old-rt',
        }
        user.refresh_token = 'old-rt'
        user.get_id.return_value = 12345
        return user

    def test_returns_true_when_token_is_fresh(self):
        from app.routes_helpers import update_token
        user = self._make_user(expires_in=600)
        with patch('app.routes_helpers.esi') as mock_esi:
            result = update_token(user)
        assert result is True
        mock_esi.refresh_access_token.assert_not_called()

    def test_refreshes_when_token_expires_in_under_10s(self):
        from app.routes_helpers import update_token
        mock_esi = MagicMock()
        mock_esi.refresh_access_token.return_value = {
            'access_token': 'new-at',
            'refresh_token': 'new-rt',
            'expires_in': 1199,
        }
        user = self._make_user(expires_in=5)

        with patch('app.routes_helpers.esi', mock_esi):
            result = update_token(user)

        assert result is True
        mock_esi.refresh_access_token.assert_called_once_with('old-rt')
        user.update_token.assert_called_once()

    def test_raises_esi_error_on_ssl_failure(self):
        from requests.exceptions import SSLError
        from app.routes_helpers import update_token, EsiError

        mock_esi = MagicMock()
        mock_esi.refresh_access_token.side_effect = SSLError('ssl')
        user = self._make_user(expires_in=0)

        with patch('app.routes_helpers.esi', mock_esi):
            with pytest.raises(EsiError):
                update_token(user)

    def test_raises_esi_error_on_general_exception(self):
        from app.routes_helpers import update_token, EsiError

        mock_esi = MagicMock()
        mock_esi.refresh_access_token.side_effect = Exception('network timeout')
        user = self._make_user(expires_in=0)

        with patch('app.routes_helpers.esi', mock_esi):
            with pytest.raises(EsiError):
                update_token(user)


# ---------------------------------------------------------------------------
# add_db_entity
# ---------------------------------------------------------------------------

class TestAddDbEntity:
    def test_upserts_with_correct_filter_and_data(self):
        mock_mongo = MagicMock()

        with patch('app.routes_helpers.mongo', mock_mongo):
            from app.routes_helpers import add_db_entity
            add_db_entity(587, 'Rifter')

        args = mock_mongo.db.entities.find_one_and_update.call_args[0]
        assert args[0] == {'id': 587}
        assert args[1]['$set']['id'] == 587
        assert args[1]['$set']['name'] == 'Rifter'


# ---------------------------------------------------------------------------
# add_db_sid
# ---------------------------------------------------------------------------

class TestAddDbSid:
    def test_uses_addtoset_operator(self):
        mock_mongo = MagicMock()

        with patch('app.routes_helpers.mongo', mock_mongo):
            from app.routes_helpers import add_db_sid
            add_db_sid(12345, 'sid-abc')

        args = mock_mongo.db.characters.find_one_and_update.call_args[0]
        assert args[0] == {'id': 12345}
        assert args[1]['$addToSet']['sid'] == 'sid-abc'


# ---------------------------------------------------------------------------
# remove_db_sid
# ---------------------------------------------------------------------------

class TestRemoveDbSid:
    def test_uses_pull_operator(self):
        mock_mongo = MagicMock()
        mock_mongo.db.characters.find_one_and_update.return_value = {
            'id': 12345, 'sid': ['remaining']
        }
        mock_mongo.db.fleets.find.return_value = []

        with patch('app.routes_helpers.mongo', mock_mongo):
            from app.routes_helpers import remove_db_sid
            remove_db_sid(12345, 'removed-sid')

        args = mock_mongo.db.characters.find_one_and_update.call_args[0]
        assert args[1]['$pull']['sid'] == 'removed-sid'

    def test_removes_character_from_fleet_when_no_sids_remain(self):
        mock_mongo = MagicMock()
        mock_mongo.db.characters.find_one_and_update.return_value = {
            'id': 12345, 'sid': []  # empty after removal
        }
        mock_mongo.db.fleets.find.return_value = [
            {'id': 99, 'connected_webapps': [12345]}
        ]

        with patch('app.routes_helpers.mongo', mock_mongo):
            from app.routes_helpers import remove_db_sid
            remove_db_sid(12345, 'last-sid')

        mock_mongo.db.fleets.update_one.assert_called_once()
        update_args = mock_mongo.db.fleets.update_one.call_args[0]
        assert update_args[0] == {'id': 99}
        assert 12345 not in update_args[1]['$set']['connected_webapps']

    def test_does_not_touch_fleets_when_sids_remain(self):
        mock_mongo = MagicMock()
        mock_mongo.db.characters.find_one_and_update.return_value = {
            'id': 12345, 'sid': ['still-here']
        }

        with patch('app.routes_helpers.mongo', mock_mongo):
            from app.routes_helpers import remove_db_sid
            remove_db_sid(12345, 'one-sid')

        mock_mongo.db.fleets.update_one.assert_not_called()
