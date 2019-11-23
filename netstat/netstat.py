#!/usr/bin/env python3
import secrets
import warnings
warnings.simplefilter(action='ignore', category=UserWarning)

import numpy as np
import pandas as pd
import psutil
import requests


# available colors for leaflet markers
# COLORS = ['blue', 'orange', 'darkblue', 'red', 'pink', 'green', 'purple', 'lightblue', 'darkgreen', 'cadetblue', 'white', 'gray', 'darkred', 'lightgray', 'lightgreen', 'black']

def yield_remote_connections():
    FALSE_POSITIVE_IPS = ['127.0.0.1']
    for p in psutil.net_connections(kind='inet'):
        try:
            remoteip, remoteport = p.raddr
            if remoteip not in FALSE_POSITIVE_IPS:
                yield {'pid': p.pid, 'remoteip': remoteip, 'remoteport': remoteport, 'status': p.status}
        except ValueError:
            pass
        except Exception as e:
            print(f"---\t[!]\t---\t{type(e)}:\n{e}")


def get_my_location():
    url = f"http://ip-api.com/json/"
    try:
        r = requests.get(url)
        ip_data = r.json()
        return ip_data['lat'], ip_data['lon']
    except Exception as e:
        print(f"Exception {type(e)}:\n{e}")


def get_foreign_locations(ips):
    url = "http://ip-api.com/batch"
    try:
        r = requests.post(url, json=list(ips))
        return pd.DataFrame(r.json())
    except Exception as e:
        print(f"Exception {type(e)}:\n{e}")


def run(markers_df_path='netstat/lastscan.csv'):

    # def get_marker_hash(lat, lon, lastscan_df):
    #     try:
    #         return lastscan_df[np.isclose(lastscan_df["lat"], lat) & np.isclose(lastscan_df["lon"], lon)]["markerHash"].values[0]
    #     except (IndexError, TypeError):
    #         return secrets.token_hex(3)

    connections_df = pd.DataFrame(yield_remote_connections())
    processes_df = pd.DataFrame([p.info for p in psutil.process_iter(attrs=['pid', 'name', 'username'])])
    full_connections_df = pd.merge(connections_df, processes_df, on='pid', how='left')

    geodata_df = get_foreign_locations(full_connections_df['remoteip'])
    markers_df = pd.concat([full_connections_df, geodata_df], axis=1, sort=False).dropna(subset=["lat", "lon"])

    # try:
    #     lastscan_df = pd.read_csv(markers_df_path)
    # except FileNotFoundError:
    #     lastscan_df = None

    markers_df.to_csv(markers_df_path)
    return markers_df
