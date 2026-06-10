# 🎬 Tamil Movie Recommender & Similarity Engine

A premium, interactive web application for browsing, searching, and recommending Tamil movies from 2015 to 2025. The app implements a content-based recommendation engine and fetches live movie poster images using a custom, multi-threaded metadata scraper.

---

## ✨ Features

- **💎 Sleek Modern UI:** Fully responsive glassmorphism dark-mode design using CSS variables and dynamic layouts.
- **🔍 Content-Based Filtering:** Implements Jaccard similarity token matching on director, cast, genres, and overviews to recommend similar movies in real-time.
- **🖼️ 98.2% Poster Accuracy:** Built with a custom Python scraping engine that verifies image availability, queries the OMDb API, and uses Wikipedia Search and lead-section Infobox parsing to fetch high-resolution posters.
- **⭐ Favorites System:** Save your favorite movies directly to your browser's `localStorage` for offline access.
- **📂 Clean & Lightweight:** Operates client-side using vanilla HTML, CSS, and JavaScript, parsing raw CSV data directly in the browser.

---

## 🛠️ Technology Stack

- **Frontend:** Vanilla HTML5, CSS3, JavaScript (ES6+)
- **Typography:** Google Fonts (Outfit)
- **Scraper & Matcher:** Python 3 (urllib, threading, concurrent.futures)
- **APIs Used:** OMDb API, Wikipedia Search & PageImages APIs

---

## 🤖 Metadata & Poster Scraper Bot

To make the app lively and ensure all active movies display their correct posters (rather than outdated links or random Hollywood images), we developed a robust two-phase scraper:

1. **OMDb Lookup (`build_correct_poster_map.py`):** Uses phonetic spelling variations, search pagination, and director/cast overlap verification to match Tamil movie indexes with OMDb/IMDb poster links in parallel.
2. **Wikipedia Fallback (`scrape_wikipedia_posters.py`):** Identifies outdated 404 links and queries Wikipedia Search/Page Revisions APIs, extracting the exact filename from `{{Infobox film}}` and fetching the high-res upload URL.

This pipeline matches **776 out of 790 movies (98.2%)** correctly, with the remaining 14 upcoming/hypothetical movies falling back to generated text-initial gradient cards.

---

## 🚀 How to Run Locally

### 1. Clone the Repository
```bash
git clone https://github.com/jeyasrisivaananth/Movie_recommendation.git
cd Movie_recommendation
```

### 2. Start a Local Server
Since the browser restricts loading local CSV and JSON files directly from the filesystem (`file://`) due to CORS security policies, serve the project using a local web server:

**Using Python:**
```bash
python -m http.server 8000
```

**Using Node.js (npx):**
```bash
npx http-server -p 8000
```

### 3. Open in Browser
Visit **`http://localhost:8000/index.html`** in your web browser.
