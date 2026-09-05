from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend import server
from backend.app.kitchen_interface import get_stock_status, reset_kitchen, set_stock


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


def test_available_item_enters_cart_without_reserving_stock(client):
    path = new(client)
    set_stock('chicken_rice', 2)
    response = client.post(path+'/lines', json=payload(item_id='chicken_rice', quantity=2))
    assert response.status_code == 200
    assert response.json()['snapshot']['lines'][0]['quantity'] == 2
    assert get_stock_status('chicken_rice') == 2


def test_sold_out_add_returns_structured_conflict_and_preserves_cart(client):
    path = new(client)
    assert client.post(path+'/lines', json=payload(item_id='fried_rice')).status_code == 200
    set_stock('chicken_rice', 0)
    before = client.get(path).json()['snapshot']
    request = payload(item_id='chicken_rice')

    response = client.post(path+'/lines', json=request)
    assert response.status_code == 409
    assert response.json()['detail'] == {
        'code': 'stock_unavailable',
        'message': 'Not enough stock for chicken_rice: requested 1, but only 0 available.',
        'item_id': 'chicken_rice',
        'requested_quantity': 1,
        'available_quantity': 0,
    }
    assert client.get(path).json()['snapshot'] == before
    assert client.post(path+'/lines', json=request).status_code == 409
    assert client.get(path).json()['snapshot'] == before


def test_combined_draft_quantity_and_quantity_edit_are_checked(client):
    path = new(client)
    set_stock('chicken_rice', 1)
    first = client.post(path+'/lines', json=payload(item_id='chicken_rice'))
    assert first.status_code == 200
    before = first.json()['snapshot']

    second = client.post(path+'/lines', json=payload(item_id='chicken_rice'))
    assert second.status_code == 409
    assert second.json()['detail']['requested_quantity'] == 2
    assert second.json()['detail']['available_quantity'] == 1
    assert client.get(path).json()['snapshot'] == before

    line = before['lines'][0]
    edited = client.patch(
        path+'/lines/'+line['key'],
        json=payload(item_id='chicken_rice', quantity=2),
    )
    assert edited.status_code == 409
    assert edited.json()['detail']['requested_quantity'] == 2
    assert client.get(path).json()['snapshot'] == before


def test_all_unavailable_conversational_add_returns_conflict_without_mutation(client):
    path = new(client)
    set_stock('chicken_rice', 0)
    before = client.get(path).json()['snapshot']
    response = client.post(path+'/messages', json=payload(text='one chicken rice'))

    assert response.status_code == 409
    assert response.json()['detail']['item_id'] == 'chicken_rice'
    assert client.get(path).json()['snapshot'] == before


def test_mixed_conversational_add_keeps_available_lines(client):
    path = new(client)
    set_stock('chicken_rice', 0)
    set_stock('fried_rice', 1)
    response = client.post(
        path+'/messages', json=payload(text='one chicken rice and one fried rice')
    )

    assert response.status_code == 200
    snapshot = response.json()['snapshot']
    assert [line['id'] for line in snapshot['lines']] == ['fried_rice']
    assert 'couldn\'t add' in response.json()['message']
    assert get_stock_status('fried_rice') == 1


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
    assert client.request('DELETE',path+'/lines/'+state['lines'][0]['key'],json=payload()).status_code == 409


def test_sessions_are_isolated_and_unknown_session_is_not_silently_recreated(client):
    first, second = new(client), new(client)
    client.post(first+'/lines',json=payload(item_id='kopi'))
    assert client.get(second).json()['snapshot']['lines'] == []
    assert client.get('/sessions/'+str(uuid4())).status_code == 404
