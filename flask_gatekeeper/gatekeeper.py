"""A (very) simple banning & rate limiting extension for Flask.
"""
import time
from collections import deque
from functools import wraps

from flask import request


class IP:
    def __init__(self, ban_count, rate_count):
        """IP record that keeps track of reports and requests made by that IP.

        Args:
            ban_count (int): number of reports to keep
            rate_count (int): number of requets to keep
        """
        self.ban_active = False
        self.ban_entries = deque(maxlen=ban_count)
        self.rate_entries = deque(maxlen=rate_count)

        self.add_report = lambda: self.ban_entries.append(time.time())
        self.add_entry = lambda: self.rate_entries.append(time.time())


class GateKeeper:
    def __init__(self, app=None, ban_rule=None, rate_limit_rule=None, ip_header=None):
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

        As an example, ban_rule=[3,60,600], rate_limit_rule=[100,10] would:
        - ban any IP for 600s if it has been reported 3 times in the last 60s,
        - rate limit any IP if it has made more than 100 requests in the last 10s.

        If you do not set ban_rule, no banning will be done. Same goes for the rate limiting.

        Requests made during the rate limiting period or ban period are not counted.

        You can delay the init by omitting `app` here and calling `.init_app()` later.

        If you set ip_header but the header is not present in the request, it falls back to a "no-ip" string, and any request made by potentially different clients will be added to this.
        
        Args:
            app (flask.Flask, optional): Flask app to wrap around. Defaults to None.
            ban_rule (list, optional): Global ban rule for the whole app. Defaults to None.
            rate_limit_rule (list, optional): Global rate limit rule for the whole app. Defaults to None.
            ip_header (str, optional): Header to check for the IP. useful with a proxy that will add a header with the ip of the actual client. Defaults to request.remote_addr.
        """
        if ban_rule:
            self.ban_enabled = True
            self.ban_count = ban_rule[0]
            self.ban_window = ban_rule[1]
            self.ban_duration = ban_rule[2]
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
        self.bypass_routes = set()
        if app:
            self.init_app(app)

    def _get_ip(self) -> str:
        """Returns the IP of the client
        """
        if self.ip_header:
            return request.headers.get(self.ip_header) or "no-ip"

        return request.remote_addr

    def _create(self, ip):
        """add the IP to the tracked dict
        """
        if ip not in self.ips:
            self.ips[ip] = IP(ban_count=self.ban_count if self.ban_enabled else 0,
                              rate_count=self.rate_count if self.rate_limit_enabled else 0)

    def _before_request(self):
        """Function which runs before every request
        """
        if request.endpoint not in self.bypass_routes:  # avoid routes with the @bypass decorator, or if they use specific limits with override
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

    def banned_for(self, ip) -> int:
        """returns the time in seconds this IP is banned for"""
        return int((self.ips[ip].ban_entries[-1] + self.ban_duration) - time.time())

    def rate_limited_for(self, ip) -> int:
        """returns the time in seconds this IP is rate limited for"""
        rate_entries = [e for e in self.ips[ip].rate_entries if e >= time.time() - self.rate_window]

        return int((rate_entries[0] + self.rate_window) - time.time()) if rate_entries else 0

    def is_banned(self, ip) -> bool:
        """returns whether this IP is currently banned or not
        """
        # have we too much counts for our interval
        if not self.ips[ip].ban_active and len([e for e in self.ips[ip].ban_entries if e >= time.time() - self.ban_window]) >= self.ban_count:
            self.ips[ip].ban_active = True
        # is the last entry still in our ban duration ?
        if self.ips[ip].ban_active:
            if time.time() <= self.ips[ip].ban_entries[-1] + self.ban_duration:
                return True
            self.ips[ip].ban_active = False

        return False

    def is_rate_limited(self, ip) -> bool:
        """returns whether this IP is currently rate limited or not
        """
        # in the last rate_interval, did we had more entries than rate_count ?
        if len([e for e in self.ips[ip].rate_entries if e >= time.time() - self.rate_window]) >= self.rate_count:
            return True
        return False

    def init_app(self, app):
        """add our before request to flask now
        """
        app.before_request(self._before_request)

    def report(self, ip=None):
        """Report an IP. If no ip arg is provided, uses the ip_header arg provided to the GateKeeper instance
        """
        client_ip = ip or self._get_ip()
        self._add(client_ip)
        self.ips[client_ip].add_report()

    def bypass(self, route):
        @wraps(route)
        def wrapper(*a, **k):
            return route(*a, **k)
        
        # We store the name of the function associated with the route, not the path of the route
        self.bypass_routes.add(route.__name__)
        return wrapper

    def specific(self, rate_limit_rule, standalone=False, ip_header=None):
        """Route specific gatekeeper. Only for rate limiting purposes.

        By defaults the rate_limite is set _on top_ of the global instance rule. 
        If you want to set a unique rate limite rule, set `standalone` to True.

        You can supply a different ip_header, otherwise it will default to the instance configuration.
        """
        specific_gk = GateKeeper(rate_limit_rule=rate_limit_rule,
                                 ip_header=ip_header or self.ip_header)

        def decorator(route):
            @wraps(route)
            def wrapper(*args, **kwargs):

                # We reproduce the same behavior as our _before_request func here
                # but for the gk instance tied to this route
                ip = specific_gk._get_ip()
                specific_gk._create(ip)

                if specific_gk.rate_limit_enabled and specific_gk.is_rate_limited(ip):
                    return "rate limited for {}s".format(specific_gk.rate_limited_for(ip)), 429

                specific_gk._add(ip)
                return route(*args, **kwargs)

            # remove ourselves from the global instance _before_request
            if standalone:
                self.bypass_routes.add(route.__name__)
            return wrapper

        return decorator
