# Gemini Ratelimit Increaser
This is an attempt to use multiple gemini API keys to get high rate limits, especially on larger models(e.g. the recent 2.5 pro, wich has ratelimits of only 2 RPM). A great deal of this repo may or may not be written by gemini 2.5 pro.

## install: 
1. clone this repo (havent pushed to gh yet, TODO)
2. copy `.env.example` to `.env`.
3. add your API keys in `.env`.
4. set your API endpoint to `localhost:5001` (or `server:5001` if using a different machine for proxy server & reciever)

## run:
`python3 app.py`