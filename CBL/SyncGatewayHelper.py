import requests
import json
import re

class SGHelper:

    def create_user(self, url, db, name, password, channels=None, roles=None):

        if channels is None:
            channels = []

        if roles is None:
            roles = []

        data = {
            "name": name,
            "password": password,
            "admin_channels": channels,
            "admin_roles": roles
        }
        resp = requests.post("{}/{}/_user/".format(url, db), data=json.dumps(data))
        resp.raise_for_status()
        return name, password

    def create_session(self, url, db, name, password=None, ttl=86400):
        resp = self._request_session(url, db, name, password, ttl)
        resp_obj = resp.json()

        if "cookie_name" in resp_obj:
            # _session called via admin port
            # Cookie name / session is returned in response
            cookie_name = resp_obj["cookie_name"]
            session_id = resp_obj["session_id"]
        else:
            # _session called via public port.
            # get session info from 'Set-Cookie' header
            set_cookie_header = resp.headers["Set-Cookie"]

            # Split header on '=' and ';' characters
            cookie_parts = re.split("=|;", set_cookie_header)

            cookie_name = cookie_parts[0]
            session_id = cookie_parts[1]
        print("cookie name {}, session id {}".format(cookie_name, session_id))
        return cookie_name, session_id

    def _request_session(self, url, db, name, password=None, ttl=86400):
        data = {
            "name": name,
            "ttl": ttl
        }

        if password:
            data["password"] = password

        resp = requests.post("{}/{}/_session".format(url, db), data=json.dumps(data))
        resp.raise_for_status()
        return resp