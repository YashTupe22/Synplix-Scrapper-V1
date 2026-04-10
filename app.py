import os
import tempfile
import threading
import uuid
from datetime import datetime

from flask import Flask, jsonify, render_template, request, send_file
from flask_cors import CORS

from scraper_backend import run_scrape


app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _resolve_output_dir():
    env_output_dir = os.getenv("OUTPUT_DIR", "").strip()
    if env_output_dir:
        preferred_dir = env_output_dir
    elif os.getenv("VERCEL") == "1":
        preferred_dir = os.path.join(tempfile.gettempdir(), "outputs")
    else:
        preferred_dir = os.path.join(BASE_DIR, "outputs")

    try:
        os.makedirs(preferred_dir, exist_ok=True)
        return preferred_dir
    except OSError:
        fallback_dir = os.path.join(tempfile.gettempdir(), "outputs")
        os.makedirs(fallback_dir, exist_ok=True)
        return fallback_dir


OUTPUT_DIR = _resolve_output_dir()

DEFAULT_HEADLESS = os.getenv("DEFAULT_HEADLESS", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "").strip()
if allowed_origins_raw:
    allowed_origins = [origin.strip() for origin in allowed_origins_raw.split(",") if origin.strip()]
    CORS(app, resources={r"/api/*": {"origins": allowed_origins}})
else:
    CORS(app, resources={r"/api/*": {"origins": "*"}})

jobs = {}
jobs_lock = threading.Lock()


def _to_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _job_worker(job_id, query, max_results, headless):
    output_name = f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{job_id[:8]}.csv"
    output_path = os.path.join(OUTPUT_DIR, output_name)

    try:
        leads, saved_csv = run_scrape(
            query=query,
            max_results=max_results,
            output_file=output_path,
            headless=headless,
        )
        with jobs_lock:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["results"] = leads
            jobs[job_id]["csv_path"] = saved_csv
    except Exception as exc:
        with jobs_lock:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(exc)


@app.route("/")
def index():
    return render_template("index.html", api_base_url=os.getenv("API_BASE_URL", ""))


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/api/scrape", methods=["POST"])
def start_scrape():
    payload = request.get_json(silent=True) or {}
    query = str(payload.get("query", "")).strip()
    max_results_raw = payload.get("max_results", 20)
    headless = _to_bool(payload.get("headless", DEFAULT_HEADLESS), default=DEFAULT_HEADLESS)

    if not query:
        return jsonify({"error": "Search query is required."}), 400

    try:
        max_results = int(max_results_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "max_results must be a number."}), 400

    if max_results < 1 or max_results > 200:
        return jsonify({"error": "max_results must be between 1 and 200."}), 400

    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {
            "status": "running",
            "query": query,
            "max_results": max_results,
            "headless": headless,
            "created_at": datetime.now().isoformat(),
            "results": [],
            "csv_path": "",
            "error": "",
        }

    thread = threading.Thread(
        target=_job_worker,
        args=(job_id, query, max_results, headless),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id, "status": "running"})


@app.route("/api/scrape/<job_id>", methods=["GET"])
def scrape_status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "Job not found."}), 404

        response = {
            "job_id": job_id,
            "status": job["status"],
            "query": job["query"],
            "max_results": job["max_results"],
            "created_at": job["created_at"],
            "count": len(job["results"]),
            "error": job["error"],
        }

        if job["status"] == "completed":
            response["results"] = job["results"]
            response["download_url"] = f"/api/scrape/{job_id}/download"

    return jsonify(response)


@app.route("/api/scrape/<job_id>/download", methods=["GET"])
def download_results(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "Job not found."}), 404
        if job["status"] != "completed":
            return jsonify({"error": "Job is not completed yet."}), 409
        csv_path = job.get("csv_path", "")

    if not csv_path or not os.path.exists(csv_path):
        return jsonify({"error": "Result file is missing."}), 404

    return send_file(csv_path, as_attachment=True)


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}
    app.run(host=host, port=port, debug=debug)
