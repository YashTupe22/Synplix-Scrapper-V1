# Synplix Leads Studio (Vercel Native)

Production-ready Google Maps lead generator built for Vercel using:

- **Node.js serverless API** (`/api/generate`)
- **Google Places API** (no browser runtime needed)
- **Static frontend** (`/public`)
- **In-memory CSV export** (no writable disk dependency)

## Features

- Search Google Maps by query (e.g. `dentist in mumbai`)
- Extract lead details:
  - Name
  - Category
  - Rating
  - Phone
  - Email (best-effort)
  - Address
  - Website
- Download results as CSV instantly from browser
- Dark, production-style Synplix UI

## Project Structure

```text
api/
  generate.js        # Vercel serverless scraping endpoint
public/
  index.html         # UI
  style.css          # Design system styling
  app.js             # Client-side fetch/render/download
vercel.json          # Node/static build + routing config
package.json         # Node dependencies
```

## Local Setup

1. Install Node.js 18+
2. Install dependencies:

```bash
npm install
```

3. Run locally with Vercel CLI:

```bash
vercel dev
```

4. Open:

```text
http://localhost:3000
```

## Deploy to Vercel

1. Push to GitHub.
2. Import project in Vercel.
3. Add environment variable:
   - `GOOGLE_PLACES_API_KEY=<your_google_api_key>`
4. Deploy.
5. On major runtime/config changes, use **Redeploy with Clear Build Cache**.

## Runtime Notes

- Uses Google Places API calls from Vercel serverless.
- `max_results` is capped for runtime safety.
- Requires Google Cloud billing + Places API enabled.

## Security Notes

- Never paste live API tokens publicly.
- Rotate any token that has been exposed in logs/chat.

## License

Use internally for your Synplix workflows unless your team sets a separate license policy.
