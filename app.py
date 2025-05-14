import os
import requests
from flask import Flask, request, Response, jsonify
from dotenv import load_dotenv
import logging
from key_manager import key_manager  # Import the shared instance

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

# Configuration
GATEWAY_API_KEY = os.getenv("GATEWAY_API_KEY")
GEMINI_API_BASE_URL = os.getenv("GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/models")  # Standard Gemini API base URL, with a fallback
PROXY_HOST = os.getenv("PROXY_HOST", "0.0.0.0")
PROXY_PORT = int(os.getenv("PROXY_PORT", 5000))
DEFAULT_MODEL = "gemini-pro"  # Default model if none is specified
GEMINI_API_VERSION = os.getenv("GEMINI_API_VERSION", "v1beta") # Default API version

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

def construct_gemini_request_body(data):
    """
    Constructs the request body for the Gemini API, allowing model specification.
    Handles both chat and non-chat formats.
    """
    try:
        json_data = request.get_json()
        if not json_data:
            return {"error": "No JSON data provided in the request"}, 400, DEFAULT_MODEL

        model_name = json_data.get("model", DEFAULT_MODEL)  # Get model from request, default to gemini-pro

        if "messages" in json_data:
            messages = json_data["messages"]
            gemini_messages = []
            for message in messages:
                role = message.get("role", "user")
                content = message.get("content", "")
                gemini_messages.append({
                    "role": role,
                    "parts": [{"text": content}]
                })
            gemini_request_body = {
                "contents": gemini_messages
            }
        else:
            prompt_text = json_data.get("prompt")
            if not prompt_text:
                return {"error": "No prompt provided in the request"}, 400, DEFAULT_MODEL
            gemini_request_body = {
                "contents": [{"parts": [{"text": prompt_text}]}]
            }
        return gemini_request_body, 200, model_name  # Return model name

    except Exception as e:
        logging.error(f"Error constructing Gemini request body: {e}")
        return {"error": f"Invalid request format: {e}"}, 400, DEFAULT_MODEL

# --- Routes ---

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def forward_request(path):
    """Catches all requests and forwards them to the Gemini API."""
    # 1. Authentication
    if not validate_request(request):
        auth_header = request.headers.get('Authorization')
        logging.warning(f"Unauthorized attempt. Header: '{auth_header}'")
        return jsonify({
            "error": {
                "message": "Incorrect API key provided.",
                "type": "invalid_request_error",
                "param": None,
                "code": "invalid_api_key"
            }
        }), 401

    # 2. Get current Gemini key
    gemini_api_key = key_manager.get_key()
    key_short = gemini_api_key[:4] + "..." + gemini_api_key[-4:]
    logging.info(f"Using Gemini API key: {key_short} for request path: {path}")

    # 3. Prepare the request for Gemini
    gemini_request_body, status_code, model_name = construct_gemini_request_body(request.get_data())
    if status_code != 200:
        return jsonify(gemini_request_body), status_code

    # Construct the target URL with the dynamic model name and API version
    target_url = f"{GEMINI_API_BASE_URL.rstrip('/')}/{GEMINI_API_VERSION}/{model_name}:generateContent"

    # Copy query parameters
    forward_params = request.args.copy()
    forward_params['key'] = gemini_api_key

    # Copy headers, removing Host and the original Authorization
    forward_headers = {
        key: value for key, value in request.headers.items()
        if key.lower() not in ['host', 'authorization', 'content-length']
    }

    # 4. Make the request to Gemini
    try:
        gemini_response = requests.post(
            url=target_url,
            headers=forward_headers,
            params=forward_params,
            json=gemini_request_body,
            stream=True,
            timeout=180
        )
        gemini_response.raise_for_status()

    except requests.exceptions.RequestException as e:
        status_code = e.response.status_code if e.response else 500
        error_body = e.response.content if e.response else b'{"error": "Upstream connection error"}'
        error_headers = e.response.headers if e.response else {}
        logging.error(f"Error forwarding request to Gemini ({status_code}): {e}")
        if e.response:
            logging.error(f"Gemini Response Body: {error_body.decode('utf-8', errors='ignore')}")

        if status_code == 429 or status_code == 503:
            logging.warning(f"Rate limit detected (Status {status_code}) with key {key_short}.")
            key_manager.rotate_key()

        excluded_headers = ['content-encoding', 'transfer-encoding', 'connection']
        response_headers = [(k, v) for k, v in error_headers.items() if k.lower() not in excluded_headers]
        return Response(error_body, status=status_code, headers=response_headers)

    # 5. Stream the successful response back to the client
    excluded_headers = ['content-encoding', 'transfer-encoding', 'connection']
    response_headers = [(k, v) for k, v in gemini_response.headers.items() if k.lower() not in excluded_headers]

    if 'content-type' in gemini_response.headers:
        response_headers.append(('Content-Type', gemini_response.headers['content-type']))

    return Response(gemini_response.iter_content(chunk_size=8192),
                    status=gemini_response.status_code,
                    headers=response_headers)

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint."""
    return jsonify({"status": "ok", "using_gemini_endpoint": True}), 200

# --- Run the App ---
if __name__ == '__main__':
    logging.info(f"Starting Gemini Proxy on {PROXY_HOST}:{PROXY_PORT}")
    logging.info(f"Forwarding to: {GEMINI_API_BASE_URL}")
    logging.info(f"Expecting Gateway Key: {GATEWAY_API_KEY[:4]}... (Check Authorization: Bearer header)")
    app.run(host=PROXY_HOST, port=PROXY_PORT, threaded=True)
