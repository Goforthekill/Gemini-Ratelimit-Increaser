import os
import requests
from flask import Flask, request, Response, jsonify
from dotenv import load_dotenv
import logging
from key_manager import key_manager # Import the shared instance

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

# Configuration
GATEWAY_API_KEY = os.getenv("GATEWAY_API_KEY")
GEMINI_API_BASE_URL = os.getenv("GEMINI_API_BASE_URL")
PROXY_HOST = os.getenv("PROXY_HOST", "0.0.0.0")
PROXY_PORT = int(os.getenv("PROXY_PORT", 5000))

if not GEMINI_API_BASE_URL:
    raise ValueError("GEMINI_API_BASE_URL environment variable not set.")
if not GATEWAY_API_KEY:
    raise ValueError("GATEWAY_API_KEY environment variable not set.")

app = Flask(__name__)

# --- Helper Functions ---

def validate_request(incoming_request):
    """Checks if the incoming request uses the correct gateway API key via Bearer token."""
    auth_header = incoming_request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return False
    provided_key = auth_header.split(' ')[1]
    return provided_key == GATEWAY_API_KEY

# --- Routes ---

# Catch all routes matching the base path (e.g., /v1/...)
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def forward_request(path):
    """Catches all requests and forwards them to the Gemini OpenAI-compatible API."""

    # 1. Authentication
    if not validate_request(request):
        auth_header = request.headers.get('Authorization')
        logging.warning(f"Unauthorized attempt. Header: '{auth_header}'")
        # Mimic OpenAI's typical unauthorized response
        return jsonify({
            "error": {
                "message": "Incorrect API key provided.",
                "type": "invalid_request_error",
                "param": None,
                "code": "invalid_api_key"
            }
        }), 401 # Unauthorized

    # 2. Get current Gemini key
    gemini_api_key = key_manager.get_key()
    key_short = gemini_api_key[:4] + "..." + gemini_api_key[-4:]
    logging.info(f"Using Gemini API key: {key_short} for request path: {path}")

    # 3. Prepare the request for Gemini's OpenAI endpoint
    # Ensure leading/trailing slashes are handled correctly
    target_url = f"{GEMINI_API_BASE_URL.rstrip('/')}/{path.lstrip('/')}"

    # Copy query parameters (OpenAI uses these less often for core APIs, but maybe for others)
    forward_params = request.args.copy()

    # Copy headers, removing Host and the original Authorization, adding the new one
    forward_headers = {
        key: value for key, value in request.headers.items()
        if key.lower() not in ['host', 'authorization']
    }
    forward_headers['Authorization'] = f'Bearer {gemini_api_key}' # Add real Gemini key

    # Get request body
    data = request.get_data()

    # 4. Make the request to Gemini
    try:
        gemini_response = requests.request(
            method=request.method,
            url=target_url,
            headers=forward_headers,
            params=forward_params,
            data=data,
            stream=True, # Important for streaming responses
            timeout=180 # Set a reasonable timeout
        )
        gemini_response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

    except requests.exceptions.RequestException as e:
        status_code = e.response.status_code if e.response is not None else 500
        error_body = e.response.content if e.response is not None else b'{"error": "Upstream connection error"}'
        error_headers = e.response.headers if e.response is not None else {}

        logging.error(f"Error forwarding request to Gemini ({status_code}): {e}")
        if e.response is not None:
             logging.error(f"Gemini Response Body: {error_body.decode('utf-8', errors='ignore')}")

        # Check specifically for rate limiting errors (429 or 503)
        # Google often uses 429 for rate limits, even via the OpenAI endpoint
        if status_code == 429 or status_code == 503:
            logging.warning(f"Rate limit detected (Status {status_code}) with key {key_short}.")
            key_manager.rotate_key() # Rotate to the next key

        # Forward the exact error response back to the client
        # Filter headers like requests does by default
        excluded_headers = ['content-encoding', 'transfer-encoding', 'connection']
        response_headers = [(k, v) for k, v in error_headers.items() if k.lower() not in excluded_headers]
        return Response(error_body, status=status_code, headers=response_headers)


    # 5. Stream the successful response back to the client
    excluded_headers = ['content-encoding', 'transfer-encoding', 'connection']
    response_headers = [(k, v) for k, v in gemini_response.headers.items() if k.lower() not in excluded_headers]

    # Set content type explicitly if it exists, as Flask/requests might sometimes alter it
    if 'content-type' in gemini_response.headers:
         response_headers.append(('Content-Type', gemini_response.headers['content-type']))


    return Response(gemini_response.iter_content(chunk_size=8192), # Stream content
                    status=gemini_response.status_code,
                    headers=response_headers)


@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({"status": "ok", "using_openai_compat_endpoint": True}), 200

# --- Run the App ---

if __name__ == '__main__':
    logging.info(f"Starting OpenAI-compatible Gemini Proxy on {PROXY_HOST}:{PROXY_PORT}")
    logging.info(f"Forwarding to: {GEMINI_API_BASE_URL}")
    logging.info(f"Expecting Gateway Key: {GATEWAY_API_KEY[:4]}... (Check Authorization: Bearer header)")
    # Use a production-ready server like Gunicorn or Waitress in production
    app.run(host=PROXY_HOST, port=PROXY_PORT, threaded=True) # threaded=True for basic concurrency
    # Production command example: gunicorn --workers 4 --bind 0.0.0.0:5000 app:app