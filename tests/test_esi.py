"""Tests for app/esi.py — EVE SSO OAuth2 and ESI HTTP client."""

import pytest
import requests
from unittest.mock import MagicMock, patch

from app.esi import (
    get_auth_uri,
    exchange_code,
    refresh_access_token,
    revoke_token,
    decode_jwt,
    _check_response,
    _check_fleet_response,
    get_fleet_members,
    get_fleet_wings,
    delete_fleet_member,
    put_fleet_member,
    get_universe_names,
    get_universe_ids,
    EsiError,
    EsiException,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code=200, json_data=None):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = json_data if json_data is not None else {}
    r.raise_for_status.return_value = None
    if status_code >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(str(status_code))
    return r


# ---------------------------------------------------------------------------
# get_auth_uri
# ---------------------------------------------------------------------------

class TestGetAuthUri:
    def test_includes_client_id(self):
        url = get_auth_uri(['s1'], 'state1')
        assert 'test-client-id' in url

    def test_includes_state(self):
        url = get_auth_uri(['s1'], 'mystate')
        assert 'mystate' in url

    def test_includes_scope(self):
        url = get_auth_uri(['esi-fleets.read_fleet.v1'], 'state')
        assert 'esi-fleets.read_fleet.v1' in url

    def test_response_type_is_code(self):
        url = get_auth_uri([], 'state')
        assert 'response_type=code' in url

    def test_multiple_scopes_joined(self):
        url = get_auth_uri(['scope-a', 'scope-b'], 'state')
        assert 'scope-a' in url
        assert 'scope-b' in url


# ---------------------------------------------------------------------------
# exchange_code
# ---------------------------------------------------------------------------

class TestExchangeCode:
    def test_returns_token_json(self):
        payload = {'access_token': 'at', 'refresh_token': 'rt', 'expires_in': 1199}
        with patch('requests.post', return_value=_mock_response(200, payload)):
            result = exchange_code('auth-code')
        assert result == payload

    def test_sends_authorization_code_grant(self):
        with patch('requests.post', return_value=_mock_response(200, {})) as mock_post:
            exchange_code('code123')
        data = mock_post.call_args[1]['data']
        assert data['grant_type'] == 'authorization_code'
        assert data['code'] == 'code123'

    def test_raises_on_http_error(self):
        with patch('requests.post', return_value=_mock_response(401)):
            with pytest.raises(requests.HTTPError):
                exchange_code('bad-code')


# ---------------------------------------------------------------------------
# refresh_access_token
# ---------------------------------------------------------------------------

class TestRefreshAccessToken:
    def test_returns_new_token_json(self):
        payload = {'access_token': 'new-at', 'refresh_token': 'new-rt', 'expires_in': 1199}
        with patch('requests.post', return_value=_mock_response(200, payload)):
            result = refresh_access_token('old-refresh')
        assert result['access_token'] == 'new-at'

    def test_sends_refresh_token_grant(self):
        with patch('requests.post', return_value=_mock_response(200, {})) as mock_post:
            refresh_access_token('my-refresh')
        data = mock_post.call_args[1]['data']
        assert data['grant_type'] == 'refresh_token'
        assert data['refresh_token'] == 'my-refresh'

    def test_raises_on_http_error(self):
        with patch('requests.post', return_value=_mock_response(401)):
            with pytest.raises(requests.HTTPError):
                refresh_access_token('bad-refresh')


# ---------------------------------------------------------------------------
# revoke_token
# ---------------------------------------------------------------------------

class TestRevokeToken:
    def test_posts_to_revoke_endpoint(self):
        with patch('requests.post', return_value=_mock_response()) as mock_post:
            revoke_token('my-token')
        assert mock_post.called
        url = mock_post.call_args[0][0]
        assert 'revoke' in url

    def test_includes_token_in_body(self):
        with patch('requests.post', return_value=_mock_response()) as mock_post:
            revoke_token('tok')
        data = mock_post.call_args[1]['data']
        assert data['token'] == 'tok'


