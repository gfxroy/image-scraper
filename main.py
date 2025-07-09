import functions_framework
import urllib.parse
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

# This decorator turns our Python function into an HTTP-triggered web service.
@functions_framework.http
def scrape_product_images(request):
    """
    An HTTP Cloud Function that scrapes product images from a given URL.
    """
    # Set headers to allow requests from any website (CORS).
    headers = {'Access-Control-Allow-Origin': '*'}

    # --- 1. Get the URL from the incoming request ---
    # We expect a POST request with a JSON body like: {"url": "http://..."}
    request_json = request.get_json(silent=True)
    if not request_json or 'url' not in request_json:
        return ('Error: Missing "url" in JSON request body.', 400, headers)
    
    product_url = request_json['url']
    if not product_url:
        return ('Error: The "url" field cannot be empty.', 400, headers)

    print(f"Received request to scrape URL: {product_url}")

    # --- 2. Launch the Headless Browser and Scrape the Page ---
    image_urls = []
    try:
        with sync_playwright() as p:
            # Launch a new Chromium browser instance.
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Go to the URL and wait until the page is fully loaded (including network activity).
            page.goto(product_url, wait_until="networkidle", timeout=60000) # 60 second timeout

            # Get the final HTML content of the page after all JavaScript has run.
            html_content = page.content()
            browser.close()
            print("Successfully retrieved page content.")

            # --- 3. Parse the HTML to find the images ---
            # THIS IS THE MOST IMPORTANT PART THAT YOU WILL NEED TO CUSTOMIZE.
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # ** PARSER LOGIC FOR WALMART.COM **
            # We found this by inspecting Walmart's page. Other sites will be different.
            image_container = soup.find('div', {'data-testid': 'image-carousel-container'})
            
            if image_container:
                print("Found the image container.")
                img_tags = image_container.find_all('img')
                for img in img_tags:
                    src = img.get('src')
                    if src:
                        # Make sure the URL is a full URL (not a relative path).
                        absolute_src = urllib.parse.urljoin(product_url, src)
                        image_urls.append(absolute_src)
            else:
                print("WARNING: Could not find the specific image container for Walmart.")
                # You could add fallback logic here to find ALL images on the page if needed.

    except Exception as e:
        print(f"An error occurred during scraping: {e}")
        return (f"An error occurred during scraping: {e}", 500, headers)

    # --- 4. Return the Results ---
    # Remove any duplicate image URLs and return the list as JSON.
    final_images = list(set(image_urls))
    print(f"Found {len(final_images)} unique images.")
    return ({"images": final_images}, 200, headers)
