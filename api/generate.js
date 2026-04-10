const chromium = require("@sparticuz/chromium");
const puppeteer = require("puppeteer-core");

const DEFAULT_MAX_RESULTS = 20;

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

async function launchBrowser() {
  return puppeteer.launch({
    args: chromium.args,
    defaultViewport: chromium.defaultViewport,
    executablePath: await chromium.executablePath(),
    headless: chromium.headless
  });
}

async function collectPlaceLinks(page, query, maxResults) {
  const url = `https://www.google.com/maps/search/${encodeURIComponent(query)}`;
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.waitForSelector("div[role='feed']", { timeout: 15000 });

  const links = new Set();
  let stableRounds = 0;
  let previousCount = 0;

  while (links.size < maxResults && stableRounds < 8) {
    const hrefs = await page.$$eval("a[href*='/maps/place/']", (anchors) =>
      anchors.map((a) => (a.href || "").split("&")[0]).filter(Boolean)
    );
    for (const href of hrefs) {
      links.add(href);
      if (links.size >= maxResults) {
        break;
      }
    }

    await page.evaluate(() => {
      const feed = document.querySelector("div[role='feed']");
      if (feed) {
        feed.scrollTop = feed.scrollHeight;
      }
    });
    await page.waitForTimeout(1200);

    if (links.size === previousCount) {
      stableRounds += 1;
    } else {
      stableRounds = 0;
    }
    previousCount = links.size;
  }

  return [...links].slice(0, maxResults);
}

async function firstText(page, selectors) {
  for (const selector of selectors) {
    const text = await page.$$eval(selector, (nodes) => (nodes[0]?.textContent || "").trim());
    if (text) {
      return text;
    }
  }
  return "";
}

async function firstHref(page, selectors) {
  for (const selector of selectors) {
    const href = await page.$$eval(selector, (nodes) => (nodes[0]?.getAttribute("href") || "").trim());
    if (href) {
      return href;
    }
  }
  return "";
}

function firstMatch(text, regex) {
  const match = text.match(regex);
  return match ? match[0].trim() : "";
}

async function extractPhone(page) {
  const candidates = [
    "button[data-item-id^='phone']",
    "button[aria-label*='Phone']",
    "a[href^='tel:']"
  ];

  for (const selector of candidates) {
    const values = await page.$$eval(
      selector,
      (nodes) =>
        nodes.slice(0, 1).map((n) => ({
          text: (n.textContent || "").trim(),
          aria: (n.getAttribute("aria-label") || "").trim(),
          href: (n.getAttribute("href") || "").trim()
        }))
    );
    if (!values.length) {
      continue;
    }
    const value = values[0];

    const fromText = firstMatch(value.text, /\+?\d[\d\s().-]{6,}\d/);
    if (fromText) {
      return fromText;
    }

    const fromAria = firstMatch(value.aria, /\+?\d[\d\s().-]{6,}\d/);
    if (fromAria) {
      return fromAria;
    }

    if (value.href.startsWith("tel:")) {
      return value.href.replace("tel:", "").trim();
    }
  }

  const body = await page.content();
  return firstMatch(body, /\+?\d[\d\s().-]{8,}\d/);
}

async function extractEmail(page, websiteUrl) {
  const emailRegex = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/;

  const mailto = await page.$$eval("a[href^='mailto:']", (nodes) => (nodes[0]?.getAttribute("href") || "").trim());
  if (mailto.toLowerCase().startsWith("mailto:")) {
    const email = mailto.slice(7).split("?")[0].trim();
    if (emailRegex.test(email)) {
      return email;
    }
  }

  const pageSource = await page.content();
  const match = pageSource.match(emailRegex);
  if (match) {
    return match[0];
  }

  if (!websiteUrl) {
    return "";
  }

  try {
    await page.goto(websiteUrl, { waitUntil: "domcontentloaded", timeout: 12000 });
    const siteSource = await page.content();
    const siteMatch = siteSource.match(emailRegex);
    return siteMatch ? siteMatch[0] : "";
  } catch {
    return "";
  }
}

async function extractPlaceDetails(page, url, query) {
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForSelector("h1", { timeout: 12000 });

  const name = await firstText(page, ["h1.DUwDvf", "h1"]);
  if (!name) {
    return null;
  }

  const website = await firstHref(page, [
    "a[data-item-id='authority']",
    "a[data-tooltip='Open website']"
  ]);
  const category = await firstText(page, ["button[jsaction*='pane.rating.category']"]);
  const rating = await firstText(page, ["div.F7nice span[aria-hidden='true']"]);
  const phone = await extractPhone(page);
  const address = await firstText(page, [
    "button[data-item-id='address']",
    "button[data-item-id*='address']",
    "button[aria-label*='Address']",
    "div[data-item-id='address']"
  ]);
  const email = await extractEmail(page, website);

  return {
    Name: name,
    Category: category,
    Rating: rating,
    Phone: phone,
    Email: email,
    Website: website,
    Address: address,
    "Google Maps URL": url,
    "Search Query": query
  };
}

async function scrapeGoogleMaps(query, maxResults) {
  const browser = await launchBrowser();
  const page = await browser.newPage();
  const leads = [];

  await page.setViewport({ width: 1400, height: 1000 });
  await page.setUserAgent(
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      + "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
  );

  try {
    const links = await collectPlaceLinks(page, query, maxResults);
    for (const link of links) {
      try {
        const details = await extractPlaceDetails(page, link, query);
        if (details) {
          leads.push(details);
        }
      } catch {
        continue;
      }

      if (leads.length >= maxResults) {
        break;
      }
      await page.waitForTimeout(700);
    }
    return leads;
  } finally {
    await page.close();
    await browser.close();
  }
}

module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    res.status(405).json({ error: "Method not allowed" });
    return;
  }

  const query = (req.body?.query || "").trim();
  const maxRaw = String(req.body?.max_results ?? DEFAULT_MAX_RESULTS).trim();

  if (!query) {
    res.status(400).json({ error: "Query is required." });
    return;
  }

  const maxResults = Number.parseInt(maxRaw, 10);
  if (!Number.isFinite(maxResults) || maxResults < 1 || maxResults > 100) {
    res.status(400).json({ error: "max_results must be between 1 and 100." });
    return;
  }

  try {
    const leads = await scrapeGoogleMaps(query, maxResults);
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
