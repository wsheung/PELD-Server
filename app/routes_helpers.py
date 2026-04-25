"""
 Helper functions for routes and background process
"""

from flask_login import current_user

from flask_socketio import disconnect

from app.flask_shared_modules import mongo
from app.flask_shared_modules import socketio
from app import esi
from app.esi import EsiError, EsiException

from requests import exceptions
from pymongo import ReturnDocument

import logging
import functools


def authenticated_only(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            disconnect()
        else:
            return f(*args, **kwargs)
    return wrapped

def emit_to_char(emit_type, data, sids=None, char_id=None, namespace=None):
    if char_id:
        id_filter = {'id': char_id}
        result = mongo.db.characters.find_one(id_filter)
        if result is not None and 'sid' in result:
            sids = result['sid']
        else:
            sids = []
    for sid in sids:
        socketio.emit(emit_type, data, room=sid, namespace=namespace)

def decode_fleet_member(member):
    member['character_name'] = decode_character_id(member['character_id'])
    member['ship_name'] = decode_ship_id(member['ship_type_id'])
    member['location_name'] = decode_system_id(member['solar_system_id'])
    member.pop('join_time')
    member.pop('solar_system_id')
    member.pop('squad_id')
    member.pop('takes_fleet_warp')
    member.pop('wing_id')
    return member

def id_from_name(_name):
    id_filter = {'name': _name}
    result = mongo.db.entities.find_one(id_filter)
    if result is not None:
        return result['id']
    try:
        data = esi.get_universe_ids([_name])
    except EsiError:
        return 0
    if 'inventory_types' in data and data['inventory_types']:
        _id = data['inventory_types'][0]['id']
        add_db_entity(_id, _name)
        return _id
    add_db_entity(-1, _name)
    return -1

def decode_character_id(_id):
    id_filter = {'id': _id}
    result = mongo.db.entities.find_one(id_filter)
    if result is not None:
        return result['name']
    try:
        data = esi.get_universe_names([_id])
        name = data[0]['name']
    except (EsiError, EsiException, IndexError):
        return str(_id)
    add_db_entity(_id, name)
    return name

def decode_ship_id(_id):
    id_filter = {'id': _id}
    result = mongo.db.entities.find_one(id_filter)
    if result is not None:
        return result['name']
    try:
        data = esi.get_universe_names([_id])
        name = data[0]['name']
    except (EsiError, EsiException, IndexError):
        return str(_id)
    add_db_entity(_id, name)
    return name

def decode_system_id(_id):
    id_filter = {'id': _id}
    result = mongo.db.entities.find_one(id_filter)
    if result is not None:
        return result['name']
    try:
        data = esi.get_universe_names([_id])
        name = data[0]['name']
    except (EsiError, EsiException, IndexError):
        return str(_id)
    add_db_entity(_id, name)
    return name

def add_db_sid(_id, sid):
    _filter = {'id': _id}
    data_to_update = {}
    data_to_update['sid'] = sid
    update = {"$addToSet": data_to_update}
    mongo.db.characters.find_one_and_update(_filter, update, upsert=True)

def remove_db_sid(_id, sid):
    _filter = {'id': _id}
    data_to_update = {}
    data_to_update['sid'] = sid
    update = {"$pull": data_to_update}
    doc = mongo.db.characters.find_one_and_update(_filter, update, return_document=ReturnDocument.AFTER)
    if len(doc['sid']) == 0:
        fleets = mongo.db.fleets.find({'connected_webapps': _id})
        if fleets is not None:
            for fleet in fleets:
                fleet['connected_webapps'].remove(_id)
                update = {'$set': {'connected_webapps': fleet['connected_webapps']}}
                mongo.db.fleets.update_one({'id': fleet['id']}, update)

def add_db_entity(_id, name):
    _filter = {'id': _id}
    data_to_update = {}
    data_to_update['id'] = _id
    data_to_update['name'] = name
    update = {"$set": data_to_update}
    mongo.db.entities.find_one_and_update(_filter, update, upsert=True)

def update_token(current_user):
    sso_data = current_user.get_sso_data()
    if sso_data['expires_in'] <= 10:
        try:
            tokens = esi.refresh_access_token(current_user.refresh_token)
        except exceptions.SSLError:
            logging.error('ssl error refreshing token for: %s', current_user.get_id())
            raise EsiError('ssl error refreshing token')
        except Exception as e:
            logging.error('error refreshing token for: %s', current_user.get_id())
            logging.error('error is: %s', e)
            raise EsiError(e)
        current_user.update_token(tokens)
    return True
