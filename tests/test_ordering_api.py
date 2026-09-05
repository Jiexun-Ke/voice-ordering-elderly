from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend import server
from backend.app.kitchen_interface import (
    advance_line_status,
    get_stock_status,
    reset_kitchen,
    set_stock,
)


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


def test_menu_exposes_live_stock_without_changing_existing_item_fields(client):
    set_stock('chicken_rice', 2)

    item = next(item for item in client.get('/menu').json()['items'] if item['id'] == 'chicken_rice')

    assert item['name'] == 'Hainanese Chicken Rice'
    assert item['price'] == 4.5
    assert item['modifier_groups']
    assert item['available'] is True
    assert item['remaining_stock'] == 2

    set_stock('chicken_rice', 0)
    sold_out = next(item for item in client.get('/menu').json()['items'] if item['id'] == 'chicken_rice')
    assert sold_out['available'] is False
    assert sold_out['remaining_stock'] == 0


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
    assert client.request('DELETE',path+'/lines/'+state['lines'][0]['key'],json=payload()).status_code == 200


def test_confirmation_rechecks_stock_and_keeps_all_unavailable_lines_unconfirmed(client):
    path = new(client)
    set_stock('chicken_rice', 1)
    added = client.post(path+'/lines', json=payload(item_id='chicken_rice'))
    assert added.status_code == 200
    set_stock('chicken_rice', 0)

    response = client.post(path+'/confirm', json=payload(takeaway=False))

    assert response.status_code == 200
    assert response.json()['snapshot']['lines'] == []
    assert response.json()['snapshot']['confirmed'] is False
    assert 'run out' in response.json()['message'].lower()
    assert 'sent to the kitchen' not in response.json()['message'].lower()
    assert get_stock_status('chicken_rice') == 0


def test_confirmation_partially_accepts_lines_when_stock_changes(client):
    path = new(client)
    set_stock('chicken_rice', 1)
    set_stock('fried_rice', 1)
    assert client.post(path+'/lines', json=payload(item_id='chicken_rice')).status_code == 200
    assert client.post(path+'/lines', json=payload(item_id='fried_rice')).status_code == 200
    set_stock('chicken_rice', 0)

    response = client.post(path+'/confirm', json=payload(takeaway=False))
    snapshot = response.json()['snapshot']

    assert response.status_code == 200
    assert [line['id'] for line in snapshot['lines']] == ['fried_rice']
    assert snapshot['lines'][0]['sent'] is True
    assert snapshot['lines'][0]['kitchen_status'] == 'received'
    assert snapshot['confirmed'] is True
    assert 'run out' in response.json()['message'].lower()
    assert 'rest of your order has been sent' in response.json()['message'].lower()
    assert get_stock_status('chicken_rice') == 0
    assert get_stock_status('fried_rice') == 0


def test_repeated_confirmation_request_does_not_deduct_stock_twice(client):
    path = new(client)
    set_stock('kopi', 2)
    assert client.post(path+'/lines', json=payload(item_id='kopi', quantity=2)).status_code == 200
    request = payload(takeaway=False)

    first = client.post(path+'/confirm', json=request)
    second = client.post(path+'/confirm', json=request)

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert get_stock_status('kopi') == 0


def test_http_cancellation_removes_unsent_and_received_lines_once(client):
    path = new(client)
    set_stock('kopi', 5)
    draft = client.post(path+'/lines', json=payload(item_id='kopi', quantity=2)).json()['snapshot']
    draft_key = draft['lines'][0]['key']
    before = get_stock_status('kopi')

    removed_draft = client.request('DELETE', path+'/lines/'+draft_key, json=payload())
    assert removed_draft.status_code == 200
    assert removed_draft.json()['snapshot']['lines'] == []
    assert get_stock_status('kopi') == before

    added = client.post(path+'/lines', json=payload(item_id='kopi', quantity=2)).json()['snapshot']
    line_key = added['lines'][0]['key']
    assert client.post(path+'/confirm', json=payload(takeaway=False)).status_code == 200
    assert get_stock_status('kopi') == 3
    cancel_request = payload()

    first = client.request('DELETE', path+'/lines/'+line_key, json=cancel_request)
    second = client.request('DELETE', path+'/lines/'+line_key, json=cancel_request)

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert first.json()['snapshot']['lines'] == []
    assert get_stock_status('kopi') == 5


