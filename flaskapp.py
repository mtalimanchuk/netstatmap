from flask import Flask, render_template, request, jsonify

from netstat import get_my_location, run_netstat

app = Flask(__name__)


@app.route('/')
def index():
    return "<a href=\"/map\">Map is here</a>"


@app.route('/map')
def map():
    my_lat, my_lon = get_my_location()
    return render_template("map.html.j2", my_lat=my_lat, my_lon=my_lon)


@app.route('/map/update', methods=["POST"])
def update():
    r = request.get_json(force=True)
    print(r)
    new_markers_df = run_netstat()
    new_markers = new_markers_df.to_json(orient='records')
    return jsonify(new_markers)


if __name__ == '__main__':
    app.run(debug=True)
