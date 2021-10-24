flask-gatekeeper
================

A (very) simple banning & rate limiting extension for Flask.

|PyPI|

It’s not meant to be a replacement for other, more complex banning &
rate limiting modules like ``flask-Limiter`` or ``flask-ipban``.

It has the following specificities: - no dependencies, - quite fast due
to the use of ``collections.deque``, - in-memory configuration (no
persistence)

Getting started
---------------

Install
~~~~~~~

::

   pip install flask-gatekeeper

Basic usage
~~~~~~~~~~~

Import flask-gatekeeper along flask

.. code:: py

   from flask import Flask
   from flask_gatekeeper import GateKeeper

then after creating the flask app, create the Gatekeeper instance:

.. code:: py

   gk = GateKeeper(app=app, # link to our app now or use .init_app(app) later.
                   ip_header="X-Forwarded-For", # optionnaly specify a header for the IP (e.g. if using a reverse proxy in front)
                   ban_rule=[3,60,600], # will ban for 600s if an IP is reported using `.report()` 3 times in a 60s window.
                   rate_limit_rule=[100,60]) # will rate limit if an IP makes more than 100 request in a 60s window.

By default, routes will use the rate limiting of the previously created
instance:

-  Rate limiting is applied automatically by counting the number of
   requests.
-  Banning uses the ``.report()`` function. This function can be used
   when a provided password is incorrect, or when you define an abnormal
   behavior that should lead to banning.

.. code:: py

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

Finally, you can specify custom rules for a given route, using
decorators:

.. code:: py

   @app.route("/global_plus_specific")
   @gk.specific(rate_limit_rule=[1,10]) # add another rate limit on top of the global one (to avoid bursting for example)
   def specific():
       return "ok",200

   @app.route("/standalone")
   @gk.specific(rate_limit_rule=[1,10],standalone=True) # rate limited only by this rule
   def standalone():
       return "ok",200

   @app.route("/bypass")
   @gk.bypass # do not apply anything on that route
   def bypass():
       return "ok",200

Complete example
~~~~~~~~~~~~~~~~

Here is a demo app showing the main capabilities of flask-gatekeeper :

.. code:: py

   from flask import Flask, request
   from flask_gatekeeper import GateKeeper


   app = Flask(__name__)

   # add our GateKeeper instance with global rules
   gk = GateKeeper(app=app, # link to our app now or use .init_app(app) later.
                   # ip_header="X-Forwarded-For", # optionnaly specify a header for the IP (e.g. if using a reverse proxy in front)
                   ban_rule=[3,60,600], # will ban for 600s if an IP is reported using `gk.report()` 3 times in a 60s window.
                   rate_limit_rule=[100,60]) # will rate limit if an IP makes more than 100 request in a 60s window.


   @app.route("/ping") # this route is rate limited by the global rule
   def ping():
       return "ok",200

   @app.route("/login") # also rate limited by the global rule
   def login():
       if request.json.get("password") == "password":
           return token,200
       else:
           gk.report() # report that IP
           return "bad password",401

   @app.route("/global_plus_specific")
   @gk.specific(rate_limit_rule=[1,10]) # add another rate limit on top of the global one (to avoid bursting for example)
   def specific():
       return "ok",200

   @app.route("/standalone")
   @gk.specific(rate_limit_rule=[1,10],standalone=True) # rate limited only by this rule
   def standalone():
       return "ok",200

   @app.route("/bypass")
   @gk.bypass # do not apply anything on that route
   def bypass():
       return "ok",200


   app.run("127.0.0.1",5000)

Copy that in a file or your REPL, then try the various endpoints.

.. |PyPI| image:: https://img.shields.io/pypi/v/flask-gatekeeper.svg
   :target: https://pypi.org/project/flask-gatekeeper/
