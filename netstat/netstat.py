#!/usr/bin/env python3
import locale
import platform
import secrets
import subprocess
import warnings
warnings.simplefilter(action='ignore', category=UserWarning)

import numpy as np
import pandas as pd
import requests


# available colors for leaflet markers
# COLORS = ['blue', 'orange', 'darkblue', 'red', 'pink', 'green', 'purple', 'lightblue', 'darkgreen', 'cadetblue', 'white', 'gray', 'darkred', 'lightgray', 'lightgreen', 'black']


class NetStat:
    NORMALIZED_OUTPUT_COLUMNS = ["State", "PIDName", "LocalAddress", "ForeignAddress"]
    FEATURES = ["State", "PIDName", "ForeignAddress", "ForeignPort"]

    def __init__(self, command, headers, normalize_func):
        self._command = command
        self._headers = headers
        self._source_normalization_func = normalize_func
        self._rows = self.run_command()

    @classmethod
    def auto_flavor(cls):
        flavor = platform.system()
        if flavor == "Linux":
            command = ["netstat", "-tupn"]
            headers = ["Proto", "Recv-Q", "Send-Q", "LocalAddress", "ForeignAddress", "State", "PIDName"]
            normalize_func = NetStat.normalize_linux

        elif flavor == "Windows":
            command = ["netstat", "/ano"]
            headers = ["Proto", "LocalAddress", "ForeignAddress", "State", "PIDName"]
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

    def run_command(self):
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
        return df.loc[:, NetStat.NORMALIZED_OUTPUT_COLUMNS]

    @staticmethod
    def normalize_windows(df):
        return df.loc[:, NetStat.NORMALIZED_OUTPUT_COLUMNS]

    @staticmethod
    def normalize_darwin(df):
        df["PIDName"] = df["PID"] + "/" + df["COMMAND"]
        df[["LocalAddress", "ForeignAddress"]] = df["NAME"].str.split("->", expand=True)
        df[["ForeignAddress", "State"]] = df["ForeignAddress"].str.split(" ", expand=True)
        df.dropna(subset=["ForeignAddress"], inplace=True)
        return df.loc[:, NetStat.NORMALIZED_OUTPUT_COLUMNS]

    def extract_features(self, normalized_df):
        df = self._source_normalization_func(normalized_df)
        df[["LocalAddress", "LocalPort"]] = df["LocalAddress"].str.rsplit(":", n=1, expand=True)
        df[["ForeignAddress", "ForeignPort"]] = df["ForeignAddress"].str.rsplit(":", n=1, expand=True)
        df = df.drop(df[df["ForeignAddress"].str.contains(r"^(0|127|10)\..*?\..*?\..*?.*|\*|\[::\]")].index).reset_index()
        return df.loc[:, NetStat.FEATURES]

    @property
    def df(self):
        _df = pd.DataFrame(self._rows, columns=self._headers)
        return self.extract_features(_df)


def get_my_location():
    url = f"http://ip-api.com/json/"
    r = requests.get(url)
    ip_data = r.json()
    return ip_data['lat'], ip_data['lon']


def get_foreign_locations(ips):
    url = "http://ip-api.com/batch"
    r = requests.post(url, json=list(ips))
    return pd.DataFrame(r.json())


def run(markers_df_path='netstat/lastscan.csv'):

    def get_marker_hash(lat, lon, lastscan_df):
        try:
            return lastscan_df[np.isclose(lastscan_df["lat"], lat) & np.isclose(lastscan_df["lon"], lon)]["markerHash"].values[0]
        except (IndexError, TypeError):
            return secrets.token_hex(3)

    ns = NetStat.auto_flavor()
    connections_df = ns.df

    geodata_df = get_foreign_locations(connections_df["ForeignAddress"])
    markers_df = pd.concat([connections_df, geodata_df], axis=1, sort=False).dropna(subset=["lat", "lon"])
    unique_locations_df = markers_df[["lat", "lon"]].drop_duplicates()

    try:
        lastscan_df = pd.read_csv(markers_df_path)
    except FileNotFoundError:
        lastscan_df = None

    unique_locations_df["markerHash"] = unique_locations_df.apply(lambda x: get_marker_hash(x.lat, x.lon, lastscan_df), axis=1)
    markers_df = pd.merge(markers_df, unique_locations_df, on=["lat", "lon"], how='left')[["State", "ForeignAddress", "ForeignPort", "PIDName", "lat", "lon", "markerHash", "isp", "org", "country", "city"]]
    markers_df["desc"] = markers_df["State"] + " " + markers_df['ForeignAddress'] + ":" + markers_df["ForeignPort"] + " " + markers_df['PIDName'] + " " + markers_df['org']
    unique_markers_df = markers_df.groupby(["markerHash"]).aggregate({"lat": "first", "lon": "first", "city": "first", "country": "first", "desc": "<br>".join}).reset_index()

    unique_markers_df.to_csv(markers_df_path, index=False)
    return unique_markers_df