@pytest.mark.parametrize('advances, expected_status', [(1, 'preparing'), (2, 'done')])
def test_http_cancellation_rejects_preparing_and_done_lines(client, advances, expected_status):
    path = new(client)
    set_stock('kopi', 5)
    added = client.post(path+'/lines', json=payload(item_id='kopi', quantity=2)).json()['snapshot']
    line_key = added['lines'][0]['key']
    assert client.post(path+'/confirm', json=payload(takeaway=False)).status_code == 200
    status = None
    for _ in range(advances):
        status = advance_line_status(line_key)
    assert status == expected_status

    response = client.request('DELETE', path+'/lines/'+line_key, json=payload())

    assert response.status_code == 409
    expected_message = 'being prepared' if expected_status == 'preparing' else 'already ready'
    assert expected_message in response.json()['detail']
    current = client.get(path).json()['snapshot']
    assert current['lines'][0]['key'] == line_key
    assert current['lines'][0]['kitchen_status'] == expected_status
    assert get_stock_status('kopi') == 3


def test_dialogue_cancellation_uses_the_synchronized_kitchen_status_gate(client):
    path = new(client)
    set_stock('kopi', 2)
    added = client.post(path+'/lines', json=payload(item_id='kopi', quantity=2)).json()['snapshot']
    line_key = added['lines'][0]['key']
    assert client.post(path+'/confirm', json=payload(takeaway=False)).status_code == 200
    assert advance_line_status(line_key) == 'preparing'

    response = client.post(
        path+'/messages', json=payload(text='actually the kopi i dun want already')
    )

    assert response.status_code == 200
    assert 'already being prepared' in response.json()['message'].lower()
    assert response.json()['snapshot']['lines'][0]['kitchen_status'] == 'preparing'
    assert get_stock_status('kopi') == 0


def test_session_get_synchronizes_status_after_mock_helper_update(client):
    path = new(client)
    added = client.post(path+'/lines', json=payload(item_id='kopi')).json()['snapshot']
    line_key = added['lines'][0]['key']
    assert client.post(path+'/confirm', json=payload(takeaway=False)).status_code == 200
    assert client.get(path).json()['snapshot']['lines'][0]['kitchen_status'] == 'received'

    assert advance_line_status(line_key) == 'preparing'
    current = client.get(path).json()['snapshot']
    assert current['lines'][0]['kitchen_status'] == 'preparing'


def test_demo_status_route_advances_once_per_request_and_persists_in_process(client):
    path = new(client)
    added = client.post(path+'/lines', json=payload(item_id='kopi')).json()['snapshot']
    line_key = added['lines'][0]['key']
    assert client.post(path+'/confirm', json=payload(takeaway=False)).status_code == 200

    request = payload()
    first = client.post(path+f'/lines/{line_key}/advance-status', json=request)
    replay = client.post(path+f'/lines/{line_key}/advance-status', json=request)

    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert first.json()['snapshot']['lines'][0]['kitchen_status'] == 'preparing'

    second = client.post(path+f'/lines/{line_key}/advance-status', json=payload())
    assert second.status_code == 200
    assert second.json()['snapshot']['lines'][0]['kitchen_status'] == 'done'
    assert client.get(path).json()['snapshot']['lines'][0]['kitchen_status'] == 'done'


def test_demo_status_route_rejects_draft_and_terminal_advancement(client):
    path = new(client)
    draft = client.post(path+'/lines', json=payload(item_id='kopi')).json()['snapshot']
    line_key = draft['lines'][0]['key']

    draft_response = client.post(path+f'/lines/{line_key}/advance-status', json=payload())
    assert draft_response.status_code == 409
    assert 'confirm' in draft_response.json()['detail'].lower()

    assert client.post(path+'/confirm', json=payload(takeaway=False)).status_code == 200
    assert client.post(path+f'/lines/{line_key}/advance-status', json=payload()).status_code == 200
    assert client.post(path+f'/lines/{line_key}/advance-status', json=payload()).status_code == 200

    terminal = client.post(path+f'/lines/{line_key}/advance-status', json=payload())
    assert terminal.status_code == 409
    assert 'already done' in terminal.json()['detail'].lower()
    assert client.get(path).json()['snapshot']['lines'][0]['kitchen_status'] == 'done'


def test_sessions_are_isolated_and_unknown_session_is_not_silently_recreated(client):
    first, second = new(client), new(client)
    client.post(first+'/lines',json=payload(item_id='kopi'))
    assert client.get(second).json()['snapshot']['lines'] == []
    assert client.get('/sessions/'+str(uuid4())).status_code == 404
