const form = document.getElementById("lead-form");
const alertBox = document.getElementById("alert-box");
const tableWrap = document.getElementById("table-wrap");
const leadsBody = document.getElementById("leads-body");
const liveResults = document.getElementById("live-results");
const recordsCount = document.getElementById("records-count");
const downloadBox = document.getElementById("download-box");
const downloadFile = document.getElementById("download-file");
const downloadLink = document.getElementById("download-link");

function showError(message) {
  alertBox.textContent = message;
  alertBox.classList.remove("hidden");
}

function clearError() {
  alertBox.textContent = "";
  alertBox.classList.add("hidden");
}

function resetResults() {
  leadsBody.innerHTML = "";
  tableWrap.classList.add("hidden");
  liveResults.textContent = "0";
  recordsCount.textContent = "0 records";
  downloadBox.classList.add("hidden");
  downloadFile.textContent = "";
  downloadLink.removeAttribute("href");
  downloadLink.removeAttribute("download");
}

function createDownload(csvBase64, filename) {
  const binary = atob(csvBase64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  const blob = new Blob([bytes], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  downloadLink.href = url;
  downloadLink.download = filename;
  downloadFile.textContent = filename;
  downloadBox.classList.remove("hidden");
}

function renderLeads(leads) {
  leadsBody.innerHTML = "";

  for (const row of leads) {
    const tr = document.createElement("tr");
    const cells = [
      row.Name || "",
      row.Category || "",
      row.Rating || "",
      row.Phone || "",
      row.Email || "",
      row.Address || ""
    ];

    for (const value of cells) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.appendChild(td);
    }

    const websiteTd = document.createElement("td");
    if (row.Website) {
      const a = document.createElement("a");
      a.href = row.Website;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.className = "table-link";
      a.textContent = "Open";
      websiteTd.appendChild(a);
    }
    tr.appendChild(websiteTd);
    leadsBody.appendChild(tr);
  }

  liveResults.textContent = String(leads.length);
  recordsCount.textContent = `${leads.length} records`;
  tableWrap.classList.remove("hidden");
}

if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    resetResults();
    document.body.classList.add("is-loading");

    try {
      const formData = new FormData(form);
      const payload = {
        query: (formData.get("query") || "").toString(),
        max_results: (formData.get("max_results") || "20").toString()
      };

      const response = await fetch("/api/generate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });

      const raw = await response.text();
      let data = {};
      try {
        data = raw ? JSON.parse(raw) : {};
      } catch {
        throw new Error(`Server returned non-JSON response: ${raw.slice(0, 160)}`);
      }
      if (!response.ok) {
        throw new Error(data.error || "Request failed.");
      }
      if (data.error) {
        showError(data.error);
      }
      if (Array.isArray(data.leads) && data.leads.length) {
        renderLeads(data.leads);
      }
      if (data.csvBase64 && data.csvFilename) {
        createDownload(data.csvBase64, data.csvFilename);
      }
    } catch (error) {
      showError(error.message || "Unexpected error while generating leads.");
    } finally {
      document.body.classList.remove("is-loading");
    }
  });
}
