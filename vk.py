from collections import namedtuple

import string
import itertools
import time
import requests
import requests.exceptions

_ERR_APICALL = "Запрос завершился с ошибкой {0}: {1}"
_ERR_NORESPONSE = "Ответ сервера не содержит запрошенные данные:\n{0}"
_ERR_NOTUSER = "Идентификатор не принадлежит пользователю: {0}"


class API:
    _API_URL = "https://api.vk.com/method/"

    _VKS_REQ_POSVAR = "pos"
    _VKS_REQ_CHUNKED = string.Template("""
        var acl = $api_limit;
        var pos = $offset;
        var count = 0;
        var items = [];
        while (acl > 0) {
            var result = $req;
            acl = acl - 1;
            var broken = (result.count == null);
            if (!broken) {
                items = items + result.items;
                pos = pos + result.items.length;
                count = result.count;
            }
            if (pos == count || broken) {
                acl = 0;
            }
        }
        return {"count": count, "offset": pos, "items": items};
    """)

    _ERRCODE_REQLIMIT = 6
    _API_THROTTLE_DELAY = 1
    _MAX_RETRIES = 3

    def __init__(self, api_ver, api_token, rlim_lock=None, pulse_callback=None):
        self._api_ver = api_ver
        self._api_token = api_token
        self._rlock = rlim_lock
        self._pulse = pulse_callback

    def vk_user(self, ident):
        return next(self.vk_user_iter([ident]))

    def vk_user_iter(self, idents):
        result = []
        for id_chunk in _ichopped(idents, 1000):
            req_result = self._request("users.get", {
                "user_ids": ",".join(str(uid) for uid in id_chunk),
            })
            result.extend(req_result)
        return (User.from_dict(u) for u in result)

    def vk_group(self, ident):
        return next(self.vk_group_iter([ident]))

    def vk_group_iter(self, idents):
        result = []
        for id_chunk in _ichopped(idents, 1000):
            req_result = self._request("groups.getById", {
                "group_ids": ",".join(str(uid) for uid in id_chunk),
                "fields": "members_count",
            })
            result.extend(req_result)
        return (Group.from_dict(u) for u in result)

    def _request_chunked(self, method, params):
        offset, count, elems = 0, None, []
        req_str = VKScript.call_string(method, dict(
            params,
            offset=VKScript.CALLSTR_ESCAPE + self._VKS_REQ_POSVAR,
            v=self._api_ver,
        ))
        while offset != count:
            vk_script = self._VKS_REQ_CHUNKED.substitute(
                api_limit=VKScript.API_CALL_LIMIT,
                offset=offset,
                req=req_str,
            )
            vk_script = " ".join(vk_script.split())
            req_result = self._request("execute", {"code": vk_script})
            count, offset = int(req_result["count"]), int(req_result["offset"])
            elems.extend(req_result["items"])
        return elems

    def _request(self, method, params):
        while True:
            resp = self._http_request(self._API_URL + method, params=dict(
                params,
                access_token=self._api_token,
                v=self._api_ver,
            ))
            resp.raise_for_status()
            resp_json = resp.json()
            resp_error = resp_json.get("error")
            resp_body = resp_json.get("response")
            err_code = resp_error["error_code"] if resp_error else None
            if err_code == self._ERRCODE_REQLIMIT:
                time.sleep(self._API_THROTTLE_DELAY)
            else:
                break
        if resp_error:
            raise RuntimeError(_ERR_APICALL.format(
                resp_error["error_code"], resp_error["error_msg"]
            ))
        if resp_body is None:
            raise RuntimeError(_ERR_NORESPONSE.format(resp.content))
        if self._pulse:
            self._pulse()
        return resp_body

    def _http_request(self, url, params):
        for _ in range(0, self._MAX_RETRIES):
            req_exc = None
            try:
                if self._rlock:
                    self._rlock(1)
                resp = requests.get(url, params)
                break
            except requests.exceptions.RequestException as e:
                req_exc = e
        if req_exc:
            raise req_exc
        else:
            return resp


class User(namedtuple("User", "first_name last_name uid active")):
    @classmethod
    def from_dict(cls, udict):
        act = False if udict.get("deactivated") else True
        return cls(udict["first_name"], udict["last_name"], udict["id"], act)

    def friend_ids(self, api):
        return api._request_chunked("friends.get", {
            "user_id": self.uid,
        })

    def group_ids(self, api):
        return api._request_chunked("groups.get", {
            "user_id": self.uid,
        })


class Group(namedtuple("Group", "name gid members_count")):
    @classmethod
    def from_dict(cls, gdict):
        return cls(gdict["name"], gdict["id"], gdict["members_count"])

    def member_ids(self, api):
        return api._request_chunked("groups.getMembers", {
            "group_id": self.gid,
        })


class VKScript:
    API_PREFIX = "API."
    API_CALL_LIMIT = 25
    CALLSTR_ESCAPE = "$"
    QMARK = '"'

    @classmethod
    def call_string(cls, method, params):
        p_pairs = []
        for p_name, p_val in params.items():
            p_name = cls.quoted_string(p_name, cls.QMARK)
            p_val = cls.quoted_value(p_val, cls.QMARK)
            p_pairs.append(": ".join([p_name, p_val]))
        param_str = "".join(["{", ", ".join(p_pairs), "}"])
        return "{0}({1})".format(cls.API_PREFIX + method, param_str)

    @classmethod
    def quoted_value(cls, param, qmark):
        if isinstance(param, str):
            if param.startswith(cls.CALLSTR_ESCAPE):
                return param.lstrip(cls.CALLSTR_ESCAPE)
            else:
                return cls.quoted_string(param, qmark)
        else:
            return str(param)

    @classmethod
    def quoted_string(cls, s, qmark):
        return "".join([qmark, s.replace(qmark, "\\" + qmark), qmark])


def _ichopped(iterable, chunk_size):
    it = iter(iterable)
    result = []
    while True:
        chunk = list(itertools.islice(it, chunk_size))
        if not chunk:
            return result
        result.append(chunk)
