from collections import namedtuple
import string
import itertools
import time
import requests
import requests.exceptions

_ERR_APICALL = "Запрос завершился с ошибкой {0}: {1}"
_ERR_NORESPONSE = "Ответ сервера не содержит запрошенные данные:\n{0}"
_ERR_NOTUSER = "Идентификатор не принадлежит пользователю: {0}"

_MAX_RETRIES = 3


class API:
    _API_URL = "https://api.vk.com/method/"

    _VKS_ACL = 25
    _VKS_REQ_CHUNKED = string.Template("""
        var acl = $api_limit;
        var pos = $offset;
        var count = pos + 1;
        var items = [];
        while (acl >= $req_cost && pos < count) {
            var result = $req;
            acl = acl - $req_cost;
            items = items + result.items;
            pos = pos + result.items.length;
            count = result.count;
        }
        return {"count": count, "offset": pos, "items": items};
    """)
    _VKS_CALLSTR_ESCAPE = "$"
    _VKS_REQ_POSVAR = "pos"
    _VKS_API_PREFIX = "API."

    _ERRCODE_REQLIMIT = 6
    _API_THROTTLE_DELAY = 1

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
        for _ in range(0, _MAX_RETRIES):
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

    def _request_chunked(self, method, params):
        offset, count, elems = 0, 1, []
        req_str = self._vks_callstr(method, dict(
            params,
            offset=self._VKS_CALLSTR_ESCAPE + self._VKS_REQ_POSVAR
        ))
        req_cost = req_str.count(self._VKS_API_PREFIX)
        while offset < count:
            vk_script = self._VKS_REQ_CHUNKED.substitute(
                api_limit=self._VKS_ACL,
                offset=offset,
                req=req_str,
                req_cost=req_cost,
            )
            vk_script = " ".join(vk_script.split())
            req_result = self._request("execute", {"code": vk_script})
            count, offset = req_result["count"], req_result["offset"]
            elems.extend(req_result["items"])
        return elems

    @classmethod
    def _vks_callstr(cls, method, params):
        p_pairs = []
        for p_name, p_val in params.items():
            p_name = cls._vks_qstr(p_name, '"')
            p_val = cls._vks_qparam(p_val, '"')
            p_pairs.append(": ".join([p_name, p_val]))
        param_str = "".join(["{", ", ".join(p_pairs), "}"])
        return "{0}({1})".format(cls._VKS_API_PREFIX + method, param_str)

    @classmethod
    def _vks_qparam(cls, param, qmark):
        if isinstance(param, str):
            if param.startswith(cls._VKS_API_PREFIX):
                return param
            elif param.startswith(cls._VKS_CALLSTR_ESCAPE):
                return param.lstrip(cls._VKS_CALLSTR_ESCAPE)
            else:
                return cls._vks_qstr(param, qmark)
        else:
            return str(param)

    @classmethod
    def _vks_qstr(cls, s, qmark):
        return "".join([qmark, s.replace(qmark, "\\" + qmark), qmark])


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


def _ichopped(iterable, chunk_size):
    it = iter(iterable)
    result = []
    while True:
        chunk = list(itertools.islice(it, chunk_size))
        if not chunk:
            return result
        result.append(chunk)
