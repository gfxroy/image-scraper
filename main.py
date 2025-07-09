import functions_framework
import urllib.parse
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

@functions_framework.http
def scrape_product_images(request):
    headers = {'Access-Control-Allow-Origin': '*'}

    request_json = request.get_json(silent=True)
    if not request_json or 'url' not in request_json:
        return ('Error: Missing "url" in JSON request body.', 400, headers)
    
    product_url = request_json['url']
    if not product_url:
        return ('Error: The "url" field cannot be empty.', 400, headers)

    print(f"INFO: Received request to scrape URL: {product_url}")

    image_urls = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Go to the URL and wait until the page is fully loaded
            page.goto(product_url, wait_until="networkidle", timeout=60000)
            
            # Give the page an extra moment just in case of lazy-loading scripts
            page.wait_for_timeout(3000)

            html_content = page.content()
            browser.close()
            print("INFO: Successfully retrieved page content.")

            # --- NEW ADAPTIVE PARSING LOGIC ---
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # METHOD 1: Try the specific, "nice" selector for WooCommerce first.
            image_container = soup.find('figure', {'class': 'woocommerce-product-gallery'})
            
            if image_container:
                print("INFO: Found 'woocommerce-product-gallery' container. Parsing images inside.")
                img_tags = image_container.find_all('img')
            else:
                # METHOD 2: FALLBACK / BRUTE FORCE
                # If the specific container isn't found, just get ALL images on the page.
                print("WARNING: Specific container not found. Falling back to find ALL img tags on page.")
                img_tags = soup.find_all('img')

            print(f"INFO: Found a total of {len(img_tags)} <img> tags to process.")

            for img in img_tags:
                # Prioritize high-resolution 'srcset' if it exists, otherwise use 'src'.
                src = ""
                if img.get('srcset'):
                    # srcset is a comma-separated list of "url size", e.g., "img-300.jpg 300w, img-600.jpg 600w"
                    # We'll just take the first URL from the set.
                    src = img.get('srcset').split(',')[0].split(' ')[0]
                elif img.get('src'):
                    src = img.get('src')

                if src:
                    # Filter out tiny images like tracking pixels or icons (e.g., 1x1 pixel gifs)
                    if 'data:image' in src or '.svg' in src or 'gif' in src:
                        continue
                    
                    absolute_src = urllib.parse.urljoin(product_url, src)
                    image_urls.append(absolute_src)

    except Exception as e:
        print(f"CRITICAL: An error occurred during scraping: {e}")
        # For debugging, let's also dump the HTML we received on error
        # with open("error_page.html", "w") as f:
        #    f.write(html_content)
        return (f"An error occurred during scraping: {e}", 500, headers)

    # Remove duplicates and return
    final_images = list(set(image_urls))
    print(f"SUCCESS: Found {len(final_images)} unique images.")
    return ({"images": final_images}, 200, headers)
