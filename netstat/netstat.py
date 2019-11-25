import secrets
import warnings
warnings.simplefilter(action='ignore', category=UserWarning)

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
                yield {'pid': p.pid, 'remoteip': remoteip, 'remoteport': remoteport, 'pstatus': p.status}
        except ValueError:
            pass
        except Exception as e:
            print(f"---\t[!]\t---\t{type(e)}:\n{e}")


def yield_process_info():
    for p in psutil.process_iter(attrs=['pid', 'name', 'username']):
        pid = p.info['pid']
        pname = p.info['name']
        pusername = p.info['username']
        yield {"pid": pid, "pname": pname, "pusername": pusername}


def get_my_location():
    url = f"http://ip-api.com/json/"
    try:
        r = requests.get(url)
        ip_data = r.json()
        return ip_data
    except Exception as e:
        print(f"Exception {type(e)}:\n{e}")


def get_foreign_locations(ips):
    url = "http://ip-api.com/batch"
    try:
        r = requests.post(url, json=list(ips))
        return pd.DataFrame(r.json())
    except Exception as e:
        print(f"Exception {type(e)}:\n{e}")


def run(known_procs):
    connections_df = pd.DataFrame(yield_remote_connections())
    processes_df = pd.DataFrame(yield_process_info())
    full_connections_df = pd.merge(connections_df, processes_df, on='pid', how='left')

    geodata_df = get_foreign_locations(full_connections_df['remoteip'])
    markers_df = pd.concat([full_connections_df, geodata_df], axis=1, sort=False).dropna(subset=["lat", "lon"])

    markers_df["globalPid"] = markers_df.apply(lambda row: f"{row['pname']}/{row['pid']}", axis=1)
    unique_procs_df = markers_df[['globalPid']].drop_duplicates()
    unique_procs_df["procHash"] = unique_procs_df.apply(lambda row: known_procs.get(row['globalPid'], secrets.token_hex(3)), axis=1)
    markers_df = pd.merge(markers_df, unique_procs_df, on="globalPid", how='left')
    markers_df["desc"] = markers_df.apply(lambda row: f"{row['pstatus']} {row['remoteip']}:{row['remoteport']} ({row['org']}) {row['globalPid']} U: {row['pusername']}", axis=1)
    markers_df.fillna("NaN", inplace=True)
    markers_df.drop_duplicates(inplace=True)
    print(markers_df)

    print("[!] Client may experience errors parsing response because these columns contain NaN values:\n", markers_df.loc[:, markers_df.isna().any()])
    return markers_df.to_dict('records'), unique_procs_df.to_dict('records')
