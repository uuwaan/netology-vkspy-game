import sys
import os
import argparse
import json

import vk
import ratelim

API_VER = "5.52"
API_RATE = 3

FILE_TOKEN = "api_token.txt"
FILE_STDOUT = "-"

MSG_NOTACTIVE = "User is not active (maybe deleted or banned)."


def main():
    args = configured_cli().parse_args()
    lim = ratelim.TokenBucket(API_RATE)
    vk_api = vk.API(API_VER, api_token(),
                    lim.wait, pulse,
                    cctl=args.countctl,
                    fast=args.fast)
    vk_user = vk_api.vk_user(args.user)
    if not vk_user.active:
        print()
        print(MSG_NOTACTIVE)
        return
    usr_friend_ids = set(vk_user.friend_ids(vk_api))
    grp_list = []
    for vk_grp in vk_api.vk_group_iter(vk_user.group_ids(vk_api)):
        grp_friend_ids = set(vk_grp.member_ids(vk_api)) & usr_friend_ids
        grp_friends = [
            u for u in vk_api.vk_user_iter(grp_friend_ids) if u.active
        ]
        if len(grp_friends) <= args.threshold:
            grp_list.append({
                "name": vk_grp.name,
                "gid": vk_grp.gid,
                "members_count": vk_grp.members_count,
            })
    print()
    write_output(args.output, grp_list)


def pulse():
    print(".", end="", flush=True)


def write_output(file_path, group_list):
    if file_path == FILE_STDOUT:
        out_file = sys.stdout
        should_close = False
    else:
        out_file = open(file_path, "w")
        should_close = True
    try:
        json.dump(group_list, out_file, ensure_ascii=False, indent=4)
    finally:
        if should_close:
            out_file.close()


def api_token():
    with open(FILE_TOKEN, "r") as token_file:
        return token_file.readline().strip()


def configured_cli():
    cli_parser = argparse.ArgumentParser(
        prog=progname(),
        description="VK spy game"
    )
    cli_parser.add_argument(
        "--user", "-u",
        help="username or id",
        type=str,
        required=True,
    )
    cli_parser.add_argument(
        "--threshold", "-t",
        help="output groups with no more than this friends",
        type=int,
        default=0,
    )
    cli_parser.add_argument(
        "--output", "-o",
        help="write output to file ('-' for stdout)",
        type=str,
        default="-"
    )
    cli_parser.add_argument(
        "--countctl", "-c",
        help="enables control of items count reported by API server",
        action="store_true"
    )
    cli_parser.add_argument(
        "--fast", "-f",
        help="accelerate data requests with VKScript",
        action="store_true"
    )
    return cli_parser


def progname():
    # got this from source code of pip
    try:
        prog = os.path.basename(sys.argv[0])
        if prog in ("__main__.py", "-c"):
            return "{0} -m {1}".format(sys.executable, __package__)
        else:
            return prog
    except (AttributeError, TypeError, IndexError):
        pass
    return __package__
