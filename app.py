import os
from datetime import datetime
from uuid import uuid4

from flask import Flask
from flask import render_template
from flask import request
from flask import send_from_directory
from werkzeug.utils import secure_filename

from scraper_core import scrape_google_maps
from scraper_core import write_to_csv


app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(BASE_DIR, "exports")
os.makedirs(EXPORT_DIR, exist_ok=True)


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", leads=[], csv_file="", error="")


@app.route("/generate", methods=["POST"])
def generate():
    query = (request.form.get("query") or "").strip()
    max_results_raw = (request.form.get("max_results") or "20").strip()
    headless = request.form.get("headless") == "on"

    if not query:
        return render_template("index.html", leads=[], csv_file="", error="Query is required.")

    try:
        max_results = int(max_results_raw)
        if max_results < 1:
            raise ValueError
    except ValueError:
        return render_template(
            "index.html",
            leads=[],
            csv_file="",
            error="Max results must be a positive number.",
        )

    leads = scrape_google_maps(query=query, max_results=max_results, headless=headless)
    if not leads:
        return render_template(
            "index.html",
            leads=[],
            csv_file="",
            error="No leads found for this query. Try a different location or business type.",
        )

    safe_query = secure_filename(query.replace(" ", "_"))[:40] or "leads"
    filename = f"{safe_query}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}.csv"
    output_path = os.path.join(EXPORT_DIR, filename)
    written_path = write_to_csv(leads, output_path)
    csv_file = os.path.basename(written_path) if written_path else ""

    return render_template("index.html", leads=leads, csv_file=csv_file, error="")


@app.route("/downloads/<path:filename>", methods=["GET"])
def download_file(filename):
    safe_name = os.path.basename(filename)
    return send_from_directory(EXPORT_DIR, safe_name, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
