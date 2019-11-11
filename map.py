#!/usr/bin/env python3
import locale
import platform
import random
import subprocess

import pandas as pd
import requests
import folium


def _normalize_df_linux(df):
    return df


def _normalize_df_windows(df):
    return df


def _normalize_df_darwin(df):
    df["PID/Name"] = df["PID"] + "/" + df["COMMAND"]
    df[["LocalAddress", "ForeignAddress"]] = df["NAME"].str.split("->", expand=True)
    df[["ForeignAddress", "State"]] = df["ForeignAddress"].str.split(" ", expand=True)
    df.dropna(subset=["ForeignAddress"], inplace=True)
    return df


COLORS = ['blue', 'orange', 'darkblue', 'red', 'pink', 'green', 'purple', 'lightblue', 'darkgreen', 'cadetblue', 'white', 'gray', 'darkred', 'lightgray', 'lightgreen', 'black']
FLAVORED_COMMANDS = {
    "Linux": (
        ["netstat", "-tupn"],
        ["Proto", "Recv-Q", "Send-Q", "LocalAddress", "ForeignAddress", "State", "PID/Name"],
        _normalize_df_linux,
    ),
    "Windows": (
        ["netstat", "/ano"],
        ["Proto", "LocalAddress", "ForeignAddress", "State", "PID/Name"],
        _normalize_df_windows,
    ),
    "Darwin": (
        ["lsof", "-i"],
        ['COMMAND', 'PID', 'USER', 'FD', 'TYPE', 'DEVICE', 'SIZE/OFF', 'NODE', 'NAME'],
        _normalize_df_darwin,
    ),
    # MacOS command needs testing
    # more details here https://github.com/easybuilders/easybuild/wiki/OS_flavor_name_version
}


def get_netstat_df():
    os_flavor = platform.system()
    cmd, header, normalize_f = FLAVORED_COMMANDS[os_flavor]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    stdout, stderr = proc.communicate()
    raw_output = stdout.decode(locale.getpreferredencoding())  # '866' or 'cp1251' for Russian codepage (check with chcp on windows)
    rows = [connection.strip().split(maxsplit=len(header) - 1) for connection in raw_output.split("\n") if "tcp" in connection.strip().lower()]
    return normalize_f(pd.DataFrame(rows, columns=header))


def get_my_location():
    url = f"http://ip-api.com/json/"
    r = requests.get(url)
    ip_data = r.json()
    return ip_data['lat'], ip_data['lon']


def get_foreign_locations(ips):
    url = "http://ip-api.com/batch"
    r = requests.post(url, json=list(ips))
    return r.json()


def draw_map(my_lat, my_lon, markers_df):
    world = folium.Map(location=[my_lat, my_lon], zoom_start=2)

    for m in markers_df.itertuples():
        feature_group = folium.FeatureGroup(f"{m.city} [{m.countryCode}]")

        randcolor = random.choice(COLORS)
        line_locations = [(my_lat, my_lon), (m.lat, m.lon)]
        line_tooltip = folium.Tooltip(m.desc)
        marker_location = [m.lat, m.lon]
        marker_popup = folium.Popup(m.desc, max_width=500, show=True)
        marker_icon = folium.Icon(color=randcolor, icon='info-sign')

        folium.PolyLine(locations=line_locations, tooltip=line_tooltip, no_clip=True, color=randcolor).add_to(feature_group)
        folium.Marker(location=marker_location, popup=marker_popup, icon=marker_icon).add_to(feature_group)
        feature_group.add_to(world)

    folium.LayerControl('topleft', collapsed=False).add_to(world)
    return world


if __name__ == "__main__":
    connections_df = get_netstat_df()
    connections_df[["LocalAddress", "LocalPort"]] = connections_df["LocalAddress"].str.rsplit(":", n=1, expand=True)
    connections_df[["ForeignAddress", "ForeignPort"]] = connections_df["ForeignAddress"].str.rsplit(":", n=1, expand=True)
    connections_df = connections_df.drop(connections_df[connections_df["ForeignAddress"].str.contains(r"^(0|127|10)\..*?\..*?\..*?.*|\*|\[::\]")].index).reset_index()

    my_lat, my_lon = get_my_location()
    geodata = get_foreign_locations(connections_df["ForeignAddress"])
    geodata_df = pd.DataFrame(geodata)
    # check if there're any rows with status == "success"
    markers_df = pd.concat([connections_df, geodata_df], axis=1, sort=False).dropna(subset=["lat", "lon"])
    markers_df["desc"] = markers_df["State"] + " " + markers_df['PID/Name'] + " " + markers_df['ForeignAddress']
    unique_markers_df = markers_df.groupby(["lat", "lon", "city", "countryCode"]).aggregate({"desc": "<br>".join}).reset_index()

    world = draw_map(my_lat, my_lon, unique_markers_df)
    world.save("world.html")
