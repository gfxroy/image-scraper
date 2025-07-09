import functions_framework
import urllib.parse
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# Helper function to score images based on clues
def score_image(img_tag, product_url):
    score = 0
    src = ""
    # Use the highest resolution source available from srcset
    if img_tag.get('srcset'):
        src = img_tag.get('srcset').split(',')[0].strip().split(' ')[0]
    elif img_tag.get('src'):
        src = img_tag.get('src')
    else:
        return 0, ""

    # Ignore tiny placeholders, icons, and logos
    if 'data:image' in src or '.svg' in src or '.gif' in src:
        return 0, ""

    # CLUE 1: Higher score for being a high-resolution image
    if '1000x1000' in src or 'large' in src or '1024x1024' in src:
        score += 20
    if '300x300' in src or 'medium' in src:
        score += 10
    if '150x150' in src or 'thumb' in src:
        score -= 10

    # CLUE 2: Check the 'alt' text
    alt_text = img_tag.get('alt', '').lower()
    if 'zoom' in alt_text or 'front' in alt_text:
        score += 15
    if 'logo' in alt_text:
        score -= 50

    # CLUE 3: Check the image's class names
    class_names = " ".join(img_tag.get('class', [])).lower()
    if 'wp-post-image' in class_names or 'main-image' in class_names or 'product-image' in class_names:
        score += 30

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
            page.goto(product_url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(2000)
            html_content = page.content()
            browser.close()
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            gallery = soup.find('figure', {'class': 'woocommerce-product-gallery'}) or \
                      soup.find('div', {'data-testid': 'image-carousel-container'})
            
            candidate_images = gallery.find_all('img') if gallery else soup.find_all('img')

            if not candidate_images:
                return ({"error": "No images could be found on the page."}, 404, headers)

            scored_images = []
            print("\n--- STARTING IMAGE SCORING ---")
            for img in candidate_images:
                score, url = score_image(img, product_url)
                # DEBUG: Print the score for every single image
                if url:
                    print(f"DEBUG: Score={score}, URL={url}")
                    if score > 0:
                        scored_images.append({'score': score, 'url': url})
            print("--- FINISHED IMAGE SCORING ---\n")
            
            if not scored_images:
                return ({"error": "Could not identify a suitable product image."}, 404, headers)

            seen_urls = set()
            unique_sorted_images = []
            for item in sorted(scored_images, key=lambda x: x['score'], reverse=True):
                if item['url'] not in seen_urls:
                    unique_sorted_images.append(item)
                    seen_urls.add(item['url'])
            
            print(f"SUCCESS: Found {len(unique_sorted_images)} unique, scorable images.")
            # --- CHANGE FOR DEBUGGING ---
            # Instead of returning just one, return the whole sorted list.
            return ({"scored_images": unique_sorted_images}, 200, headers)

    except Exception as e:
        print(f"CRITICAL: An error occurred: {e}")
        return (f"An error occurred: {e}", 500, headers)