# ---------------------------------------------------------------------------
# decode_jwt
# ---------------------------------------------------------------------------

class TestDecodeJwt:
    def _patch_jwt(self, sub, name, scp):
        mock_key = MagicMock()
        mock_key.key = 'fake-key'
        payload = {'sub': sub, 'name': name, 'scp': scp}

        jwks_patch = patch('app.esi._jwks_client')
        decode_patch = patch('jwt.decode', return_value=payload)
        return jwks_patch, decode_patch, mock_key

    def test_extracts_character_id_from_sub(self):
        jwks_p, dec_p, mock_key = self._patch_jwt('CHARACTER:EVE:12345678', 'Pilot', [])
        with jwks_p as mock_jwks, dec_p:
            mock_jwks.get_signing_key_from_jwt.return_value = mock_key
            result = decode_jwt('fake.jwt')
        assert result['CharacterID'] == 12345678

    def test_extracts_character_name(self):
        jwks_p, dec_p, mock_key = self._patch_jwt('CHARACTER:EVE:1', 'Test Pilot', [])
        with jwks_p as mock_jwks, dec_p:
            mock_jwks.get_signing_key_from_jwt.return_value = mock_key
            result = decode_jwt('fake.jwt')
        assert result['CharacterName'] == 'Test Pilot'

    def test_list_scopes_joined_with_space(self):
        jwks_p, dec_p, mock_key = self._patch_jwt('CHARACTER:EVE:1', 'P', ['scope-a', 'scope-b'])
        with jwks_p as mock_jwks, dec_p:
            mock_jwks.get_signing_key_from_jwt.return_value = mock_key
            result = decode_jwt('fake.jwt')
        assert result['Scopes'] == 'scope-a scope-b'

    def test_string_scope_returned_as_is(self):
        jwks_p, dec_p, mock_key = self._patch_jwt('CHARACTER:EVE:1', 'P', 'single-scope')
        with jwks_p as mock_jwks, dec_p:
            mock_jwks.get_signing_key_from_jwt.return_value = mock_key
            result = decode_jwt('fake.jwt')
        assert result['Scopes'] == 'single-scope'


# ---------------------------------------------------------------------------
# _check_response
# ---------------------------------------------------------------------------

class TestCheckResponse:
    def test_200_does_not_raise(self):
        _check_response(_mock_response(200), 'ok')

    def test_404_raises_esi_exception(self):
        with pytest.raises(EsiException):
            _check_response(_mock_response(404, {'error': 'not found'}), 'test')

    def test_400_raises_esi_error(self):
        with pytest.raises(EsiError):
            _check_response(_mock_response(400, {'error': 'bad request'}), 'test')

    def test_500_raises_esi_error(self):
        with pytest.raises(EsiError):
            _check_response(_mock_response(500, {'error': 'server error'}), 'test')

    def test_uses_status_code_string_when_json_missing(self):
        r = _mock_response(503)
        r.json.side_effect = Exception('no json')
        with pytest.raises(EsiError) as exc_info:
            _check_response(r, 'test')
        assert '503' in str(exc_info.value)


# ---------------------------------------------------------------------------
# _check_fleet_response
# ---------------------------------------------------------------------------

class TestCheckFleetResponse:
    def test_200_does_not_raise(self):
        _check_fleet_response(_mock_response(200), 'ok')

    def test_404_not_found_raises_esi_error(self):
        with pytest.raises(EsiError):
            _check_fleet_response(_mock_response(404, {'error': 'Not found'}), 'test')

    def test_404_non_boss_raises_esi_exception_with_message(self):
        with pytest.raises(EsiException) as exc_info:
            _check_fleet_response(_mock_response(404, {'error': 'Character is not fleet boss'}), 'test')
        assert 'not fleet boss' in str(exc_info.value)

    def test_403_raises_esi_error(self):
        with pytest.raises(EsiError):
            _check_fleet_response(_mock_response(403, {'error': 'forbidden'}), 'test')

    def test_500_raises_esi_error(self):
        with pytest.raises(EsiError):
            _check_fleet_response(_mock_response(500, {'error': 'server error'}), 'test')


