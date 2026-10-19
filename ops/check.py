"""Public deployment smoke check. Does not invoke LLM or quantum calculations."""
import argparse
import uuid

import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://139.196.11.38:8889')
    parser.add_argument('--api-only', action='store_true', help='Check an internal gateway before the public frontend is enabled')
    args = parser.parse_args()
    base = args.url.rstrip('/')
    session = requests.Session()
    if not args.api_only:
        response = session.get(base + '/', timeout=15)
        response.raise_for_status()
        assert '<div id="app"></div>' in response.text, 'Unexpected frontend document'
        response = session.get(base + '/chat', timeout=15)
        response.raise_for_status()
        assert '<div id="app"></div>' in response.text, 'SPA route fallback failed'
    response = session.get(base + '/api/health/server', timeout=15)
    assert response.status_code == 401, 'API must require authentication'
    response = session.post(base + '/api/auth/guest', json={}, timeout=15)
    response.raise_for_status()
    session.headers['Authorization'] = 'Bearer ' + response.json()['token']
    for endpoint in ['/api/health/server', '/api/tools', '/api/conversations']:
        response = session.get(base + endpoint, timeout=15)
        response.raise_for_status()
        print('PASS', endpoint)
    title = 'deployment-smoke-' + uuid.uuid4().hex[:8]
    response = session.post(base + '/api/conversations', json={'title': title, 'model': 'default'}, timeout=15)
    response.raise_for_status()
    record = response.json()
    conversation_id = record['id']
    try:
        response = session.get(base + '/api/conversations/' + conversation_id, timeout=15)
        response.raise_for_status()
        assert response.json()['title'] == title, 'Conversation persistence failed'
        print('PASS conversation persistence')
    finally:
        session.delete(base + '/api/conversations/' + conversation_id, timeout=15).raise_for_status()
    print('PASS authentication, tools and persistent database' if args.api_only else 'PASS frontend, SPA routing, authentication, tools and persistent database')


if __name__ == '__main__':
    main()
