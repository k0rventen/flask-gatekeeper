# flask-gatekeeper

A simple banning & rate limiting extension for Flask.

[![PyPI](https://img.shields.io/pypi/v/flask-gatekeeper.svg)](https://pypi.org/project/flask-gatekeeper/)


It's not meant to be a replacement for other, more complex banning & rate limiting modules like `flask-Limiter` or `flask-ipban`.

It has the following specificities:

- no dependencies,
- quite fast due to the use of `collections.deque`,
- in-memory storage (no persistence across restarts).

Full documentation can be found here: https://k0rventen.github.io/flask-gatekeeper/

## Getting started

### Install

```
pip install flask-gatekeeper
```

### Sample usage

Here is a demo app showing the main capabilities of flask-gatekeeper : 


```py

# import flask-gatekeeper along flask
from flask import Flask
from flask_gatekeeper import GateKeeper 

app = Flask(__name__)
gk = GateKeeper(app, # or use .init_app(app) later 
                ip_header="x-my-ip", # optionnal header to use for the client IP (e.g if using a reverse proxy)
                ban_rule={"count":3,"window":10,"duration":600}, # 3 reports in a 10s window will ban for 600s
                rate_limit_rules=[{"count":20,"window":1},{"count":100,"window":10}], # rate limiting will be applied if over 20 requests in 1s or 100 requests in 10s
                excluded_methods=["HEAD"]) # do not add HEAD requests to the tally 

# By default, all routes will use the rate limiting we defined above:

@app.route("/ping") # this route is rate limited by the global rule
def ping():
    return "ok",200

@app.route("/login") # also rate limited by the global rule
def login():
    if request.json.get("password") == "password":
        return token,200
    else:
        gk.report() # report the request's IP, after 3 reports in this case the IP will be banned 
        return "bad password",401

# we can specify different rate limiting rules using decorators

@app.route("/global_plus_specific")
@gk.specific(rate_limit_rules=[{"count":1,"window":2}]) # add another rate limit on top of the global one (to avoid bursting for example)
def specific():
    return "ok",200

@app.route("/standalone")
@gk.specific(rate_limit_rules=[{"count":10,"window":3600}],standalone=True) # rate limited only by this rule
def standalone():
    return "ok",200

@app.route("/bypass")
@gk.bypass # do not apply anything on that route
def bypass():
    return "ok",200


app.run("127.0.0.1",5000)
```

Copy that in a file or your REPL, then try the various endpoints.
