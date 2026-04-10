const DEFAULT_MAX_RESULTS = 20;
const MAX_RESULTS_LIMIT = 100;
const PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText";
const PLACES_FIELDS = [
  "places.id",
  "places.displayName",
  "places.formattedAddress",
  "places.rating",
  "places.internationalPhoneNumber",
  "places.nationalPhoneNumber",
  "places.websiteUri",
  "places.types",
  "places.googleMapsUri",
  "nextPageToken"
].join(",");

function csvEscape(value) {
  const text = value == null ? "" : String(value);
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function toCsv(rows) {
  if (!rows.length) {
    return "";
  }
  const headers = Object.keys(rows[0]);
  const lines = [headers.join(",")];
  for (const row of rows) {
    lines.push(headers.map((h) => csvEscape(row[h])).join(","));
  }
  return `${lines.join("\n")}\n`;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function toLead(place, query) {
  const displayName = place.displayName?.text || "";
  const category = Array.isArray(place.types) && place.types.length ? place.types[0] : "";
  const phone = place.internationalPhoneNumber || place.nationalPhoneNumber || "";
  return {
    Name: displayName,
    Category: category,
    Rating: place.rating != null ? String(place.rating) : "",
    Phone: phone,
    Email: "",
    Website: place.websiteUri || "",
    Address: place.formattedAddress || "",
    "Google Maps URL": place.googleMapsUri || "",
    "Search Query": query
  };
}

async function searchPlacesPage(apiKey, query, pageToken = "") {
  const body = {
    textQuery: query,
    pageSize: 20
  };
  if (pageToken) {
    body.pageToken = pageToken;
  }

  const response = await fetch(PLACES_SEARCH_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Goog-Api-Key": apiKey,
      "X-Goog-FieldMask": PLACES_FIELDS
    },
    body: JSON.stringify(body)
  });

  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(`Places API returned non-JSON response: ${text.slice(0, 160)}`);
  }

  if (!response.ok) {
    const message = data.error?.message || `HTTP ${response.status}`;
    throw new Error(`Places API error: ${message}`);
  }
  return data;
}

async function fetchLeads(query, maxResults, apiKey) {
  const leads = [];
  let nextPageToken = "";
  let pageCount = 0;

  while (leads.length < maxResults && pageCount < 5) {
    if (nextPageToken) {
      await sleep(2200);
    }

    const data = await searchPlacesPage(apiKey, query, nextPageToken);
    const places = Array.isArray(data.places) ? data.places : [];

    for (const place of places) {
      leads.push(toLead(place, query));
      if (leads.length >= maxResults) {
        break;
      }
    }

    nextPageToken = data.nextPageToken || "";
    pageCount += 1;
    if (!nextPageToken) {
      break;
    }
  }

  return leads.slice(0, maxResults);
}

module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  const apiKey = (process.env.GOOGLE_PLACES_API_KEY || "").trim();
  if (!apiKey) {
    res.status(500).json({
      error: "Missing GOOGLE_PLACES_API_KEY environment variable."
    });
    return;
  }

  const query = (req.body?.query || "").trim();
  const maxRaw = String(req.body?.max_results ?? DEFAULT_MAX_RESULTS).trim();

  if (!query) {
    res.status(400).json({ error: "Query is required." });
    return;
  }

  const maxResults = Number.parseInt(maxRaw, 10);
  if (!Number.isFinite(maxResults) || maxResults < 1 || maxResults > MAX_RESULTS_LIMIT) {
    res.status(400).json({ error: `max_results must be between 1 and ${MAX_RESULTS_LIMIT}.` });
    return;
  }

  try {
    const leads = await fetchLeads(query, maxResults, apiKey);
    if (!leads.length) {
      res.status(200).json({
        leads: [],
        csvBase64: "",
        csvFilename: "",
        error: "No leads found for this query. Try a different location or business type."
      });
      return;
    }

    const csvText = toCsv(leads);
    const safeQuery = query.replace(/[^a-z0-9_-]/gi, "_").slice(0, 40) || "leads";
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");

    res.status(200).json({
      leads,
      csvBase64: Buffer.from(csvText, "utf8").toString("base64"),
      csvFilename: `${safeQuery}_${stamp}.csv`,
      error: ""
    });
  } catch (error) {
    res.status(500).json({
      error: `Scraping failed in Vercel runtime: ${error.message || String(error)}`
    });
  }
};
