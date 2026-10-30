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
        assert params[0] == FCM and params[3] == ["BOS", "PIT"] and params[4:] == (True, True, True, True, False)  # game alerts on, value alerts opt-in

    def test_saves_the_alert_settings(self, client, db_router):
        db_router.when("from teams where team_abbrev = any", lambda params: [{"team_abbrev": t} for t in params[0]])
        db_router.when("insert into push_subscriptions", None)
        body = _body(starts=False, goals=True, goals_against=False, finals=True, value=True)
        assert client.post("/push/subscriptions", json=body).status_code == 204
        assert db_router.calls[-1][1][4:] == (False, True, False, True, True)  # starts, goals, goals against, finals, value

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


class TestSend:
    def test_sends_with_high_urgency_and_returns_the_status(self, monkeypatch):
        import pywebpush

        captured = {}

        class Response:
            status_code = 201

        def fake_webpush(**kwargs):
            captured.update(kwargs)
            return Response()

        monkeypatch.setattr(pywebpush, "webpush", fake_webpush)

        status = push.send({"endpoint": FCM, "p256dh": P256DH, "auth": AUTH}, {"title": "t"}, ttl=900)

        assert status == 201
        assert captured["headers"] == {"Urgency": "high"} and captured["ttl"] == 900

    def test_a_dropped_subscription_raises_gone(self, monkeypatch):
        import pywebpush

        class Gone:
            status_code = 410

        def fake_webpush(**kwargs):
            raise pywebpush.WebPushException("gone", response=Gone())

        monkeypatch.setattr(pywebpush, "webpush", fake_webpush)

        with pytest.raises(push.SubscriptionGone):
            push.send({"endpoint": FCM, "p256dh": P256DH, "auth": AUTH}, {"title": "t"})


class TestRenewEndpoint:
    NEW = "https://fcm.googleapis.com/fcm/send/new456"

    def _renew(self, client, **overrides):
        body = {"old_endpoint": FCM, "endpoint": self.NEW, "keys": {"p256dh": P256DH, "auth": AUTH}, **overrides}
        return client.post("/push/subscriptions/renew", json=body)

    def test_moves_the_subscription_keeping_its_settings(self, client, db_router):
        db_router.when("delete from push_subscriptions", None)
        db_router.when("update push_subscriptions set endpoint", {"endpoint": self.NEW})
        assert self._renew(client).status_code == 204
        update = next(p for q, p in db_router.calls if "UPDATE push_subscriptions" in q)
        assert update == (self.NEW, P256DH, AUTH, FCM)  # only the endpoint and keys change

    def test_unknown_old_subscription_is_404(self, client, db_router):
        db_router.when("delete from push_subscriptions", None)
        db_router.when("update push_subscriptions set endpoint", None)
        assert self._renew(client).status_code == 404

    def test_new_endpoint_must_be_a_push_service(self, client, db_router):
        assert self._renew(client, endpoint="https://attacker.example/hook").status_code == 400
        assert not db_router.calls


class TestReceipts:
    def _receipt(self, client, **overrides):
        return client.post("/push/receipts", json={"endpoint": FCM, "key": "goal:2026020194:FLA:4-1", **overrides})

    def test_stamps_the_devices_own_delivery(self, client, db_router):
        db_router.when("select 1 from push_subscriptions", {"?column?": 1})
        db_router.when("update push_deliveries set received_at", None)
        assert self._receipt(client).status_code == 204
        update = next(p for q, p in db_router.calls if "UPDATE push_deliveries" in q)
        assert update == ("goal:2026020194:FLA:4-1", push.device_label(FCM))

    def test_an_unsubscribed_endpoint_changes_nothing(self, client, db_router):
        db_router.when("select 1 from push_subscriptions", None)
        assert self._receipt(client).status_code == 204
        assert not any("UPDATE" in q for q, _ in db_router.calls)

    def test_rejects_odd_keys_and_non_push_endpoints(self, client, db_router):
        assert self._receipt(client, key="goal; DROP TABLE x").status_code == 422
        assert self._receipt(client, endpoint="https://attacker.example/hook").status_code == 400
        assert not db_router.calls
