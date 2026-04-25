"""Tests for app/sso.py — EVE SSO login/logout/callback routes."""

import pytest
from unittest.mock import MagicMock, patch
from flask import Flask
from flask_login import LoginManager


# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------

def _make_app():
    """Create a minimal Flask app with the SSO blueprint registered."""
    flask_app = Flask(__name__, template_folder='../templates')
    flask_app.config.update({'TESTING': True, 'SECRET_KEY': 'test-secret'})
    lm = LoginManager()
    lm.init_app(flask_app)

    @lm.user_loader
    def load_user(user_id):
        return None  # always anonymous; tests that need auth log in explicitly

    from app.sso import sso_pages
    flask_app.register_blueprint(sso_pages)
    return flask_app


# ---------------------------------------------------------------------------
# generate_token (pure function, no Flask needed)
# ---------------------------------------------------------------------------

class TestGenerateToken:
    def test_returns_string(self):
        from app.sso import generate_token
        assert isinstance(generate_token(), str)

    def test_is_valid_hex(self):
        from app.sso import generate_token
        token = generate_token()
        int(token, 16)  # raises ValueError if not hex

    def test_length_is_64_chars(self):
        from app.sso import generate_token
        # SHA-256 hexdigest is always 64 characters
        assert len(generate_token()) == 64

    def test_each_token_is_unique(self):
        from app.sso import generate_token
        tokens = {generate_token() for _ in range(20)}
        assert len(tokens) == 20


# ---------------------------------------------------------------------------
# GET /sso/login
# ---------------------------------------------------------------------------

class TestLoginRoute:
    def test_redirects_to_eve_login_url(self):
        mock_esi = MagicMock()
        mock_esi.get_auth_uri.return_value = 'https://login.eveonline.com/authorize?foo=bar'

        with patch('app.sso.esi', mock_esi):
            app = _make_app()
            with app.test_client() as c:
                resp = c.get('/sso/login')

        assert resp.status_code == 302
        assert 'login.eveonline.com' in resp.headers['Location']

    def test_stores_state_token_in_session(self):
        mock_esi = MagicMock()
        mock_esi.get_auth_uri.return_value = 'https://login.eveonline.com/authorize'

        with patch('app.sso.esi', mock_esi):
            app = _make_app()
            with app.test_client() as c:
                c.get('/sso/login')
                with c.session_transaction() as sess:
                    assert 'token' in sess

    def test_stores_login_type_in_session(self):
        mock_esi = MagicMock()
        mock_esi.get_auth_uri.return_value = 'https://login.eveonline.com/authorize'

        with patch('app.sso.esi', mock_esi):
            app = _make_app()
            with app.test_client() as c:
                c.get('/sso/login?login_type=member')
                with c.session_transaction() as sess:
                    assert sess.get('login_type') == 'member'

    def test_non_reserved_params_become_scopes(self):
        """Query params other than login_type/socket_guid/character_name are scopes."""
        mock_esi = MagicMock()
        mock_esi.get_auth_uri.return_value = 'https://login.eveonline.com/authorize'

        with patch('app.sso.esi', mock_esi):
            app = _make_app()
            with app.test_client() as c:
                c.get('/sso/login?read_fleet=esi-fleets.read_fleet.v1')

        call_kwargs = mock_esi.get_auth_uri.call_args[1]
        assert 'esi-fleets.read_fleet.v1' in call_kwargs['scopes']


# ---------------------------------------------------------------------------
# GET /sso/callback — CSRF checks
# ---------------------------------------------------------------------------

class TestCallbackCsrf:
    def test_missing_session_token_renders_error(self):
        with patch('app.sso.render_template', return_value='error') as mock_render:
            app = _make_app()
            with app.test_client() as c:
                resp = c.get('/sso/callback?code=abc&state=xyz')

        assert resp.status_code == 200
        mock_render.assert_called_with(
            'error.html',
            error='Login EVE Online SSO failed: Session Token Mismatch',
        )

    def test_mismatched_state_renders_error(self):
        with patch('app.sso.render_template', return_value='error') as mock_render:
            app = _make_app()
            with app.test_client() as c:
                with c.session_transaction() as sess:
                    sess['token'] = 'correct-token'
                resp = c.get('/sso/callback?code=abc&state=wrong-token')

        assert resp.status_code == 200
        mock_render.assert_called_with(
            'error.html',
            error='Login EVE Online SSO failed: Session Token Mismatch',
        )

    def test_missing_state_param_renders_error(self):
        with patch('app.sso.render_template', return_value='error') as mock_render:
            app = _make_app()
            with app.test_client() as c:
                with c.session_transaction() as sess:
                    sess['token'] = 'correct-token'
                resp = c.get('/sso/callback?code=abc')  # no state param

        assert resp.status_code == 200
        mock_render.assert_called_with(
            'error.html',
            error='Login EVE Online SSO failed: Session Token Mismatch',
        )


