import csv
import urllib.request
import urllib.parse
import json
import ssl
import re
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

ctx = ssl._create_unverified_context()

CSV_PATH = r"c:\Users\91999\OneDrive\Desktop\movie\Movies(Tamil)2015-2025.csv"
POSTER_MAP_PATH = r"c:\Users\91999\OneDrive\Desktop\movie\poster_map.json"

lock = threading.Lock()

# Standardized User-Agent header as required by Wikimedia Foundation API Policy
WIKI_HEADERS = {
    'User-Agent': 'TamilMovieRecommenderPosterBot/1.0 (contact@tamilmovierecommender.org; public bot for class project)'
}

# Simple thread-safe rate limiter to avoid 429 Too Many Requests
last_request_time = 0

def rate_limit_delay():
    global last_request_time
    with lock:
        now = time.time()
        elapsed = now - last_request_time
        # Ensure at least 0.4 seconds between queries
        if elapsed < 0.4:
            time.sleep(0.4 - elapsed)
        last_request_time = time.time()

def query_wiki_api(params):
    rate_limit_delay()
    query_str = urllib.parse.urlencode(params)
    url = f"https://en.wikipedia.org/w/api.php?{query_str}"
    req = urllib.request.Request(url, headers=WIKI_HEADERS)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=8) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        with lock:
            print(f"API error querying {url}: {e}", flush=True)
        return {}

def check_url_status(url):
    """
    Returns True if the URL is valid and does not return a 404 error.
    Otherwise, returns False.
    """
    if not url:
        return False
    req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
            if response.status == 200:
                return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        return True
    except Exception:
        return True
    return True

def clean_name(name):
    if not name:
        return ""
    name = re.sub(r'[^a-zA-Z0-9\s]', '', name)
    return name.lower().strip()

def check_overlap(list1, list2):
    set1 = set(clean_name(x) for x in list1 if x)
    set2 = set(clean_name(x) for x in list2 if x)
    set1 = {x for x in set1 if len(x) > 2}
    set2 = {x for x in set2 if len(x) > 2}
    
    for s1 in set1:
        for s2 in set2:
            if s1 in s2 or s2 in s1:
                return True
    return False

def find_wikipedia_poster(title, director, cast):
    # Clean parenthetical ratings like (U), (U/A), (A), (PG)
    clean_title = re.sub(r'\s*\([^)]*\)', '', title).strip()
    
    # 1. Search Wikipedia
    search_query = f"{clean_title} Tamil film"
    search_data = query_wiki_api({
        'action': 'query',
        'list': 'search',
        'srsearch': search_query,
        'utf8': '',
        'format': 'json'
    })
    
    search_results = search_data.get('query', {}).get('search', [])
    if not search_results:
        # Try broader search
        search_query = f"{clean_title} film"
        search_data = query_wiki_api({
            'action': 'query',
            'list': 'search',
            'srsearch': search_query,
            'utf8': '',
            'format': 'json'
        })
        search_results = search_data.get('query', {}).get('search', [])
        
    if not search_results:
        return None, "No Wikipedia pages found"

    # Inspect the top 4 candidates
    candidates = [r['title'] for r in search_results[:4]]
    
    # 2. Query lead section revisions (content) of candidates
    titles_param = '|'.join(candidates)
    page_data = query_wiki_api({
        'action': 'query',
        'prop': 'revisions',
        'titles': titles_param,
        'rvprop': 'content',
        'rvsection': '0',
        'format': 'json'
    })
    
    pages = page_data.get('query', {}).get('pages', {})
    
    best_candidate_title = None
    best_image_name = None
    best_score = -1
    best_reasons = ""
    
    for page_id, p_info in pages.items():
        if 'missing' in p_info:
            continue
            
        p_title = p_info.get('title', '')
        revisions = p_info.get('revisions', [])
        if not revisions:
            continue
            
        content = revisions[0].get('*', '')
        
        # Relevance scoring
        score = 0
        reasons = []
        
        p_title_clean = clean_name(p_title)
        clean_title_clean = clean_name(clean_title)
        if clean_title_clean in p_title_clean or p_title_clean in clean_title_clean:
            score += 10
            reasons.append("Title matched")
            
        if '{{infobox film' in content.lower():
            score += 20
            reasons.append("Infobox film")
            
        if director and check_overlap([director], [content]):
            score += 15
            reasons.append("Director matched")
            
        cast_matches = 0
        if cast:
            for actor in cast:
                if clean_name(actor) in clean_name(content):
                    cast_matches += 1
            if cast_matches > 0:
                score += (5 * cast_matches)
                reasons.append(f"{cast_matches} cast matched")
                
        if 'tamil' in content.lower():
            score += 8
            reasons.append("Tamil keyword matched")
            
        if 'soundtrack' in p_title_clean or 'discography' in p_title_clean or 'album' in p_title_clean:
            score -= 20
        if 'list of' in p_title_clean or 'filmography' in p_title_clean:
            score -= 15
            
        # Parse image parameter from infobox
        img_match = re.search(r'\|\s*(?:image|poster)\s*=\s*([^|\n\r]+)', content, re.IGNORECASE)
        img_name = None
        if img_match:
            img_val = img_match.group(1).strip()
            # Clean image name formatting (e.g. removing [[File: prefix)
            img_val = re.sub(r'\[\[(?:File|Image):', '', img_val, flags=re.IGNORECASE)
            img_val = img_val.split('|')[0].replace(']]', '').strip()
            if img_val and not img_val.lower().endswith(('.svg', '.png_placeholder', 'no_image.png')):
                img_name = img_val
                
        if img_name:
            score += 5
            reasons.append("Has image")
        else:
            score -= 10
            reasons.append("No image")
            
        if score > best_score:
            best_score = score
            best_candidate_title = p_title
            best_image_name = img_name
            best_reasons = ", ".join(reasons)
            
    # Require a baseline score of 10 (needs to have matched title or other strong film cues) and an image
    if best_score > 10 and best_image_name:
        file_title = best_image_name
        if not file_title.lower().startswith('file:') and not file_title.lower().startswith('image:'):
            file_title = f"File:{file_title}"
            
        img_data = query_wiki_api({
            'action': 'query',
            'prop': 'imageinfo',
            'titles': file_title,
            'iiprop': 'url',
            'format': 'json'
        })
        
        img_pages = img_data.get('query', {}).get('pages', {})
        for img_id, img_info in img_pages.items():
            info = img_info.get('imageinfo', [])
            if info:
                poster_url = info[0].get('url')
                return poster_url, f"Wikipedia (Score: {best_score}, Reasons: {best_reasons}, Page: {best_candidate_title})"
                
    return None, f"No confident page with image found (best candidate: {best_candidate_title}, score: {best_score})"

