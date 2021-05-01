"""A (very) simple banning & rate limiting extension for Flask.
"""
import time
from collections import deque
from functools import wraps

from flask import abort, request,Flask

class IP:
    def __init__(self, ban_count,rate_count):
        """IP record that keeps track of reports and requests made by that IP.

        Args:
            ban_count (int): number of reports to keep
            rate_count (int): number of requets to keep
        """
        self.ban_active = False
        self.ban_entries = deque(maxlen=ban_count)
        self.rate_entries = deque(maxlen=rate_count)

        self.add_report = lambda: self.ban_entries.append(int(time.time()))
        self.add_entry = lambda: self.rate_entries.append(int(time.time()))


class GateKeeper:
    def __init__(self, app=None, ban_rule=None,rate_limit_rule=None, ip_header=None):
        """GateKeeper instance around a flask app.

        Provides rate-limiting & ban functions.

        Rate limiting is done automatically, 
        but you have to specify when an IP should be reported, using `.report()` (usually in your login route when the creds are not valid)


        ban_rule should be a list [<ban_count>,<ban_window>,<ban_duration>] where
        - ban_count is the number of reports before actually banning the IP
        - ban_window is the rolling time window to look for ban reports
        - ban_duration is the duration of the ban in seconds.

        rate_limit_rule should be a list [<rate_count>,<rate_window>] where
        - rate_count is the maximum number of requests 
        - rate_window is the rolling time window for the rate count.

        As an example, ban_rule=[3,60,600],rate_limit_rule=[100,10] would:
        - ban any IP for 600s if it has been reported 3 times in the last 60s,
        - rate limit any IP if it has made more than 100 requests in the last 10s.

        If you do not set ban_rule, no banning will be done. Same goes for the rate limiting.

        Requests made during the rate limiting period or ban period are not counted.

        You can delay the init by omitting `app` here and calling `.init_app()` later.

        Args:
            app (flask.Flask, optional): Flask app to wrap around. Defaults to None.
            ban_rule (list, optional): Global ban rule for the whole app. Defaults to None.
            rate_limit_rule (list, optional): Global rate limit rule for the whole app. Defaults to None.
            ip_header (str, optional): Header to check for the IP. useful with a proxy that will add a header with the ip of the actual client. Defaults to request.remote_addr.
        """
        if ban_rule:
            self.ban_enabled = True
            self.ban_count = ban_rule[0]
            self.ban_duration = ban_rule[1]
            self.ban_window = ban_rule[2]
        else:
            self.ban_enabled = False

        if rate_limit_rule:
            self.rate_limit_enabled = True
            self.rate_count = rate_limit_rule[0]
            self.rate_window = rate_limit_rule[1]
        else:
            self.rate_limit_enabled = False

        
        self.ip_header = ip_header
        self.ips = {}
        if app:
            self.init_app(app)

    def _get_ip(self) -> str:
        """Returns the IP of the client
        """
        if self.ip_header:
            return request.headers.get(self.ip_header)
        return request.remote_addr

    def _create(self, ip):
        """add the IP to the tracked dict
        """
        if not ip in self.ips:
            self.ips[ip] = IP(ban_count=self.ban_count if self.ban_enabled else 0,
                              rate_count=self.rate_count if self.rate_limit_enabled else 0)

    def _before_request(self):
        """Function which runs before every request
        """
        ip = self._get_ip()
        self._create(ip)

        if self.ban_enabled and self.is_banned(ip):
            return "banned for {}s".format(self.banned_for(ip)), 403
        if self.rate_limit_enabled and self.is_rate_limited(ip):
            return "rate limited for {}s".format(self.rate_limited_for(ip)), 429
        self._add(ip)

    def _add(self, ip):
        """add a request to this IP tracked
        """
        self.ips[ip].add_entry()


    def banned_for(self,ip) -> int:
        """returns the time in seconds this IP is banned for"""
        return max((self.ips[ip].ban_entries[-1] + self.ban_duration) - int(time.time()), 1)

    def rate_limited_for(self,ip) -> int:
        """returns the time in seconds this IP is rate limited for"""
        rate_entries = [e for e in self.ips[ip].rate_entries if  e >= time.time() - self.rate_window]

        return int((rate_entries[0] + self.rate_window) - time.time()) if rate_entries else 1


    def is_banned(self,ip) -> bool:
        """returns whether this IP is currently banned or not
        """
        # have we too much counts for our interval
        if not self.ips[ip].ban_active and len([e for e in self.ips[ip].ban_entries if e >= int(time.time())  - self.ban_window]) >= self.ban_count:
            self.ips[ip].ban_active = True
        # is the last entry still in our ban duration ?
        if self.ips[ip].ban_active:
            if int(time.time())  <= self.ips[ip].ban_entries[-1] + self.ban_duration:
                return True
            else:
                self.ips[ip].ban_active = False

        return False

    def is_rate_limited(self,ip) -> bool:
        """returns whether this IP is currently rate limited or not
        """
        # in the last rate_interval, did we had more entries than rate_count ?
        if len([e for e in self.ips[ip].rate_entries if  e >= int(time.time()) - self.rate_window]) >= self.rate_count:
            return True
        return False

    def init_app(self, app):
        """add our before request to flask now
        """
        app.before_request(self._before_request)

    def report(self,ip=None):
        """Report an IP. If no ip arg is provided, uses the ip_header arg provided to the GateKeeper instance
        """
        client_ip = ip or self._get_ip()
        self._add(client_ip)
        self.ips[client_ip].add_report()


    def specific(self,rate_limit_rule=None,ip_header=None):
        """Route specific Gatekeeper. Only supports rate limiting.
        Note that this _does not_ disable the global GateKeeper on this route, so having a looser rate limit rule here is pretty much useless.
        
        """
        specific_gk = GateKeeper(rate_limit_rule=rate_limit_rule,ip_header=ip_header)

        def decorator(fn):
            @wraps(fn)
            def wrapper(*args, **kwargs):

                # We reproduce the same behavior as our _before_request func here
                # but for the gk instance tied to this route
                ip = specific_gk._get_ip()
                specific_gk._create(ip)

                if specific_gk.rate_limit_enabled and specific_gk.is_rate_limited(ip):
                    return "rate limited for {}s".format(specific_gk.rate_limited_for(ip)), 429

                specific_gk._add(ip)
                return fn(*args, **kwargs)
            return wrapper
        return decorator


if __name__ == "__main__":
    app = Flask(__name__)
    gk = GateKeeper(app,ban_rule=[3,60,600],rate_limit_rule=[100,60])

    @app.route("/ping")
    def ping():
        return "ok",200

    @app.route("/ban")
    def ban():
        gk.report()
        return "ok",200

    @app.route("/specific")
    @gk.specific(rate_limit_rule=[1,10])
    def specific():
        return "ok",200

    app.run("127.0.0.1",5001)