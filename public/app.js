const form = document.getElementById("scrapeForm");
const statusPill = document.getElementById("statusPill");
const statusText = document.getElementById("statusText");
const resultCount = document.getElementById("resultCount");
const resultsBody = document.getElementById("resultsBody");
const downloadLink = document.getElementById("downloadLink");
const startBtn = document.getElementById("startBtn");
const resetBtn = document.getElementById("resetBtn");
const API_BASE = (window.__API_BASE_URL || "").replace(/\/+$/, "");

let pollTimer = null;
let activeJobId = null;

function apiUrl(path) {
  return API_BASE ? `${API_BASE}${path}` : path;
}

async function readResponsePayload(response) {
  const rawText = await response.text();
  if (!rawText) {
    return { data: null, rawText: "" };
  }

  try {
    return { data: JSON.parse(rawText), rawText };
  } catch {
    return { data: null, rawText };
  }
}

function setStatus(kind, text) {
  statusPill.className = `pill pill-${kind}`;
  statusPill.textContent = kind.charAt(0).toUpperCase() + kind.slice(1);
  statusText.textContent = text;
}

function renderResults(rows) {
  resultsBody.innerHTML = "";
  resultCount.textContent = `${rows.length} rows`;

  for (const row of rows) {
    const tr = document.createElement("tr");

    const websiteCell = row.Website
      ? `<a href="${row.Website}" target="_blank" rel="noopener noreferrer">${row.Website}</a>`
      : "";

    tr.innerHTML = `
      <td>${row.Name || ""}</td>
      <td>${row.Category || ""}</td>
      <td>${row.Rating || ""}</td>
      <td>${row.Phone || ""}</td>
      <td>${row.Email || ""}</td>
      <td>${websiteCell}</td>
      <td>${row.Address || ""}</td>
    `;

    resultsBody.appendChild(tr);
  }
}

async function pollJob(jobId) {
  const response = await fetch(apiUrl(`/api/scrape/${jobId}`));
  const { data, rawText } = await readResponsePayload(response);

  if (!response.ok) {
    const errorMessage =
      data?.error ||
      data?.message ||
      (rawText ? rawText.replace(/\s+/g, " ").slice(0, 180) : "") ||
      `Failed to fetch job status (${response.status})`;
    throw new Error(errorMessage);
  }

  if (!data) {
    throw new Error("Server returned an empty response while checking job status.");
  }

  if (data.status === "running") {
    setStatus("running", `Scraping in progress for \"${data.query}\"...`);
    return;
  }

  clearInterval(pollTimer);
  pollTimer = null;
  startBtn.disabled = false;

  if (data.status === "completed") {
    setStatus("completed", `Completed. Found ${data.count} leads.`);
    renderResults(data.results || []);
    downloadLink.href = data.download_url?.startsWith("http")
      ? data.download_url
      : apiUrl(data.download_url || "#");
    downloadLink.classList.remove("hidden");
    return;
  }

  setStatus("failed", data.error || "Scrape failed.");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const query = document.getElementById("query").value.trim();
  const maxResults = Number(document.getElementById("maxResults").value);
  const headless = document.getElementById("headless").checked;

  if (!query) {
    setStatus("failed", "Please enter a search query.");
    return;
  }

  startBtn.disabled = true;
  downloadLink.classList.add("hidden");
  renderResults([]);
  setStatus("running", "Starting scraping job...");

  try {
    const response = await fetch(apiUrl("/api/scrape"), {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query,
        max_results: maxResults,
        headless,
      }),
    });

    const { data, rawText } = await readResponsePayload(response);
    if (!response.ok) {
      const errorMessage =
        data?.error ||
        data?.message ||
        (rawText ? rawText.replace(/\s+/g, " ").slice(0, 180) : "") ||
        `Could not start scraping (${response.status}).`;
      throw new Error(errorMessage);
    }

    if (!data || !data.job_id) {
      throw new Error("Server did not return a valid job id.");
    }

    activeJobId = data.job_id;

    if (pollTimer) {
      clearInterval(pollTimer);
    }

    pollTimer = setInterval(async () => {
      try {
        await pollJob(activeJobId);
      } catch (error) {
        clearInterval(pollTimer);
        pollTimer = null;
        startBtn.disabled = false;
        setStatus("failed", error.message);
      }
    }, 2500);

    await pollJob(activeJobId);
  } catch (error) {
    startBtn.disabled = false;
    setStatus("failed", error.message);
  }
});

resetBtn.addEventListener("click", () => {
  form.reset();
  startBtn.disabled = false;
  downloadLink.classList.add("hidden");
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  activeJobId = null;
  setStatus("idle", "Waiting for input.");
  renderResults([]);
});
