import json

import vk
import ratelim

API_VER = "5.52"
API_RATE = 3
API_BURST = 3

VK_USER = "eshmargunov"
THRESHOLD = 1


def display_pulse():
    print(".", end="", flush=True)


with open("api_token.txt", "r") as api_file:
    vk_token = api_file.readline().strip()

vk_limiter = ratelim.TokenBucket(API_RATE, API_BURST)
vk_api = vk.API(API_VER, vk_token, vk_limiter.wait, display_pulse)
vk_user = vk_api.vk_user(VK_USER)
usr_friends = set(vk_user.friend_ids(vk_api))
grp_list = []
for vk_grp in vk_api.vk_group_iter(vk_user.group_ids(vk_api)):
    grp_members = set(vk_grp.member_ids(vk_api))
    grp_friends = [
        u for u in vk_api.vk_user_iter(grp_members & usr_friends)
        if u.active
    ]
    if len(grp_friends) <= THRESHOLD:
        grp_list.append({
            "name": vk_grp.name,
            "gid": vk_grp.gid,
            "members_count": vk_grp.members_count,
        })

with open("groups.json", "w") as out_file:
    json.dump(grp_list, out_file, ensure_ascii=False, indent=4)
