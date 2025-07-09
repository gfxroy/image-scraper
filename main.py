import functions_framework
import urllib.parse
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def get_best_src(img_tag):
    """Parses srcset to find the highest quality image URL."""
    if img_tag.get('srcset'):
        sources = img_tag.get('srcset').split(',')
        best_url = ""
        max_width = 0
        for source in sources:
            parts = source.strip().split(' ')
            if len(parts) == 2 and parts[1].endswith('w'):
                try:
                    width = int(parts[1][:-1])
                    if width > max_width:
                        max_width = width
                        best_url = parts[0]
                except ValueError:
                    continue
        if best_url:
            return best_url
    # Fallback to src if srcset is not available or unparsable
    return img_tag.get('src', '')

def score_image(img_tag, product_url):
    """Scores an image based on a more robust set of heuristics."""
    score = 0
    src = get_best_src(img_tag)

    if not src or 'data:image' in src or '.svg' in src or '.gif' in src:
        return 0, ""

    # CLUE 1: Huge bonus for being the main WordPress post image
    class_names = " ".join(img_tag.get('class', [])).lower()
    if 'wp-post-image' in class_names:
        score += 100  # This is a very strong signal

    # CLUE 2: Penalize small thumbnail images based on URL
    for thumb_size in ['-220x', '-300x', '-150x']:
        if thumb_size in src:
            score -= 50

    # CLUE 3: Check alt text
    alt_text = img_tag.get('alt', '').lower()
    if 'logo' in alt_text:
        score -= 100

    full_url = urllib.parse.urljoin(product_url, src)
    return score, full_url

@functions_framework.http
def scrape_product_images(request):
    headers = {'Access-Control-Allow-Origin': '*'}
    request_json = request.get_json(silent=True)
    if not request_json or 'url' not in request_json:
        return ('Error: Missing "url" in JSON request body.', 400, headers)
    
    product_url = request_json['url']
    print(f"INFO: Received request for URL: {product_url}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(product_url, wait_until="domcontentloaded", timeout=60000)
            
            # --- THE CRITICAL FIX ---
            # Wait specifically for the gallery container to be rendered by JavaScript.
            # This is more reliable than waiting for network or a fixed time.
            gallery_selector = 'figure.woocommerce-product-gallery'
            print(f"INFO: Waiting for selector '{gallery_selector}' to appear...")
            page.wait_for_selector(gallery_selector, timeout=15000) # Wait up to 15 seconds
            print("INFO: Gallery selector found!")

            html_content = page.content()
            browser.close()
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            gallery = soup.find('figure', {'class': 'woocommerce-product-gallery'})
            candidate_images = gallery.find_all('img') if gallery else soup.find_all('img')

            if not candidate_images:
                return ({"error": "No images could be found on the page."}, 404, headers)

            scored_images = []
            print("\n--- STARTING IMAGE SCORING (v3) ---")
            for img in candidate_images:
                score, url = score_image(img, product_url)
                if url:
                    print(f"DEBUG: Score={score}, URL={url}")
                    if score > 0:
                        scored_images.append({'score': score, 'url': url})
            print("--- FINISHED IMAGE SCORING ---\n")
            
            if not scored_images:
                return ({"error": "Could not identify a suitable product image."}, 404, headers)

            # Sort and remove duplicates
            seen_urls = set()
            unique_sorted_images = []
            for item in sorted(scored_images, key=lambda x: x['score'], reverse=True):
                if item['url'] not in seen_urls:
                    unique_sorted_images.append(item)
                    seen_urls.add(item['url'])
            
            print(f"SUCCESS: Found {len(unique_sorted_images)} unique, scorable images.")

            # FOR NOW, let's keep it in "Debug Mode" and return the whole list
            return ({"scored_images": unique_sorted_images}, 200, headers)
            
            # ONCE YOU ARE HAPPY, switch to this to return only the best one:
            # best_image_url = unique_sorted_images[0]['url']
            # return ({"product_image": best_image_url}, 200, headers)

    except Exception as e:
        print(f"CRITICAL: An error occurred: {e}")
        return (f"An error occurred: {e}", 500, headers)
