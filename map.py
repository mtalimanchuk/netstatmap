from flask import Flask, render_template, request, jsonify

from netstat import netstat

app = Flask(__name__)


@app.route('/')
def index():
    return "<a href=\"/map\">Map is here</a>"


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
    new_markers, new_procs = netstat.run(known_procs=client_procs)
    app.logger.info(f"Sending layers: {new_procs}")
    return jsonify([new_markers, new_procs])


if __name__ == '__main__':
    app.run(debug=True)
