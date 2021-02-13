#!/usr/bin/env python3
import secrets
import warnings

warnings.simplefilter(action='ignore', category=UserWarning)

import pandas as pd
import psutil
import requests

FALSE_POSITIVE_IPS = ['127.0.0.1']

# available colors for leaflet markers
# COLORS = ['blue', 'orange', 'darkblue', 'red', 'pink', 'green', 'purple', 'lightblue', 'darkgreen', 'cadetblue', 'white', 'gray', 'darkred', 'lightgray', 'lightgreen', 'black']

pids = set()


def yield_remote_connections(netstat_file=None):
    if netstat_file:
        with open(netstat_file, 'r') as f:
            connection_states = ['ESTABLISHED', 'TIME_WAIT', 'HERGESTELLT', 'GESCHLOSSEN_WARTEN']
            for line in f.readlines():
                if not any(state in line.upper() for state in connection_states):
                    continue
                else:
                    # parse the line and extract remote connections
                    chunks = [chunk.strip() for chunk in line.split(' ') if chunk.strip()]
                    if '/' in line:
                        # a workaround for Linux
                        pid = line.split('/')[0].split(' ')[-1]
                        pids.add(pid)
                    else:
                        if '/' in chunks[-1]:
                            pid = chunks[-1].split('/')[0]
                        elif chunks[-1] == '-':
                            pid = 0
                        else:
                            pid = int(chunks[-1])
                            pids.add(pid)

                    state = chunks[-2]

                    filtered_chunks = [chunk for chunk in chunks if chunk != '0']
                    remote_socket = filtered_chunks[2]
                    remote_ip = remote_socket.split(':')[0]
                    remote_port = remote_socket.split(':')[1]

                    if remote_ip not in FALSE_POSITIVE_IPS and not remote_ip.startswith('['):
                        print(line)
                        print(filtered_chunks)
                        print({'pid': pid, 'remoteip': remote_ip, 'remoteport': remote_port, 'pstatus': state})
                        print('---')
                        yield {'pid': pid, 'remoteip': remote_ip, 'remoteport': remote_port, 'pstatus': state}

    else:
        for p in psutil.net_connections(kind='inet'):
            try:
                remoteip, remoteport = p.raddr
                if remoteip not in FALSE_POSITIVE_IPS:
                    print({'pid': p.pid, 'remoteip': remoteip, 'remoteport': remoteport, 'pstatus': p.status})
                    yield {'pid': p.pid, 'remoteip': remoteip, 'remoteport': remoteport, 'pstatus': p.status}
            except ValueError:
                pass
            except Exception as e:
                print(f"---\t[!]\t---\t{type(e)}:\n{e}")


def yield_process_info(netstat_file=None):
    if netstat_file:
        for p in pids:
            yield {"pid": p, "pname": '-', "pusername": '-'}
    else:
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


def run(known_procs, netstat_file=None):
    connections_df = pd.DataFrame(yield_remote_connections(netstat_file))

    processes_df = pd.DataFrame(yield_process_info(netstat_file))
    full_connections_df = pd.merge(connections_df, processes_df, on='pid', how='left')

    geodata_df = get_foreign_locations(full_connections_df['remoteip'])
    markers_df = pd.concat([full_connections_df, geodata_df], axis=1, sort=False).dropna(subset=["lat", "lon"])

    markers_df["globalPid"] = markers_df.apply(lambda row: f"{row['pname']}/{row['pid']}", axis=1)
    unique_procs_df = markers_df[['globalPid']].drop_duplicates()
    unique_procs_df["procHash"] = unique_procs_df.apply(
        lambda row: known_procs.get(row['globalPid'], secrets.token_hex(3)), axis=1)
    markers_df = pd.merge(markers_df, unique_procs_df, on="globalPid", how='left')
    markers_df["desc"] = markers_df.apply(lambda
                                              row: f"{row['pstatus']} {row['remoteip']}:{row['remoteport']} ({row['org']}) {row['globalPid']} U: {row['pusername']}",
                                          axis=1)
    markers_df.fillna("NaN", inplace=True)
    markers_df.drop_duplicates(inplace=True)

    print("[!] Client may experience errors parsing response because these columns contain NaN values:\n",
          markers_df.loc[:, markers_df.isna().any()])
    return markers_df.to_dict('records'), unique_procs_df.to_dict('records')