def process_movie(m, poster_map):
    m_id = str(m['id'])
    existing_url = poster_map.get(m_id, "")
    
    # 1. If we already have a valid poster URL, keep it!
    # (Skip checking OMDb URLs that were already validated in previous run to save network resources)
    # If the URL is already a Wikipedia URL or standard media-amazon URL, let's do a status check
    # to make sure it's valid. If it's not empty, we verify it.
    if existing_url:
        is_valid = check_url_status(existing_url)
        if is_valid:
            return m_id, existing_url, "Existing (Validated)"
        else:
            with lock:
                print(f"[{m_id}] '{m['title']}' Existing URL returned 404: {existing_url}. Resolving fallback...", flush=True)

    # 2. Try Wikipedia fallback
    poster, reason = find_wikipedia_poster(m['title'], m['director'], m['cast'])
    if poster:
        with lock:
            print(f"[{m_id}] '{m['title']}' -> WIKIPEDIA SUCCESS: {poster}", flush=True)
        return m_id, poster, reason
    else:
        with lock:
            print(f"[{m_id}] '{m['title']}' -> FAILED to resolve Wikipedia: {reason}", flush=True)
        return m_id, "", reason

def main():
    movies = []
    with open(CSV_PATH, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            if len(row) >= 6:
                movies.append({
                    'id': row[0].strip(),
                    'title': row[1].strip(),
                    'director': row[4].strip(),
                    'cast': [x.strip() for x in row[5].split(',') if x.strip()]
                })

    # Load existing poster map
    poster_map = {}
    if os.path.exists(POSTER_MAP_PATH):
        try:
            with open(POSTER_MAP_PATH, 'r') as f:
                poster_map = json.load(f)
        except Exception:
            pass

    print(f"Loaded {len(movies)} Tamil movies from CSV.")
    print(f"Loaded {len(poster_map)} entries from poster_map.json.")
    print("Resolving fallbacks on Wikipedia (using 4 worker threads with rate-limiting)...")

    updated_map = {}
    success_count = 0
    wiki_resolved = 0
    existing_validated = 0
    failed_count = 0

    # Limit to 4 worker threads to work nicely with rate limiting
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(process_movie, m, poster_map): m for m in movies}
        
        for future in as_completed(futures):
            m_id, poster, source = future.result()
            updated_map[m_id] = poster
            
            if poster:
                success_count += 1
                if "Wikipedia" in source:
                    wiki_resolved += 1
                else:
                    existing_validated += 1
            else:
                failed_count += 1
                
            # Progressive save
            if (wiki_resolved + failed_count) % 10 == 0:
                with lock:
                    with open(POSTER_MAP_PATH, 'w') as f:
                        json.dump(updated_map, f, indent=2)

    # Final save
    with open(POSTER_MAP_PATH, 'w') as f:
        json.dump(updated_map, f, indent=2)

    print("\n" + "="*50)
    print("Wikipedia Poster Fallback Matching Complete!")
    print(f"Total Movies: {len(movies)}")
    print(f"Successfully Matched: {success_count} ({success_count/len(movies)*100:.1f}%)")
    print(f"  - Existing Validated: {existing_validated}")
    print(f"  - Wikipedia Fallback Resolved: {wiki_resolved}")
    print(f"Failed/Fallback Initials: {failed_count}")
    print("="*50)

if __name__ == '__main__':
    main()