# ---------------------------------------------------------------------------
# get_fleet_members / get_fleet_wings
# ---------------------------------------------------------------------------

class TestGetFleetMembers:
    def test_returns_member_list(self):
        members = [{'character_id': 1}, {'character_id': 2}]
        with patch('requests.get', return_value=_mock_response(200, members)):
            assert get_fleet_members(111, 'tok') == members

    def test_url_contains_fleet_id(self):
        with patch('requests.get', return_value=_mock_response(200, [])) as mock_get:
            get_fleet_members(99999, 'tok')
        assert '99999' in mock_get.call_args[0][0]

    def test_propagates_esi_error_on_404_not_found(self):
        with patch('requests.get', return_value=_mock_response(404, {'error': 'Not found'})):
            with pytest.raises(EsiError):
                get_fleet_members(111, 'tok')

    def test_propagates_esi_exception_on_non_boss_404(self):
        with patch('requests.get', return_value=_mock_response(404, {'error': 'other'})):
            with pytest.raises(EsiException):
                get_fleet_members(111, 'tok')


class TestGetFleetWings:
    def test_returns_wings_list(self):
        wings = [{'id': 1, 'name': 'Wing 1', 'squads': []}]
        with patch('requests.get', return_value=_mock_response(200, wings)):
            assert get_fleet_wings(111, 'tok') == wings

    def test_url_contains_fleet_id_and_wings(self):
        with patch('requests.get', return_value=_mock_response(200, [])) as mock_get:
            get_fleet_wings(55555, 'tok')
        url = mock_get.call_args[0][0]
        assert '55555' in url
        assert 'wings' in url


# ---------------------------------------------------------------------------
# delete_fleet_member / put_fleet_member
# ---------------------------------------------------------------------------

class TestDeleteFleetMember:
    def test_calls_delete_with_correct_url(self):
        with patch('requests.delete', return_value=_mock_response(204)) as mock_del:
            delete_fleet_member(111, 999, 'tok')
        url = mock_del.call_args[0][0]
        assert '111' in url
        assert '999' in url

    def test_raises_on_error(self):
        with patch('requests.delete', return_value=_mock_response(404, {'error': 'Not found'})):
            with pytest.raises(EsiException):
                delete_fleet_member(111, 999, 'tok')


class TestPutFleetMember:
    def test_sends_movement_as_json(self):
        movement = {'role': 'squad_member', 'squad_id': 5, 'wing_id': 2}
        with patch('requests.put', return_value=_mock_response(204)) as mock_put:
            put_fleet_member(111, 999, movement, 'tok')
        assert mock_put.call_args[1]['json'] == movement

    def test_url_contains_fleet_and_member_ids(self):
        with patch('requests.put', return_value=_mock_response(204)) as mock_put:
            put_fleet_member(111, 999, {}, 'tok')
        url = mock_put.call_args[0][0]
        assert '111' in url
        assert '999' in url


# ---------------------------------------------------------------------------
# get_universe_names / get_universe_ids
# ---------------------------------------------------------------------------

class TestGetUniverseNames:
    def test_returns_name_list(self):
        data = [{'id': 1, 'name': 'Jita', 'category': 'solar_system'}]
        with patch('requests.post', return_value=_mock_response(200, data)):
            assert get_universe_names([1]) == data

    def test_raises_on_error(self):
        with patch('requests.post', return_value=_mock_response(400, {'error': 'bad ids'})):
            with pytest.raises(EsiError):
                get_universe_names([])


class TestGetUniverseIds:
    def test_returns_id_dict(self):
        data = {'systems': [{'id': 30000142, 'name': 'Jita'}]}
        with patch('requests.post', return_value=_mock_response(200, data)):
            assert get_universe_ids(['Jita']) == data

    def test_raises_on_error(self):
        with patch('requests.post', return_value=_mock_response(422, {'error': 'unprocessable'})):
            with pytest.raises(EsiError):
                get_universe_ids(['!!!'])
