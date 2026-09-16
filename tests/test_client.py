import json

import responses

from opening_divergence.client import ExplorerAuthError, ExplorerClient


def test_query_raises_auth_error_without_token(tmp_path):
    client = ExplorerClient(token=None, cache_dir=tmp_path)
    try:
        client.query("lichess", {"play": "e2e4"})
        assert False, "expected ExplorerAuthError"
    except ExplorerAuthError as e:
        assert "LICHESS_TOKEN" in str(e)


@responses.activate
def test_query_sends_bearer_token_and_caches(tmp_path):
    payload = {"white": 10, "draws": 5, "black": 5, "moves": []}
    responses.add(
        responses.GET,
        "https://explorer.lichess.org/lichess",
        json=payload,
        status=200,
    )
    client = ExplorerClient(token="secret-token", cache_dir=tmp_path, min_interval=0)
    result = client.query("lichess", {"play": "e2e4"})
    assert result == payload
    assert len(responses.calls) == 1
    assert responses.calls[0].request.headers["Authorization"] == "Bearer secret-token"

    # Second call with identical params should hit the cache, not the network.
    result2 = client.query("lichess", {"play": "e2e4"})
    assert result2 == payload
    assert len(responses.calls) == 1
    assert client.cache_hits == 1

    cached_files = list((tmp_path / "lichess").glob("*.json"))
    assert len(cached_files) == 1
    with open(cached_files[0]) as f:
        on_disk = json.load(f)
    assert on_disk["response"] == payload


@responses.activate
def test_query_raises_auth_error_on_401_with_token(tmp_path):
    responses.add(
        responses.GET,
        "https://explorer.lichess.org/masters",
        status=401,
    )
    client = ExplorerClient(token="bad-token", cache_dir=tmp_path, min_interval=0)
    try:
        client.query("masters", {"play": "d2d4"})
        assert False, "expected ExplorerAuthError"
    except ExplorerAuthError:
        pass


@responses.activate
def test_query_retries_on_429_then_succeeds(tmp_path):
    payload = {"white": 1, "draws": 1, "black": 1, "moves": []}
    responses.add(
        responses.GET,
        "https://explorer.lichess.org/lichess",
        status=429,
        headers={"Retry-After": "0"},
    )
    responses.add(responses.GET, "https://explorer.lichess.org/lichess", json=payload, status=200)
    client = ExplorerClient(token="t", cache_dir=tmp_path, min_interval=0)
    result = client.query("lichess", {"play": "e2e4"})
    assert result == payload
    assert len(responses.calls) == 2
