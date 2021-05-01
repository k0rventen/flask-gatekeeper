# flask-gatekeeper

A (very) simple banning & rate limiting extension for Flask.

It's not meant to be a remplacement for other, more complex banning & rate limiting modules like `flask-Limiter` or `flask-ipban`.

It's simple, does not require any dependancies, and quite fast due to the use of `collections.deque`.

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

@app.route("/ping") # This route is rate limited
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
@gk.specific(rate_limit_rule=[1,10]) # add a route specific, tighter rate limit
def specific():
    return "ok",200



 app.run("127.0.0.1",5001)
```