# ---------------------------------------------------------------------------
# GET /sso/callback — business logic
# ---------------------------------------------------------------------------

class TestCallbackSuccess:
    def _setup_esi_mocks(self):
        mock_esi = MagicMock()
        mock_esi.exchange_code.return_value = {
            'access_token': 'at',
            'refresh_token': 'rt',
            'expires_in': 1199,
        }
        mock_esi.decode_jwt.return_value = {
            'CharacterID': 12345,
            'CharacterName': 'Test Pilot',
            'Scopes': 'esi-fleets.read_fleet.v1',
        }
        return mock_esi

    def test_redirects_after_successful_login(self):
        mock_esi = self._setup_esi_mocks()
        mock_mongo = MagicMock()
        mock_user = MagicMock()

        with patch('app.sso.esi', mock_esi), \
             patch('app.sso.mongo', mock_mongo), \
             patch('app.sso.User', return_value=mock_user), \
             patch('app.sso.login_user'), \
             patch('app.sso.url_for', return_value='/app'):
            app = _make_app()
            with app.test_client() as c:
                with c.session_transaction() as sess:
                    sess['token'] = 'valid-state'
                resp = c.get('/sso/callback?code=auth-code&state=valid-state')

        assert resp.status_code == 302

    def test_character_name_mismatch_renders_error(self):
        mock_esi = self._setup_esi_mocks()
        # EVE returns 'Test Pilot' but session expects 'Other Pilot'

        with patch('app.sso.esi', mock_esi), \
             patch('app.sso.render_template', return_value='error') as mock_render:
            app = _make_app()
            with app.test_client() as c:
                with c.session_transaction() as sess:
                    sess['token'] = 'valid-state'
                    sess['character_name'] = 'Other Pilot'
                resp = c.get('/sso/callback?code=auth-code&state=valid-state')

        assert resp.status_code == 200
        error_msg = mock_render.call_args[1]['error']
        assert 'does not match' in error_msg

    def test_esi_exchange_http_error_renders_error(self):
        from requests.exceptions import HTTPError
        mock_esi = MagicMock()
        mock_esi.exchange_code.side_effect = HTTPError('401 Unauthorized')

        with patch('app.sso.esi', mock_esi), \
             patch('app.sso.render_template', return_value='error') as mock_render:
            app = _make_app()
            with app.test_client() as c:
                with c.session_transaction() as sess:
                    sess['token'] = 'valid-state'
                resp = c.get('/sso/callback?code=bad-code&state=valid-state')

        assert resp.status_code == 200
        error_msg = mock_render.call_args[1]['error']
        assert 'SSO failed' in error_msg

    def test_member_login_type_renders_success_message(self):
        mock_esi = self._setup_esi_mocks()
        mock_mongo = MagicMock()
        mock_user = MagicMock()

        with patch('app.sso.esi', mock_esi), \
             patch('app.sso.mongo', mock_mongo), \
             patch('app.sso.User', return_value=mock_user), \
             patch('app.sso.login_user'), \
             patch('app.sso.render_template', return_value='success') as mock_render:
            app = _make_app()
            with app.test_client() as c:
                with c.session_transaction() as sess:
                    sess['token'] = 'valid-state'
                    sess['login_type'] = 'member'
                resp = c.get('/sso/callback?code=auth-code&state=valid-state')

        mock_render.assert_called_with(
            'error.html',
            error='You have successfully logged in, you may close this window.',
        )


# ---------------------------------------------------------------------------
# GET /sso/logout
# ---------------------------------------------------------------------------

class TestLogoutRoute:
    def test_unauthenticated_access_blocked(self):
        app = _make_app()
        with app.test_client() as c:
            resp = c.get('/sso/logout')
        # Flask-Login blocks unauthenticated access: 401 (no handler set)
        assert resp.status_code in (401, 302)
