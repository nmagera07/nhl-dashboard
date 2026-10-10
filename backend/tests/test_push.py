"""push.py (subscription validation) and the /push API endpoints."""

import pytest

import push

FCM = "https://fcm.googleapis.com/fcm/send/abc123"
P256DH = "B" + "A" * 86  # 87 base64url chars, like a real 65-byte key
AUTH = "A" * 22


class TestEndpointAllowlist:
    @pytest.mark.parametrize("url", [
        FCM,
        "https://updates.push.services.mozilla.com/wpush/v2/xyz",
        "https://web.push.apple.com/QGx",
        "https://jmt17.google.com/fcm/send/abc",
        "https://wns2-par02p.notify.windows.com/w/?token=abc",
    ])
    def test_accepts_browser_push_services(self, url):
        assert push.is_allowed_endpoint(url)

    @pytest.mark.parametrize("url", [
        "http://fcm.googleapis.com/fcm/send/abc",       # not https
        "https://evil.example.com/fcm.googleapis.com",  # host is what counts
        "https://fcm.googleapis.com.evil.com/x",         # suffix trick
        "https://notify.windows.com.evil.com/x",
        "https://169.254.169.254/latest/meta-data",      # cloud metadata
        "https://fcm.googleapis.com:8443/x",             # odd port
        "not a url",
    ])
    def test_rejects_everything_else(self, url):
        assert not push.is_allowed_endpoint(url)

    def test_key_shapes(self):
        assert push.valid_keys(P256DH, AUTH)
        assert not push.valid_keys("short", AUTH)
        assert not push.valid_keys(P256DH, "has spaces in it!!!!!!")


def _body(**overrides):
    body = {"endpoint": FCM, "keys": {"p256dh": P256DH, "auth": AUTH}, "teams": ["pit"]}
    body.update(overrides)
    return body


class TestSubscribeEndpoint:
    def test_saves_the_subscription_with_normalized_teams(self, client, db_router):
        db_router.when("from teams where team_abbrev = any", lambda params: [{"team_abbrev": t} for t in params[0]])
        db_router.when("insert into push_subscriptions", None)

        response = client.post("/push/subscriptions", json=_body(teams=["pit", "PIT", "bos"]))

        assert response.status_code == 204
        _, params = db_router.calls[-1]
        assert params[0] == FCM and params[3] == ["BOS", "PIT"] and params[4:] == (True, True)

    def test_rejects_a_non_push_endpoint_before_touching_the_database(self, client, db_router):
        response = client.post("/push/subscriptions", json=_body(endpoint="https://attacker.example/hook"))

        assert response.status_code == 400
        assert db_router.calls == []

    def test_rejects_unknown_teams(self, client, db_router):
        db_router.when("from teams where team_abbrev = any", [{"team_abbrev": "PIT"}])

        response = client.post("/push/subscriptions", json=_body(teams=["PIT", "XYZ"]))

        assert response.status_code == 400
        assert not any("insert" in q.lower() for q, _ in db_router.calls)

    def test_rejects_bad_keys_and_empty_team_lists(self, client, db_router):
        assert client.post("/push/subscriptions", json=_body(keys={"p256dh": "x", "auth": AUTH})).status_code == 400
        assert client.post("/push/subscriptions", json=_body(teams=[])).status_code == 422
        assert db_router.calls == []

    def test_unsubscribe(self, client, db_router):
        db_router.when("delete from push_subscriptions", None)

        response = client.request("DELETE", "/push/subscriptions", json={"endpoint": FCM})

        assert response.status_code == 204
        assert db_router.calls[-1][1] == (FCM,)

    def test_config_exposes_only_the_public_key(self, client, monkeypatch):
        monkeypatch.setattr(push, "VAPID_PUBLIC_KEY", "BPublicKey")
        monkeypatch.setattr(push, "VAPID_PRIVATE_KEY", "secret")

        body = client.get("/push/config").json()

        assert body == {"vapid_public_key": "BPublicKey", "enabled": True}
