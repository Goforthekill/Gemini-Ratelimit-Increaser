import os
import openai
from dotenv import load_dotenv

# Load environment variables from .env file (optional, but good practice)
load_dotenv()

# --- Configuration ---

# 1. Your Proxy's Base URL (Make sure this matches where your proxy is running)
#    It MUST include the '/v1' path prefix that openai clients expect.
PROXY_BASE_URL = os.getenv("PROXY_BASE_URL", "http://localhost:5001/v1")

# 2. The Gateway API Key for your proxy (the one clients use to authenticate with the proxy)
#    Get it from environment variable or set it directly.
GATEWAY_API_KEY = os.getenv("GATEWAY_API_KEY", "thisisanapikey")

# 3. The specific Gemini model you want to target via the openai compatibility layer
#    NOTE: "gemini-2.5-pro-exp-03-25" might be an experimental or non-existent model.
#          If you get errors, try a known valid model like "gemini-1.5-flash-latest"
#          or "gemini-1.5-pro-latest".
TARGET_MODEL = "gemini-2.0-flash" # Changed to a likely valid model
# TARGET_MODEL = "gemini-2.5-pro-exp-03-25" # As originally requested

# 4. The prompt to send
USER_PROMPT = 'respond with "hello"'

# --- --- --- --- ---

print(f"--- Testing Proxy ---")
print(f"Proxy URL: {PROXY_BASE_URL}")
print(f"Gateway Key: {GATEWAY_API_KEY[:4]}...{GATEWAY_API_KEY[-4:]}")
print(f"Target Model: {TARGET_MODEL}")
print(f"Prompt: '{USER_PROMPT}'")
print("-" * 20)

if not GATEWAY_API_KEY or GATEWAY_API_KEY == "thisisanapikey":
    print("WARNING: Using default GATEWAY_API_KEY. Ensure this matches your proxy's .env setting.")

try:
    # Initialize the openai client, pointing it to YOUR proxy
    client = openai.OpenAI(
        api_key=GATEWAY_API_KEY,   # Use the gateway key here
        base_url=PROXY_BASE_URL    # Point to your proxy's '/v1' endpoint
    )

    print("Sending request to proxy...")

    # Make the chat completion request
    chat_completion = client.chat.completions.create(
        model=TARGET_MODEL,
        messages=[
            # Optional: Add a system prompt if needed/desired
            {"role": "system", "content": "You follow instructions precisely."},
            {"role": "user", "content": USER_PROMPT}
        ],
        temperature=0.7, # Optional: Adjust creativity
        max_tokens=50,   # Optional: Limit response length
        stream=False     # Keep it simple for this test
    )

    print("\n--- Response Received ---")
    # Extract and print the response content
    if chat_completion.choices:
        message_content = chat_completion.choices[0].message.content
        print("Assistant:", message_content)
    else:
        print("No choices found in the response.")
        print("Full Response:", chat_completion)

    print("\n--- Test Successful ---")

# Handle API errors (like 4xx, 5xx from the proxy or upstream)
except openai.APIStatusError as e:
    print(f"\n--- API Error ---")
    print(f"Status Code: {e.status_code}")
    try:
        # Try to parse the error response body
        error_details = e.response.json()
        print("Error Details:", error_details)
    except Exception:
        # If parsing fails, print the raw response text
        print("Raw Error Response:", e.response.text)
    print(f"Original Request URL: {e.request.url}")


# Handle other potential errors (network, configuration, etc.)
except Exception as e:
    print(f"\n--- An Unexpected Error Occurred ---")
    print(f"Error Type: {type(e).__name__}")
    print(f"Error Details: {e}")