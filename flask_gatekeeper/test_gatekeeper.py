from random import randint
from time import sleep

import pytest
from flask import Flask

from .gatekeeper import GateKeeper


def test_gk_internals_ban():
    """test internal functions of the ban mechanism
    """
    ban_rule = [randint(2, 5), randint(2, 5), randint(5, 8)]
    ip1 = "10.0.1.1"
    ip2 = "10.0.1.2"
    test_gk = GateKeeper(ban_rule=ban_rule)
    test_gk._create(ip1)
    test_gk._create(ip2)

    for _ in range(ban_rule[0] - 1):
        test_gk.report(ip1)

    # We should not be banned
    assert test_gk.is_banned(ip1) is False

    # add one more
    test_gk.report(ip1)

    # now we should
    assert test_gk.is_banned(ip1) is True

    # but not ip2
    assert test_gk.is_banned(ip2) is False

    # w8 for ban to lift
    sleep(ban_rule[2])
    assert test_gk.is_banned(ip1) is False


def test_gk_internals_rate_limit():
    """test internal functions of the rate limit mechanism
    """
    rate_limit_rule = [randint(10, 20), randint(4, 8)]

    ip1 = "10.0.1.1"
    ip2 = "10.0.1.2"
    test_gk = GateKeeper(rate_limit_rule=rate_limit_rule)
    test_gk._create(ip1)
    test_gk._create(ip2)

    for _ in range(rate_limit_rule[0] - 1):
        test_gk._add(ip1)

    # we should be ok
    assert test_gk.is_rate_limited(ip1) is False

    # make one more
    test_gk._add(ip1)
    assert test_gk.is_rate_limited(ip1) is True

    # not ip2
    assert test_gk.is_rate_limited(ip2) is False

    # if we w8 for the window we are ok
    sleep(rate_limit_rule[1])
    assert test_gk.is_rate_limited(ip1) is False


@pytest.fixture()
def flask_server():
    """create a dummy flask server
    """
    app = Flask(__name__)
    gk = GateKeeper(app, ban_rule=[3, 60, 10], rate_limit_rule=[5, 2])

    @app.route("/ping")
    def ping():
        return "ok", 200

    @app.route("/ban")
    def ban():
        gk.report()
        return "ok", 200

    @app.route("/specific")
    @gk.specific(rate_limit_rule=[1, 10])
    def specific():
        return "ok", 200

    @app.route("/specific-standalone")
    @gk.specific(rate_limit_rule=[10, 10], standalone=True)
    def specific_standalone():
        return "ok", 200

    @app.route("/bypass")
    @gk.bypass
    def bypass():
        return "ok", 200

    yield app.test_client()


def test_gk_on_flask_server(flask_server):
    """test gatekeeper against a "real" server
    """
    # global rate limiting
    # We can request until getting rate limited w8 and retry
    for _ in range(5):
        assert flask_server.get("/ping").status_code == 200

    assert flask_server.get("/ping").status_code == 429
    sleep(3)
    assert flask_server.get("/ping").status_code == 200

    # route specific additionnal rate limit
    # This rule is tigher, so onely 1 call triggers the rate limit
    assert flask_server.get("/specific").status_code == 200
    assert flask_server.get("/specific").status_code == 429

    # route specific, standalone rate limit
    # This route does not enforce the global rule, so we have a looser rule
    for _ in range(10):
        assert flask_server.get("/specific-standalone").status_code == 200
    assert flask_server.get("/specific-standalone").status_code == 429

    # ban
    # We can report 3 times this IP, then following calls will be banned
    sleep(3)
    for _ in range(3):
        assert flask_server.get("/ban").status_code == 200
    assert flask_server.get("/ping").status_code == 403

    # bypass
    # We should not have any rate limiting nor banning here
    for _ in range(30):
        assert flask_server.get("/bypass").status_code == 200


@pytest.fixture()
def flask_server_headers():
    """creates a dummy flask server
    """
    app = Flask(__name__)
    gk = GateKeeper(app, ban_rule=[3, 60, 10], ip_header="x-my-ip")

    @app.route("/ping")
    def ping():
        return "ok", 200

    @app.route("/ban")
    def ban():
        gk.report()
        return "ok", 200

    yield app.test_client()


def test_gk_on_flask_server_header(flask_server_headers):
    """test the ip_header function of gatekeeper
    """
    headers1 = {"x-my-ip": "10.0.1.1"}
    headers2 = {"x-my-ip": "10.0.1.2"}
    noheaders = {"no-x-my-ip": "10.0.1.3"}

    assert flask_server_headers.get(
        "/ping", headers=headers1).status_code == 200

    for _ in range(3):
        assert flask_server_headers.get(
            "/ban", headers=headers1).status_code == 200
    assert flask_server_headers.get(
        "/ping", headers=headers1).status_code == 403

    assert flask_server_headers.get(
        "/ping", headers=headers2).status_code == 200

    for _ in range(3):
        assert flask_server_headers.get(
            "/ban", headers=noheaders).status_code == 200
    assert flask_server_headers.get(
        "/ping", headers=noheaders).status_code == 403
