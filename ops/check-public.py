"""Read-only public transport checks; never sends keys or signed requests over HTTP."""
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ORIGIN = 'https://memory.useroot.xyz'
REPORT = Path(__file__).resolve().parents[1] / 'results/hosted-memory.json'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(path, *, http=False, headers=None, body=None):
    url = (ORIGIN.replace('https:', 'http:') if http else ORIGIN) + path
    opener = build_opener(NoRedirect())  # Default certificate validation stays enabled.
    try:
        response = opener.open(Request(url, data=body, headers=headers or {}), timeout=30)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.headers, response.read()


def check():
    evidence = {}
    saved = json.loads(REPORT.read_text())
    context_path = f"/v0/projects/{saved['projectId']}/context"
    for label, headers in (
        ('plainHttpRedirect', {}),
        ('spoofedHttpsHeaderRedirect', {'X-Forwarded-Proto': 'https'}),
        ('spoofedForwardedHeaderRedirect', {'Forwarded': 'proto=https', 'X-Forwarded-Ssl': 'on'}),
    ):
        status, response_headers, _ = request('/head', http=True, headers=headers)
        assert status in (301, 302, 307, 308), (label, status)
        assert response_headers.get('Location') == ORIGIN + '/head', label
        evidence[label] = status
    status, _, body = request('/healthz')
    assert status == 200 and json.loads(body) == {'status': 'alive'}
    evidence['certificateValidatedLiveness'] = status
    status, _, body = request('/head')
    assert status == 200, ('head', status)
    assert json.loads(body)['checkpointDigest'] == saved['acceptedDigest']
    evidence['acceptedHead'] = status
    for label, path, headers, body, expected in (
        ('wrongOrigin', context_path, {'Origin': 'https://untrusted.invalid', 'Content-Type': 'application/json'}, b'{}', 403),
        ('unsignedRead', context_path, {'Content-Type': 'application/json'}, b'{}', 400),
        ('oversizedBody', context_path, {'Content-Type': 'application/json'}, b'x' * 65537, 413),
        ('noDemoKeys', '/demo-config', {}, None, 404),
    ):
        status, _, _ = request(path, headers=headers, body=body)
        assert status == expected, (label, status)
        evidence[label] = status
    return evidence


if __name__ == '__main__':
    result = check()
    report = json.loads(REPORT.read_text())
    report['publicTransportChecks'] = result
    report['checks']['publicTransportBoundaries'] = True
    REPORT.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(result, indent=2))
