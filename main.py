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
        # Get the first URL from the list
        src = img_tag.get('srcset').split(',')[0].strip().split(' ')[0]
    elif img_tag.get('src'):
        src = img_tag.get('src')
    else:
        return 0, "" # No source, no score

    # Ignore tiny placeholders, icons, and logos
    if 'data:image' in src or '.svg' in src or '.gif' in src:
        return 0, ""

    # CLUE 1: Higher score for being a high-resolution image
    # We check if the 'src' URL itself gives a hint about size
    if '1000x1000' in src or 'large' in src:
        score += 20
    if '300x300' in src or 'medium' in src:
        score += 10
    if '150x150' in src or 'thumb' in src:
        score -= 10 # Penalize thumbnails

    # CLUE 2: Check the 'alt' text for descriptive words
    alt_text = img_tag.get('alt', '').lower()
    if 'zoom' in alt_text or 'front' in alt_text:
        score += 15
    if 'logo' in alt_text:
        score -= 50 # Heavily penalize logos

    # CLUE 3: Check the image's class names
    class_names = " ".join(img_tag.get('class', [])).lower()
    if 'wp-post-image' in class_names or 'main-image' in class_names:
        score += 30 # This is a strong positive signal

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
            
            candidate_images = []
            # Try to find a specific gallery container first for higher quality candidates
            gallery = soup.find('figure', {'class': 'woocommerce-product-gallery'}) or \
                      soup.find('div', {'data-testid': 'image-carousel-container'})

            if gallery:
                print("INFO: Found specific image gallery. Processing candidates.")
                candidate_images = gallery.find_all('img')
            else:
                print("WARNING: No specific gallery found. Using all images on page.")
                candidate_images = soup.find_all('img')

            if not candidate_images:
                print("ERROR: No images found on the page at all.")
                return ({"error": "No images could be found on the page."}, 404, headers)

            # Score all candidate images
            scored_images = []
            for img in candidate_images:
                score, url = score_image(img, product_url)
                if score > 0 and url:
                    scored_images.append({'score': score, 'url': url})
            
            # If no images scored positive, return an error
            if not scored_images:
                print("ERROR: Found images, but none met the filtering criteria.")
                return ({"error": "Could not identify a suitable product image."}, 404, headers)

            # Sort by score (highest first) and remove duplicates
            # A bit of logic to handle duplicate URLs from scoring
            seen_urls = set()
            unique_sorted_images = []
            for item in sorted(scored_images, key=lambda x: x['score'], reverse=True):
                if item['url'] not in seen_urls:
                    unique_sorted_images.append(item)
                    seen_urls.add(item['url'])

            best_image_url = unique_sorted_images[0]['url']
            print(f"SUCCESS: Best image found with score {unique_sorted_images[0]['score']}: {best_image_url}")

            # Return just the single best URL
            return ({"product_image": best_image_url}, 200, headers)

    except Exception as e:
        print(f"CRITICAL: An error occurred: {e}")
        return (f"An error occurred: {e}", 500, headers)
