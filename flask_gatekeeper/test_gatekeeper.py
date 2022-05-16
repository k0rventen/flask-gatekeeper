# tests for flask-gatekeeper
from time import sleep

import pytest
from flask import Flask

from .gatekeeper import GateKeeper

@pytest.fixture()
def flask_server_factory():
    def _flask_server():
        """fixture 'factory' to create test flask servers for GateKeeper"""
        app = Flask(__name__)
        gk = GateKeeper(app, 
                        ip_header="x-my-ip",
                        ban_rule={"count":3,"window":10,"duration":10},
                        rate_limit_rules=[{"count":20,"window":1},{"count":100,"window":10}],
                        excluded_methods=["HEAD"])
        
        @app.route("/ping")
        def ping():
            return "ok", 200

        @app.route("/ban")
        def ban():
            gk.report()
            return "ok", 200

        @app.route("/specific")
        @gk.specific(rate_limit_rules=[{"count":1,"window":2}]) # add a tighter rule here 
        def specific():
            return "ok", 200

        @app.route("/specific-standalone")
        @gk.specific(rate_limit_rules=[{"count":40,"window":5}], standalone=True) # only loose rule here
        def specific_standalone():
            return "ok", 200

        @app.route("/bypass")
        @gk.bypass
        def bypass():
            return "ok", 200

        return app.test_client()
    return _flask_server


def test_gatekeeper_ban(flask_server_factory):
    flask_server = flask_server_factory()

    ip1 = {"x-my-ip": "10.0.0.1"}
    ip2 = {"x-my-ip": "10.0.0.2"}

    for _ in range(2):
        assert flask_server.get("/ban",headers=ip1).status_code == 200 # 2 reports in a 10s window should not trigger a ban 
    assert flask_server.get("/ping",headers=ip1).status_code == 200 # ip1 not banned

    sleep(10)
    for _ in range(3):
        assert flask_server.get("/ban",headers=ip1).status_code == 200 # get reported
    assert flask_server.get("/ping",headers=ip1).status_code == 403 # ip1 is ban
    assert flask_server.get("/ping",headers=ip2).status_code == 200 # but only ip1
    assert "Retry-After" in flask_server.get("/ping",headers=ip1).headers # header is present

    sleep(10)
    assert flask_server.get("/ping",headers=ip1).status_code == 200 # ip1 unbanned

def test_gatekeeper_rate_limit(flask_server_factory):
    flask_server = flask_server_factory()
    # {"count":20,"window":1},{"count":100,"window":10}])
    ip1 = {"x-my-ip": "10.0.1.1"}
    ip2 = {"x-my-ip": "10.0.1.2"}

    # test that all the rules are applied
    for _ in range(20):
        assert flask_server.get("/ping").status_code == 200
    assert flask_server.get("/ping").status_code == 429
    sleep(10)

    for _ in range(10):
        for _ in range(10):
            assert flask_server.get("/ping").status_code == 200
        sleep(.9)
    assert flask_server.get("/ping").status_code == 429
    sleep(10)
    assert flask_server.get("/ping").status_code == 200


def test_gatekeeper_specific(flask_server_factory):
    flask_server = flask_server_factory()
    
    ip1 = {"x-my-ip": "10.0.2.1"}
    ip2 = {"x-my-ip": "10.0.2.2"}

    # This rule is tigher, so only 1 call triggers the rate limit
    assert flask_server.get("/specific",headers=ip1).status_code == 200
    assert flask_server.get("/specific",headers=ip1).status_code == 429
    assert flask_server.get("/specific",headers=ip2).status_code == 200
    sleep(2)
    assert flask_server.get("/specific",headers=ip1).status_code == 200

def test_gatekeeper_specific_standalone(flask_server_factory):
    flask_server = flask_server_factory()
    
    ip1 = {"x-my-ip": "10.0.3.1"}
    ip2 = {"x-my-ip": "10.0.3.2"}

    # This route does not enforce the global rule, so we have a looser rule
    for _ in range(40):
        assert flask_server.get("/specific-standalone",headers=ip1).status_code == 200
    assert flask_server.get("/specific-standalone",headers=ip1).status_code == 429
    assert flask_server.get("/specific-standalone",headers=ip2).status_code == 200
    sleep(5)
    assert flask_server.get("/specific-standalone",headers=ip1).status_code == 200


def test_gatekeeper_bypass(flask_server_factory):
    flask_server = flask_server_factory()
    
    ip1 = {"x-my-ip": "10.0.4.1"}
    for _ in range(30):
        assert flask_server.get("/bypass",headers=ip1).status_code == 200 # we can burst the route
    
    still_not_rate_limited = True # get rate limited
    while still_not_rate_limited:
        still_not_rate_limited = flask_server.get("/ping",headers=ip1).status_code == 200
    
    assert flask_server.get("/bypass",headers=ip1).status_code == 200 # but we can still access the bypass

def test_gatekeeper_methods(flask_server_factory):
    flask_server = flask_server_factory()
    for _ in range(30):
        assert flask_server.head("/ping").status_code == 200 # we can burst the route
