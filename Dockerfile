# Start with the official Google base image
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install -r requirements.txt

# --- THIS IS THE CRITICAL FIX ---
# 1. Define a system-wide, predictable path for Playwright's browser cache.
ENV PLAYWRIGHT_BROWSERS_PATH=/var/cache/ms-playwright

# 2. Run the installer. It will now use the path from the environment variable.
RUN playwright install --with-deps

# 3. Ensure the directory is writable by all users.
RUN chmod -R 777 $PLAYWRIGHT_BROWSERS_PATH
# --- END OF FIX ---

# Copy the rest of your application code
COPY . .

# Set the entrypoint for Functions Framework
CMD exec functions-framework --target=scrape_product_images --port=8080
