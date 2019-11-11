#!/usr/bin/env python3
import locale
import platform
import random
import subprocess

import pandas as pd
import requests
import folium

COLORS = ['darkblue', 'white', 'orange', 'green', 'beige', 'darkred', 'gray', 'red', 'lightgray', 'lightgreen', 'lightred', 'lightblue', 'darkgreen', 'black', 'blue', 'purple', 'cadetblue']
FLAVORED_COMMANDS = {
    "Linux": (
        "netstat -tupn",
        ["Proto", "Recv-Q", "Send-Q", "LocalAddress", "ForeignAddress", "State", "PID/Name"]
    ),
    "Windows": (
        "netstat /ano",
        ["Proto", "LocalAddress", "ForeignAddress", "State", "PID/Name"]
    ),
    # more details here https://github.com/easybuilders/easybuild/wiki/OS_flavor_name_version
}


def get_netstat_df():
    os_flavor = platform.system()
    cmd, header = FLAVORED_COMMANDS[os_flavor]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    stdout, stderr = proc.communicate()
    raw_output = stdout.decode(locale.getpreferredencoding())  # '866' or 'cp1251' for Russian codepage (check with chcp on windows)
    rows = [connection.strip().split(maxsplit=6) for connection in raw_output.split("\n") if "tcp" in connection.strip().lower()]
    return pd.DataFrame(rows, columns=header)


def get_my_location():
    url = f"http://ip-api.com/json/"
    r = requests.get(url)
    ip_data = r.json()
    return ip_data['lat'], ip_data['lon']


def get_foreign_locations(ips):
    url = "http://ip-api.com/batch"
    r = requests.post(url, json=list(ips))
    # data = [ip_data for ip_data in r.json() if ip_data.get("status") == "success"]
    return r.json()


if __name__ == "__main__":
    connections_df = get_netstat_df()
    try:
        connections_df[["PID", "Name"]] = connections_df["PID/Name"].str.split("/", expand=True)
    except ValueError:
        pass
    connections_df[["LocalAddress", "LocalPort"]] = connections_df["LocalAddress"].str.rsplit(":", n=1, expand=True)
    connections_df[["ForeignAddress", "ForeignPort"]] = connections_df["ForeignAddress"].str.rsplit(":", n=1, expand=True)
    connections_df = connections_df.drop(connections_df[connections_df["ForeignAddress"].str.contains(r"^(0|127|10)\..*?\..*?\..*?.*|\*|\[::\]")].index).reset_index()

    my_lat, my_lon = get_my_location()
    geodata = get_foreign_locations(connections_df["ForeignAddress"])
    geodata_df = pd.DataFrame(geodata)

    markers_df = pd.concat([connections_df, geodata_df], axis=1, sort=False).dropna(subset=["lat", "lon"])

    markers_df["desc"] = markers_df["State"] + " " + markers_df['PID/Name'] + " " + markers_df['ForeignAddress']
    unique_markers_df = markers_df.groupby(["lat", "lon", "city", "countryCode"]).aggregate({"desc": "<br>".join}).reset_index()

    world = folium.Map(location=[20, 0], zoom_start=2)

    for m in unique_markers_df.itertuples():
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
    world.save("world.html")
