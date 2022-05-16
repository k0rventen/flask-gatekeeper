"""A simple banning & rate limiting extension for Flask.
"""
import time
from collections import deque
from functools import wraps

from flask import Flask, Response, request


class IP:
    def __init__(self, ban_count, rate_count):
        """IP record that keeps track of reports and requests made by that IP.

        Args:
            ban_count (int): number of reports to keep
            rate_count (int): number of requests to keep
        """
        self.ban_entries = deque(maxlen=ban_count)
        self.rate_entries = deque(maxlen=rate_count)
        self.ban_active_until = 0

        # setters
        self.add_report = lambda: self.ban_entries.append(time.time())
        self.add_entry = lambda: self.rate_entries.append(time.time())


class GateKeeper:
    def __init__(self, app: Flask = None, ban_rule: dict = None, rate_limit_rules: list = None, ip_header: str = None, excluded_methods: list = None):
        """GateKeeper instance around a flask app.

        Provides rate-limiting & ban functions.

        Rate limiting is done automatically, 
        but you have to specify when an IP should be reported, using `.report()` (usually in your login route when the creds are not valid)

        ban_rule should be a dict {"count":int,"window":int,"duration":int} where
        - count is the number of reports before actually banning the IP
        - window is the rolling time window to look for ban reports
        - duration is the duration of the ban in seconds.

        rate_limit_rules should be a list [{"count":int,"window":int},..] where
        - count is the maximum number of requests 
        - window is the rolling time window for the rate count.

        As an example, ban_rule={"count":3,"window":60,"duration":600}, rate_limit_rules=[{"count":20,"window":1},{"count":100,"window":10}] would:
        - ban any IP for 600s if it has been reported 3 times in the last 60s,
        - rate limit any IP if it has made more than 20 requests in the last 1s or more than 100 requests in a 10s window.

        If you do not set ban_rule, no banning will be done. Same goes for the rate limiting.

        Requests made during the rate limiting period or ban period are not counted.

        You can delay the init by omitting `app` here and calling `.init_app()` later.

        If you set ip_header but the header is not present in the request, it falls back to the client seen by flask (which might be the proxy's IP if using one) string, and any request made by potentially different clients will be added to this.

        Args:
            app (flask.Flask, optional): Flask app to wrap around. Defaults to None.
            ban_rule (dict, optional): Global ban rule for the whole app. Defaults to None.
            rate_limit_rules (list, optional): Global rate limit rules for the whole app. Defaults to None.
            ip_header (str, optional): Header to check for the IP. useful with a proxy that will add a header with the ip of the actual client. Defaults to request.remote_addr.
            excluded_methods (str, optional): Types of requests to ignore when counting requests. Can be GET, POST, HEAD, OPTIONS.. Defaults to None.
        """
        self.ban_rule = ban_rule
        self.ban_count = ban_rule["count"] if ban_rule else 0
        self.rate_limit_rules = rate_limit_rules
        self.rate_count = max([r["count"] for r in rate_limit_rules]) if rate_limit_rules else 0

        self.excluded_methods = excluded_methods or []
        self.ip_header = ip_header
        self.ips = {}
        self.bypass_routes = set()
        if app:
            self.init_app(app)

    def _ban_func(self, ban_infos):
        """internal func for creating a http response when the client is banned. 

        Args:
            ban_infos (dict): dict containing the infos about the ban

        Returns:
            Response: ready to be server response with 403 http code and retry after header
        """
        ban_response = Response("ip {} banned for {}s (reported {} times in a {}s window)".format(
            ban_infos["ip"], ban_infos["retry"], ban_infos["count"], ban_infos["window"]), status=403)
        ban_response.headers["Retry-After"] = ban_infos["retry"]
        return ban_response

    def _rate_limit_func(self, rate_limit_infos):
        """internal func for creating a http response when the client is being rate limited.

        Args:
            rate_limit_infos (dict): dict containing the infos about the rate limiting

        Returns:
            Response: ready to be served response with 429 http code and retry after header
        """
        rate_limit_response = Response("ip {} rate limited for {}s (over {} requests in a {}s window)".format(
            rate_limit_infos["ip"], rate_limit_infos["retry"], rate_limit_infos["count"], rate_limit_infos["window"]), status=429)
        rate_limit_response.headers["Retry-After"] = rate_limit_infos["retry"]
        return rate_limit_response

    def _get_ip(self) -> str:
        """Returns the IP of the client"""
        if self.ip_header:
            return request.headers.get(self.ip_header,request.remote_addr)
        return request.remote_addr

    def _create(self, ip):
        """add the IP to the tracked dict"""
        if ip not in self.ips:
            self.ips[ip] = IP(ban_count=self.ban_count, rate_count=self.rate_count)

    def _before_request(self):
        """Function which runs before every request

           if the client is either banned or rate-limited, we short-circuit the response 
           and reply directly with the appropriate message.
        """
        if request.method not in self.excluded_methods and request.endpoint not in self.bypass_routes:
            ip = self._get_ip()
            self._create(ip)

            if self.ban_rule:
                is_banned = self._is_ip_banned(ip)
                if is_banned:
                    return self._ban_func(is_banned)

            if self.rate_limit_rules:
                is_rate_limited = self._is_ip_rate_limited(ip)
                if is_rate_limited:
                    return self._rate_limit_func(is_rate_limited)
            self.ips[ip].add_entry()

    def _is_ip_banned(self, ip) -> bool:
        """returns whether this IP is currently banned or not
        """
        # have we too much counts for any of our rules -> ban
        time_now = time.time()
        if not self.ips[ip].ban_active_until:
            if len([e for e in self.ips[ip].ban_entries if e >= time_now - self.ban_rule["window"]]) >= self.ban_rule["count"]:
                banned_for = int((self.ips[ip].ban_entries[-1] + self.ban_rule["duration"]) - time_now)
                self.ips[ip].ban_active_until = time_now + banned_for
                return {"ip": ip, "window": self.ban_rule["window"], "count": self.ban_rule["count"], "retry": int(banned_for)}
            return None

        # is the ban duration over ? -> unban
        if self.ips[ip].ban_active_until > time_now:
            banned_for = self.ips[ip].ban_active_until - time_now
            return {"ip": ip, "window": self.ban_rule["window"], "count": self.ban_rule["count"], "retry": int(banned_for)}
        else:
            self.ips[ip].ban_active_until = 0

        return None

    def _is_ip_rate_limited(self, ip) -> bool:
        """returns whether this IP is currently rate limited or not"""
        # in the last rate_interval, did we had more entries than rate_count ?
        time_now = time.time()

        for rule in self.rate_limit_rules:
            rule_entries = [
                e for e in self.ips[ip].rate_entries if e >= time_now - rule["window"]]
            if len(rule_entries) >= rule["count"]:
                retry_in = int(
                    (rule_entries[0] + rule["window"]) - time_now) or 0
                return {"ip": ip, "window": rule["window"], "count": rule["count"], "retry": retry_in}
        return None

    def init_app(self, app):
        """add our before request to flask now"""
        app.before_request(self._before_request)

    def report(self, ip:str=None):
        """Report the client who made the request, increasing its tally towards being banned.
        
        If no ip arg is provided, uses the ip_header arg provided to the GateKeeper instance

        Args:
            ip (str, optional): IP to ban. Defaults to None.
        """
        client_ip = ip or self._get_ip()
        self.ips[client_ip].add_report()

    def bypass(self, route):
        """do not apply rate-limiting to this route"""
        @wraps(route)
        def wrapper(*a, **k):
            return route(*a, **k)

        # We store the name of the function associated with the route, not the path of the route
        self.bypass_routes.add(route.__name__)
        return wrapper

    def specific(self, rate_limit_rules:list=[], standalone:bool=False):
        """Route specific gatekeeper. Only for rate limiting purposes.

        By defaults the specific rate_limit rule is set on top of the global instance rule. 
        A use-case could be a global per-minute rule, and a per-second bursting rule here
        If you want to set a unique rate limite rule, set `standalone` to True.

        You can supply a different ip_header, otherwise it will default to the instance configuration.
        """
        specific_gk = GateKeeper(rate_limit_rules=rate_limit_rules,ip_header=self.ip_header)

        def decorator(route):
            @wraps(route)
            def wrapper(*args, **kwargs):

                # We reproduce the same behavior as our _before_request func here
                # but for the gk instance tied to this route
                ip = specific_gk._get_ip()
                specific_gk._create(ip)

                if specific_gk.rate_limit_rules:
                    rate_limited = specific_gk._is_ip_rate_limited(ip)
                    if rate_limited:
                        return self._rate_limit_func(rate_limited)

                specific_gk.ips[ip].add_entry()
                return route(*args, **kwargs)

            # remove ourselves from the global instance _before_request
            if standalone:
                self.bypass_routes.add(route.__name__)
            return wrapper

        return decorator
