import os
import tempfile
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


def resolve_export_dir():
    if os.getenv("VERCEL"):
        vercel_tmp = os.path.join(tempfile.gettempdir(), "synplix_exports")
        os.makedirs(vercel_tmp, exist_ok=True)
        return vercel_tmp

    candidates = [
        os.path.join(BASE_DIR, "exports"),
        os.path.join(tempfile.gettempdir(), "synplix_exports"),
    ]
    for candidate in candidates:
        try:
            os.makedirs(candidate, exist_ok=True)
            return candidate
        except OSError:
            continue
    raise OSError("Could not create a writable export directory.")


EXPORT_DIR = resolve_export_dir()


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

    try:
        leads = scrape_google_maps(query=query, max_results=max_results, headless=headless)
    except Exception as exc:
        app.logger.exception("Lead scraping failed")
        return render_template(
            "index.html",
            leads=[],
            csv_file="",
            error=(
                "Scraping could not start in this deployment environment. "
                f"Details: {exc}"
            ),
        )

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
    try:
        written_path = write_to_csv(leads, output_path)
    except OSError as exc:
        app.logger.exception("CSV write failed")
        return render_template(
            "index.html",
            leads=[],
            csv_file="",
            error=f"Failed to save CSV export. Details: {exc}",
        )
    csv_file = os.path.basename(written_path) if written_path else ""

    return render_template("index.html", leads=leads, csv_file=csv_file, error="")


@app.route("/downloads/<path:filename>", methods=["GET"])
def download_file(filename):
    safe_name = os.path.basename(filename)
    return send_from_directory(EXPORT_DIR, safe_name, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
