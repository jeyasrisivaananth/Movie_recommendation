import csv
import urllib.request
import urllib.parse
import json
import ssl
import time
import re
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

ctx = ssl._create_unverified_context()

CSV_PATH = r"c:\Users\91999\OneDrive\Desktop\movie\Movies(Tamil)2015-2025.csv"
OUTPUT_JSON = r"c:\Users\91999\OneDrive\Desktop\movie\poster_map.json"
CACHE_JSON = r"c:\Users\91999\OneDrive\Desktop\movie\omdb_cache.json"

# Lock for print, progressive saves, and cache access
lock = threading.Lock()

# Load cache if exists
omdb_cache = {}
if os.path.exists(CACHE_JSON):
    try:
        with open(CACHE_JSON, 'r', encoding='utf-8') as f:
            omdb_cache = json.load(f)
    except Exception:
        pass

def save_cache():
    with open(CACHE_JSON, 'w', encoding='utf-8') as f:
        json.dump(omdb_cache, f, indent=2)

def query_omdb(params):
    query_str = urllib.parse.urlencode(params)
    cache_key = query_str
    
    # Check cache first
    with lock:
        if cache_key in omdb_cache:
            return omdb_cache[cache_key]
            
    # Fetch from API
    url = f"http://www.omdbapi.com/?apikey=thewdb&{query_str}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=8) as response:
            data = json.loads(response.read().decode('utf-8'))
            with lock:
                omdb_cache[cache_key] = data
                # Progressive save cache every 50 requests
                if len(omdb_cache) % 50 == 0:
                    save_cache()
            return data
    except Exception:
        return {}

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

def verify_movie(data, director, cast):
    if not data or data.get('Response') != 'True':
        return False
    if data.get('Type') != 'movie':
        return False
        
    omdb_year = data.get('Year', '')
    year_match_res = re.search(r'\d{4}', omdb_year)
    if not year_match_res:
        return False
    year_val = int(year_match_res.group(0))
    if not (2014 <= year_val <= 2026):
        return False
        
    omdb_director = data.get('Director', '')
    omdb_actors = data.get('Actors', '').split(',')
    omdb_lang = data.get('Language', '')
    
    dir_match = check_overlap([director], [omdb_director])
    cast_match = check_overlap(cast, omdb_actors)
    lang_match = 'tamil' in omdb_lang.lower()
    
    return dir_match or cast_match or lang_match

def generate_variations(clean_title):
    variations = [clean_title]
    title_lower = clean_title.lower()
    
    # spelling variation 1: dh -> th
    if "dh" in title_lower:
        variations.append(title_lower.replace("dh", "th"))
        variations.append(title_lower.replace("dh", "t"))
    # spelling variation 2: double consonants
    consonants = ['n', 'k', 't', 'p', 'r', 'l', 'd']
    for c in consonants:
        cc = c + c
        if cc in title_lower:
            variations.append(title_lower.replace(cc, c))
        elif c in title_lower:
            # Replace single with double
            variations.append(re.sub(c, cc, title_lower, count=1))
            
    # spelling variation 3: trailing a/aa/i/ee
    if title_lower.endswith('i'):
        variations.append(title_lower[:-1] + 'y')
    elif title_lower.endswith('y'):
        variations.append(title_lower[:-1] + 'i')
        
    return list(dict.fromkeys(variations))

