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
gk = GateKeeper(app=app, # link to our app now or use .init_app() later.
                ban_rule=[3,60,600], # will ban for 600s if an IP is reported using `report()` 3 times in a 60s window.
                rate_limit_rule=[100,60] # will rate limit if an IP makes more than 100 request in a 60s window.
                ) 


@app.route("/ping") # this route is rate limited by the global rule
def ping():
    return "ok",200

@app.route("/login") # also rate limited by the global rule
def login():
    if password_is_ok():
        return token,200
    else:
        gk.report() # report that IP
        return "bad password",401

@app.route("/global_plus_specific")
@gk.specific(rate_limit_rule=[1,10]) # add another rate limit on top of the global one
def specific():
    return "ok",200

@app.route("/standalone_specific")
@gk.specific(rate_limit_rule=[1,10],standalone=True) # rate limited only by this rule
def specific():
    return "ok",200


@app.route("/bypass")
@gk.bypass # do not apply anything on that route
def bypass():
    return "ok",200


app.run("127.0.0.1",5000)
```
