#!/usr/bin/env python3
"""
Requirements:
    - xdotool
    - xrandr
    - ddcutil
    - light
"""
import re
import subprocess
import argparse
import os.path
import json

from collections import namedtuple


LAPTOP_MONITOR = "eDP1"
SUDO = ["sudo"]
FEATURE_LOOKUP_FILE = "~/.cache/monitor_brightness"

Monitor = namedtuple("Monitor", ["name", "EDID"])

import time
starttime = None
def pt(s):
    global starttime
    if starttime is None:
        starttime = time.time()
    print(f"{time.time()-starttime}:\t{s}")


g_feature_lookup = {}
def load_feature_lookup():
    global g_feature_lookup
    if FEATURE_LOOKUP_FILE and os.path.isfile(os.path.expanduser(FEATURE_LOOKUP_FILE)):
        with open(os.path.expanduser(FEATURE_LOOKUP_FILE)) as f:
            s = f.read()
        try:
            g_feature_lookup = json.loads(s)
        except:
            pass

def flush_g_feature_lookup():
    with open(os.path.expanduser(FEATURE_LOOKUP_FILE), "w+") as f:
        f.write(json.dumps(g_feature_lookup))



def get_active_monitor() -> Monitor:
    args = ["xdotool", "getmouselocation", "--shell"]
    r = subprocess.run(args, stdout=subprocess.PIPE)
    x = re.search(r"X=(\d*)\n", r.stdout.decode('utf-8')).groups()[0]
    x = int(x)
    y = re.search(r"Y=(\d*)\n", r.stdout.decode('utf-8')).groups()[0]
    y = int(y)

    args = ["xrandr", "--verbose"]
    r = subprocess.run(args, stdout=subprocess.PIPE)
    xrandr = r.stdout.decode('utf-8')

    monitors = []
    for line in xrandr.split('\n')[1:]:
        if not line.startswith("\t") and not line.startswith(" "):
            monitors.append([])
        monitors[-1].append(line)

    matches = []
    for monitor in monitors:
        m = re.match(
            r"^([\w-]*) connected.* (\d+)x(\d+)\+(\d+)\+(\d+) .*$", monitor[0])
        if m:
            name, xlen, ylen, x0, y0 = m.groups()
      #      if name == LAPTOP_MONITOR:
      #          matches.append(Monitor(name, ""))
            name, xlen, ylen, x0, y0 = name, int(xlen), int(ylen), int(x0), int(y0)
            if x0 <= x < x0+xlen and y0 <= y < y0+ylen:
                pos1 = [i for (i, line) in enumerate(monitor)
                        if line.strip() == "EDID:"][0] + 1
                pos2 = [i for (i, line) in enumerate(monitor) if not re.match(
                    r"[0-9a-f]{32}", line.strip()) and i > pos1][0]
                edid = "".join(line.strip() for line in monitor[pos1:pos2])
                matches.append(Monitor(name=name, EDID=edid))
    if len(matches) > 1:
        print("Warning, more than one match")
    return matches[0]


def get_brightness_feature(monitor: Monitor):
    if monitor.EDID[:256] in g_feature_lookup:
        return g_feature_lookup[monitor.EDID[:256]]
    args = SUDO + ["ddcutil", "-e", monitor.EDID[:256], "capabilities"]
    r = subprocess.run(args, stdout=subprocess.PIPE)
    output = r.stdout.decode('utf-8')
    m = re.search(r"Feature: (\d+) \(Brightness\)", output)
    if m is not None:
        feature_val = int(m.groups()[0])
        g_feature_lookup[monitor.EDID[:256]] = feature_val
        flush_g_feature_lookup()
        return feature_val


def get_laptop():
    args = ["light"]
    r = subprocess.run(args, stdout=subprocess.PIPE)
    return float(r.stdout.decode('utf-8').strip())


def get_ddc(monitor: Monitor):
    #args = SUDO + ["ddcutil", "detect"]
    #r = subprocess.run(args, stdout=subprocess.PIPE)
    feature = get_brightness_feature(monitor)
    args = SUDO + ["ddcutil", "-e", monitor.EDID[:256], "getvcp", str(feature)]
    r = subprocess.run(args, stdout=subprocess.PIPE)
    m = re.search(r"current\s+value\s*=\s*(\d*.?\d*),",
                  r.stdout.decode('utf-8'))
    if m is not None:
        return float(m.groups()[0])


def get_brightness(monitor: Monitor):
    if monitor.name == LAPTOP_MONITOR:
        pt("b4 get_laptop")
        tmp = get_laptop()
        pt("after get_laptop")
        return tmp
    else:
        pt("b4 get_ddc")
        tmp = get_ddc(monitor)
        pt("after get_ddc")
        return tmp


def set_laptop(value: int):
    args = SUDO + ["light", "-S", str(value)]
    subprocess.run(args)


def set_ddc(monitor: Monitor, value: int):
    feature = get_brightness_feature(monitor)
    #subprocess.run([SUDO, "modprobe", "i2c-dev"])
    args = SUDO + ["ddcutil", "-e", monitor.EDID[:256],
            "setvcp", str(feature), str(value)]
    subprocess.run(args, stdout=subprocess.PIPE)


def set_brightness(monitor: Monitor, value: int):
    if monitor.name == LAPTOP_MONITOR:
        return set_laptop(value)
    else:
        return set_ddc(monitor, value)


def print_brightness_cli(args):
    pt("b4 get_active_mon")
    monitor = get_active_monitor()
    pt("after get_active_mon")
    print(get_brightness(monitor))


def set_brightness_cli(args):
    monitor = get_active_monitor()
    print(monitor)
    set_brightness(monitor, args.value)


def create_parser():
    parser = argparse.ArgumentParser(prog="DDC Brightness utility")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-m", "--monitor", type=str,
                        help="name of the monitor to set brightness on, WIP not implemented yet")
    subparsers = parser.add_subparsers(
        title="subcommands", description="valid subcommands", required=True, dest="subcommand")

    parser_get = subparsers.add_parser(
        "get", help="get active monitor brightness via ddc")
    parser_get.set_defaults(func=print_brightness_cli)

    parser_set = subparsers.add_parser(
        "set", help="set active monitor brightness via ddc")
    parser_set.add_argument("value", type=int, help="brightness value")
    parser_set.set_defaults(func=set_brightness_cli)

    return parser


def main():
    load_feature_lookup()
    args = create_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
