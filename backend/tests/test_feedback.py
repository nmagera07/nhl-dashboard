"""POST /feedback and feedback.clean()."""

import feedback


def test_clean_trims_strips_control_characters_and_caps_length():
    assert feedback.clean("  hi\x00 there\n ok \x07", 100) == "hi there\n ok"
    assert feedback.clean("x" * 50, 10) == "x" * 10
    assert feedback.clean("   ", 10) is None and feedback.clean(None, 10) is None


class TestEndpoint:
    def test_stores_an_idea(self, client, db_router):
        db_router.when("insert into feedback", None)
        response = client.post("/feedback", json={"kind": "idea", "message": "  Add a playoff bracket!  ",
                                                  "contact": "@fan", "page": "/playoffs"})
        assert response.status_code == 200 and response.json() == {"ok": True}
        sql, params = db_router.calls[-1]
        assert params == ("idea", "Add a playoff bracket!", "@fan", "/playoffs")

    def test_a_filled_honeypot_is_thanked_but_not_stored(self, client, db_router):
        response = client.post("/feedback", json={"kind": "bug", "message": "buy pills", "website": "spam.example"})
        assert response.status_code == 200 and db_router.calls == []

    def test_rejects_bad_input(self, client, db_router):
        assert client.post("/feedback", json={"kind": "rant", "message": "hello"}).status_code == 422
        assert client.post("/feedback", json={"kind": "idea", "message": "hi"}).status_code == 422
        assert client.post("/feedback", json={"kind": "idea", "message": "\x00\x00\x00 "}).status_code == 400
        assert db_router.calls == []

    def test_is_rate_limited(self, client, db_router):
        db_router.when("insert into feedback", None)
        codes = [client.post("/feedback", json={"kind": "idea", "message": f"idea {i}"}).status_code for i in range(6)]
        assert codes == [200] * 5 + [429]
