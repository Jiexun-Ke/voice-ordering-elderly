from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend import server
from backend.app.kitchen_interface import reset_kitchen


@pytest.fixture
def client():
    server.sessions.clear()
    reset_kitchen()
    return TestClient(server.app)


def new(client):
    response = client.post('/sessions')
    assert response.status_code == 200
    return '/sessions/' + response.json()['snapshot']['session_id']


def payload(**values):
    return {'request_id': str(uuid4()), **values}


def test_menu_buttons_chat_and_edits_share_backend_prices(client):
    path = new(client)
    first = client.post(path+'/lines', json=payload(item_id='chicken_rice')).json()['snapshot']
    assert first['total_cents'] == 450
    response = client.post(path+'/messages', json=payload(text='two kopi c, siew dai, takeaway'))
    assert response.status_code == 200
    state = response.json()['snapshot']
    assert state['total_cents'] == 730
    kopi = next(line for line in state['lines'] if line['id'] == 'kopi')
    assert kopi['quantity'] == 2
    assert kopi['unit_cents'] == 140
    assert kopi['options']['sweetness'] == 'less_sweet'
    edited = client.patch(path+'/lines/'+kopi['key'], json=payload(item_id='kopi',quantity=3,options=kopi['options'])).json()['snapshot']
    assert edited['total_cents'] == 870
    assert client.get(path).json()['snapshot'] == edited


def test_duplicate_add_and_message_requests_are_idempotent(client):
    path = new(client)
    request = payload(item_id='kopi',quantity=2)
    for _ in range(2):
        assert client.post(path+'/lines',json=request).status_code == 200
    assert client.get(path).json()['snapshot']['total_cents'] == 240
    request = payload(text='one chicken rice')
    for _ in range(2):
        assert client.post(path+'/messages',json=request).status_code == 200
    assert client.get(path).json()['snapshot']['total_cents'] == 690
    request['text'] = 'two chicken rice'
    assert client.post(path+'/messages',json=request).status_code == 409


def test_invalid_choices_and_quantities_leave_order_unchanged(client):
    path = new(client)
    for values in [dict(item_id='unknown'),dict(item_id='kopi',quantity=0),dict(item_id='kopi',quantity=1.5),dict(item_id='kopi',options={'spice':'no_chilli'}),dict(item_id='nasi_lemak')]:
        assert client.post(path+'/lines',json=payload(**values)).status_code == 422
    assert client.get(path).json()['snapshot']['total_cents'] == 0


def test_greetings_and_menu_queries_do_not_add_food(client):
    path = new(client)
    for text in ['hello','Show drinks','Under $5','What is kopi?']:
        result = client.post(path+'/messages',json=payload(text=text)).json()
        assert result['message']
        assert result['snapshot']['lines'] == []


def test_clarification_then_confirmation_uses_existing_dialogue(client):
    path = new(client)
    result = client.post(path+'/messages',json=payload(text='one fishball noodles')).json()['snapshot']
    assert result['pending']
    assert result['lines'] == []
    result = client.post(path+'/messages',json=payload(text='yellow noodle, soup, no chilli')).json()['snapshot']
    assert result['pending'] is None
    assert result['total_cents'] == 400
    request = payload(takeaway=True)
    first = client.post(path+'/confirm',json=request)
    assert first.status_code == 200
    state = first.json()['snapshot']
    assert state['confirmed'] is True
    assert state['lines'][0]['kitchen_status'] == 'received'
    assert state['kitchen_mode'] == 'mock'
    assert client.post(path+'/confirm',json=request).json() == first.json()
    cancel_request = payload()
    cancelled = client.request('DELETE',path+'/lines/'+state['lines'][0]['key'],json=cancel_request)
    assert cancelled.status_code == 200
    assert cancelled.json()['snapshot']['lines'] == []
    assert client.request('DELETE',path+'/lines/'+state['lines'][0]['key'],json=cancel_request).json() == cancelled.json()


def test_confirmed_line_cannot_be_deleted_after_kitchen_starts_preparing(client):
    from backend.app.kitchen_interface import advance_line_status

    path = new(client)
    state = client.post(path+'/lines', json=payload(item_id='kopi')).json()['snapshot']
    state = client.post(path+'/confirm', json=payload(takeaway=False)).json()['snapshot']
    line = state['lines'][0]
    assert advance_line_status(line['key']) == 'preparing'
    response = client.request('DELETE', path+'/lines/'+line['key'], json=payload())
    assert response.status_code == 409
    assert client.get(path).json()['snapshot']['total_cents'] == 120


def test_saying_cancel_uses_the_same_kitchen_cancellation_rule(client):
    from backend.app.kitchen_interface import advance_line_status

    cancellable = new(client)
    state = client.post(cancellable+'/lines', json=payload(item_id='kopi')).json()['snapshot']
    state = client.post(cancellable+'/confirm', json=payload(takeaway=False)).json()['snapshot']
    response = client.post(cancellable+'/messages', json=payload(text='cancel'))
    assert response.status_code == 200
    assert response.json()['snapshot']['lines'] == []

    preparing = new(client)
    state = client.post(preparing+'/lines', json=payload(item_id='kopi')).json()['snapshot']
    state = client.post(preparing+'/confirm', json=payload(takeaway=False)).json()['snapshot']
    assert advance_line_status(state['lines'][0]['key']) == 'preparing'
    response = client.post(preparing+'/messages', json=payload(text='cancel'))
    assert response.status_code == 200
    assert len(response.json()['snapshot']['lines']) == 1
    assert 'already being prepared' in response.json()['message'].lower()


def test_sessions_are_isolated_and_unknown_session_is_not_silently_recreated(client):
    first, second = new(client), new(client)
    client.post(first+'/lines',json=payload(item_id='kopi'))
    assert client.get(second).json()['snapshot']['lines'] == []
    assert client.get('/sessions/'+str(uuid4())).status_code == 404