def find_movie_poster(title, director, cast):
    clean_title = re.sub(r'\s*\([^)]*\)', '', title).strip()
    
    # Strategy 1: Direct lookup on clean title
    data = query_omdb({'t': clean_title})
    if verify_movie(data, director, cast):
        poster = data.get('Poster')
        if poster and poster != 'N/A':
            return poster, f"Strategy 1 (Direct: {data.get('Title')})"
            
    # Strategy 2: Direct lookup on variations
    variations = generate_variations(clean_title)
    for var in variations:
        if var == clean_title:
            continue
        data = query_omdb({'t': var})
        if verify_movie(data, director, cast):
            poster = data.get('Poster')
            if poster and poster != 'N/A':
                return poster, f"Strategy 2 (Direct Var '{var}': {data.get('Title')})"
                
    # Strategy 3: OMDb Search on clean title (Check first 3 pages of search results)
    for page in range(1, 4):
        search_data = query_omdb({'s': clean_title, 'type': 'movie', 'page': page})
        if search_data.get('Response') == 'True':
            for cand in search_data.get('Search', []):
                # Verify cand year is 2014-2026 before fetching detail
                cand_year = cand.get('Year', '')
                year_match_res = re.search(r'\d{4}', cand_year)
                if year_match_res:
                    year_val = int(year_match_res.group(0))
                    if not (2014 <= year_val <= 2026):
                        continue
                
                cand_data = query_omdb({'i': cand.get('imdbID')})
                if verify_movie(cand_data, director, cast):
                    poster = cand_data.get('Poster')
                    if poster and poster != 'N/A':
                        return poster, f"Strategy 3 (Search P{page}: {cand_data.get('Title')})"
                        
    # Strategy 4: OMDb Search on variations (Check first 2 pages)
    for var in variations:
        if var == clean_title:
            continue
        for page in range(1, 3):
            search_data = query_omdb({'s': var, 'type': 'movie', 'page': page})
            if search_data.get('Response') == 'True':
                for cand in search_data.get('Search', []):
                    cand_year = cand.get('Year', '')
                    year_match_res = re.search(r'\d{4}', cand_year)
                    if year_match_res:
                        year_val = int(year_match_res.group(0))
                        if not (2014 <= year_val <= 2026):
                            continue
                    
                    cand_data = query_omdb({'i': cand.get('imdbID')})
                    if verify_movie(cand_data, director, cast):
                        poster = cand_data.get('Poster')
                        if poster and poster != 'N/A':
                            return poster, f"Strategy 4 (Search Var '{var}' P{page}: {cand_data.get('Title')})"
                            
    # Strategy 5: Word splitting fallback
    words = [w for w in clean_title.split() if len(w) >= 3]
    for w in words:
        if w.lower() in ['the', 'and', 'for', 'with', 'tamil', 'movie']:
            continue
        search_data = query_omdb({'s': w, 'type': 'movie'})
        if search_data.get('Response') == 'True':
            for cand in search_data.get('Search', []):
                cand_year = cand.get('Year', '')
                year_match_res = re.search(r'\d{4}', cand_year)
                if year_match_res:
                    year_val = int(year_match_res.group(0))
                    if not (2014 <= year_val <= 2026):
                        continue
                
                cand_data = query_omdb({'i': cand.get('imdbID')})
                if verify_movie(cand_data, director, cast):
                    poster = cand_data.get('Poster')
                    if poster and poster != 'N/A':
                        return poster, f"Strategy 5 (Word '{w}': {cand_data.get('Title')})"

    # Strategy 6: Direct + "Tamil"
    data = query_omdb({'t': clean_title + " Tamil"})
    if data.get('Response') == 'True' and data.get('Type') == 'movie':
        omdb_year = data.get('Year', '')
        year_match_res = re.search(r'\d{4}', omdb_year)
        if year_match_res and 2014 <= int(year_match_res.group(0)) <= 2026:
            poster = data.get('Poster')
            if poster and poster != 'N/A':
                return poster, f"Strategy 6 (Direct + Tamil: {data.get('Title')})"
                
    # Strategy 7: Search + "Tamil"
    search_data = query_omdb({'s': clean_title + " Tamil", 'type': 'movie'})
    if search_data.get('Response') == 'True':
        for cand in search_data.get('Search', []):
            cand_year = cand.get('Year', '')
            year_match_res = re.search(r'\d{4}', cand_year)
            if year_match_res and 2014 <= int(year_match_res.group(0)) <= 2026:
                cand_data = query_omdb({'i': cand.get('imdbID')})
                poster = cand_data.get('Poster')
                if poster and poster != 'N/A':
                    return poster, f"Strategy 7 (Search + Tamil: {cand_data.get('Title')})"
                    
    # Strategy 8: Relaxed Year/Type Match (Last resort)
    data = query_omdb({'t': clean_title})
    if data.get('Response') == 'True' and data.get('Type') == 'movie':
        omdb_year = data.get('Year', '')
        year_match_res = re.search(r'\d{4}', omdb_year)
        if year_match_res:
            year_val = int(year_match_res.group(0))
            if 2014 <= year_val <= 2026:
                poster = data.get('Poster')
                if poster and poster != 'N/A':
                    return poster, f"Strategy 8 (Relaxed: {data.get('Title')})"

    return None, None

def process_single_movie(m, index, total):
    poster, strategy = find_movie_poster(m['title'], m['director'], m['cast'])
    with lock:
        if poster:
            print(f"[{index}/{total}] '{m['title']}' -> SUCCESS: {poster}", flush=True)
        else:
            print(f"[{index}/{total}] '{m['title']}' -> FAILED", flush=True)
    return m['id'], poster

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

    print(f"Loaded {len(movies)} Tamil movies from CSV.")
    
    # We clear the poster map entirely and start from the beginning as requested
    poster_map = {}
    print("Starting matching from the beginning (wiped old map).")

    total_to_process = len(movies)
    print(f"Starting parallel matching for {total_to_process} movies with 15 worker threads...")
    
    completed_count = 0
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(process_single_movie, m, i+1, total_to_process): m for i, m in enumerate(movies)}
        
        for future in as_completed(futures):
            m_id, poster = future.result()
            if poster:
                poster_map[m_id] = poster
            else:
                poster_map[m_id] = "" # Mark failed to skip in case of script reruns
            completed_count += 1
            
            # Save progressively
            if completed_count % 10 == 0 or completed_count == total_to_process:
                with lock:
                    with open(OUTPUT_JSON, 'w') as f:
                        json.dump(poster_map, f, indent=2)
                    save_cache()

    save_cache()
    total_matched = len([v for v in poster_map.values() if v])
    print(f"\nCompleted! Total movies: {len(movies)}, Successfully matched posters: {total_matched}")

if __name__ == "__main__":
    main()
