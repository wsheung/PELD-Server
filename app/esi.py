"""
EVE SSO OAuth2 and direct ESI HTTP client.
Replaces ESIPy entirely.
"""

import base64
import logging

import jwt
from jwt import PyJWKClient
import requests

import config

_jwks_client = PyJWKClient('https://login.eveonline.com/oauth/jwks')


class EsiError(Exception):
    pass


class EsiException(Exception):
    pass


def _basic_auth():
    credentials = f"{config.ESI_CLIENT_ID}:{config.ESI_SECRET_KEY}"
    return base64.b64encode(credentials.encode()).decode()


def get_auth_uri(scopes, state):
    params = {
        'response_type': 'code',
        'redirect_uri': config.ESI_CALLBACK,
        'client_id': config.ESI_CLIENT_ID,
        'scope': ' '.join(scopes),
        'state': state,
    }
    req = requests.Request('GET', config.EVE_AUTH_URL, params=params)
    return req.prepare().url


def exchange_code(code):
    headers = {
        'Authorization': f'Basic {_basic_auth()}',
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': config.ESI_USER_AGENT,
    }
    data = {
        'grant_type': 'authorization_code',
        'code': code,
    }
    r = requests.post(config.EVE_TOKEN_URL, headers=headers, data=data)
    r.raise_for_status()
    return r.json()


def refresh_access_token(refresh_token):
    headers = {
        'Authorization': f'Basic {_basic_auth()}',
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': config.ESI_USER_AGENT,
    }
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    }
    r = requests.post(config.EVE_TOKEN_URL, headers=headers, data=data)
    r.raise_for_status()
    return r.json()


def revoke_token(access_token):
    headers = {
        'Authorization': f'Basic {_basic_auth()}',
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': config.ESI_USER_AGENT,
    }
    data = {
        'token': access_token,
        'token_type_hint': 'access_token',
    }
    requests.post(config.EVE_REVOKE_URL, headers=headers, data=data)


def decode_jwt(access_token):
    signing_key = _jwks_client.get_signing_key_from_jwt(access_token)
    payload = jwt.decode(
        access_token,
        signing_key.key,
        algorithms=['RS256'],
        options={'verify_aud': False},
    )
    sub = payload.get('sub', '')
    # sub format: "CHARACTER:EVE:1234567890"
    character_id = int(sub.split(':')[-1])
    name = payload.get('name', '')
    scp = payload.get('scp', [])
    if isinstance(scp, str):
        scopes = scp
    else:
        scopes = ' '.join(scp)
    return {
        'CharacterID': character_id,
        'CharacterName': name,
        'Scopes': scopes,
    }


def _esi_headers(access_token=None):
    headers = {'User-Agent': config.ESI_USER_AGENT}
    if access_token:
        headers['Authorization'] = f'Bearer {access_token}'
    return headers


def _check_response(r, description):
    if r.status_code >= 400:
        try:
            error_msg = r.json().get('error', str(r.status_code))
        except Exception:
            error_msg = str(r.status_code)
        logging.error('ESI error for %s: %s', description, error_msg)
        if r.status_code == 404:
            raise EsiException(error_msg)
        raise EsiError(error_msg)


def _check_fleet_response(r, description):
    """Like _check_response but distinguishes 404 'Not found' (no fleet) from
    other 404s (user is not fleet boss)."""
    if 400 <= r.status_code < 500:
        try:
            error_msg = r.json().get('error', str(r.status_code))
        except Exception:
            error_msg = str(r.status_code)
        logging.error('ESI error for %s: %s', description, error_msg)
        if r.status_code == 404:
            if error_msg == 'Not found':
                raise EsiError(error_msg)
            raise EsiException('not fleet boss')
        raise EsiError(error_msg)
    elif r.status_code >= 500:
        try:
            error_msg = r.json().get('error', str(r.status_code))
        except Exception:
            error_msg = str(r.status_code)
        logging.error('ESI error for %s: %s', description, error_msg)
        raise EsiError(error_msg)


def get_character_fleet(character_id, access_token):
    r = requests.get(
        f'{config.ESI_BASE_URL}/latest/characters/{character_id}/fleet/',
        headers=_esi_headers(access_token),
    )
    _check_response(r, f'character fleet for {character_id}')
    return r.json()


def get_fleet_members(fleet_id, access_token):
    r = requests.get(
        f'{config.ESI_BASE_URL}/latest/fleets/{fleet_id}/members/',
        headers=_esi_headers(access_token),
    )
    _check_fleet_response(r, f'fleet members for {fleet_id}')
    return r.json()


def get_fleet_wings(fleet_id, access_token):
    r = requests.get(
        f'{config.ESI_BASE_URL}/latest/fleets/{fleet_id}/wings/',
        headers=_esi_headers(access_token),
    )
    _check_fleet_response(r, f'fleet wings for {fleet_id}')
    return r.json()


def delete_fleet_member(fleet_id, member_id, access_token):
    r = requests.delete(
        f'{config.ESI_BASE_URL}/latest/fleets/{fleet_id}/members/{member_id}/',
        headers=_esi_headers(access_token),
    )
    _check_response(r, f'kick member {member_id}')


def put_fleet_member(fleet_id, member_id, movement, access_token):
    r = requests.put(
        f'{config.ESI_BASE_URL}/latest/fleets/{fleet_id}/members/{member_id}/',
        headers={**_esi_headers(access_token), 'Content-Type': 'application/json'},
        json=movement,
    )
    _check_response(r, f'move member {member_id}')


def get_universe_names(ids):
    r = requests.post(
        f'{config.ESI_BASE_URL}/latest/universe/names/',
        headers=_esi_headers(),
        json=ids,
    )
    _check_response(r, f'universe names for {ids}')
    return r.json()


def get_universe_ids(names):
    r = requests.post(
        f'{config.ESI_BASE_URL}/latest/universe/ids/',
        headers=_esi_headers(),
        json=names,
    )
    _check_response(r, f'universe ids for {names}')
    return r.json()
