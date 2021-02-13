#!/usr/bin/env python3
from flask import Flask, render_template, request, jsonify, redirect, url_for

from netstat import netstat

app = Flask(__name__)

DEFAULT_IP = '127.0.0.1'
DEFAULT_PORT = 5000


def get_arguments():
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument('--ip',
                        dest='ip',
                        required=False,
                        default=DEFAULT_IP,
                        type=str,
                        help='Specify the IP address to bind to. '
                             f'Default is {DEFAULT_IP}')
    parser.add_argument('--port',
                        dest='port',
                        required=False,
                        default=DEFAULT_PORT,
                        type=str,
                        help='Specify the TCP port to bind to. '
                             f'Default is {DEFAULT_PORT}')
    parser.add_argument('--file',
                        dest='file',
                        required=False,
                        type=str,
                        help='Provide a txt file with execution result of the netstat command '
                             '(Unix: "netstat -tupn", Windows: "netstat -ano") '
                             'to build the map with network connections. '
                             'By default the script attempts to retrieve network connections '
                             'of its current host machine.')
    options = parser.parse_args()
    return options


options = get_arguments()


@app.route('/')
def index():
    return redirect(url_for('map'))
    # return "<a href=\"/map\">Map is here</a>"


@app.route('/map')
def map():
    my_loc = netstat.get_my_location()
    my_lat, my_lon = my_loc['lat'], my_loc['lon']
    my_desc = f"{my_loc['city']}, {my_loc['region']}. {my_loc['country']}"
    return render_template("map.html.j2", my_lat=my_lat, my_lon=my_lon, my_desc=my_desc)


@app.route('/map/update', methods=["POST"])
def update():
    client_procs = request.get_json(force=True)
    app.logger.info(f"Client has layers: {client_procs}")
    new_markers, new_procs = netstat.run(known_procs=client_procs,
                                         netstat_file=options.file)
    app.logger.info(f"Sending layers: {new_procs}")
    return jsonify([new_markers, new_procs])


if __name__ == '__main__':
    app.run(host=options.ip, port=options.port, debug=True)
