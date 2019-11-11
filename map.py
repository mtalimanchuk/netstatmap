#!/usr/bin/env python3
from argparse import ArgumentParser
import locale
import platform
import random
import subprocess
import warnings
warnings.simplefilter(action='ignore', category=UserWarning)

import pandas as pd
import requests
import folium

COLORS = ['blue', 'orange', 'darkblue', 'red', 'pink', 'green', 'purple', 'lightblue', 'darkgreen', 'cadetblue', 'white', 'gray', 'darkred', 'lightgray', 'lightgreen', 'black']


class NetStat:
    NORMALIZED_OUTPUT_COLUMNS = ["State", "PID/Name", "LocalAddress", "ForeignAddress"]
    FEATURES = ["State", "PID/Name", "ForeignAddress"]

    def __init__(self, command, headers, normalize_func):
        self._command = command
        self._headers = headers
        self._normalize_source = normalize_func
        self._rows = self.run()

    @classmethod
    def auto_flavor(cls):
        flavor = platform.system()
        if flavor == "Linux":
            command = ["netstat", "-tupn"]
            headers = ["Proto", "Recv-Q", "Send-Q", "LocalAddress", "ForeignAddress", "State", "PID/Name"]
            normalize_func = NetStat.normalize_linux

        elif flavor == "Windows":
            command = ["netstat", "/ano"]
            headers = ["Proto", "LocalAddress", "ForeignAddress", "State", "PID/Name"]
            normalize_func = NetStat.normalize_windows

        elif flavor == "Darwin":
            command = ["lsof", "-i"]
            headers = ['COMMAND', 'PID', 'USER', 'FD', 'TYPE', 'DEVICE', 'SIZE/OFF', 'NODE', 'NAME']
            normalize_func = NetStat.normalize_darwin
            # MacOS command needs testing
        else:
            raise NotImplementedError(f"No support for platform '{flavor}' just yet. You can open an issue if you see this.")
            # more details here https://github.com/easybuilders/easybuild/wiki/OS_flavor_name_version
        return cls(command, headers, normalize_func)

    def run(self):
        proc = subprocess.Popen(
            self._command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = proc.communicate()
        raw_output = stdout.decode(locale.getpreferredencoding())  # '866' or 'cp1251' for Russian codepage (check with chcp on windows)
        rows = [connection.strip().split(maxsplit=len(self._headers) - 1) for connection in raw_output.split("\n") if "tcp" in connection.strip().lower()]
        return rows

    @staticmethod
    def normalize_linux(df):
        return df[NetStat.NORMALIZED_OUTPUT_COLUMNS]

    @staticmethod
    def normalize_windows(df):
        return df.loc[:, NetStat.NORMALIZED_OUTPUT_COLUMNS]

    @staticmethod
    def normalize_darwin(df):
        df["PID/Name"] = df["PID"] + "/" + df["COMMAND"]
        df[["LocalAddress", "ForeignAddress"]] = df["NAME"].str.split("->", expand=True)
        df[["ForeignAddress", "State"]] = df["ForeignAddress"].str.split(" ", expand=True)
        df.dropna(subset=["ForeignAddress"], inplace=True)
        return df[NetStat.NORMALIZED_OUTPUT_COLUMNS]

    def extract_features(self, normalized_df):
        df = normalized_df
        df[["LocalAddress", "LocalPort"]] = df["LocalAddress"].str.rsplit(":", n=1, expand=True)
        df[["ForeignAddress", "ForeignPort"]] = df["ForeignAddress"].str.rsplit(":", n=1, expand=True)
        df = df.drop(df[df["ForeignAddress"].str.contains(r"^(0|127|10)\..*?\..*?\..*?.*|\*|\[::\]")].index).reset_index()
        return df.loc[:, NetStat.FEATURES]

    @property
    def df(self):
        _df = pd.DataFrame(self._rows, columns=self._headers)
        return self.extract_features(self._normalize_source(_df))


def get_my_location():
    url = f"http://ip-api.com/json/"
    r = requests.get(url)
    ip_data = r.json()
    return ip_data['lat'], ip_data['lon']


def get_foreign_locations(ips):
    url = "http://ip-api.com/batch"
    r = requests.post(url, json=list(ips))
    return pd.DataFrame(r.json())


def group_markers(connections_df, geodata_df):
    markers_df = pd.concat([connections_df, geodata_df], axis=1, sort=False).dropna(subset=["lat", "lon"])
    markers_df["desc"] = markers_df["State"] + " " + markers_df['PID/Name'] + " " + markers_df['ForeignAddress']
    unique_markers_df = markers_df.groupby(["lat", "lon", "city", "countryCode"]).aggregate({"desc": "<br>".join}).reset_index()
    return unique_markers_df


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


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("path", help="path to save the map, 'world.html' by default", type=str, nargs='?', default="world.html")
    parser.add_argument("-o", "--open", help="open the map in your default browser once finished", action="store_true")
    parser.add_argument("-v", "--verbose", help="show detailed console output", action="store_true")

    args = parser.parse_args()
    if not args.path.endswith(".html"):
        args.path = f"{args.path}.html"
    return args


if __name__ == "__main__":
    args = parse_args()

    ns = NetStat.auto_flavor()
    connections_df = ns.df
    if args.verbose:
        print(f"\nConnections:\n{connections_df}")

    my_lat, my_lon = get_my_location()
    geodata_df = get_foreign_locations(connections_df["ForeignAddress"])
    s, f = geodata_df['status'].value_counts()
    failed_ips = '\n'.join(geodata_df.loc[geodata_df['status'] == 'fail', 'query'].values)
    print(f"\nLooked up {s} ips. {f} failed:\n{failed_ips}")
    # check if there're any rows with status == "success"

    markers_df = group_markers(connections_df, geodata_df)
    if args.verbose:
        print(f"\nUnique locations:\n{markers_df}")
    world = draw_map(my_lat, my_lon, markers_df)
    world.save(args.path)
    print(f"\nMap saved to {args.path}")

    if args.open:
        import webbrowser
        print(f"Opening {args.path} in browser...")
        webbrowser.open(args.path)
