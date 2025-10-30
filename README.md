# CBOE Optionable Stock Screener

**Real-time, interactive, production-grade stock screener** for **all CBOE-listed optionable stocks** (~4,850 symbols).

- **404-proof** – Invalid symbols (like `CWEN.A`, `BTEST`) are silently ignored  
- **Fully vectorized** – 3–5× faster than loop-based scanners  
- **Accurate Bull/Bear counts** – **All selected indicators must agree**  
- **Bull + Bear + Neutral = Valid** – No overlap, no gaps  
- **Interactive candlestick charts** – Click any symbol to verify signals  
- **Self-tuning** – Auto-adjusts speed on rate limits  
- **Cache-aware** – 24h history, 7-day symbol list  
- **Streamlit UI** – Clean, fast, responsive  

---

## Features

| Feature | Description |
|--------|-------------|
| **Live CBOE Symbol List** | Auto-fetched from `cdn.cboe.com` |
| **Volume Filter** | Min avg daily volume (100K–5M) |
| **5 Technical Indicators** | RSI, SMA, Bollinger Bands, MACD, Support/Resistance |
| **Strict Signal Logic** | Bull = **all** indicators bullish |
| **Interactive Plotly Charts** | Candlestick + indicators + zoom/pan |
| **Session Persistence** | Results & charts survive page reload |
| **Dry Run Mode** | Test with first 30 symbols |
| **Cache Management** | Auto-clear stale data |
| **No 404 Spam** | `yfinance` errors silenced |


## Installation

### 1. Clone & Enter Directory

https://github.com/rickblien/qs_option_scanner.git
