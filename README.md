# flask-gatekeeper

A (very) simple banning & rate limiting extension for Flask.

It's not meant to be a replacement for other, more complex banning & rate limiting modules like `flask-Limiter` or `flask-ipban`.

It's simple, does not require any dependancies, and quite fast due to the use of `collections.deque` and minimal storage of information regarding the clients.

## Install

```
pip install flask-gatekeeper
```

## Usage

Here is a demo app showing all the capabilities of flask-gatekeeper : 

```py
from flask import Flask
from flask_gatekeeper import GateKeeper # important

# create our flask app 
app = Flask(__name__)

# add our GateKeeper instance with global rules
gk = GateKeeper(app,ban_rule=[3,60,600],rate_limit_rule=[100,60])

@app.route("/ping")
def ping():
    return "ok",200

@app.route("/login")
def login():
    if password_is_ok():
        return token,200
    else:
        gk.report() # ban if an IP is "reported" 3 times in less than 60s
        return "bad password",401

@app.route("/specific")
@gk.specific(rate_limit_rule=[1,10]) # add another rate limit on top of the global one
def specific():
    return "ok",200

@app.route("/specific")
@gk.specific(rate_limit_rule=[1,10],standalone=True) # route only limited by the specific rule
def specific():
    return "ok",200


@app.route("/bypass")
@gk.bypass # do not apply anything on that route
def bypass():
    return "ok",200


app.run("127.0.0.1",5001)
```
