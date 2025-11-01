# import streamlit as st
# from datetime import datetime
# import pytz
# import importlib.util
# import sys

# # ----------------------------
# # Import 1_fetch_optionable_stocks dynamically
# # ----------------------------
# module_path = "1_fetch_optionable_stocks.py"
# spec = importlib.util.spec_from_file_location("fetch_module", module_path)
# fetch_module = importlib.util.module_from_spec(spec)
# sys.modules["fetch_module"] = fetch_module
# spec.loader.exec_module(fetch_module)

# PACIFIC = pytz.timezone("US/Pacific")

# def main():
#     st.set_page_config(page_title="Optionable Stocks", layout="centered")
#     st.title("📈 Optionable Stocks Summary")

#     st.subheader("Fetching latest optionable symbols...")
#     new_df, new_count, total_symbols = fetch_module.update_symbols()

#     last_run = datetime.utcnow().astimezone(PACIFIC)

#     with st.expander("📊 Latest Summary", expanded=True):
#         summary_df = [{
#             "Last Update": last_run.strftime("%Y-%m-%d %I:%M:%S %p %Z"),
#             "New Symbols": new_count,
#             "Total Symbols": total_symbols
#         }]
#         st.dataframe(summary_df, use_container_width=True)

#     with st.expander("📝 Newly Added Symbols", expanded=True):
#         if not new_df.empty:
#             st.dataframe(new_df.sort_values("symbol").reset_index(drop=True), use_container_width=True)
#         else:
#             st.info("No new symbols found in this update.")

# if __name__ == "__main__":
#     main()


# #### v1

# import os
# import io
# import time
# import math
# import logging
# import threading
# from collections import deque
# from concurrent.futures import ThreadPoolExecutor, as_completed
# from datetime import datetime

# import pandas as pd
# import numpy as np
# import requests
# import yfinance as yf
# import streamlit as st
# import pytz
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# # ----------------------------
# # CONFIG & LOGGING
# # ----------------------------
# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# PARQUET_FILE = "optionable_full.parquet"
# CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"
# PACIFIC = pytz.timezone("US/Pacific")

# # ----------------------------
# # RETRY HELPERS
# # ----------------------------
# def log_retry(retry_state):
#     exc = retry_state.outcome.exception()
#     logging.warning(f"Retry attempt {retry_state.attempt_number} due to {exc}")

# @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30),
#        retry=retry_if_exception_type(requests.RequestException), after=log_retry)
# def fetch_cboe_symbols():
#     """Download the official CBOE optionable underlying list."""
#     resp = requests.get(CBOE_URL, timeout=30)
#     resp.raise_for_status()
#     df = pd.read_csv(io.StringIO(resp.text))
#     ticker_col = next((c for c in df.columns if "symbol" in c.lower() or "root" in c.lower()), None)
#     if not ticker_col:
#         raise ValueError(f"No symbol column found. Columns: {list(df.columns)}")
#     df = df[[ticker_col]].rename(columns={ticker_col: "symbol"})
#     df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
#     return df.drop_duplicates()

# # ----------------------------
# # Local cache helpers
# # ----------------------------
# def load_existing_symbols():
#     if os.path.exists(PARQUET_FILE):
#         df = pd.read_parquet(PARQUET_FILE)
#         logging.info(f"Loaded {len(df)} cached symbols")
#         return df
#     return pd.DataFrame(columns=["symbol", "updated_at"])

# def update_symbols():
#     existing_df = load_existing_symbols()
#     existing_symbols = set(existing_df["symbol"])
#     df = fetch_cboe_symbols()
#     new_df = df[~df["symbol"].isin(existing_symbols)].copy()
#     new_df["updated_at"] = datetime.utcnow().isoformat()

#     if not new_df.empty:
#         combined_df = pd.concat([existing_df, new_df], ignore_index=True)
#         tmp_file = PARQUET_FILE + ".tmp"
#         combined_df.to_parquet(tmp_file, index=False)
#         os.replace(tmp_file, PARQUET_FILE)
#         logging.info(f"Inserted {len(new_df)} new symbols")
#     else:
#         combined_df = existing_df
#     return combined_df

# # ----------------------------
# # Rate limiter (sliding window)
# # ----------------------------
# class RateLimiter:
#     def __init__(self, max_per_minute: int):
#         self.max_per_minute = max_per_minute
#         self.lock = threading.Lock()
#         self.requests = deque()  # timestamps of requests (seconds)
#         self.window = 60.0  # 60 seconds sliding window

#     def wait_for_slot(self):
#         """Block until a request slot is available, then record this request."""
#         while True:
#             with self.lock:
#                 now = time.time()
#                 # drop timestamps older than window
#                 while self.requests and now - self.requests[0] > self.window:
#                     self.requests.popleft()
#                 if len(self.requests) < self.max_per_minute:
#                     # we have capacity
#                     self.requests.append(now)
#                     return
#                 # else compute wait time until the oldest expires
#                 oldest = self.requests[0]
#                 wait_seconds = (oldest + self.window) - now
#             # sleep outside lock
#             if wait_seconds > 0:
#                 time.sleep(wait_seconds + 0.01)
#             else:
#                 # tiny yield
#                 time.sleep(0.05)

# # ----------------------------
# # Safe yfinance wrappers
# # ----------------------------
# def safe_fetch_history(symbol, rate_limiter: RateLimiter):
#     """
#     Fetch limited price history safely using the rate limiter.
#     Returns a DataFrame or None on failure.
#     """
#     try:
#         rate_limiter.wait_for_slot()
#         hist = yf.Ticker(symbol).history(period="3mo", interval="1d")
#         return hist if not hist.empty else None
#     except Exception as e:
#         logging.debug(f"{symbol} history fetch failed: {e}")
#         return None

# def safe_option_chain(symbol, rate_limiter: RateLimiter):
#     """
#     Fetch option chain safely using the rate limiter.
#     Returns (calls, puts) or (None, None).
#     """
#     try:
#         rate_limiter.wait_for_slot()
#         opt = yf.Ticker(symbol).option_chain()
#         return opt.calls, opt.puts
#     except Exception as e:
#         logging.debug(f"{symbol} option_chain failed: {e}")
#         return None, None

# # ----------------------------
# # Metrics computation (thread worker)
# # ----------------------------
# def compute_metrics_worker(symbol: str, rate_limiter: RateLimiter):
#     """
#     Worker function run in threadpool. Returns dict or None.
#     Keep function self-contained for easy threading.
#     """
#     try:
#         hist = safe_fetch_history(symbol, rate_limiter)
#         if hist is None or hist.empty:
#             return None

#         # SMA20
#         hist = hist.copy()
#         hist["SMA20"] = hist["Close"].rolling(20).mean()

#         # RSI (14) - robust simple calculation to avoid NaNs
#         delta = hist["Close"].diff()
#         up = delta.clip(lower=0)
#         down = -1 * delta.clip(upper=0)
#         roll_up = up.ewm(alpha=1/14, adjust=False).mean()
#         roll_down = down.ewm(alpha=1/14, adjust=False).mean()
#         rs = roll_up / roll_down
#         rsi_series = 100 - (100 / (1 + rs))
#         rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else np.nan

#         sma_dev = (hist["Close"].iloc[-1] - hist["SMA20"].iloc[-1]) / hist["SMA20"].iloc[-1] if not np.isnan(hist["SMA20"].iloc[-1]) else np.nan

#         # Option chain
#         calls, puts = safe_option_chain(symbol, rate_limiter)
#         if calls is None or puts is None or calls.empty or puts.empty:
#             return None

#         close = float(hist["Close"].iloc[-1])

#         # find ~20% OTM proxies
#         call_otm_df = calls.iloc[(calls["strike"] - close * 1.2).abs().argsort()[:1]]
#         put_otm_df = puts.iloc[(puts["strike"] - close * 0.8).abs().argsort()[:1]]

#         iv_call = float(call_otm_df.get("impliedVolatility", pd.Series([np.nan])).mean())
#         iv_put = float(put_otm_df.get("impliedVolatility", pd.Series([np.nan])).mean())
#         iv_skew = (iv_put / iv_call) if (iv_call and not math.isnan(iv_call) and iv_call > 0) else np.nan

#         atm_call_df = calls.iloc[(calls["strike"] - close).abs().argsort()[:1]]
#         atm_iv = float(atm_call_df.get("impliedVolatility", pd.Series([np.nan])).mean())

#         iv_rank = atm_iv / np.nanmean([iv_call, iv_put]) if not math.isnan(atm_iv) and (not math.isnan(iv_call) or not math.isnan(iv_put)) else np.nan

#         # crude credit spread proxy
#         spread_credit = (atm_iv or 0) * 0.1  # placeholder
#         reward_risk = (spread_credit / (1 - spread_credit)) if spread_credit and spread_credit < 1 else np.nan

#         return {
#             "Symbol": symbol,
#             "Price": close,
#             "RSI": rsi,
#             "SMA Dev": sma_dev,
#             "IV ATM": atm_iv,
#             "IV Skew": iv_skew,
#             "IV Rank": iv_rank,
#             "Credit": spread_credit,
#             "Reward:Risk": reward_risk
#         }
#     except Exception as e:
#         logging.debug(f"{symbol} compute failed: {e}")
#         return None

# # ----------------------------
# # Streamlit UI & orchestration
# # ----------------------------
# def main():
#     st.set_page_config(page_title="Parallel CBOE Credit Spread Screener", layout="wide")
#     st.title("📊 Parallel Vertical Credit Spread Screener (CBOE + Rate-Limited)")

#     # Sidebar controls
#     st.sidebar.header("CBOE & Rate-Limiter Settings")
#     if st.sidebar.button("Update / Refresh CBOE symbols"):
#         with st.spinner("Fetching fresh CBOE symbol list..."):
#             symbols_df = update_symbols()
#             st.success(f"Updated symbol cache: {len(symbols_df)} symbols")
#     else:
#         symbols_df = update_symbols()

#     total_symbols = len(symbols_df)
#     st.sidebar.markdown(f"**Cached symbols:** {total_symbols}")
#     sample_size = st.sidebar.slider("Sample Universe Size", 20, min(20, total_symbols), min(200, max(20, total_symbols)), step=10)
#     concurrency = st.sidebar.slider("Concurrency (threads)", 1, 30, 10)
#     rate_limit_per_min = st.sidebar.slider("Rate limit (calls / minute)", 10, 300, 80)
#     # note: yfinance is unofficially ~60-90 req/min; default here is 80
#     batch_mode = st.sidebar.checkbox("Use sample-only mode (do not scan whole universe)", value=True)
#     st.sidebar.markdown("---")
#     st.sidebar.caption("Guidelines: keep rate limit * concurrency* reasonable. Recommended concurrency 5-15 and rate limit 60-90.")

#     # screening filters
#     st.sidebar.header("Screener Filters")
#     min_rr = st.sidebar.slider("Min Reward:Risk", 0.01, 0.8, 0.15)
#     max_rsi = st.sidebar.slider("Max RSI (call credit candidates)", 30.0, 90.0, 65.0)
#     min_rsi = st.sidebar.slider("Min RSI (put credit candidates)", 10.0, 70.0, 35.0)

#     # sample / selection
#     if batch_mode:
#         st.info("Sample-only mode enabled — scanning a sample subset of the universe.")
#     symbols = symbols_df["symbol"].sample(sample_size, random_state=42).tolist()

#     st.write(f"Preparing to analyze {len(symbols)} symbols with concurrency={concurrency}, rate_limit={rate_limit_per_min}/min")

#     # instantiate rate limiter
#     rate_limiter = RateLimiter(max_per_minute=rate_limit_per_min)

#     # threadpool
#     results = []
#     progress_bar = st.progress(0)
#     status_txt = st.empty()
#     results_placeholder = st.empty()

#     start_time = time.time()
#     futures = []
#     with ThreadPoolExecutor(max_workers=concurrency) as executor:
#         # submit all tasks
#         for symbol in symbols:
#             futures.append(executor.submit(compute_metrics_worker, symbol, rate_limiter))

#         # collect as they complete
#         total = len(futures)
#         completed = 0
#         for fut in as_completed(futures):
#             completed += 1
#             try:
#                 res = fut.result()
#             except Exception as e:
#                 res = None
#                 logging.debug(f"future exception: {e}")

#             if res:
#                 results.append(res)

#             # update progress UI
#             progress_bar.progress(completed / total)
#             elapsed = time.time() - start_time
#             status_txt.info(f"Completed {completed}/{total} — found {len(results)} candidates — {elapsed:.1f}s elapsed")

#             # live partial results (avoid too frequent updates)
#             if completed % max(1, total // 10) == 0 or completed == total:
#                 if results:
#                     df_partial = pd.DataFrame(results).sort_values("Reward:Risk", ascending=False)
#                     results_placeholder.dataframe(df_partial.head(200), use_container_width=True)

#     # finished
#     elapsed_total = time.time() - start_time
#     st.success(f"Scan complete — {len(results)} viable results found in {elapsed_total:.1f}s")

#     if not results:
#         st.warning("No valid results. Try increasing sample size, lowering thresholds, or raising the rate limit.")
#         return

#     df = pd.DataFrame(results)
#     # basic filtering and ranking
#     df_filtered = df[
#         (df["Reward:Risk"].fillna(0) >= min_rr) &
#         ((df["RSI"].fillna(0) <= max_rsi) | (df["RSI"].fillna(100) >= min_rsi))
#     ].sort_values("Reward:Risk", ascending=False)

#     st.subheader("📈 Filtered Candidates")
#     st.dataframe(df_filtered.reset_index(drop=True), use_container_width=True)
#     st.download_button("📥 Download CSV", df_filtered.to_csv(index=False), "credit_spread_candidates.csv")

#     st.caption("⚠️ Educational use only. These are approximations — use verified option Greeks / IV surfaces for live trading.")

# if __name__ == "__main__":
#     main()


# #### v2



# import os
# import io
# import time
# import math
# import logging
# import requests
# import numpy as np
# import pandas as pd
# import yfinance as yf
# import streamlit as st
# from datetime import datetime
# import pytz
# from concurrent.futures import ThreadPoolExecutor, as_completed
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# # ----------------------------
# # CONFIG & LOGGING
# # ----------------------------
# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# PARQUET_FILE = "optionable_full.parquet"
# METRICS_CACHE = "metrics_cache.parquet"
# CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"
# PACIFIC = pytz.timezone("US/Pacific")

# # ----------------------------
# # RETRY HELPERS
# # ----------------------------
# def log_retry(retry_state):
#     exc = retry_state.outcome.exception() if retry_state.outcome else None
#     logging.warning(f"Retry attempt {retry_state.attempt_number} due to {exc}")

# @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30),
#        retry=retry_if_exception_type(requests.RequestException), after=log_retry)
# def fetch_cboe_symbols():
#     """Download official CBOE optionable underlying list."""
#     resp = requests.get(CBOE_URL, timeout=30)
#     resp.raise_for_status()
#     df = pd.read_csv(io.StringIO(resp.text))
#     ticker_col = next((c for c in df.columns if "symbol" in c.lower() or "root" in c.lower()), None)
#     if not ticker_col:
#         raise ValueError(f"No symbol column found. Columns: {list(df.columns)}")
#     df = df[[ticker_col]].rename(columns={ticker_col: "symbol"})
#     df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
#     return df.drop_duplicates()

# def load_existing_symbols():
#     if os.path.exists(PARQUET_FILE):
#         try:
#             df = pd.read_parquet(PARQUET_FILE)
#             return df
#         except Exception:
#             logging.exception("Failed reading symbol cache, refetching.")
#             return pd.DataFrame(columns=["symbol", "updated_at"])
#     return pd.DataFrame(columns=["symbol", "updated_at"])

# def update_symbols():
#     """Update local CBOE symbol list."""
#     existing_df = load_existing_symbols()
#     existing_symbols = set(existing_df["symbol"].tolist())
#     df = fetch_cboe_symbols()
#     new_df = df[~df["symbol"].isin(existing_symbols)].copy()
#     if not new_df.empty:
#         new_df["updated_at"] = datetime.utcnow().isoformat()
#     combined_df = pd.concat([existing_df, new_df], ignore_index=True).drop_duplicates("symbol")
#     tmp_file = PARQUET_FILE + ".tmp"
#     combined_df.to_parquet(tmp_file, index=False)
#     os.replace(tmp_file, PARQUET_FILE)
#     return combined_df

# # ----------------------------
# # YFINANCE SAFE WRAPPERS
# # ----------------------------
# def safe_fetch_history(symbol):
#     try:
#         data = yf.Ticker(symbol).history(period="3mo", interval="1d")
#         return data if not data.empty else None
#     except Exception as e:
#         logging.debug(f"history fetch failed for {symbol}: {e}")
#         return None

# def safe_option_chain(symbol):
#     try:
#         opt = yf.Ticker(symbol).option_chain()
#         return opt.calls, opt.puts
#     except Exception as e:
#         logging.debug(f"option chain fetch failed for {symbol}: {e}")
#         return None, None

# # ----------------------------
# # METRIC COMPUTATION
# # ----------------------------
# def compute_metrics(symbol):
#     hist = safe_fetch_history(symbol)
#     if hist is None or hist.empty:
#         return None

#     try:
#         # SMA20
#         hist = hist.copy()
#         hist["SMA20"] = hist["Close"].rolling(20).mean()

#         # RSI (robust EWM-based)
#         delta = hist["Close"].diff()
#         up = delta.clip(lower=0)
#         down = -1 * delta.clip(upper=0)
#         roll_up = up.ewm(alpha=1/14, adjust=False).mean()
#         roll_down = down.ewm(alpha=1/14, adjust=False).mean()
#         rs = roll_up / roll_down
#         rsi_series = 100 - (100 / (1 + rs))
#         rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else np.nan

#         sma20_val = hist["SMA20"].iloc[-1]
#         sma_dev = (hist["Close"].iloc[-1] - sma20_val) / sma20_val if not math.isnan(sma20_val) and sma20_val != 0 else np.nan

#         calls, puts = safe_option_chain(symbol)
#         if calls is None or puts is None or calls.empty or puts.empty:
#             return None

#         close = float(hist["Close"].iloc[-1])

#         # proxies for OTM and ATM IV
#         call_otm = calls.iloc[(calls["strike"] - close * 1.2).abs().argsort()[:1]]
#         put_otm = puts.iloc[(puts["strike"] - close * 0.8).abs().argsort()[:1]]
#         iv_call = call_otm.get("impliedVolatility", pd.Series([np.nan])).mean()
#         iv_put = put_otm.get("impliedVolatility", pd.Series([np.nan])).mean()
#         iv_skew = float(iv_put / iv_call) if (iv_call and not math.isnan(iv_call) and iv_call > 0) else np.nan

#         atm_call = calls.iloc[(calls["strike"] - close).abs().argsort()[:1]]
#         atm_iv = atm_call.get("impliedVolatility", pd.Series([np.nan])).mean()
#         iv_rank = float(atm_iv / np.nanmean([iv_call, iv_put])) if (not math.isnan(atm_iv) and (not math.isnan(iv_call) or not math.isnan(iv_put))) else np.nan

#         spread_credit = float((atm_iv or 0) * 0.1) if not pd.isna(atm_iv) else np.nan
#         reward_risk = float(spread_credit / (1 - spread_credit)) if spread_credit and spread_credit < 1 else np.nan

#         return {
#             "Symbol": symbol,
#             "RSI": rsi,
#             "SMA Dev": sma_dev,
#             "IV ATM": float(atm_iv) if not pd.isna(atm_iv) else np.nan,
#             "IV Skew": iv_skew,
#             "IV Rank": iv_rank,
#             "Credit": spread_credit,
#             "Reward:Risk": reward_risk,
#             "Timestamp": datetime.utcnow().isoformat()
#         }
#     except Exception as e:
#         logging.debug(f"{symbol} compute_metrics failed: {e}")
#         return None

# # ----------------------------
# # CACHE HELPERS
# # ----------------------------
# def load_metrics_cache():
#     if os.path.exists(METRICS_CACHE):
#         try:
#             df = pd.read_parquet(METRICS_CACHE)
#             return df
#         except Exception:
#             logging.exception("Failed to read metrics cache; starting fresh.")
#             return pd.DataFrame()
#     return pd.DataFrame()

# def save_metrics_cache(df):
#     tmp = METRICS_CACHE + ".tmp"
#     df.to_parquet(tmp, index=False)
#     os.replace(tmp, METRICS_CACHE)

# # ----------------------------
# # STREAMLIT APP
# # ----------------------------
# def main():
#     st.set_page_config(page_title="CBOE Credit Spread Screener", layout="wide")
#     st.title("📊 Vertical Credit Spread Screener (CBOE — Full Universe Scan)")

#     # Update symbol cache
#     with st.spinner("Updating CBOE symbol list..."):
#         symbols_df = update_symbols()
#     st.success(f"Loaded {len(symbols_df)} CBOE optionable symbols")

#     # Sidebar: performance & classification settings
#     st.sidebar.header("Performance Settings")
#     max_workers = st.sidebar.slider("Concurrent Threads", 2, 20, 10)
#     sleep_time = st.sidebar.slider("Sleep Between Batches (sec)", 0.2, 3.0, 1.0, step=0.1)
#     batch_size = st.sidebar.slider("Batch Size (submit per loop)", 10, 200, max_workers * 5)

#     st.sidebar.markdown("---")
#     st.sidebar.header("Spread Classification Thresholds")
#     rsi_high = st.sidebar.slider("RSI High (Bear Call)", 50, 80, 60)
#     rsi_low = st.sidebar.slider("RSI Low (Bull Put)", 20, 50, 40)
#     sma_dev_high = st.sidebar.number_input("SMA Dev High (Bear Call)", -0.1, 0.5, 0.02, step=0.005, format="%.4f")
#     sma_dev_low = st.sidebar.number_input("SMA Dev Low (Bull Put)", -0.5, 0.1, -0.02, step=0.005, format="%.4f")

#     # Use all CBOE symbols
#     symbols = symbols_df["symbol"].dropna().unique().tolist()
#     st.info(f"Scanning **all {len(symbols)} CBOE optionable symbols** using up to {max_workers} threads (batch_size={batch_size})")

#     # scanning in batches with ThreadPoolExecutor
#     results = []
#     total_batches = math.ceil(len(symbols) / batch_size)
#     progress = st.progress(0)
#     start_time = time.time()

#     for batch_index in range(total_batches):
#         start_idx = batch_index * batch_size
#         batch = symbols[start_idx:start_idx + batch_size]
#         with ThreadPoolExecutor(max_workers=max_workers) as executor:
#             futures = {executor.submit(compute_metrics, s): s for s in batch}
#             for fut in as_completed(futures):
#                 sym = futures[fut]
#                 try:
#                     res = fut.result()
#                 except Exception as e:
#                     logging.debug(f"Future error for {sym}: {e}")
#                     res = None
#                 if res:
#                     results.append(res)
#         # update progress
#         progress.progress((batch_index + 1) / total_batches)
#         elapsed = time.time() - start_time
#         st.caption(f"Batch {batch_index+1}/{total_batches} done — elapsed {elapsed:.1f}s — found {len(results)} candidates")
#         time.sleep(sleep_time)

#     if not results:
#         st.warning("No valid results found.")
#         return

#     df = pd.DataFrame(results).dropna()
#     if df.empty:
#         st.warning("No valid data processed.")
#         return

#     # Classify strategies
#     df["Strategy"] = np.where(
#         (df["RSI"] > rsi_high) & (df["SMA Dev"] > sma_dev_high),
#         "🐻 Bear Call Spread",
#         np.where(
#             (df["RSI"] < rsi_low) & (df["SMA Dev"] < sma_dev_low),
#             "🐂 Bull Put Spread",
#             "— Neutral / Skip —"
#         )
#     )

#     # Merge with old cache and save
#     old_cache = load_metrics_cache()
#     if old_cache is None or old_cache.empty:
#         combined = df.copy()
#     else:
#         combined = pd.concat([old_cache[~old_cache["Symbol"].isin(df["Symbol"])], df], ignore_index=True)
#     save_metrics_cache(combined)

#     # Display results
#     st.subheader("📈 Filtered Candidates by Strategy")
#     col1, col2 = st.columns(2)

#     with col1:
#         st.markdown("### 🐻 Bear Call Spread Candidates")
#         bear_df = df[df["Strategy"] == "🐻 Bear Call Spread"].sort_values("Reward:Risk", ascending=False)
#         st.dataframe(bear_df.reset_index(drop=True).head(200), use_container_width=True)
#         if not bear_df.empty:
#             st.download_button("Download Bear Call CSV", bear_df.to_csv(index=False), "bear_call_candidates.csv")

#     with col2:
#         st.markdown("### 🐂 Bull Put Spread Candidates")
#         bull_df = df[df["Strategy"] == "🐂 Bull Put Spread"].sort_values("Reward:Risk", ascending=False)
#         st.dataframe(bull_df.reset_index(drop=True).head(200), use_container_width=True)
#         if not bull_df.empty:
#             st.download_button("Download Bull Put CSV", bull_df.to_csv(index=False), "bull_put_candidates.csv")

#     st.markdown("---")
#     st.markdown("### 📋 All Filtered Candidates (for reference)")
#     st.dataframe(df.reset_index(drop=True).head(500), use_container_width=True)
#     st.download_button("Download All Metrics CSV", df.to_csv(index=False), "credit_spread_all_metrics.csv")

#     st.caption("⚠️ Educational use only. Validate signals before trading.")
    
# if __name__ == "__main__":
#     main()


## v3

# import os
# import io
# import time
# import math
# import logging
# import requests
# import numpy as np
# import pandas as pd
# import yfinance as yf
# import streamlit as st
# from datetime import datetime, timedelta
# import pytz
# from concurrent.futures import ThreadPoolExecutor, as_completed
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# # ----------------------------
# # CONFIG & LOGGING
# # ----------------------------
# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# PARQUET_FILE = "optionable_full.parquet"
# METRICS_CACHE = "metrics_cache.parquet"
# CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"
# PACIFIC = pytz.timezone("US/Pacific")

# # ----------------------------
# # RETRY HELPERS
# # ----------------------------
# def log_retry(retry_state):
#     exc = retry_state.outcome.exception() if retry_state.outcome else None
#     logging.warning(f"Retry attempt {retry_state.attempt_number} due to {exc}")

# @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30),
#        retry=retry_if_exception_type(requests.RequestException), after=log_retry)
# def fetch_cboe_symbols():
#     """Download official CBOE optionable underlying list."""
#     resp = requests.get(CBOE_URL, timeout=30)
#     resp.raise_for_status()
#     df = pd.read_csv(io.StringIO(resp.text))
#     ticker_col = next((c for c in df.columns if "symbol" in c.lower() or "root" in c.lower()), None)
#     if not ticker_col:
#         raise ValueError(f"No symbol column found. Columns: {list(df.columns)}")
#     df = df[[ticker_col]].rename(columns={ticker_col: "symbol"})
#     df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
#     return df.drop_duplicates()

# def load_existing_symbols():
#     if os.path.exists(PARQUET_FILE):
#         try:
#             df = pd.read_parquet(PARQUET_FILE)
#             return df
#         except Exception:
#             logging.exception("Failed reading symbol cache, refetching.")
#             return pd.DataFrame(columns=["symbol", "updated_at"])
#     return pd.DataFrame(columns=["symbol", "updated_at"])

# def update_symbols():
#     """Update local CBOE symbol list."""
#     existing_df = load_existing_symbols()
#     existing_symbols = set(existing_df["symbol"].tolist())
#     df = fetch_cboe_symbols()
#     new_df = df[~df["symbol"].isin(existing_symbols)].copy()
#     if not new_df.empty:
#         new_df["updated_at"] = datetime.utcnow().isoformat()
#     combined_df = pd.concat([existing_df, new_df], ignore_index=True).drop_duplicates("symbol")
#     tmp_file = PARQUET_FILE + ".tmp"
#     combined_df.to_parquet(tmp_file, index=False)
#     os.replace(tmp_file, PARQUET_FILE)
#     return combined_df

# # ----------------------------
# # YFINANCE SAFE WRAPPERS
# # ----------------------------
# def safe_fetch_history(symbol):
#     try:
#         data = yf.Ticker(symbol).history(period="3mo", interval="1d")
#         return data if not data.empty else None
#     except Exception as e:
#         logging.debug(f"history fetch failed for {symbol}: {e}")
#         return None

# def safe_option_chain(symbol, expiration=None):
#     try:
#         ticker = yf.Ticker(symbol)
#         if expiration:
#             opt = ticker.option_chain(expiration)
#         else:
#             opt = ticker.option_chain()
#         return opt.calls, opt.puts
#     except Exception as e:
#         logging.debug(f"option chain fetch failed for {symbol}: {e}")
#         return None, None

# def get_nearest_expiration(ticker, min_days=30):
#     """Get the nearest expiration date at least min_days out."""
#     try:
#         expirations = ticker.options
#         today = datetime.now(pytz.UTC)
#         for exp in expirations:
#             exp_date = datetime.strptime(exp, "%Y-%m-%d").replace(tzinfo=pytz.UTC)
#             if (exp_date - today).days >= min_days:
#                 return exp
#         return None
#     except Exception as e:
#         logging.debug(f"Failed to get expiration dates for {ticker.ticker}: {e}")
#         return None

# # ----------------------------
# # METRIC COMPUTATION
# # ----------------------------
# def compute_metrics(symbol):
#     hist = safe_fetch_history(symbol)
#     if hist is None or hist.empty:
#         return None

#     try:
#         # SMA20
#         hist = hist.copy()
#         hist["SMA20"] = hist["Close"].rolling(20).mean()

#         # RSI (robust EWM-based)
#         delta = hist["Close"].diff()
#         up = delta.clip(lower=0)
#         down = -1 * delta.clip(upper=0)
#         roll_up = up.ewm(alpha=1/14, adjust=False).mean()
#         roll_down = down.ewm(alpha=1/14, adjust=False).mean()
#         rs = roll_up / roll_down
#         rsi_series = 100 - (100 / (1 + rs))
#         rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else np.nan

#         sma20_val = hist["SMA20"].iloc[-1]
#         sma_dev = (hist["Close"].iloc[-1] - sma20_val) / sma20_val if not math.isnan(sma20_val) and sma20_val != 0 else np.nan

#         # Get option chain for the nearest expiration >= 30 days
#         ticker = yf.Ticker(symbol)
#         expiration = get_nearest_expiration(ticker, min_days=30)
#         if not expiration:
#             return None
#         calls, puts = safe_option_chain(symbol, expiration)
#         if calls is None or puts is None or calls.empty or puts.empty:
#             return None

#         close = float(hist["Close"].iloc[-1])

#         # Proxies for OTM and ATM IV
#         call_otm = calls.iloc[(calls["strike"] - close * 1.2).abs().argsort()[:1]]
#         put_otm = puts.iloc[(puts["strike"] - close * 0.8).abs().argsort()[:1]]
#         iv_call = call_otm.get("impliedVolatility", pd.Series([np.nan])).mean()
#         iv_put = put_otm.get("impliedVolatility", pd.Series([np.nan])).mean()
#         iv_skew = float(iv_put / iv_call) if (iv_call and not math.isnan(iv_call) and iv_call > 0) else np.nan

#         atm_call = calls.iloc[(calls["strike"] - close).abs().argsort()[:1]]
#         atm_iv = atm_call.get("impliedVolatility", pd.Series([np.nan])).mean()
#         iv_rank = float(atm_iv / np.nanmean([iv_call, iv_put])) if (not math.isnan(atm_iv) and (not math.isnan(iv_call) or not math.isnan(iv_put))) else np.nan

#         spread_credit = float((atm_iv or 0) * 0.1) if not pd.isna(atm_iv) else np.nan
#         reward_risk = float(spread_credit / (1 - spread_credit)) if spread_credit and spread_credit < 1 else np.nan

#         # Bear Call Spread: Sell OTM call (~5-10% above close), buy next strike up
#         call_sell_strike = calls.iloc[(calls["strike"] - close * 1.05).abs().argsort()[:1]]["strike"].iloc[0]
#         call_buy_strike = calls[calls["strike"] > call_sell_strike]["strike"].min() if not calls[calls["strike"] > call_sell_strike].empty else np.nan

#         # Bull Put Spread: Sell OTM put (~5-10% below close), buy next strike down
#         put_sell_strike = puts.iloc[(puts["strike"] - close * 0.95).abs().argsort()[:1]]["strike"].iloc[0]
#         put_buy_strike = puts[puts["strike"] < put_sell_strike]["strike"].max() if not puts[puts["strike"] < put_sell_strike].empty else np.nan

#         return {
#             "Symbol": symbol,
#             "RSI": rsi,
#             "SMA Dev": sma_dev,
#             "IV ATM": float(atm_iv) if not pd.isna(atm_iv) else np.nan,
#             "IV Skew": iv_skew,
#             "IV Rank": iv_rank,
#             "Credit": spread_credit,
#             "Reward:Risk": reward_risk,
#             "Timestamp": datetime.utcnow().isoformat(),
#             "Expiration": expiration,
#             "Bear Call Sell Strike": call_sell_strike,
#             "Bear Call Buy Strike": call_buy_strike,
#             "Bull Put Sell Strike": put_sell_strike,
#             "Bull Put Buy Strike": put_buy_strike
#         }
#     except Exception as e:
#         logging.debug(f"{symbol} compute_metrics failed: {e}")
#         return None

# # ----------------------------
# # CACHE HELPERS
# # ----------------------------
# def load_metrics_cache():
#     if os.path.exists(METRICS_CACHE):
#         try:
#             df = pd.read_parquet(METRICS_CACHE)
#             return df
#         except Exception:
#             logging.exception("Failed to read metrics cache; starting fresh.")
#             return pd.DataFrame()
#     return pd.DataFrame()

# def save_metrics_cache(df):
#     tmp = METRICS_CACHE + ".tmp"
#     df.to_parquet(tmp, index=False)
#     os.replace(tmp, METRICS_CACHE)

# # ----------------------------
# # STREAMLIT APP
# # ----------------------------
# def main():
#     st.set_page_config(page_title="CBOE Credit Spread Screener", layout="wide")
#     st.title("📊 Vertical Credit Spread Screener (CBOE — Full Universe Scan)")

#     # Update symbol cache
#     with st.spinner("Updating CBOE symbol list..."):
#         symbols_df = update_symbols()
#     st.success(f"Loaded {len(symbols_df)} CBOE optionable symbols")

#     # Sidebar: performance & classification settings
#     st.sidebar.header("Performance Settings")
#     max_workers = st.sidebar.slider("Concurrent Threads", 2, 20, 10)
#     sleep_time = st.sidebar.slider("Sleep Between Batches (sec)", 0.2, 3.0, 1.0, step=0.1)
#     batch_size = st.sidebar.slider("Batch Size (submit per loop)", 10, 200, max_workers * 5)

#     st.sidebar.markdown("---")
#     st.sidebar.header("Spread Classification Thresholds")
#     rsi_high = st.sidebar.slider("RSI High (Bear Call)", 50, 80, 60)
#     rsi_low = st.sidebar.slider("RSI Low (Bull Put)", 20, 50, 40)
#     sma_dev_high = st.sidebar.number_input("SMA Dev High (Bear Call)", -0.1, 0.5, 0.02, step=0.005, format="%.4f")
#     sma_dev_low = st.sidebar.number_input("SMA Dev Low (Bull Put)", -0.5, 0.1, -0.02, step=0.005, format="%.4f")

#     # Use all CBOE symbols
#     symbols = symbols_df["symbol"].dropna().unique().tolist()
#     st.info(f"Scanning **all {len(symbols)} CBOE optionable symbols** using up to {max_workers} threads (batch_size={batch_size})")

#     # Scanning in batches with ThreadPoolExecutor
#     results = []
#     total_batches = math.ceil(len(symbols) / batch_size)
#     progress = st.progress(0)
#     start_time = time.time()

#     for batch_index in range(total_batches):
#         start_idx = batch_index * batch_size
#         batch = symbols[start_idx:start_idx + batch_size]
#         with ThreadPoolExecutor(max_workers=max_workers) as executor:
#             futures = {executor.submit(compute_metrics, s): s for s in batch}
#             for fut in as_completed(futures):
#                 sym = futures[fut]
#                 try:
#                     res = fut.result()
#                 except Exception as e:
#                     logging.debug(f"Future error for {sym}: {e}")
#                     res = None
#                 if res:
#                     results.append(res)
#         # Update progress
#         progress.progress((batch_index + 1) / total_batches)
#         elapsed = time.time() - start_time
#         st.caption(f"Batch {batch_index+1}/{total_batches} done — elapsed {elapsed:.1f}s — found {len(results)} candidates")
#         time.sleep(sleep_time)

#     if not results:
#         st.warning("No valid results found.")
#         return

#     df = pd.DataFrame(results).dropna()
#     if df.empty:
#         st.warning("No valid data processed.")
#         return

#     # Classify strategies
#     df["Strategy"] = np.where(
#         (df["RSI"] > rsi_high) & (df["SMA Dev"] > sma_dev_high),
#         "🐻 Bear Call Spread",
#         np.where(
#             (df["RSI"] < rsi_low) & (df["SMA Dev"] < sma_dev_low),
#             "🐂 Bull Put Spread",
#             "— Neutral / Skip —"
#         )
#     )

#     # Merge with old cache and save
#     old_cache = load_metrics_cache()
#     if old_cache is None or old_cache.empty:
#         combined = df.copy()
#     else:
#         combined = pd.concat([old_cache[~old_cache["Symbol"].isin(df["Symbol"])], df], ignore_index=True)
#     save_metrics_cache(combined)

#     # Display results
#     st.subheader("📈 Filtered Candidates by Strategy")
#     col1, col2 = st.columns(2)

#     with col1:
#         st.markdown("### 🐻 Bear Call Spread Candidates")
#         bear_df = df[df["Strategy"] == "🐻 Bear Call Spread"][[
#             "Symbol", "RSI", "SMA Dev", "IV ATM", "IV Skew", "IV Rank", "Credit", 
#             "Reward:Risk", "Expiration", "Bear Call Sell Strike", "Bear Call Buy Strike"
#         ]].sort_values("Reward:Risk", ascending=False)
#         st.dataframe(bear_df.reset_index(drop=True).head(200), use_container_width=True)
#         if not bear_df.empty:
#             st.download_button("Download Bear Call CSV", bear_df.to_csv(index=False), "bear_call_candidates.csv")

#     with col2:
#         st.markdown("### 🐂 Bull Put Spread Candidates")
#         bull_df = df[df["Strategy"] == "🐂 Bull Put Spread"][[
#             "Symbol", "RSI", "SMA Dev", "IV ATM", "IV Skew", "IV Rank", "Credit", 
#             "Reward:Risk", "Expiration", "Bull Put Sell Strike", "Bull Put Buy Strike"
#         ]].sort_values("Reward:Risk", ascending=False)
#         st.dataframe(bull_df.reset_index(drop=True).head(200), use_container_width=True)
#         if not bull_df.empty:
#             st.download_button("Download Bull Put CSV", bull_df.to_csv(index=False), "bull_put_candidates.csv")

#     st.markdown("---")
#     st.markdown("### 📋 All Filtered Candidates (for reference)")
#     st.dataframe(df.reset_index(drop=True).head(500), use_container_width=True)
#     st.download_button("Download All Metrics CSV", df.to_csv(index=False), "credit_spread_all_metrics.csv")

#     st.caption("⚠️ Educational use only. Validate signals before trading.")

# if __name__ == "__main__":
#     main()


# ### v4 change credit and reward:risk calculation

# import os
# import io
# import time
# import math
# import logging
# import requests
# import numpy as np
# import pandas as pd
# import yfinance as yf
# import streamlit as st
# from datetime import datetime, timedelta
# import pytz
# from concurrent.futures import ThreadPoolExecutor, as_completed
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# # ----------------------------
# # CONFIG & LOGGING
# # ----------------------------
# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# PARQUET_FILE = "optionable_full.parquet"
# METRICS_CACHE = "metrics_cache.parquet"
# CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"
# PACIFIC = pytz.timezone("US/Pacific")

# # ----------------------------
# # RETRY HELPERS
# # ----------------------------
# def log_retry(retry_state):
#     exc = retry_state.outcome.exception() if retry_state.outcome else None
#     logging.warning(f"Retry attempt {retry_state.attempt_number} due to {exc}")

# @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30),
#        retry=retry_if_exception_type(requests.RequestException), after=log_retry)
# def fetch_cboe_symbols():
#     """Download official CBOE optionable underlying list."""
#     resp = requests.get(CBOE_URL, timeout=30)
#     resp.raise_for_status()
#     df = pd.read_csv(io.StringIO(resp.text))
#     ticker_col = next((c for c in df.columns if "symbol" in c.lower() or "root" in c.lower()), None)
#     if not ticker_col:
#         raise ValueError(f"No symbol column found. Columns: {list(df.columns)}")
#     df = df[[ticker_col]].rename(columns={ticker_col: "symbol"})
#     df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
#     return df.drop_duplicates()

# def load_existing_symbols():
#     if os.path.exists(PARQUET_FILE):
#         try:
#             df = pd.read_parquet(PARQUET_FILE)
#             return df
#         except Exception:
#             logging.exception("Failed reading symbol cache, refetching.")
#             return pd.DataFrame(columns=["symbol", "updated_at"])
#     return pd.DataFrame(columns=["symbol", "updated_at"])

# def update_symbols():
#     """Update local CBOE symbol list."""
#     existing_df = load_existing_symbols()
#     existing_symbols = set(existing_df["symbol"].tolist())
#     df = fetch_cboe_symbols()
#     new_df = df[~df["symbol"].isin(existing_symbols)].copy()
#     if not new_df.empty:
#         new_df["updated_at"] = datetime.utcnow().isoformat()
#     combined_df = pd.concat([existing_df, new_df], ignore_index=True).drop_duplicates("symbol")
#     tmp_file = PARQUET_FILE + ".tmp"
#     combined_df.to_parquet(tmp_file, index=False)
#     os.replace(tmp_file, PARQUET_FILE)
#     return combined_df

# # ----------------------------
# # YFINANCE SAFE WRAPPERS
# # ----------------------------
# def safe_fetch_history(symbol):
#     try:
#         data = yf.Ticker(symbol).history(period="3mo", interval="1d")
#         return data if not data.empty else None
#     except Exception as e:
#         logging.debug(f"history fetch failed for {symbol}: {e}")
#         return None

# def safe_option_chain(symbol, expiration=None):
#     try:
#         ticker = yf.Ticker(symbol)
#         if expiration:
#             opt = ticker.option_chain(expiration)
#         else:
#             opt = ticker.option_chain()
#         return opt.calls, opt.puts
#     except Exception as e:
#         logging.debug(f"option chain fetch failed for {symbol}: {e}")
#         return None, None

# def get_nearest_expiration(ticker, min_days=30):
#     """Get the nearest expiration date at least min_days out."""
#     try:
#         expirations = ticker.options
#         today = datetime.now(pytz.UTC)
#         for exp in expirations:
#             exp_date = datetime.strptime(exp, "%Y-%m-%d").replace(tzinfo=pytz.UTC)
#             if (exp_date - today).days >= min_days:
#                 return exp
#         return None
#     except Exception as e:
#         logging.debug(f"Failed to get expiration dates for {ticker.ticker}: {e}")
#         return None

# # ----------------------------
# # METRIC COMPUTATION
# # ----------------------------
# def compute_metrics(symbol):
#     hist = safe_fetch_history(symbol)
#     if hist is None or hist.empty:
#         return None

#     try:
#         # SMA20
#         hist = hist.copy()
#         hist["SMA20"] = hist["Close"].rolling(20).mean()

#         # RSI (robust EWM-based)
#         delta = hist["Close"].diff()
#         up = delta.clip(lower=0)
#         down = -1 * delta.clip(upper=0)
#         roll_up = up.ewm(alpha=1/14, adjust=False).mean()
#         roll_down = down.ewm(alpha=1/14, adjust=False).mean()
#         rs = roll_up / roll_down
#         rsi_series = 100 - (100 / (1 + rs))
#         rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else np.nan

#         sma20_val = hist["SMA20"].iloc[-1]
#         sma_dev = (hist["Close"].iloc[-1] - sma20_val) / sma20_val if not math.isnan(sma20_val) and sma20_val != 0 else np.nan

#         # Get option chain for the nearest expiration >= 30 days
#         ticker = yf.Ticker(symbol)
#         expiration = get_nearest_expiration(ticker, min_days=30)
#         if not expiration:
#             return None
#         calls, puts = safe_option_chain(symbol, expiration)
#         if calls is None or puts is None or calls.empty or puts.empty:
#             return None

#         close = float(hist["Close"].iloc[-1])

#         # Proxies for OTM and ATM IV
#         call_otm = calls.iloc[(calls["strike"] - close * 1.2).abs().argsort()[:1]]
#         put_otm = puts.iloc[(puts["strike"] - close * 0.8).abs().argsort()[:1]]
#         iv_call = call_otm.get("impliedVolatility", pd.Series([np.nan])).mean()
#         iv_put = put_otm.get("impliedVolatility", pd.Series([np.nan])).mean()
#         iv_skew = float(iv_put / iv_call) if (iv_call and not math.isnan(iv_call) and iv_call > 0) else np.nan

#         atm_call = calls.iloc[(calls["strike"] - close).abs().argsort()[:1]]
#         atm_iv = atm_call.get("impliedVolatility", pd.Series([np.nan])).mean()
#         iv_rank = float(atm_iv / np.nanmean([iv_call, iv_put])) if (not math.isnan(atm_iv) and (not math.isnan(iv_call) or not math.isnan(iv_put))) else np.nan

#         # Bear Call Spread: Sell OTM call (~5% above close), buy next strike up
#         call_sell = calls.iloc[(calls["strike"] - close * 1.05).abs().argsort()[:1]]
#         call_buy = calls[calls["strike"] > call_sell["strike"].iloc[0]].iloc[0:1] if not calls[calls["strike"] > call_sell["strike"].iloc[0]].empty else pd.DataFrame()
#         bear_call_credit = (call_sell["bid"].iloc[0] - call_buy["ask"].iloc[0]) if not call_sell.empty and not call_buy.empty and not pd.isna(call_sell["bid"].iloc[0]) and not pd.isna(call_buy["ask"].iloc[0]) else np.nan
#         bear_call_risk = (call_buy["strike"].iloc[0] - call_sell["strike"].iloc[0] - bear_call_credit) if not call_buy.empty and not call_sell.empty and not pd.isna(bear_call_credit) else np.nan
#         bear_call_reward_risk = bear_call_credit / bear_call_risk if not pd.isna(bear_call_risk) and bear_call_risk > 0 else np.nan

#         # Bull Put Spread: Sell OTM put (~5% below close), buy next strike down
#         put_sell = puts.iloc[(puts["strike"] - close * 0.95).abs().argsort()[:1]]
#         put_buy = puts[puts["strike"] < put_sell["strike"].iloc[0]].iloc[0:1] if not puts[puts["strike"] < put_sell["strike"].iloc[0]].empty else pd.DataFrame()
#         bull_put_credit = (put_sell["bid"].iloc[0] - put_buy["ask"].iloc[0]) if not put_sell.empty and not put_buy.empty and not pd.isna(put_sell["bid"].iloc[0]) and not pd.isna(put_buy["ask"].iloc[0]) else np.nan
#         bull_put_risk = (put_sell["strike"].iloc[0] - put_buy["strike"].iloc[0] - bull_put_credit) if not put_sell.empty and not put_buy.empty and not pd.isna(bull_put_credit) else np.nan
#         bull_put_reward_risk = bull_put_credit / bull_put_risk if not pd.isna(bull_put_risk) and bull_put_risk > 0 else np.nan

#         return {
#             "Symbol": symbol,
#             "RSI": rsi,
#             "SMA Dev": sma_dev,
#             "IV ATM": float(atm_iv) if not pd.isna(atm_iv) else np.nan,
#             "IV Skew": iv_skew,
#             "IV Rank": iv_rank,
#             "Bear Call Credit": bear_call_credit,
#             "Bear Call Reward:Risk": bear_call_reward_risk,
#             "Bull Put Credit": bull_put_credit,
#             "Bull Put Reward:Risk": bull_put_reward_risk,
#             "Timestamp": datetime.utcnow().isoformat(),
#             "Expiration": expiration,
#             "Bear Call Sell Strike": call_sell["strike"].iloc[0] if not call_sell.empty else np.nan,
#             "Bear Call Buy Strike": call_buy["strike"].iloc[0] if not call_buy.empty else np.nan,
#             "Bull Put Sell Strike": put_sell["strike"].iloc[0] if not put_sell.empty else np.nan,
#             "Bull Put Buy Strike": put_buy["strike"].iloc[0] if not put_buy.empty else np.nan
#         }
#     except Exception as e:
#         logging.debug(f"{symbol} compute_metrics failed: {e}")
#         return None

# # ----------------------------
# # CACHE HELPERS
# # ----------------------------
# def load_metrics_cache():
#     if os.path.exists(METRICS_CACHE):
#         try:
#             df = pd.read_parquet(METRICS_CACHE)
#             return df
#         except Exception:
#             logging.exception("Failed to read metrics cache; starting fresh.")
#             return pd.DataFrame()
#     return pd.DataFrame()

# def save_metrics_cache(df):
#     tmp = METRICS_CACHE + ".tmp"
#     df.to_parquet(tmp, index=False)
#     os.replace(tmp, METRICS_CACHE)

# # ----------------------------
# # STREAMLIT APP
# # ----------------------------
# def main():
#     st.set_page_config(page_title="CBOE Credit Spread Screener", layout="wide")
#     st.title("📊 Vertical Credit Spread Screener (CBOE — Full Universe Scan)")

#     # Update symbol cache
#     with st.spinner("Updating CBOE symbol list..."):
#         symbols_df = update_symbols()
#     st.success(f"Loaded {len(symbols_df)} CBOE optionable symbols")

#     # Sidebar: performance & classification settings
#     st.sidebar.header("Performance Settings")
#     max_workers = st.sidebar.slider("Concurrent Threads", 2, 20, 10)
#     sleep_time = st.sidebar.slider("Sleep Between Batches (sec)", 0.2, 3.0, 1.0, step=0.1)
#     batch_size = st.sidebar.slider("Batch Size (submit per loop)", 10, 200, max_workers * 5)

#     st.sidebar.markdown("---")
#     st.sidebar.header("Spread Classification Thresholds")
#     rsi_high = st.sidebar.slider("RSI High (Bear Call)", 50, 80, 60)
#     rsi_low = st.sidebar.slider("RSI Low (Bull Put)", 20, 50, 40)
#     sma_dev_high = st.sidebar.number_input("SMA Dev High (Bear Call)", -0.1, 0.5, 0.02, step=0.005, format="%.4f")
#     sma_dev_low = st.sidebar.number_input("SMA Dev Low (Bull Put)", -0.5, 0.1, -0.02, step=0.005, format="%.4f")

#     # Use all CBOE symbols
#     symbols = symbols_df["symbol"].dropna().unique().tolist()
#     st.info(f"Scanning **all {len(symbols)} CBOE optionable symbols** using up to {max_workers} threads (batch_size={batch_size})")

#     # Scanning in batches with ThreadPoolExecutor
#     results = []
#     total_batches = math.ceil(len(symbols) / batch_size)
#     progress = st.progress(0)
#     start_time = time.time()

#     for batch_index in range(total_batches):
#         start_idx = batch_index * batch_size
#         batch = symbols[start_idx:start_idx + batch_size]
#         with ThreadPoolExecutor(max_workers=max_workers) as executor:
#             futures = {executor.submit(compute_metrics, s): s for s in batch}
#             for fut in as_completed(futures):
#                 sym = futures[fut]
#                 try:
#                     res = fut.result()
#                 except Exception as e:
#                     logging.debug(f"Future error for {sym}: {e}")
#                     res = None
#                 if res:
#                     results.append(res)
#         # Update progress
#         progress.progress((batch_index + 1) / total_batches)
#         elapsed = time.time() - start_time
#         st.caption(f"Batch {batch_index+1}/{total_batches} done — elapsed {elapsed:.1f}s — found {len(results)} candidates")
#         time.sleep(sleep_time)

#     if not results:
#         st.warning("No valid results found.")
#         return

#     df = pd.DataFrame(results).dropna()
#     if df.empty:
#         st.warning("No valid data processed.")
#         return

#     # Classify strategies
#     df["Strategy"] = np.where(
#         (df["RSI"] > rsi_high) & (df["SMA Dev"] > sma_dev_high),
#         "🐻 Bear Call Spread",
#         np.where(
#             (df["RSI"] < rsi_low) & (df["SMA Dev"] < sma_dev_low),
#             "🐂 Bull Put Spread",
#             "— Neutral / Skip —"
#         )
#     )

#     # Merge with old cache and save
#     old_cache = load_metrics_cache()
#     if old_cache is None or old_cache.empty:
#         combined = df.copy()
#     else:
#         combined = pd.concat([old_cache[~old_cache["Symbol"].isin(df["Symbol"])], df], ignore_index=True)
#     save_metrics_cache(combined)

#     # Display results
#     st.subheader("📈 Filtered Candidates by Strategy")
#     col1, col2 = st.columns(2)

#     with col1:
#         st.markdown("### 🐻 Bear Call Spread Candidates")
#         bear_df = df[df["Strategy"] == "🐻 Bear Call Spread"][[
#             "Symbol", "RSI", "SMA Dev", "IV ATM", "IV Skew", "IV Rank", 
#             "Bear Call Credit", "Bear Call Reward:Risk", "Expiration", 
#             "Bear Call Sell Strike", "Bear Call Buy Strike"
#         ]].sort_values("Bear Call Reward:Risk", ascending=False)
#         st.dataframe(bear_df.reset_index(drop=True).head(200), use_container_width=True)
#         if not bear_df.empty:
#             st.download_button("Download Bear Call CSV", bear_df.to_csv(index=False), "bear_call_candidates.csv")

#     with col2:
#         st.markdown("### 🐂 Bull Put Spread Candidates")
#         bull_df = df[df["Strategy"] == "🐂 Bull Put Spread"][[
#             "Symbol", "RSI", "SMA Dev", "IV ATM", "IV Skew", "IV Rank", 
#             "Bull Put Credit", "Bull Put Reward:Risk", "Expiration", 
#             "Bull Put Sell Strike", "Bull Put Buy Strike"
#         ]].sort_values("Bull Put Reward:Risk", ascending=False)
#         st.dataframe(bull_df.reset_index(drop=True).head(200), use_container_width=True)
#         if not bull_df.empty:
#             st.download_button("Download Bull Put CSV", bull_df.to_csv(index=False), "bull_put_candidates.csv")

#     st.markdown("---")
#     st.markdown("### 📋 All Filtered Candidates (for reference)")
#     st.dataframe(df.reset_index(drop=True).head(500), use_container_width=True)
#     st.download_button("Download All Metrics CSV", df.to_csv(index=False), "credit_spread_all_metrics.csv")

#     st.caption("⚠️ Educational use only. Validate signals before trading.")

# if __name__ == "__main__":
#     main()

### v5 new trade parameters


# import os
# import io
# import time
# import math
# import logging
# import requests
# import numpy as np
# import pandas as pd
# import yfinance as yf
# import streamlit as st
# from datetime import datetime, timedelta
# import pytz
# from concurrent.futures import ThreadPoolExecutor, as_completed
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
# import atexit

# # ----------------------------
# # CONFIG & LOGGING
# # ----------------------------
# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# PARQUET_FILE = "optionable_full.parquet"
# CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"
# PACIFIC = pytz.timezone("US/Pacific")

# # ----------------------------
# # THREAD CLEANUP
# # ----------------------------
# executor = None

# def cleanup_threads():
#     global executor
#     if executor:
#         executor._threads.clear()
#         executor.shutdown(wait=False)
#         logging.info("ThreadPoolExecutor cleaned up.")

# atexit.register(cleanup_threads)

# # ----------------------------
# # RETRY HELPERS
# # ----------------------------
# def log_retry(retry_state):
#     exc = retry_state.outcome.exception() if retry_state.outcome else None
#     logging.warning(f"Retry attempt {retry_state.attempt_number} due to {exc}")

# @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30),
#        retry=retry_if_exception_type(requests.RequestException), after=log_retry)
# def fetch_cboe_symbols():
#     """Download official CBOE optionable underlying list."""
#     resp = requests.get(CBOE_URL, timeout=30)
#     resp.raise_for_status()
#     df = pd.read_csv(io.StringIO(resp.text))
#     ticker_col = next((c for c in df.columns if "symbol" in c.lower() or "root" in c.lower()), None)
#     if not ticker_col:
#         raise ValueError(f"No symbol column found. Columns: {list(df.columns)}")
#     df = df[[ticker_col]].rename(columns={ticker_col: "symbol"})
#     df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
#     return df.drop_duplicates()

# def load_existing_symbols():
#     if os.path.exists(PARQUET_FILE):
#         try:
#             df = pd.read_parquet(PARQUET_FILE)
#             return df
#         except Exception:
#             logging.exception("Failed reading symbol cache, refetching.")
#             return pd.DataFrame(columns=["symbol"])
#     return pd.DataFrame(columns=["symbol"])

# def update_symbols():
#     """Update local CBOE symbol list."""
#     existing_df = load_existing_symbols()
#     existing_symbols = set(existing_df["symbol"].tolist())
#     df = fetch_cboe_symbols()
#     new_df = df[~df["symbol"].isin(existing_symbols)].copy()
#     combined_df = pd.concat([existing_df, new_df], ignore_index=True).drop_duplicates("symbol")
#     tmp_file = PARQUET_FILE + ".tmp"
#     combined_df.to_parquet(tmp_file, index=False)
#     os.replace(tmp_file, PARQUET_FILE)
#     return combined_df

# # ----------------------------
# # YFINANCE SAFE WRAPPERS
# # ----------------------------
# def safe_fetch_history(symbol, period="1y"):
#     try:
#         data = yf.Ticker(symbol).history(period=period, interval="1d")
#         return data if not data.empty else None
#     except Exception as e:
#         logging.error(f"{symbol}: possibly delisted; no price data found (period={period}) (Error: {e})")
#         return None

# def safe_option_chain(symbol, expiration=None):
#     try:
#         ticker = yf.Ticker(symbol)
#         if expiration:
#             opt = ticker.option_chain(expiration)
#         else:
#             opt = ticker.option_chain()
#         return opt.calls, opt.puts
#     except Exception as e:
#         logging.debug(f"Option chain fetch failed for {symbol}: {e}")
#         return None, None

# def get_nearest_expiration(ticker, min_days=30):
#     try:
#         expirations = ticker.options
#         today = datetime.now(pytz.UTC)
#         for exp in expirations:
#             exp_date = datetime.strptime(exp, "%Y-%m-%d").replace(tzinfo=pytz.UTC)
#             if (exp_date - today).days >= min_days:
#                 return exp
#         return None
#     except Exception as e:
#         logging.debug(f"Failed to get expiration dates for {ticker.ticker}: {e}")
#         return None

# def has_earnings_before_expiration(ticker, expiration):
#     try:
#         exp_date = datetime.strptime(expiration, "%Y-%m-%d").replace(tzinfo=pytz.UTC)
#         earnings = ticker.calendar
#         if earnings and "Earnings Date" in earnings:
#             earnings_date = pd.to_datetime(earnings["Earnings Date"]).tz_localize(pytz.UTC)
#             return earnings_date <= exp_date
#         return False
#     except Exception as e:
#         logging.debug(f"Failed to check earnings for {ticker.ticker}: {e}")
#         return True  # Conservative: assume earnings exist if check fails

# def validate_symbol(symbol):
#     """Check if symbol is valid and has price data."""
#     try:
#         ticker = yf.Ticker(symbol)
#         hist = ticker.history(period="1d")
#         return not hist.empty
#     except Exception:
#         return False

# # ----------------------------
# # METRIC COMPUTATION
# # ----------------------------
# def compute_metrics(symbol):
#     if not validate_symbol(symbol):
#         return None

#     ticker = yf.Ticker(symbol)
#     hist = safe_fetch_history(symbol, period="1y")
#     if hist is None or hist.empty:
#         return None

#     try:
#         # Liquidity Filter: Average Daily Volume
#         avg_volume = hist["Volume"].mean()
#         if avg_volume < 500000:
#             return None

#         # Moving Averages and Bollinger Bands
#         hist["SMA50"] = hist["Close"].rolling(50).mean()
#         hist["SMA200"] = hist["Close"].rolling(200).mean()
#         hist["BB_Mid"] = hist["Close"].rolling(20).mean()
#         hist["BB_Std"] = hist["Close"].rolling(20).std()
#         hist["BB_Upper"] = hist["BB_Mid"] + 2 * hist["BB_Std"]
#         hist["BB_Lower"] = hist["BB_Mid"] - 2 * hist["BB_Std"]

#         # ATR for Expected Price Range
#         high_low = hist["High"] - hist["Low"]
#         high_close = abs(hist["High"] - hist["Close"].shift())
#         low_close = abs(hist["Low"] - hist["Close"].shift())
#         true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
#         atr = true_range.rolling(14).mean().iloc[-1]

#         # Historical Volatility (HV) - 20-day annualized
#         daily_returns = hist["Close"].pct_change().dropna()
#         hv = daily_returns.rolling(20).std().iloc[-1] * np.sqrt(252) * 100

#         # Option Chain for Nearest Expiration >= 30 days
#         expiration = get_nearest_expiration(ticker, min_days=30)
#         if not expiration:
#             return None

#         # Event Avoidance: Skip if earnings before expiration
#         if has_earnings_before_expiration(ticker, expiration):
#             return None

#         calls, puts = safe_option_chain(symbol, expiration)
#         if calls is None or puts is None or calls.empty or puts.empty:
#             return None

#         close = float(hist["Close"].iloc[-1])
#         sma50 = hist["SMA50"].iloc[-1]
#         sma200 = hist["SMA200"].iloc[-1]
#         bb_upper = hist["BB_Upper"].iloc[-1]
#         bb_lower = hist["BB_Lower"].iloc[-1]

#         # Liquidity Filter: Option Chain
#         calls["BidAskSpread"] = calls["ask"] - calls["bid"]
#         puts["BidAskSpread"] = puts["ask"] - puts["bid"]
#         calls["MidPrice"] = (calls["bid"] + calls["ask"]) / 2
#         puts["MidPrice"] = (puts["bid"] + puts["ask"]) / 2
#         calls["SpreadPct"] = calls["BidAskSpread"] / calls["MidPrice"]
#         puts["SpreadPct"] = puts["BidAskSpread"] / puts["MidPrice"]

#         valid_calls = calls[
#             (calls["openInterest"] > 500) &
#             (calls["volume"] > 100) &
#             (calls["SpreadPct"] < 0.1)
#         ]
#         valid_puts = puts[
#             (puts["openInterest"] > 500) &
#             (puts["volume"] > 100) &
#             (puts["SpreadPct"] < 0.1)
#         ]
#         if valid_calls.empty or valid_puts.empty:
#             return None

#         # Volatility Filter: IV Rank and IV vs HV
#         atm_call = valid_calls.iloc[(valid_calls["strike"] - close).abs().argsort()[:1]]
#         iv_atm = atm_call["impliedVolatility"].iloc[0] if not atm_call.empty else np.nan
#         if pd.isna(iv_atm) or iv_atm > 1.0:  # IV > 100%
#             return None

#         # IV Rank: Collect IVs from multiple expirations
#         iv_series = []
#         for exp in ticker.options[:5]:  # Check up to 5 expirations
#             c, p = safe_option_chain(symbol, exp)
#             if c is not None and not c.empty:
#                 c_atm = c.iloc[(c["strike"] - close).abs().argsort()[:1]]
#                 if not c_atm.empty:
#                     iv_series.append(c_atm["impliedVolatility"].iloc[0])
#         iv_series = [iv for iv in iv_series if not pd.isna(iv)]
#         if not iv_series:
#             return None
#         iv_low = min(iv_series)
#         iv_high = max(iv_series)
#         ivr = (iv_atm - iv_low) / (iv_high - iv_low) if iv_high != iv_low else 0
#         if ivr < 0.5:  # IVR < 50%
#             return None
#         if iv_atm * 100 <= hv:  # IV <= HV
#             return None

#         # Fundamental Filter (Bull Put only)
#         try:
#             info = ticker.info
#             earnings_growth = info.get("earningsGrowth", 0)
#             debt_to_equity = info.get("debtToEquity", float("inf"))
#             bull_eligible = earnings_growth > 0 and debt_to_equity < 100
#         except Exception as e:
#             logging.error(f"Failed to fetch fundamentals for {symbol}: {e}")
#             bull_eligible = False

#         # Price Trend and Strategy Classification
#         expected_range = close + atr  # Upper bound
#         expected_range_lower = close - atr  # Lower bound

#         # Bear Call Spread: Downtrend or at resistance
#         bear_eligible = close < sma50 and close < sma200 or abs(close - bb_upper) / bb_upper < 0.01
#         if bear_eligible:
#             call_sell = valid_calls[valid_calls["strike"] > expected_range].iloc[:1]
#             call_buy = valid_calls[valid_calls["strike"] > call_sell["strike"].iloc[0]].iloc[:1] if not call_sell.empty else pd.DataFrame()
#             bear_call_credit = (call_sell["bid"].iloc[0] - call_buy["ask"].iloc[0]) if not call_sell.empty and not call_buy.empty else np.nan
#             bear_call_risk = (call_buy["strike"].iloc[0] - call_sell["strike"].iloc[0] - bear_call_credit) if not call_buy.empty and not call_sell.empty else np.nan
#             bear_call_reward_risk = bear_call_credit / bear_call_risk if not pd.isna(bear_call_risk) and bear_call_risk > 0 else np.nan
#         else:
#             bear_call_credit = bear_call_risk = bear_call_reward_risk = call_sell = call_buy = np.nan

#         # Bull Put Spread: Uptrend or at support
#         bull_eligible = bull_eligible and (close > sma50 and close > sma200 or abs(close - bb_lower) / bb_lower < 0.01)
#         if bull_eligible:
#             put_sell = valid_puts[valid_puts["strike"] < expected_range_lower].iloc[:1]
#             put_buy = valid_puts[valid_puts["strike"] < put_sell["strike"].iloc[0]].iloc[:1] if not put_sell.empty else pd.DataFrame()
#             bull_put_credit = (put_sell["bid"].iloc[0] - put_buy["ask"].iloc[0]) if not put_sell.empty and not put_buy.empty else np.nan
#             bull_put_risk = (put_sell["strike"].iloc[0] - put_buy["strike"].iloc[0] - bull_put_credit) if not put_sell.empty and not put_buy.empty else np.nan
#             bull_put_reward_risk = bull_put_credit / bull_put_risk if not pd.isna(bull_put_risk) and bull_put_risk > 0 else np.nan
#         else:
#             bull_put_credit = bull_put_risk = bull_put_reward_risk = put_sell = put_buy = np.nan

#         if pd.isna(bear_call_reward_risk) and pd.isna(bull_put_reward_risk):
#             return None

#         return {
#             "Symbol": symbol,
#             "Close": close,
#             "IV ATM (%)": iv_atm * 100,
#             "IV Rank (%)": ivr * 100,
#             "HV (%)": hv,
#             "Bear Call Credit": bear_call_credit,
#             "Bear Call Reward:Risk": bear_call_reward_risk,
#             "Bear Call Sell Strike": call_sell["strike"].iloc[0] if not pd.isna(call_sell) and not call_sell.empty else np.nan,
#             "Bear Call Buy Strike": call_buy["strike"].iloc[0] if not pd.isna(call_buy) and not call_buy.empty else np.nan,
#             "Bull Put Credit": bull_put_credit,
#             "Bull Put Reward:Risk": bull_put_reward_risk,
#             "Bull Put Sell Strike": put_sell["strike"].iloc[0] if not pd.isna(put_sell) and not put_sell.empty else np.nan,
#             "Bull Put Buy Strike": put_buy["strike"].iloc[0] if not pd.isna(put_buy) and not put_buy.empty else np.nan,
#             "Expiration": expiration,
#             "Strategy": "🐻 Bear Call Spread" if not pd.isna(bear_call_reward_risk) else "🐂 Bull Put Spread" if not pd.isna(bull_put_reward_risk) else "— Neutral / Skip —"
#         }
#     except Exception as e:
#         logging.debug(f"{symbol} compute_metrics failed: {e}")
#         return None

# # ----------------------------
# # STREAMLIT APP
# # ----------------------------
# def main():
#     global executor
#     st.set_page_config(page_title="CBOE Credit Spread Screener", layout="wide")
#     st.title("📊 Vertical Credit Spread Screener (CBOE — Filtered Scan)")

#     # Update symbol cache
#     with st.spinner("Updating CBOE symbol list..."):
#         symbols_df = update_symbols()
#     st.success(f"Loaded {len(symbols_df)} CBOE optionable symbols")

#     # Filter valid symbols
#     with st.spinner("Validating symbols..."):
#         symbols = symbols_df["symbol"].dropna().unique().tolist()
#         valid_symbols = []
#         with ThreadPoolExecutor(max_workers=10) as temp_executor:
#             futures = {temp_executor.submit(validate_symbol, s): s for s in symbols}
#             for fut in as_completed(futures):
#                 if fut.result():
#                     valid_symbols.append(futures[fut])
#         symbols = valid_symbols
#     st.info(f"Scanning **{len(symbols)} valid CBOE optionable symbols**")

#     # Sidebar: Performance settings
#     st.sidebar.header("Performance Settings")
#     max_workers = st.sidebar.slider("Concurrent Threads", 2, 20, 10)
#     sleep_time = st.sidebar.slider("Sleep Between Batches (sec)", 0.2, 3.0, 1.0, step=0.1)
#     batch_size = st.sidebar.slider("Batch Size (submit per loop)", 10, 200, max_workers * 5)

#     # Scanning in batches with ThreadPoolExecutor
#     results = []
#     total_batches = math.ceil(len(symbols) / batch_size)
#     progress = st.progress(0)
#     start_time = time.time()

#     for batch_index in range(total_batches):
#         start_idx = batch_index * batch_size
#         batch = symbols[start_idx:start_idx + batch_size]
#         executor = ThreadPoolExecutor(max_workers=max_workers)
#         futures = {executor.submit(compute_metrics, s): s for s in batch}
#         for fut in as_completed(futures):
#             sym = futures[fut]
#             try:
#                 res = fut.result()
#             except Exception as e:
#                 logging.debug(f"Future error for {sym}: {e}")
#                 res = None
#             if res:
#                 results.append(res)
#         executor.shutdown(wait=True)
#         progress.progress((batch_index + 1) / total_batches)
#         elapsed = time.time() - start_time
#         st.caption(f"Batch {batch_index+1}/{total_batches} done — elapsed {elapsed:.1f}s — found {len(results)} candidates")
#         time.sleep(sleep_time)

#     if not results:
#         st.warning("No valid results found after applying filters.")
#         return

#     df = pd.DataFrame(results).dropna(subset=["Strategy"])
#     if df.empty:
#         st.warning("No valid data processed after filters.")
#         return

#     # Display results
#     st.subheader("📈 Filtered Candidates by Strategy")
#     col1, col2 = st.columns(2)

#     with col1:
#         st.markdown("### 🐻 Bear Call Spread Candidates")
#         bear_df = df[df["Strategy"] == "🐻 Bear Call Spread"][[
#             "Symbol", "Close", "IV ATM (%)", "IV Rank (%)", "HV (%)",
#             "Bear Call Credit", "Bear Call Reward:Risk", "Expiration",
#             "Bear Call Sell Strike", "Bear Call Buy Strike"
#         ]].sort_values("Bear Call Reward:Risk", ascending=False)
#         st.dataframe(bear_df.reset_index(drop=True).head(200), use_container_width=True)
#         if not bear_df.empty:
#             st.download_button("Download Bear Call CSV", bear_df.to_csv(index=False), "bear_call_candidates.csv")

#     with col2:
#         st.markdown("### 🐂 Bull Put Spread Candidates")
#         bull_df = df[df["Strategy"] == "🐂 Bull Put Spread"][[
#             "Symbol", "Close", "IV ATM (%)", "IV Rank (%)", "HV (%)",
#             "Bull Put Credit", "Bull Put Reward:Risk", "Expiration",
#             "Bull Put Sell Strike", "Bull Put Buy Strike"
#         ]].sort_values("Bull Put Reward:Risk", ascending=False)
#         st.dataframe(bull_df.reset_index(drop=True).head(200), use_container_width=True)
#         if not bull_df.empty:
#             st.download_button("Download Bull Put CSV", bull_df.to_csv(index=False), "bull_put_candidates.csv")

#     st.markdown("---")
#     st.markdown("### 📋 All Filtered Candidates")
#     st.dataframe(df[[
#         "Symbol", "Close", "IV ATM (%)", "IV Rank (%)", "HV (%)",
#         "Bear Call Credit", "Bear Call Reward:Risk", "Bull Put Credit",
#         "Bull Put Reward:Risk", "Expiration"
#     ]].reset_index(drop=True).head(500), use_container_width=True)
#     st.download_button("Download All Metrics CSV", df.to_csv(index=False), "credit_spread_all_metrics.csv")

#     st.caption("⚠️ Educational use only. Validate signals before trading. Note: Macro event checks are not implemented due to lack of real-time economic calendar API.")

# if __name__ == "__main__":
#     main()



# #### v2 - v1 average volume   

# import os
# import io
# import time
# import math
# import logging
# import requests
# import pandas as pd
# import streamlit as st
# import yfinance as yf
# from datetime import datetime
# from concurrent.futures import ThreadPoolExecutor, as_completed
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
# from cachetools import TTLCache

# # ----------------------------
# # CONFIG & LOGGING
# # ----------------------------
# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# PARQUET_FILE = "optionable_full.parquet"
# METRICS_CACHE = "metrics_cache.parquet"
# HISTORY_CACHE_DIR = "history_cache"
# CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"
# BATCH_SIZE = 50
# MAX_WORKERS = 5
# HISTORY_TTL = 3600  # Cache history for 1 hour

# # In-memory cache for historical data
# history_cache = TTLCache(maxsize=1000, ttl=HISTORY_TTL)

# # Ensure history cache directory exists
# if not os.path.exists(HISTORY_CACHE_DIR):
#     os.makedirs(HISTORY_CACHE_DIR)

# # ----------------------------
# # RETRY HELPERS
# # ----------------------------
# def log_retry(retry_state):
#     exc = retry_state.outcome.exception() if retry_state.outcome else None
#     logging.warning(f"Retry attempt {retry_state.attempt_number} due to {exc}")

# @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30),
#        retry=retry_if_exception_type(requests.RequestException), after=log_retry)
# def fetch_cboe_symbols():
#     """Download official CBOE optionable underlying list."""
#     resp = requests.get(CBOE_URL, timeout=30)
#     resp.raise_for_status()
#     df = pd.read_csv(io.StringIO(resp.text))
#     ticker_col = next((c for c in df.columns if "symbol" in c.lower() or "root" in c.lower()), None)
#     if not ticker_col:
#         raise ValueError(f"No symbol column found. Columns: {list(df.columns)}")
#     df = df[[ticker_col]].rename(columns={ticker_col: "symbol"})
#     df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
#     return df.drop_duplicates()

# def load_existing_symbols():
#     """Load cached CBOE symbols."""
#     if os.path.exists(PARQUET_FILE):
#         try:
#             return pd.read_parquet(PARQUET_FILE)
#         except Exception:
#             logging.exception("Failed reading symbol cache, refetching.")
#     return pd.DataFrame(columns=["symbol", "updated_at"])

# def update_symbols():
#     """Update local CBOE symbol list."""
#     existing_df = load_existing_symbols()
#     existing_symbols = set(existing_df["symbol"].tolist())
#     try:
#         df = fetch_cboe_symbols()
#     except Exception as e:
#         logging.error(f"Failed to fetch CBOE symbols: {e}")
#         return existing_df if not existing_df.empty else pd.DataFrame(columns=["symbol", "updated_at"])
    
#     new_df = df[~df["symbol"].isin(existing_symbols)].copy()
#     if not new_df.empty:
#         new_df["updated_at"] = datetime.utcnow().isoformat()
#     combined_df = pd.concat([existing_df, new_df], ignore_index=True).drop_duplicates("symbol")
#     tmp_file = PARQUET_FILE + ".tmp"
#     combined_df.to_parquet(tmp_file, index=False)
#     os.replace(tmp_file, PARQUET_FILE)
#     return combined_df

# # ----------------------------
# # YFINANCE DATA FETCHING
# # ----------------------------
# def fetch_historical_data(symbol):
#     """Fetch historical data from yfinance or cache."""
#     cache_key = f"{symbol}_history"
#     cache_file = os.path.join(HISTORY_CACHE_DIR, f"{symbol}.parquet")

#     # Check in-memory cache
#     if cache_key in history_cache:
#         return history_cache[cache_key]

#     # Check disk cache
#     if os.path.exists(cache_file):
#         try:
#             data = pd.read_parquet(cache_file)
#             if not data.empty:
#                 history_cache[cache_key] = data
#                 return data
#         except Exception:
#             logging.debug(f"Failed to read history cache for {symbol}")

#     # Fetch from yfinance
#     try:
#         data = yf.Ticker(symbol).history(period="3mo", interval="1d")
#         if data.empty:
#             logging.debug(f"No historical data for {symbol}")
#             return None
#         # Save to disk cache
#         data.to_parquet(cache_file)
#         history_cache[cache_key] = data
#         return data
#     except Exception as e:
#         logging.debug(f"History fetch failed for {symbol}: {e}")
#         return None

# # ----------------------------
# # METRIC COMPUTATION
# # ----------------------------
# def compute_metrics(symbol, min_volume):
#     """Compute metrics for a symbol using cached historical data and user-defined volume filter."""
#     hist = fetch_historical_data(symbol)
#     if hist is None or hist.empty:
#         logging.debug(f"Skipping {symbol}: No historical data available")
#         return None

#     try:
#         avg_volume = hist["Volume"].mean()
#         if avg_volume < min_volume:
#             logging.debug(f"Skipping {symbol}: Volume {avg_volume} below {min_volume}")
#             return None
#         return {
#             "Symbol": symbol,
#             "Avg Volume": avg_volume,
#             "Timestamp": datetime.utcnow().isoformat()
#         }
#     except Exception as e:
#         logging.debug(f"{symbol} compute_metrics failed: {e}")
#         return None

# # ----------------------------
# # CACHE HELPERS
# # ----------------------------
# def load_metrics_cache():
#     """Load cached metrics."""
#     if os.path.exists(METRICS_CACHE):
#         try:
#             return pd.read_parquet(METRICS_CACHE)
#         except Exception:
#             logging.exception("Failed to read metrics cache; starting fresh.")
#     return pd.DataFrame()

# def save_metrics_cache(df):
#     """Save metrics to cache."""
#     tmp = METRICS_CACHE + ".tmp"
#     df.to_parquet(tmp, index=False)
#     os.replace(tmp, METRICS_CACHE)

# # ----------------------------
# # STREAMLIT APP
# # ----------------------------
# def filter_stocks_tab():
#     st.header("🔍 Filter Stocks")
    
#     # Volume filter input
#     st.subheader("Filter Settings")
#     min_volume = st.number_input("Min Avg Daily Volume", min_value=100000, max_value=2000000, value=500000)
#     if min_volume < 0:
#         st.error("Volume must be positive.")
#         return

#     # Update symbols
#     with st.spinner("Updating CBOE symbol list..."):
#         symbols_df = update_symbols()
#     if symbols_df.empty:
#         st.error("No symbols available. Check logs for errors.")
#         return
#     st.success(f"Loaded {len(symbols_df)} CBOE optionable symbols")

#     symbols = symbols_df["symbol"].dropna().unique().tolist()
#     st.info(f"Scanning {len(symbols)} symbols with filter: Volume > {min_volume:,}")

#     # Scanning with concurrency
#     results = []
#     total_batches = math.ceil(len(symbols) / BATCH_SIZE)
#     progress = st.progress(0)
#     start_time = time.time()

#     for batch_index in range(total_batches):
#         start_idx = batch_index * BATCH_SIZE
#         batch = symbols[start_idx:start_idx + BATCH_SIZE]
#         with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
#             futures = {executor.submit(compute_metrics, s, min_volume): s for s in batch}
#             for fut in as_completed(futures):
#                 sym = futures[fut]
#                 try:
#                     res = fut.result()
#                 except Exception as e:
#                     logging.debug(f"Future error for {sym}: {e}")
#                     res = None
#                 if res:
#                     results.append(res)
#         progress.progress((batch_index + 1) / total_batches)
#         elapsed = time.time() - start_time
#         st.caption(f"Batch {batch_index+1}/{total_batches} — {elapsed:.1f}s — {len(results)} candidates")
#         time.sleep(0.5)  # Fixed delay to avoid API rate limits

#     if not results:
#         st.warning("No valid results found.")
#         return

#     df = pd.DataFrame(results).dropna()

#     # Apply volume filter (redundant but kept for clarity and future-proofing)
#     df = df[df["Avg Volume"] >= min_volume]

#     if df.empty:
#         st.warning(f"No candidates found with volume > {min_volume:,}.")
#         return

#     # Cache results
#     old_cache = load_metrics_cache()
#     combined = pd.concat([old_cache[~old_cache["Symbol"].isin(df["Symbol"])], df], ignore_index=True) if not old_cache.empty else df
#     save_metrics_cache(combined)

#     # Display results
#     st.subheader("📈 Filtered Stocks")
#     st.dataframe(df[["Symbol", "Avg Volume"]].head(100), use_container_width=True)
#     st.download_button("Download Filtered Stocks", df.to_csv(index=False), "filtered_stocks.csv")

#     st.caption("⚠️ Educational use only.")

# def main():
#     st.set_page_config(page_title="CBOE Stock Screener", layout="wide")
#     st.title("📊 CBOE Stock Screener")
#     filter_stocks_tab()

# if __name__ == "__main__":
#     main()

### v2 optimize for speed


# import os
# import io
# import time
# import math
# import logging
# import requests
# import pandas as pd
# import streamlit as st
# import yfinance as yf
# from datetime import datetime, timedelta
# from concurrent.futures import ThreadPoolExecutor, as_completed
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
# from cachetools import TTLCache
# import psutil
# import hashlib
# import json

# # ----------------------------
# # CONFIG & LOGGING
# # ----------------------------
# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# PARQUET_FILE = "optionable_full.parquet"
# METRICS_CACHE = "metrics_cache.parquet"
# HISTORY_CACHE_DIR = "history_cache"
# CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"
# SCHEMA_VERSION = "1.0"  # For cache validation
# HISTORY_TTL = 24 * 3600  # Cache history for 24 hours
# SYMBOLS_TTL = 7 * 24 * 3600  # Cache symbols for 7 days

# # Dynamic concurrency based on system resources
# CPU_COUNT = psutil.cpu_count(logical=False) or 4
# MAX_WORKERS = min(CPU_COUNT, 8)  # Cap at 8 to avoid overwhelming API
# BATCH_SIZE = min(CPU_COUNT * 10, 100)  # Dynamic batch size

# # In-memory cache with longer TTL for symbols
# history_cache = TTLCache(maxsize=1000, ttl=HISTORY_TTL)
# symbols_cache = TTLCache(maxsize=1, ttl=SYMBOLS_TTL)

# # Ensure history cache directory exists
# os.makedirs(HISTORY_CACHE_DIR, exist_ok=True)

# # ----------------------------
# # CACHE VALIDATION
# # ----------------------------
# def validate_cache(file_path, expected_columns):
#     """Validate cache file integrity and schema."""
#     if not os.path.exists(file_path):
#         return False
#     try:
#         df = pd.read_parquet(file_path)
#         if not all(col in df.columns for col in expected_columns):
#             logging.warning(f"Invalid schema in {file_path}. Expected: {expected_columns}")
#             return False
#         # Optional: Add checksum validation
#         return True
#     except Exception as e:
#         logging.error(f"Cache validation failed for {file_path}: {e}")
#         return False

# def clear_corrupted_cache(file_path):
#     """Remove corrupted cache file."""
#     if os.path.exists(file_path):
#         os.remove(file_path)
#         logging.info(f"Cleared corrupted cache: {file_path}")

# # ----------------------------
# # RETRY HELPERS
# # ----------------------------
# def log_retry(retry_state):
#     exc = retry_state.outcome.exception() if retry_state.outcome else None
#     logging.warning(f"Retry attempt {retry_state.attempt_number} due to {exc}")

# @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30),
#        retry=retry_if_exception_type(requests.RequestException), after=log_retry)
# def fetch_cboe_symbols():
#     """Download official CBOE optionable underlying list."""
#     cache_key = "cboe_symbols"
#     if cache_key in symbols_cache:
#         return symbols_cache[cache_key]

#     resp = requests.get(CBOE_URL, timeout=30)
#     resp.raise_for_status()
#     df = pd.read_csv(io.StringIO(resp.text))
#     ticker_col = next((c for c in df.columns if "symbol" in c.lower() or "root" in c.lower()), None)
#     if not ticker_col:
#         raise ValueError(f"No symbol column found. Columns: {list(df.columns)}")
#     df = df[[ticker_col]].rename(columns={ticker_col: "symbol"})
#     df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
#     df = df.drop_duplicates().assign(updated_at=datetime.utcnow().isoformat(), schema_version=SCHEMA_VERSION)
    
#     symbols_cache[cache_key] = df
#     return df

# def load_existing_symbols():
#     """Load cached CBOE symbols with validation."""
#     if validate_cache(PARQUET_FILE, ["symbol", "updated_at", "schema_version"]):
#         try:
#             df = pd.read_parquet(PARQUET_FILE)
#             if df["schema_version"].iloc[0] == SCHEMA_VERSION:
#                 return df
#             else:
#                 logging.warning("Schema version mismatch. Refetching symbols.")
#         except Exception:
#             logging.exception("Failed reading symbol cache.")
#     clear_corrupted_cache(PARQUET_FILE)
#     return pd.DataFrame(columns=["symbol", "updated_at", "schema_version"])

# def update_symbols():
#     """Update local CBOE symbol list."""
#     existing_df = load_existing_symbols()
#     if not existing_df.empty and (datetime.utcnow() - pd.to_datetime(existing_df["updated_at"].iloc[0])).total_seconds() < SYMBOLS_TTL:
#         return existing_df

#     try:
#         df = fetch_cboe_symbols()
#     except Exception as e:
#         logging.error(f"Failed to fetch CBOE symbols: {e}")
#         return existing_df if not existing_df.empty else pd.DataFrame(columns=["symbol", "updated_at", "schema_version"])
    
#     new_df = df[~df["symbol"].isin(existing_df["symbol"])].copy()
#     if not new_df.empty:
#         new_df["updated_at"] = datetime.utcnow().isoformat()
#         new_df["schema_version"] = SCHEMA_VERSION
#     combined_df = pd.concat([existing_df, new_df], ignore_index=True).drop_duplicates(subset="symbol", keep="last")
    
#     tmp_file = PARQUET_FILE + ".tmp"
#     combined_df.to_parquet(tmp_file, index=False)
#     os.replace(tmp_file, PARQUET_FILE)
#     return combined_df

# # ----------------------------
# # YFINANCE DATA FETCHING
# # ----------------------------
# @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=60),
#        retry=retry_if_exception_type(Exception), after=log_retry)
# def fetch_historical_data(symbol):
#     """Fetch historical data from yfinance or cache."""
#     cache_key = f"{symbol}_history"
#     cache_file = os.path.join(HISTORY_CACHE_DIR, f"{symbol}.parquet")

#     # Check in-memory cache
#     if cache_key in history_cache:
#         return history_cache[cache_key]

#     # Check disk cache
#     if validate_cache(cache_file, ["Open", "High", "Low", "Close", "Volume"]):
#         try:
#             data = pd.read_parquet(cache_file)
#             history_cache[cache_key] = data
#             return data
#         except Exception:
#             logging.debug(f"Failed to read history cache for {symbol}")
#             clear_corrupted_cache(cache_file)

#     # Fetch from yfinance
#     try:
#         ticker = yf.Ticker(symbol)
#         data = ticker.history(period="3mo", interval="1d")
#         if data.empty:
#             logging.debug(f"No historical data for {symbol}")
#             return None
#         data["symbol"] = symbol
#         data["schema_version"] = SCHEMA_VERSION
#         data.to_parquet(cache_file)
#         history_cache[cache_key] = data
#         return data
#     except Exception as e:
#         logging.debug(f"History fetch failed for {symbol}: {e}")
#         return None

# # ----------------------------
# # METRIC COMPUTATION
# # ----------------------------
# def compute_metrics(symbols, min_volume):
#     """Vectorized metric computation for multiple symbols."""
#     results = []
#     for symbol in symbols:
#         hist = fetch_historical_data(symbol)
#         if hist is None or hist.empty:
#             logging.debug(f"Skipping {symbol}: No historical data")
#             continue
#         try:
#             avg_volume = hist["Volume"].mean()
#             if avg_volume < min_volume:
#                 logging.debug(f"Skipping {symbol}: Volume {avg_volume} below {min_volume}")
#                 continue
#             results.append({
#                 "Symbol": symbol,
#                 "Avg Volume": avg_volume,
#                 "Timestamp": datetime.utcnow().isoformat(),
#                 "schema_version": SCHEMA_VERSION
#             })
#         except Exception as e:
#             logging.debug(f"Metrics computation failed for {symbol}: {e}")
#     return results

# # ----------------------------
# # CACHE HELPERS
# # ----------------------------
# def load_metrics_cache():
#     """Load cached metrics with validation."""
#     if validate_cache(METRICS_CACHE, ["Symbol", "Avg Volume", "Timestamp", "schema_version"]):
#         try:
#             return pd.read_parquet(METRICS_CACHE)
#         except Exception:
#             logging.exception("Failed to read metrics cache.")
#     clear_corrupted_cache(METRICS_CACHE)
#     return pd.DataFrame(columns=["Symbol", "Avg Volume", "Timestamp", "schema_version"])

# def save_metrics_cache(df):
#     """Save metrics to cache."""
#     tmp = METRICS_CACHE + ".tmp"
#     df.to_parquet(tmp, index=False)
#     os.replace(tmp, METRICS_CACHE)

# # ----------------------------
# # STREAMLIT APP
# # ----------------------------
# def filter_stocks_tab():
#     st.header("🔍 Filter Stocks")
    
#     # Volume filter input
#     st.subheader("Filter Settings")
#     min_volume = st.number_input("Min Avg Daily Volume", min_value=100000, max_value=2000000, value=500000)
#     if min_volume < 0:
#         st.error("Volume must be positive.")
#         return

#     # Cancellation button
#     cancel_scan = st.button("Cancel Scan", key="cancel_scan")
#     if "cancel" not in st.session_state:
#         st.session_state.cancel = False
#     if cancel_scan:
#         st.session_state.cancel = True
#         st.warning("Scan cancelled.")
#         return

#     # Update symbols
#     with st.spinner("Updating CBOE symbol list..."):
#         symbols_df = update_symbols()
#     if symbols_df.empty:
#         st.error("No symbols available. Check logs for errors.")
#         return
#     st.success(f"Loaded {len(symbols_df)} CBOE optionable symbols")

#     symbols = symbols_df["symbol"].dropna().unique().tolist()
#     st.info(f"Scanning {len(symbols)} symbols with filter: Volume > {min_volume:,}")

#     # Scanning with concurrency
#     results = []
#     total_batches = math.ceil(len(symbols) / BATCH_SIZE)
#     progress = st.progress(0)
#     start_time = time.time()
#     eta_placeholder = st.empty()

#     for batch_index in range(total_batches):
#         if st.session_state.cancel:
#             break
#         start_idx = batch_index * BATCH_SIZE
#         batch = symbols[start_idx:start_idx + BATCH_SIZE]
#         batch_results = compute_metrics(batch, min_volume)
#         results.extend(batch_results)

#         # Update progress and ETA
#         progress.progress((batch_index + 1) / total_batches)
#         elapsed = time.time() - start_time
#         batches_left = total_batches - (batch_index + 1)
#         eta = (elapsed / (batch_index + 1)) * batches_left if batch_index > 0 else 0
#         eta_placeholder.caption(f"Batch {batch_index+1}/{total_batches} — {elapsed:.1f}s elapsed — ETA: {eta:.1f}s — {len(results)} candidates")

#     if st.session_state.cancel:
#         return

#     if not results:
#         st.warning("No valid results found.")
#         return

#     df = pd.DataFrame(results).dropna()
#     df = df[df["Avg Volume"] >= min_volume]

#     if df.empty:
#         st.warning(f"No candidates found with volume > {min_volume:,}.")
#         return

#     # Cache results
#     old_cache = load_metrics_cache()
#     combined = pd.concat([old_cache[~old_cache["Symbol"].isin(df["Symbol"])], df], ignore_index=True) if not old_cache.empty else df
#     save_metrics_cache(combined)

#     # Display results
#     st.subheader("📈 Filtered Stocks")
#     st.dataframe(df[["Symbol", "Avg Volume"]].head(100), use_container_width=True)
#     st.download_button("Download Filtered Stocks", df.to_csv(index=False), "filtered_stocks.csv")

#     st.caption("⚠️ Educational use only.")

# def main():
#     st.set_page_config(page_title="CBOE Stock Screener", layout="wide")
#     st.title("📊 CBOE Stock Screener")
#     filter_stocks_tab()

# if __name__ == "__main__":
#     main()


###### add technical filter back in

# import os
# import io
# import time
# import math
# import logging
# import requests
# import pandas as pd
# import numpy as np
# import streamlit as st
# import yfinance as yf
# from datetime import datetime, timedelta
# from concurrent.futures import ThreadPoolExecutor, as_completed
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
# from cachetools import TTLCache
# import psutil
# import hashlib
# import json

# # ----------------------------
# # CONFIG & LOGGING
# # ----------------------------
# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# PARQUET_FILE = "optionable_full.parquet"
# METRICS_CACHE = "metrics_cache.parquet"
# HISTORY_CACHE_DIR = "history_cache"
# CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"
# SCHEMA_VERSION = "1.0"
# HISTORY_TTL = 24 * 3600
# SYMBOLS_TTL = 7 * 24 * 3600

# CPU_COUNT = psutil.cpu_count(logical=False) or 4
# MAX_WORKERS = min(CPU_COUNT, 8)
# BATCH_SIZE = min(CPU_COUNT * 10, 100)

# history_cache = TTLCache(maxsize=1000, ttl=HISTORY_TTL)
# symbols_cache = TTLCache(maxsize=1, ttl=SYMBOLS_TTL)
# os.makedirs(HISTORY_CACHE_DIR, exist_ok=True)

# # ----------------------------
# # UTILITIES
# # ----------------------------
# def validate_cache(file_path, expected_columns):
#     if not os.path.exists(file_path):
#         return False
#     try:
#         df = pd.read_parquet(file_path)
#         if not all(col in df.columns for col in expected_columns):
#             return False
#         return True
#     except Exception:
#         return False

# def clear_corrupted_cache(file_path):
#     if os.path.exists(file_path):
#         os.remove(file_path)

# def log_retry(retry_state):
#     exc = retry_state.outcome.exception() if retry_state.outcome else None
#     logging.warning(f"Retry attempt {retry_state.attempt_number} due to {exc}")

# # ----------------------------
# # FETCH SYMBOLS
# # ----------------------------
# @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30),
#        retry=retry_if_exception_type(requests.RequestException), after=log_retry)
# def fetch_cboe_symbols():
#     cache_key = "cboe_symbols"
#     if cache_key in symbols_cache:
#         return symbols_cache[cache_key]

#     resp = requests.get(CBOE_URL, timeout=30)
#     resp.raise_for_status()
#     df = pd.read_csv(io.StringIO(resp.text))
#     ticker_col = next((c for c in df.columns if "symbol" in c.lower() or "root" in c.lower()), None)
#     if not ticker_col:
#         raise ValueError(f"No symbol column found. Columns: {list(df.columns)}")
#     df = df[[ticker_col]].rename(columns={ticker_col: "symbol"})
#     df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
#     df = df.drop_duplicates().assign(updated_at=datetime.utcnow().isoformat(), schema_version=SCHEMA_VERSION)
#     symbols_cache[cache_key] = df
#     return df

# def load_existing_symbols():
#     if validate_cache(PARQUET_FILE, ["symbol", "updated_at", "schema_version"]):
#         try:
#             df = pd.read_parquet(PARQUET_FILE)
#             if df["schema_version"].iloc[0] == SCHEMA_VERSION:
#                 return df
#         except Exception:
#             pass
#     clear_corrupted_cache(PARQUET_FILE)
#     return pd.DataFrame(columns=["symbol", "updated_at", "schema_version"])

# def update_symbols():
#     existing_df = load_existing_symbols()
#     if not existing_df.empty and (datetime.utcnow() - pd.to_datetime(existing_df["updated_at"].iloc[0])).total_seconds() < SYMBOLS_TTL:
#         return existing_df
#     try:
#         df = fetch_cboe_symbols()
#     except Exception:
#         return existing_df if not existing_df.empty else pd.DataFrame(columns=["symbol", "updated_at", "schema_version"])
#     new_df = df[~df["symbol"].isin(existing_df["symbol"])].copy()
#     if not new_df.empty:
#         new_df["updated_at"] = datetime.utcnow().isoformat()
#         new_df["schema_version"] = SCHEMA_VERSION
#     combined_df = pd.concat([existing_df, new_df], ignore_index=True).drop_duplicates(subset="symbol", keep="last")
#     tmp_file = PARQUET_FILE + ".tmp"
#     combined_df.to_parquet(tmp_file, index=False)
#     os.replace(tmp_file, PARQUET_FILE)
#     return combined_df

# # ----------------------------
# # FETCH HISTORICAL DATA
# # ----------------------------
# @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=60),
#        retry=retry_if_exception_type(Exception), after=log_retry)
# def fetch_historical_data(symbol):
#     cache_key = f"{symbol}_history"
#     cache_file = os.path.join(HISTORY_CACHE_DIR, f"{symbol}.parquet")

#     if cache_key in history_cache:
#         return history_cache[cache_key]

#     if validate_cache(cache_file, ["Open", "High", "Low", "Close", "Volume"]):
#         try:
#             data = pd.read_parquet(cache_file)
#             history_cache[cache_key] = data
#             return data
#         except Exception:
#             clear_corrupted_cache(cache_file)

#     ticker = yf.Ticker(symbol)
#     data = ticker.history(period="6mo", interval="1d")
#     if data.empty:
#         return None
#     data["symbol"] = symbol
#     data.to_parquet(cache_file)
#     history_cache[cache_key] = data
#     return data

# # ----------------------------
# # TECHNICAL INDICATOR FUNCTIONS
# # ----------------------------
# def calc_rsi(series, period=14):
#     delta = series.diff()
#     gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
#     loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
#     rs = gain / loss
#     return 100 - (100 / (1 + rs))

# def calc_bb(series, period=20, std_dev=2):
#     sma = series.rolling(window=period).mean()
#     std = series.rolling(window=period).std()
#     upper = sma + (std * std_dev)
#     lower = sma - (std * std_dev)
#     return sma, upper, lower

# def calc_macd(series, fast_period=12, slow_period=26, signal_period=9):
#     ema_fast = series.ewm(span=fast_period, adjust=False).mean()
#     ema_slow = series.ewm(span=slow_period, adjust=False).mean()
#     macd = ema_fast - ema_slow
#     signal = macd.ewm(span=signal_period, adjust=False).mean()
#     hist = macd - signal
#     return macd, signal, hist

# def calc_sma(series, period=50):
#     return series.rolling(window=period).mean()

# def calc_support_resistance(df, lookback=20, tolerance=0.02):
#     highs = df["High"].rolling(lookback).max()
#     lows = df["Low"].rolling(lookback).min()
#     return highs * (1 - tolerance), lows * (1 + tolerance)

# # ----------------------------
# # METRIC COMPUTATION
# # ----------------------------
# def compute_metrics(symbols, min_volume, indicators=None, params=None):
#     results = []
#     for symbol in symbols:
#         hist = fetch_historical_data(symbol)
#         if hist is None or hist.empty:
#             continue
#         avg_volume = hist["Volume"].mean()
#         if avg_volume < min_volume:
#             continue

#         metrics = {"Symbol": symbol, "Avg Volume": avg_volume}

#         # Compute selected indicators
#         close = hist["Close"]
#         if indicators:
#             for ind in indicators:
#                 p = params.get(ind, {})
#                 if ind == "RSI":
#                     metrics["RSI"] = calc_rsi(close, p.get("period", 14)).iloc[-1]
#                 elif ind == "Bollinger Bands (BB)":
#                     sma, upper, lower = calc_bb(close, p.get("period", 20), p.get("std_dev", 2))
#                     metrics.update({"BB_Mid": sma.iloc[-1], "BB_Upper": upper.iloc[-1], "BB_Lower": lower.iloc[-1]})
#                 elif ind == "MACD":
#                     macd, signal, histo = calc_macd(close, p.get("fast_period", 12), p.get("slow_period", 26), p.get("signal_period", 9))
#                     metrics.update({"MACD": macd.iloc[-1], "Signal": signal.iloc[-1], "Hist": histo.iloc[-1]})
#                 elif ind == "SMA":
#                     metrics["SMA"] = calc_sma(close, p.get("period", 50)).iloc[-1]
#                 elif ind == "Support/Resistance":
#                     sup, res = calc_support_resistance(hist, p.get("lookback", 20), p.get("tolerance", 0.02))
#                     metrics.update({"Support": sup.iloc[-1], "Resistance": res.iloc[-1]})

#         results.append(metrics)
#     return results

# # ----------------------------
# # STREAMLIT APP
# # ----------------------------
# def filter_stocks_tab():
#     st.header("🔍 Filter Stocks")
#     st.subheader("Filter Settings")

#     min_volume = st.number_input("Min Avg Daily Volume", min_value=100000, max_value=2000000, value=500000)

#     # Technical indicator configuration
#     st.subheader("Technical Indicators")
#     indicators = st.multiselect(
#         "Select Indicators",
#         ["RSI", "Bollinger Bands (BB)", "MACD", "SMA", "Support/Resistance"],
#         default=[]
#     )

#     defaults = {
#         "RSI": {"period": 14, "overbought": 70, "oversold": 30},
#         "Bollinger Bands (BB)": {"period": 20, "std_dev": 2},
#         "MACD": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
#         "SMA": {"period": 50},
#         "Support/Resistance": {"lookback": 20, "tolerance": 0.02}
#     }

#     user_params = {}
#     for ind in indicators:
#         st.markdown(f"**{ind} Parameters**")
#         params = {}
#         if ind == "RSI":
#             params["period"] = st.number_input("RSI Period", 1, 50, defaults["RSI"]["period"], key=f"{ind}_period")
#         elif ind == "Bollinger Bands (BB)":
#             params["period"] = st.number_input("BB Period", 5, 100, defaults["Bollinger Bands (BB)"]["period"], key=f"{ind}_period")
#             params["std_dev"] = st.number_input("BB Std Dev", 1.0, 5.0, float(defaults["Bollinger Bands (BB)"]["std_dev"]), key=f"{ind}_std")
#         elif ind == "MACD":
#             params["fast_period"] = st.number_input("Fast EMA", 1, 50, defaults["MACD"]["fast_period"], key=f"{ind}_fast")
#             params["slow_period"] = st.number_input("Slow EMA", 1, 100, defaults["MACD"]["slow_period"], key=f"{ind}_slow")
#             params["signal_period"] = st.number_input("Signal Line", 1, 50, defaults["MACD"]["signal_period"], key=f"{ind}_signal")
#         elif ind == "SMA":
#             params["period"] = st.number_input("SMA Period", 5, 200, defaults["SMA"]["period"], key=f"{ind}_period")
#         elif ind == "Support/Resistance":
#             params["lookback"] = st.number_input("Lookback", 5, 100, defaults["Support/Resistance"]["lookback"], key=f"{ind}_lookback")
#             params["tolerance"] = st.number_input("Tolerance", 0.0, 0.1, float(defaults["Support/Resistance"]["tolerance"]), key=f"{ind}_tol")
#         user_params[ind] = params

#     # Update symbols
#     with st.spinner("Updating CBOE symbol list..."):
#         symbols_df = update_symbols()
#     if symbols_df.empty:
#         st.error("No symbols available.")
#         return

#     st.info(f"Loaded {len(symbols_df)} symbols — scanning...")
#     symbols = symbols_df["symbol"].dropna().unique().tolist()

#     results = []
#     progress = st.progress(0)
#     start_time = time.time()

#     total_batches = math.ceil(len(symbols) / BATCH_SIZE)
#     for i in range(total_batches):
#         batch = symbols[i * BATCH_SIZE:(i + 1) * BATCH_SIZE]
#         batch_results = compute_metrics(batch, min_volume, indicators, user_params)
#         results.extend(batch_results)
#         progress.progress((i + 1) / total_batches)
#     st.success(f"Scan completed in {time.time() - start_time:.1f}s")

#     if not results:
#         st.warning("No results found.")
#         return

#     df = pd.DataFrame(results)
#     st.dataframe(df.head(100), use_container_width=True)
#     st.download_button("Download CSV", df.to_csv(index=False), "filtered_stocks.csv")

# def main():
#     st.set_page_config(page_title="CBOE Stock Screener", layout="wide")
#     st.title("📊 CBOE Stock Screener")
#     filter_stocks_tab()

# if __name__ == "__main__":
#     main()


###### optimize


# #!/usr/bin/env python
# # -*- coding: utf-8 -*-

# """
# CBOE Optionable Stock Screener
# ALL indicators required
# Bull + Bear + Neutral = Valid
# Self-Tuning Speed + Rate-Limit Safe
# """

# import os
# import io
# import time
# import logging
# from datetime import datetime
# from concurrent.futures import ThreadPoolExecutor, as_completed

# import psutil
# import requests
# import pandas as pd
# import numpy as np
# import streamlit as st
# import yfinance as yf
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# # -------------------------------------------------
# # CONFIG
# # -------------------------------------------------
# PARQUET_FILE = "optionable_full.parquet"
# HISTORY_CACHE_DIR = "history_cache"
# CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"

# SCHEMA_VERSION = "6.1"
# HISTORY_TTL = 24 * 3600
# SYMBOLS_TTL = 7 * 24 * 3600

# CPU_COUNT = psutil.cpu_count(logical=False) or 4
# MAX_WORKERS = min(CPU_COUNT, 8)
# INITIAL_BATCH_SIZE = min(CPU_COUNT * 10, 100)

# os.makedirs(HISTORY_CACHE_DIR, exist_ok=True)

# # -------------------------------------------------
# # TUNER (Dynamic Speed)
# # -------------------------------------------------
# class Tuner:
#     def __init__(self):
#         self.rate_limited = 0
#         self.last_rate_limit = 0
#         self.workers = MAX_WORKERS
#         self.batch_size = INITIAL_BATCH_SIZE
#         self.success_streak = 0

#     def record_failure(self):
#         self.rate_limited += 1
#         self.last_rate_limit = time.time()
#         self.success_streak = 0
#         if self.rate_limited > 5:
#             self.workers = 1
#             self.batch_size = max(5, self.batch_size // 2)
#         elif self.rate_limited > 2:
#             self.workers = max(1, self.workers // 2)
#             self.batch_size = max(10, self.batch_size // 2)

#     def record_success(self):
#         self.success_streak += 1
#         if self.success_streak > 20 and self.workers < MAX_WORKERS:
#             self.workers = min(MAX_WORKERS, self.workers + 1)
#             self.batch_size = min(INITIAL_BATCH_SIZE, self.batch_size * 2)

# tuner = Tuner()

# # -------------------------------------------------
# # LOGGING
# # -------------------------------------------------
# logger = logging.getLogger("cboe_corrected")
# logger.setLevel(logging.INFO)
# if not logger.handlers:
#     handler = logging.StreamHandler()
#     handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
#     logger.addHandler(handler)

# # -------------------------------------------------
# # CACHE: AUTO-REPAIR
# # -------------------------------------------------
# def get_cached_history(symbol: str) -> pd.DataFrame | None:
#     path = os.path.join(HISTORY_CACHE_DIR, f"{symbol}.parquet")
#     if not os.path.exists(path):
#         return None
#     try:
#         df = pd.read_parquet(path)
#         req = ["Open", "High", "Low", "Close", "Volume"]
#         if not all(c in df.columns for c in req) or df[req].isna().any().any():
#             raise ValueError("corrupt")
#         if time.time() - os.path.getmtime(path) > HISTORY_TTL:
#             os.remove(path)
#             return None
#         return df
#     except Exception as e:
#         logger.debug(f"Cache corrupted {symbol}: {e} → delete")
#         if os.path.exists(path):
#             os.remove(path)
#         return None

# def cache_history(symbol: str, df: pd.DataFrame):
#     path = os.path.join(HISTORY_CACHE_DIR, f"{symbol}.parquet")
#     try:
#         df.to_parquet(path, index=False)
#     except Exception as e:
#         logger.warning(f"Cache write failed {symbol}: {e}")

# # -------------------------------------------------
# # SYMBOLS
# # -------------------------------------------------
# @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=30),
#        retry=retry_if_exception_type(requests.RequestException))
# def fetch_cboe_symbols() -> pd.DataFrame:
#     logger.info("Fetching CBOE symbol list...")
#     r = requests.get(CBOE_URL, timeout=30)
#     r.raise_for_status()
#     df = pd.read_csv(io.StringIO(r.text))
#     col = next((c for c in df.columns if "symbol" in c.lower() or "root" in c.lower()), None)
#     if not col:
#         raise ValueError("No symbol column")
#     df = df[[col]].rename(columns={col: "symbol"})
#     df["symbol"] = df["symbol"].str.upper().str.strip()
#     df = df.drop_duplicates().assign(
#         updated_at=datetime.utcnow().isoformat(),
#         schema_version=SCHEMA_VERSION
#     )
#     return df

# def update_symbols() -> pd.DataFrame:
#     if os.path.exists(PARQUET_FILE):
#         try:
#             df = pd.read_parquet(PARQUET_FILE)
#             if df["schema_version"].iloc[0] == SCHEMA_VERSION:
#                 age = (datetime.utcnow() - pd.to_datetime(df["updated_at"].iloc[0])).total_seconds()
#                 if age < SYMBOLS_TTL:
#                     logger.info(f"Using cached symbols ({len(df)})")
#                     return df
#         except: pass
#     fresh = fetch_cboe_symbols()
#     tmp = PARQUET_FILE + ".tmp"
#     fresh.to_parquet(tmp, index=False)
#     os.replace(tmp, PARQUET_FILE)
#     logger.info(f"Saved {len(fresh)} symbols")
#     return fresh

# # -------------------------------------------------
# # YFINANCE: RATE-LIMIT AWARE
# # -------------------------------------------------
# @retry(
#     stop=stop_after_attempt(3),
#     wait=wait_exponential(multiplier=2, min=30, max=120),
#     retry=retry_if_exception_type((requests.RequestException, ValueError)),
# )
# def fetch_historical_data(symbol: str) -> pd.DataFrame | None:
#     cached = get_cached_history(symbol)
#     if cached is not None:
#         tuner.record_success()
#         return cached

#     if tuner.rate_limited > 3 and time.time() - tuner.last_rate_limit < 120:
#         logger.info(f"Rate limit pause for {symbol}...")
#         time.sleep(60)

#     try:
#         logger.debug(f"Download {symbol}")
#         data = yf.Ticker(symbol).history(period="6mo", interval="1d", raise_errors=True, timeout=15)
#         if data.empty:
#             return None
#         data["symbol"] = symbol
#         cache_history(symbol, data)
#         time.sleep(0.1)
#         tuner.record_success()
#         return data
#     except Exception as e:
#         if "429" in str(e) or "rate limit" in str(e).lower():
#             tuner.record_failure()
#             logger.warning(f"Rate limited: {symbol}")
#         raise

# # -------------------------------------------------
# # INDICATORS
# # -------------------------------------------------
# def calc_rsi(s, p=14):
#     delta = s.diff()
#     gain = delta.where(delta > 0, 0).rolling(p).mean()
#     loss = -delta.where(delta < 0, 0).rolling(p).mean()
#     rs = gain / loss
#     return 100 - (100 / (1 + rs))

# def calc_sma(s, p=50):
#     return s.rolling(p).mean()

# def calc_bb(s, p=20, sd=2):
#     mid = s.rolling(p).mean()
#     std = s.rolling(p).std()
#     upper = mid + std * sd
#     lower = mid - std * sd
#     return mid, upper, lower

# def calc_macd(s, fast=12, slow=26, signal=9):
#     ema_fast = s.ewm(span=fast, adjust=False).mean()
#     ema_slow = s.ewm(span=slow, adjust=False).mean()
#     macd_line = ema_fast - ema_slow
#     signal_line = macd_line.ewm(span=signal, adjust=False).mean()
#     hist = macd_line - signal_line
#     return macd_line, signal_line, hist

# def calc_support_resistance(df: pd.DataFrame, lookback=20, tolerance=0.02):
#     high = df["High"].rolling(lookback).max()
#     low = df["Low"].rolling(lookback).min()
#     support = low * (1 + tolerance)
#     resistance = high * (1 - tolerance)
#     return support, resistance

# # -------------------------------------------------
# # SINGLE SYMBOL: ALL INDICATORS MUST BE PRESENT
# # -------------------------------------------------
# def compute_one(symbol: str, min_vol: int, inds: list, params: dict) -> dict | None:
#     try:
#         hist = fetch_historical_data(symbol)
#     except:
#         return None
#     if hist is None or hist.empty:
#         return None
#     vol = hist["Volume"].mean()
#     if vol < min_vol:
#         return None

#     row = {"Symbol": symbol, "Avg Volume": vol}
#     close = hist["Close"]

#     # Compute ALL requested indicators
#     for i in inds:
#         p = params.get(i, {})
#         try:
#             if i == "RSI":
#                 row["RSI"] = calc_rsi(close, p.get("period", 14)).iloc[-1]
#             elif i == "SMA":
#                 row["SMA"] = calc_sma(close, p.get("period", 50)).iloc[-1]
#             elif i == "Bollinger Bands (BB)":
#                 mid, upper, lower = calc_bb(close, p.get("period", 20), p.get("std_dev", 2))
#                 row["BB_Mid"] = mid.iloc[-1]
#                 row["BB_Upper"] = upper.iloc[-1]
#                 row["BB_Lower"] = lower.iloc[-1]
#             elif i == "MACD":
#                 macd, sig, hist = calc_macd(close, p.get("fast", 12), p.get("slow", 26), p.get("signal", 9))
#                 row["MACD"] = macd.iloc[-1]
#                 row["Signal"] = sig.iloc[-1]
#                 row["Hist"] = hist.iloc[-1]
#             elif i == "Support/Resistance":
#                 sup, res = calc_support_resistance(hist, p.get("lookback", 20), p.get("tolerance", 0.02))
#                 row["Support"] = sup.iloc[-1]
#                 row["Resistance"] = res.iloc[-1]
#         except Exception as e:
#             logger.debug(f"Indicator {i} failed for {symbol}: {e}")
#             return None  # Skip if ANY indicator fails

#     return row

# # -------------------------------------------------
# # BULL/BEAR/NEUTRAL CLASSIFIER (CORRECTED)
# # -------------------------------------------------
# def classify_bull_bear(df: pd.DataFrame, inds: list) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
#     if df.empty:
#         return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

#     bull = []
#     bear = []
#     neutral = []

#     for _, row in df.iterrows():
#         close = row.get("Close", np.nan)
#         if pd.isna(close):
#             close = row.get("BB_Mid", row.get("SMA", np.nan))

#         bull_signals = 0
#         bear_signals = 0
#         total_signals = 0

#         if "RSI" in inds and "RSI" in row:
#             total_signals += 1
#             if row["RSI"] > 50: bull_signals += 1
#             if row["RSI"] < 50: bear_signals += 1

#         if "SMA" in inds and "SMA" in row:
#             total_signals += 1
#             if close > row["SMA"]: bull_signals += 1
#             if close < row["SMA"]: bear_signals += 1

#         if "Bollinger Bands (BB)" in inds and "BB_Lower" in row and "BB_Upper" in row:
#             total_signals += 1
#             if close > row["BB_Lower"]: bull_signals += 1
#             if close < row["BB_Upper"]: bear_signals += 1

#         if "MACD" in inds and "MACD" in row and "Signal" in row:
#             total_signals += 1
#             if row["MACD"] > row["Signal"]: bull_signals += 1
#             if row["MACD"] < row["Signal"]: bear_signals += 1

#         if "Support/Resistance" in inds and "Support" in row and "Resistance" in row:
#             total_signals += 1
#             if close > row["Support"]: bull_signals += 1
#             if close < row["Resistance"]: bear_signals += 1

#         # Decision
#         if total_signals == 0:
#             neutral.append(row)
#         elif bull_signals == total_signals:
#             bull.append(row)
#         elif bear_signals == total_signals:
#             bear.append(row)
#         else:
#             neutral.append(row)

#     bull_df = pd.DataFrame(bull)
#     bear_df = pd.DataFrame(bear)
#     neutral_df = pd.DataFrame(neutral)

#     return bull_df, bear_df, neutral_df

# # -------------------------------------------------
# # PARALLEL DRIVER
# # -------------------------------------------------
# def compute_parallel(symbols: list, min_vol: int, inds: list, params: dict) -> list:
#     results = []
#     batch_size = tuner.batch_size
#     batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]

#     with ThreadPoolExecutor(max_workers=tuner.workers) as pool:
#         futures = [
#             pool.submit(lambda b: [compute_one(s, min_vol, inds, params) for s in b], batch)
#             for batch in batches
#         ]
#         prog = st.progress(0)
#         status = st.empty()
#         for i, future in enumerate(as_completed(futures), 1):
#             batch_res = future.result()
#             valid = [r for r in batch_res if r is not None]
#             results.extend(valid)
#             prog.progress(i / len(futures))
#             status.text(
#                 f"Workers: {tuner.workers} | Batch: {batch_size} | "
#                 f"Rate Limits: {tuner.rate_limited} | Valid: {len(results)}"
#             )
#     return results

# # -------------------------------------------------
# # UI
# # -------------------------------------------------
# def main():
#     st.set_page_config(page_title="CBOE Screener", layout="wide")
#     st.title("CBOE Optionable Stock Screener")
#     st.caption("**ALL indicators required** – Bull + Bear + Neutral = Valid")

#     # --- Settings ---
#     col1, col2 = st.columns(2)
#     with col1:
#         min_vol = st.number_input("Min Avg Daily Volume", 100_000, 5_000_000, 500_000, 50_000)
#     with col2:
#         dry_run = st.checkbox("Dry Run (first 30 symbols)", value=True)

#     # --- Indicators ---
#     st.subheader("Technical Indicators (ALL must compute)")
#     all_inds = ["RSI", "SMA", "Bollinger Bands (BB)", "MACD", "Support/Resistance"]
#     selected = st.multiselect("Select", all_inds, default=[])

#     params = {}
#     for i in selected:
#         with st.expander(i, expanded=True):
#             if i == "RSI":
#                 params[i] = {"period": st.slider("Period", 5, 50, 14, key="rsi_p")}
#             elif i == "SMA":
#                 params[i] = {"period": st.slider("Period", 10, 200, 50, key="sma_p")}
#             elif i == "Bollinger Bands (BB)":
#                 p1 = st.slider("Period", 10, 50, 20, key="bb_p")
#                 p2 = st.slider("Std Dev", 1.0, 3.0, 2.0, 0.1, key="bb_sd")
#                 params[i] = {"period": p1, "std_dev": p2}
#             elif i == "MACD":
#                 f = st.slider("Fast EMA", 5, 30, 12, key="macd_f")
#                 s = st.slider("Slow EMA", 20, 50, 26, key="macd_s")
#                 sig = st.slider("Signal EMA", 5, 20, 9, key="macd_sig")
#                 params[i] = {"fast": f, "slow": s, "signal": sig}
#             elif i == "Support/Resistance":
#                 lb = st.slider("Lookback", 10, 60, 20, key="sr_lb")
#                 tol = st.slider("Tolerance (%)", 0.0, 10.0, 2.0, 0.1, key="sr_tol") / 100
#                 params[i] = {"lookback": lb, "tolerance": tol}

#     # --- Load Symbols ---
#     with st.spinner("Loading CBOE symbols..."):
#         sym_df = update_symbols()
#     symbols = sym_df["symbol"].dropna().unique().tolist()
#     if dry_run:
#         symbols = symbols[:30]
#         st.info(f"**Dry Run**: Scanning **{len(symbols)}** symbols")
#     else:
#         st.info(f"Scanning **{len(symbols):,}** symbols")

#     # --- Run ---
#     if st.button("Start Scan", type="primary"):
#         tuner.__init__()  # reset
#         start = time.time()
#         with st.spinner("Scanning..."):
#             results = compute_parallel(symbols, min_vol, selected, params)
#         elapsed = time.time() - start

#         if not results:
#             st.warning("No stocks passed ALL indicator checks.")
#             return

#         df = pd.DataFrame(results).round(3)
#         if "Avg Volume" in df.columns:
#             df["Avg Volume"] = df["Avg Volume"].apply(lambda x: f"{x:,.0f}")

#         # Add current close price
#         close_prices = {}
#         for sym in df["Symbol"]:
#             try:
#                 close_prices[sym] = yf.Ticker(sym).history(period="1d")["Close"].iloc[-1]
#             except:
#                 close_prices[sym] = np.nan
#         df["Close"] = df["Symbol"].map(close_prices)

#         # Split Bull / Bear / Neutral
#         bull_df, bear_df, neutral_df = classify_bull_bear(df, selected)

#         st.success(
#             f"**Done in {elapsed:.1f}s** – "
#             f"{len(df)} valid | "
#             f"{len(bull_df)} bull | "
#             f"{len(bear_df)} bear | "
#             f"{len(neutral_df)} neutral"
#         )

#         # --- Display ---
#         if not bull_df.empty:
#             st.subheader("Bullish Signals (All indicators agree)")
#             st.dataframe(bull_df.head(100), use_container_width=True)
#             csv_bull = bull_df.to_csv(index=False).encode()
#             st.download_button("Download Bullish", csv_bull, "bullish.csv", "text/csv")

#         if not bear_df.empty:
#             st.subheader("Bearish Signals (All indicators agree)")
#             st.dataframe(bear_df.head(100), use_container_width=True)
#             csv_bear = bear_df.to_csv(index=False).encode()
#             st.download_button("Download Bearish", csv_bear, "bearish.csv", "text/csv")

#         if not neutral_df.empty:
#             st.subheader("Neutral / Mixed Signals")
#             st.dataframe(neutral_df.head(100), use_container_width=True)
#             csv_neutral = neutral_df.to_csv(index=False).encode()
#             st.download_button("Download Neutral", csv_neutral, "neutral.csv", "text/csv")

#         if bull_df.empty and bear_df.empty:
#             st.info("No strong bull/bear signals.")

#         st.info(f"**Tuner**: Workers: {tuner.workers}, Batch: {tuner.batch_size}, Rate Limits: {tuner.rate_limited}")

#     # --- Cache Clear ---
#     if st.button("Clear Cache & Restart"):
#         import shutil
#         if os.path.exists(HISTORY_CACHE_DIR):
#             shutil.rmtree(HISTORY_CACHE_DIR)
#         if os.path.exists(PARQUET_FILE):
#             os.remove(PARQUET_FILE)
#         st.success("Cache cleared! Reload page.")

# if __name__ == "__main__":
#     main()


##### vectorize


# #!/usr/bin/env python
# # -*- coding: utf-8 -*-

# """
# CBOE Optionable Stock Screener – FINAL VERSION
# - 404-proof (no HTTP Error spam)
# - Fully vectorized
# - Accurate Bull/Bear: ALL indicators must agree
# - Bull + Bear + Neutral = Valid
# - Self-tuning speed
# """

# import os
# import io
# import time
# import logging
# import warnings
# from datetime import datetime
# from concurrent.futures import ThreadPoolExecutor, as_completed

# import psutil
# import requests
# import pandas as pd
# import numpy as np
# import streamlit as st
# import yfinance as yf
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# # -------------------------------------------------
# # CONFIG
# # -------------------------------------------------
# PARQUET_FILE = "optionable_full.parquet"
# HISTORY_CACHE_DIR = "history_cache"
# CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"

# SCHEMA_VERSION = "9.0"
# HISTORY_TTL = 24 * 3600
# SYMBOLS_TTL = 7 * 24 * 3600

# CPU_COUNT = psutil.cpu_count(logical=False) or 4
# MAX_WORKERS = min(CPU_COUNT, 8)
# INITIAL_BATCH_SIZE = min(CPU_COUNT * 20, 200)

# os.makedirs(HISTORY_CACHE_DIR, exist_ok=True)

# # -------------------------------------------------
# # SILENCE YFINANCE 404s
# # -------------------------------------------------
# class YFinanceFilter:
#     def __enter__(self):
#         self.original_filters = warnings.filters[:]
#         warnings.filterwarnings("ignore", category=UserWarning, module="yfinance")
#         return self
#     def __exit__(self, exc_type, exc_val, exc_tb):
#         warnings.filters = self.original_filters

# def yf_safe_history(symbol: str, **kwargs):
#     with YFinanceFilter():
#         try:
#             return yf.Ticker(symbol).history(**kwargs)
#         except:
#             return pd.DataFrame()

# # -------------------------------------------------
# # TUNER (Dynamic Speed)
# # -------------------------------------------------
# class Tuner:
#     def __init__(self):
#         self.rate_limited = 0
#         self.last_rate_limit = 0
#         self.workers = MAX_WORKERS
#         self.batch_size = INITIAL_BATCH_SIZE
#         self.success_streak = 0

#     def record_failure(self):
#         self.rate_limited += 1
#         self.last_rate_limit = time.time()
#         self.success_streak = 0
#         if self.rate_limited > 5:
#             self.workers = 1
#             self.batch_size = max(10, self.batch_size // 2)
#         elif self.rate_limited > 2:
#             self.workers = max(1, self.workers // 2)
#             self.batch_size = max(20, self.batch_size // 2)

#     def record_success(self):
#         self.success_streak += 1
#         if self.success_streak > 30 and self.workers < MAX_WORKERS:
#             self.workers = min(MAX_WORKERS, self.workers + 1)
#             self.batch_size = min(INITIAL_BATCH_SIZE, self.batch_size * 2)

# tuner = Tuner()

# # -------------------------------------------------
# # LOGGING (quiet)
# # -------------------------------------------------
# logger = logging.getLogger("cboe_final")
# logger.setLevel(logging.WARNING)
# handler = logging.StreamHandler()
# handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
# logger.addHandler(handler)

# # -------------------------------------------------
# # CACHE
# # -------------------------------------------------
# def get_cached_history(symbol: str) -> pd.DataFrame | None:
#     path = os.path.join(HISTORY_CACHE_DIR, f"{symbol}.parquet")
#     if not os.path.exists(path):
#         return None
#     try:
#         df = pd.read_parquet(path)
#         req = ["Open", "High", "Low", "Close", "Volume"]
#         if not all(c in df.columns for c in req) or df[req].isna().any().any():
#             raise ValueError("corrupt")
#         if time.time() - os.path.getmtime(path) > HISTORY_TTL:
#             os.remove(path)
#             return None
#         return df
#     except Exception:
#         if os.path.exists(path):
#             os.remove(path)
#         return None

# def cache_history(symbol: str, df: pd.DataFrame):
#     path = os.path.join(HISTORY_CACHE_DIR, f"{symbol}.parquet")
#     try:
#         df.to_parquet(path, index=False)
#     except Exception:
#         pass

# # -------------------------------------------------
# # SYMBOLS
# # -------------------------------------------------
# @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=30))
# def fetch_cboe_symbols() -> pd.DataFrame:
#     r = requests.get(CBOE_URL, timeout=30)
#     r.raise_for_status()
#     df = pd.read_csv(io.StringIO(r.text))
#     col = next((c for c in df.columns if "symbol" in c.lower() or "root" in c.lower()), None)
#     if not col:
#         raise ValueError("No symbol column")
#     df = df[[col]].rename(columns={col: "symbol"})
#     df["symbol"] = df["symbol"].str.upper().str.strip()
#     df = df.drop_duplicates().assign(
#         updated_at=datetime.utcnow().isoformat(),
#         schema_version=SCHEMA_VERSION
#     )
#     return df

# def update_symbols() -> pd.DataFrame:
#     if os.path.exists(PARQUET_FILE):
#         try:
#             df = pd.read_parquet(PARQUET_FILE)
#             if df["schema_version"].iloc[0] == SCHEMA_VERSION:
#                 age = (datetime.utcnow() - pd.to_datetime(df["updated_at"].iloc[0])).total_seconds()
#                 if age < SYMBOLS_TTL:
#                     return df
#         except: pass
#     fresh = fetch_cboe_symbols()
#     tmp = PARQUET_FILE + ".tmp"
#     fresh.to_parquet(tmp, index=False)
#     os.replace(tmp, PARQUET_FILE)
#     return fresh

# # -------------------------------------------------
# # YFINANCE – 404-safe
# # -------------------------------------------------
# @retry(
#     stop=stop_after_attempt(3),
#     wait=wait_exponential(multiplier=2, min=30, max=120),
#     retry=retry_if_exception_type((requests.RequestException, ValueError)),
# )
# def fetch_historical_data(symbol: str) -> pd.DataFrame | None:
#     cached = get_cached_history(symbol)
#     if cached is not None:
#         tuner.record_success()
#         return cached

#     if tuner.rate_limited > 3 and time.time() - tuner.last_rate_limit < 120:
#         time.sleep(60)

#     try:
#         data = yf_safe_history(symbol, period="6mo", interval="1d", raise_errors=True, timeout=15)
#         if data.empty:
#             return None
#         data = data.reset_index()
#         data["symbol"] = symbol
#         cache_history(symbol, data)
#         time.sleep(0.08)
#         tuner.record_success()
#         return data
#     except Exception as e:
#         if "429" in str(e) or "rate limit" in str(e).lower():
#             tuner.record_failure()
#             logger.warning(f"Rate limited: {symbol}")
#         return None

# # -------------------------------------------------
# # VECTORIZED INDICATORS
# # -------------------------------------------------
# def compute_indicators_vectorized(df: pd.DataFrame, inds: list, params: dict) -> pd.DataFrame:
#     if df.empty:
#         return pd.DataFrame()

#     close = df["Close"]
#     high = df["High"]
#     low = df["Low"]

#     out = pd.DataFrame(index=df.index)

#     if "RSI" in inds:
#         p = params["RSI"]["period"]
#         delta = close.diff()
#         gain = delta.clip(lower=0)
#         loss = -delta.clip(upper=0)
#         avg_gain = gain.rolling(p, min_periods=p).mean()
#         avg_loss = loss.rolling(p, min_periods=p).mean()
#         rs = avg_gain / avg_loss
#         out["RSI"] = 100 - (100 / (1 + rs))

#     if "SMA" in inds:
#         p = params["SMA"]["period"]
#         out["SMA"] = close.rolling(p, min_periods=p).mean()

#     if "Bollinger Bands (BB)" in inds:
#         p = params["Bollinger Bands (BB)"]["period"]
#         sd = params["Bollinger Bands (BB)"]["std_dev"]
#         mid = close.rolling(p, min_periods=p).mean()
#         std = close.rolling(p, min_periods=p).std()
#         out["BB_Mid"] = mid
#         out["BB_Upper"] = mid + std * sd
#         out["BB_Lower"] = mid - std * sd

#     if "MACD" in inds:
#         fast = params["MACD"]["fast"]
#         slow = params["MACD"]["slow"]
#         sig = params["MACD"]["signal"]
#         ema_fast = close.ewm(span=fast, adjust=False).mean()
#         ema_slow = close.ewm(span=slow, adjust=False).mean()
#         macd_line = ema_fast - ema_slow
#         signal_line = macd_line.ewm(span=sig, adjust=False).mean()
#         out["MACD"] = macd_line
#         out["Signal"] = signal_line
#         out["Hist"] = macd_line - signal_line

#     if "Support/Resistance" in inds:
#         lb = params["Support/Resistance"]["lookback"]
#         tol = params["Support/Resistance"]["tolerance"]
#         sup = low.rolling(lb, min_periods=lb).min() * (1 + tol)
#         res = high.rolling(lb, min_periods=lb).max() * (1 - tol)
#         out["Support"] = sup
#         out["Resistance"] = res

#     last = out.groupby(df["symbol"]).tail(1).reset_index(drop=True)
#     last["symbol"] = df["symbol"].groupby(df["symbol"]).tail(1).values
#     last["Avg Volume"] = df["Volume"].groupby(df["symbol"]).mean().values

#     return last

# # -------------------------------------------------
# # BATCH PROCESSOR
# # -------------------------------------------------
# def process_batch(symbols: list, min_vol: int, inds: list, params: dict) -> pd.DataFrame:
#     data_frames = []
#     for sym in symbols:
#         hist = fetch_historical_data(sym)
#         if hist is not None and len(hist) >= 100:
#             data_frames.append(hist)

#     if not data_frames:
#         return pd.DataFrame()

#     df = pd.concat(data_frames, ignore_index=True)

#     vol_mean = df.groupby("symbol")["Volume"].mean()
#     valid_symbols = vol_mean[vol_mean >= min_vol].index
#     df = df[df["symbol"].isin(valid_symbols)]
#     if df.empty:
#         return pd.DataFrame()

#     return compute_indicators_vectorized(df, inds, params)

# # -------------------------------------------------
# # PARALLEL DRIVER
# # -------------------------------------------------
# def compute_parallel(symbols: list, min_vol: int, inds: list, params: dict) -> pd.DataFrame:
#     batch_size = tuner.batch_size
#     batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
#     results = []

#     with ThreadPoolExecutor(max_workers=tuner.workers) as pool:
#         futures = [pool.submit(process_batch, b, min_vol, inds, params) for b in batches]
#         prog = st.progress(0)
#         status = st.empty()
#         for i, f in enumerate(as_completed(futures), 1):
#             batch_res = f.result()
#             if not batch_res.empty:
#                 results.append(batch_res)
#             prog.progress(i / len(futures))
#             status.text(
#                 f"Workers: {tuner.workers} | Batch: {batch_size} | "
#                 f"Valid: {sum(len(r) for r in results)}"
#             )

#     return pd.concat(results, ignore_index=True) if results else pd.DataFrame()

# # -------------------------------------------------
# # CLASSIFIER – ACCURATE BULL/BEAR (ALL INDICATORS MUST AGREE)
# # -------------------------------------------------
# def classify_bull_bear(df: pd.DataFrame, inds: list):
#     if df.empty:
#         return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

#     close = df.get("Close")
#     if close is None or close.isna().all():
#         close = df.get("BB_Mid", df.get("SMA", np.nan))
#     close = pd.to_numeric(close, errors='coerce')

#     total_indicators = len(inds)
#     bull_count = pd.Series(0, index=df.index)
#     bear_count = pd.Series(0, index=df.index)

#     if "RSI" in inds and "RSI" in df.columns:
#         bull_count += (df["RSI"] > 50).astype(int)
#         bear_count += (df["RSI"] < 50).astype(int)

#     if "SMA" in inds and "SMA" in df.columns:
#         bull_count += (close > df["SMA"]).astype(int)
#         bear_count += (close < df["SMA"]).astype(int)

#     if "Bollinger Bands (BB)" in inds and "BB_Lower" in df.columns and "BB_Upper" in df.columns:
#         bull_count += (close > df["BB_Lower"]).astype(int)
#         bear_count += (close < df["BB_Upper"]).astype(int)

#     if "MACD" in inds and "MACD" in df.columns and "Signal" in df.columns:
#         bull_count += (df["MACD"] > df["Signal"]).astype(int)
#         bear_count += (df["MACD"] < df["Signal"]).astype(int)

#     if "Support/Resistance" in inds and "Support" in df.columns and "Resistance" in df.columns:
#         bull_count += (close > df["Support"]).astype(int)
#         bear_count += (close < df["Resistance"]).astype(int)

#     bull_mask = (bull_count == total_indicators) & (total_indicators > 0)
#     bear_mask = (bear_count == total_indicators) & (total_indicators > 0)
#     neutral_mask = ~(bull_mask | bear_mask)

#     return (
#         df[bull_mask].copy(),
#         df[bear_mask].copy(),
#         df[neutral_mask].copy()
#     )

# # -------------------------------------------------
# # UI
# # -------------------------------------------------
# def main():
#     st.set_page_config(page_title="CBOE Screener", layout="wide")
#     st.title("CBOE Optionable Stock Screener")
#     st.caption("**404-proof, vectorized, Bull + Bear + Neutral = Valid**")

#     col1, col2 = st.columns(2)
#     with col1:
#         min_vol = st.number_input("Min Avg Daily Volume", 100_000, 5_000_000, 500_000, 50_000)
#     with col2:
#         dry_run = st.checkbox("Dry Run (first 30 symbols)", value=True)

#     st.subheader("Technical Indicators")
#     all_inds = ["RSI", "SMA", "Bollinger Bands (BB)", "MACD", "Support/Resistance"]
#     selected = st.multiselect("Select", all_inds, default=[])

#     params = {}
#     for i in selected:
#         with st.expander(i, expanded=True):
#             if i == "RSI":
#                 params[i] = {"period": st.slider("Period", 5, 50, 14, key="rsi_p")}
#             elif i == "SMA":
#                 params[i] = {"period": st.slider("Period", 10, 200, 50, key="sma_p")}
#             elif i == "Bollinger Bands (BB)":
#                 p1 = st.slider("Period", 10, 50, 20, key="bb_p")
#                 p2 = st.slider("Std Dev", 1.0, 3.0, 2.0, 0.1, key="bb_sd")
#                 params[i] = {"period": p1, "std_dev": p2}
#             elif i == "MACD":
#                 f = st.slider("Fast EMA", 5, 30, 12, key="macd_f")
#                 s = st.slider("Slow EMA", 20, 50, 26, key="macd_s")
#                 sig = st.slider("Signal EMA", 5, 20, 9, key="macd_sig")
#                 params[i] = {"fast": f, "slow": s, "signal": sig}
#             elif i == "Support/Resistance":
#                 lb = st.slider("Lookback", 10, 60, 20, key="sr_lb")
#                 tol = st.slider("Tolerance (%)", 0.0, 10.0, 2.0, 0.1, key="sr_tol") / 100
#                 params[i] = {"lookback": lb, "tolerance": tol}

#     with st.spinner("Loading symbols..."):
#         sym_df = update_symbols()
#     symbols = sym_df["symbol"].dropna().unique().tolist()
#     if dry_run:
#         symbols = symbols[:30]
#         st.info(f"**Dry Run**: {len(symbols)} symbols")
#     else:
#         st.info(f"Scanning **{len(symbols):,}** symbols")

#     if st.button("Start Scan", type="primary"):
#         tuner.__init__()
#         start = time.time()
#         with st.spinner("Scanning..."):
#             df = compute_parallel(symbols, min_vol, selected, params)
#         elapsed = time.time() - start

#         if df.empty:
#             st.warning("No valid stocks.")
#             return

#         # Live close
#         closes = {}
#         for sym in df["symbol"]:
#             hist = yf_safe_history(sym, period="1d")
#             closes[sym] = hist["Close"].iloc[-1] if not hist.empty else np.nan
#         df["Close"] = df["symbol"].map(closes)

#         df["Avg Volume"] = df["Avg Volume"].apply(lambda x: f"{x:,.0f}")

#         bull_df, bear_df, neutral_df = classify_bull_bear(df, selected)

#         total = len(bull_df) + len(bear_df) + len(neutral_df)
#         st.success(
#             f"**Done in {elapsed:.1f}s** – "
#             f"{len(df)} valid | "
#             f"**{len(bull_df)} bull** | **{len(bear_df)} bear** | {len(neutral_df)} neutral "
#             f"({total} total)"
#         )

#         if not bull_df.empty:
#             st.subheader("Bullish (All Indicators Agree)")
#             st.dataframe(bull_df.head(100), use_container_width=True)
#             st.download_button("Download Bull", bull_df.to_csv(index=False).encode(), "bull.csv", "text/csv")

#         if not bear_df.empty:
#             st.subheader("Bearish (All Indicators Agree)")
#             st.dataframe(bear_df.head(100), use_container_width=True)
#             st.download_button("Download Bear", bear_df.to_csv(index=False).encode(), "bear.csv", "text/csv")

#         if not neutral_df.empty:
#             st.subheader("Neutral / Mixed")
#             st.dataframe(neutral_df.head(100), use_container_width=True)
#             st.download_button("Download Neutral", neutral_df.to_csv(index=False).encode(), "neutral.csv", "text/csv")

#     if st.button("Clear Cache"):
#         import shutil
#         if os.path.exists(HISTORY_CACHE_DIR):
#             shutil.rmtree(HISTORY_CACHE_DIR)
#         if os.path.exists(PARQUET_FILE):
#             os.remove(PARQUET_FILE)
#         st.success("Cache cleared!")

# if __name__ == "__main__":
#     main()


#### add graph


# #!/usr/bin/env python
# # -*- coding: utf-8 -*-

# """
# CBOE Optionable Stock Screener – FINAL + INTERACTIVE CHARTS
# - 404-proof
# - Fully vectorized
# - Accurate Bull/Bear: ALL indicators agree
# - Bull + Bear + Neutral = Valid
# - Interactive candlestick + indicators
# """

# import os
# import io
# import time
# import logging
# import warnings
# from datetime import datetime
# from concurrent.futures import ThreadPoolExecutor, as_completed

# import psutil
# import requests
# import pandas as pd
# import numpy as np
# import streamlit as st
# import yfinance as yf
# import plotly.graph_objects as go
# from plotly.subplots import make_subplots
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# # -------------------------------------------------
# # CONFIG
# # -------------------------------------------------
# PARQUET_FILE = "optionable_full.parquet"
# HISTORY_CACHE_DIR = "history_cache"
# CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"

# SCHEMA_VERSION = "10.0"
# HISTORY_TTL = 24 * 3600
# SYMBOLS_TTL = 7 * 24 * 3600

# CPU_COUNT = psutil.cpu_count(logical=False) or 4
# MAX_WORKERS = min(CPU_COUNT, 8)
# INITIAL_BATCH_SIZE = min(CPU_COUNT * 20, 200)

# os.makedirs(HISTORY_CACHE_DIR, exist_ok=True)

# # -------------------------------------------------
# # SILENCE YFINANCE 404s
# # -------------------------------------------------
# class YFinanceFilter:
#     def __enter__(self):
#         self.original_filters = warnings.filters[:]
#         warnings.filterwarnings("ignore", category=UserWarning, module="yfinance")
#         return self
#     def __exit__(self, exc_type, exc_val, exc_tb):
#         warnings.filters = self.original_filters

# def yf_safe_history(symbol: str, **kwargs):
#     with YFinanceFilter():
#         try:
#             return yf.Ticker(symbol).history(**kwargs)
#         except:
#             return pd.DataFrame()

# # -------------------------------------------------
# # TUNER
# # -------------------------------------------------
# class Tuner:
#     def __init__(self):
#         self.rate_limited = 0
#         self.last_rate_limit = 0
#         self.workers = MAX_WORKERS
#         self.batch_size = INITIAL_BATCH_SIZE
#         self.success_streak = 0

#     def record_failure(self):
#         self.rate_limited += 1
#         self.last_rate_limit = time.time()
#         self.success_streak = 0
#         if self.rate_limited > 5:
#             self.workers = 1
#             self.batch_size = max(10, self.batch_size // 2)
#         elif self.rate_limited > 2:
#             self.workers = max(1, self.workers // 2)
#             self.batch_size = max(20, self.batch_size // 2)

#     def record_success(self):
#         self.success_streak += 1
#         if self.success_streak > 30 and self.workers < MAX_WORKERS:
#             self.workers = min(MAX_WORKERS, self.workers + 1)
#             self.batch_size = min(INITIAL_BATCH_SIZE, self.batch_size * 2)

# tuner = Tuner()

# # -------------------------------------------------
# # LOGGING
# # -------------------------------------------------
# logger = logging.getLogger("cboe_final")
# logger.setLevel(logging.WARNING)
# handler = logging.StreamHandler()
# handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
# logger.addHandler(handler)

# # -------------------------------------------------
# # CACHE
# # -------------------------------------------------
# def get_cached_history(symbol: str) -> pd.DataFrame | None:
#     path = os.path.join(HISTORY_CACHE_DIR, f"{symbol}.parquet")
#     if not os.path.exists(path):
#         return None
#     try:
#         df = pd.read_parquet(path)
#         req = ["Open", "High", "Low", "Close", "Volume"]
#         if not all(c in df.columns for c in req) or df[req].isna().any().any():
#             raise ValueError("corrupt")
#         if time.time() - os.path.getmtime(path) > HISTORY_TTL:
#             os.remove(path)
#             return None
#         return df
#     except Exception:
#         if os.path.exists(path):
#             os.remove(path)
#         return None

# def cache_history(symbol: str, df: pd.DataFrame):
#     path = os.path.join(HISTORY_CACHE_DIR, f"{symbol}.parquet")
#     try:
#         df.to_parquet(path, index=False)
#     except Exception:
#         pass

# # -------------------------------------------------
# # SYMBOLS
# # -------------------------------------------------
# @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=30))
# def fetch_cboe_symbols() -> pd.DataFrame:
#     r = requests.get(CBOE_URL, timeout=30)
#     r.raise_for_status()
#     df = pd.read_csv(io.StringIO(r.text))
#     col = next((c for c in df.columns if "symbol" in c.lower() or "root" in c.lower()), None)
#     if not col:
#         raise ValueError("No symbol column")
#     df = df[[col]].rename(columns={col: "symbol"})
#     df["symbol"] = df["symbol"].str.upper().str.strip()
#     df = df.drop_duplicates().assign(
#         updated_at=datetime.utcnow().isoformat(),
#         schema_version=SCHEMA_VERSION
#     )
#     return df

# def update_symbols() -> pd.DataFrame:
#     if os.path.exists(PARQUET_FILE):
#         try:
#             df = pd.read_parquet(PARQUET_FILE)
#             if df["schema_version"].iloc[0] == SCHEMA_VERSION:
#                 age = (datetime.utcnow() - pd.to_datetime(df["updated_at"].iloc[0])).total_seconds()
#                 if age < SYMBOLS_TTL:
#                     return df
#         except: pass
#     fresh = fetch_cboe_symbols()
#     tmp = PARQUET_FILE + ".tmp"
#     fresh.to_parquet(tmp, index=False)
#     os.replace(tmp, PARQUET_FILE)
#     return fresh

# # -------------------------------------------------
# # YFINANCE
# # -------------------------------------------------
# @retry(
#     stop=stop_after_attempt(3),
#     wait=wait_exponential(multiplier=2, min=30, max=120),
#     retry=retry_if_exception_type((requests.RequestException, ValueError)),
# )
# def fetch_historical_data(symbol: str) -> pd.DataFrame | None:
#     cached = get_cached_history(symbol)
#     if cached is not None:
#         tuner.record_success()
#         return cached

#     if tuner.rate_limited > 3 and time.time() - tuner.last_rate_limit < 120:
#         time.sleep(60)

#     try:
#         data = yf_safe_history(symbol, period="6mo", interval="1d", raise_errors=True, timeout=15)
#         if data.empty:
#             return None
#         data = data.reset_index()
#         data["symbol"] = symbol
#         cache_history(symbol, data)
#         time.sleep(0.08)
#         tuner.record_success()
#         return data
#     except Exception as e:
#         if "429" in str(e) or "rate limit" in str(e).lower():
#             tuner.record_failure()
#             logger.warning(f"Rate limited: {symbol}")
#         return None

# # -------------------------------------------------
# # VECTORIZED INDICATORS
# # -------------------------------------------------
# def compute_indicators_vectorized(df: pd.DataFrame, inds: list, params: dict) -> pd.DataFrame:
#     if df.empty:
#         return pd.DataFrame()

#     close = df["Close"]
#     high = df["High"]
#     low = df["Low"]

#     out = pd.DataFrame(index=df.index)

#     if "RSI" in inds:
#         p = params["RSI"]["period"]
#         delta = close.diff()
#         gain = delta.clip(lower=0)
#         loss = -delta.clip(upper=0)
#         avg_gain = gain.rolling(p, min_periods=p).mean()
#         avg_loss = loss.rolling(p, min_periods=p).mean()
#         rs = avg_gain / avg_loss
#         out["RSI"] = 100 - (100 / (1 + rs))

#     if "SMA" in inds:
#         p = params["SMA"]["period"]
#         out["SMA"] = close.rolling(p, min_periods=p).mean()

#     if "Bollinger Bands (BB)" in inds:
#         p = params["Bollinger Bands (BB)"]["period"]
#         sd = params["Bollinger Bands (BB)"]["std_dev"]
#         mid = close.rolling(p, min_periods=p).mean()
#         std = close.rolling(p, min_periods=p).std()
#         out["BB_Mid"] = mid
#         out["BB_Upper"] = mid + std * sd
#         out["BB_Lower"] = mid - std * sd

#     if "MACD" in inds:
#         fast = params["MACD"]["fast"]
#         slow = params["MACD"]["slow"]
#         sig = params["MACD"]["signal"]
#         ema_fast = close.ewm(span=fast, adjust=False).mean()
#         ema_slow = close.ewm(span=slow, adjust=False).mean()
#         macd_line = ema_fast - ema_slow
#         signal_line = macd_line.ewm(span=sig, adjust=False).mean()
#         out["MACD"] = macd_line
#         out["Signal"] = signal_line
#         out["Hist"] = macd_line - signal_line

#     if "Support/Resistance" in inds:
#         lb = params["Support/Resistance"]["lookback"]
#         tol = params["Support/Resistance"]["tolerance"]
#         sup = low.rolling(lb, min_periods=lb).min() * (1 + tol)
#         res = high.rolling(lb, min_periods=lb).max() * (1 - tol)
#         out["Support"] = sup
#         out["Resistance"] = res

#     last = out.groupby(df["symbol"]).tail(1).reset_index(drop=True)
#     last["symbol"] = df["symbol"].groupby(df["symbol"]).tail(1).values
#     last["Avg Volume"] = df["Volume"].groupby(df["symbol"]).mean().values

#     return last

# # -------------------------------------------------
# # BATCH PROCESSOR
# # -------------------------------------------------
# def process_batch(symbols: list, min_vol: int, inds: list, params: dict) -> pd.DataFrame:
#     data_frames = []
#     for sym in symbols:
#         hist = fetch_historical_data(sym)
#         if hist is not None and len(hist) >= 100:
#             data_frames.append(hist)

#     if not data_frames:
#         return pd.DataFrame()

#     df = pd.concat(data_frames, ignore_index=True)

#     vol_mean = df.groupby("symbol")["Volume"].mean()
#     valid_symbols = vol_mean[vol_mean >= min_vol].index
#     df = df[df["symbol"].isin(valid_symbols)]
#     if df.empty:
#         return pd.DataFrame()

#     return compute_indicators_vectorized(df, inds, params)

# # -------------------------------------------------
# # PARALLEL DRIVER
# # -------------------------------------------------
# def compute_parallel(symbols: list, min_vol: int, inds: list, params: dict) -> pd.DataFrame:
#     batch_size = tuner.batch_size
#     batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
#     results = []

#     with ThreadPoolExecutor(max_workers=tuner.workers) as pool:
#         futures = [pool.submit(process_batch, b, min_vol, inds, params) for b in batches]
#         prog = st.progress(0)
#         status = st.empty()
#         for i, f in enumerate(as_completed(futures), 1):
#             batch_res = f.result()
#             if not batch_res.empty:
#                 results.append(batch_res)
#             prog.progress(i / len(futures))
#             status.text(
#                 f"Workers: {tuner.workers} | Batch: {batch_size} | "
#                 f"Valid: {sum(len(r) for r in results)}"
#             )

#     return pd.concat(results, ignore_index=True) if results else pd.DataFrame()

# # -------------------------------------------------
# # CLASSIFIER – ALL INDICATORS AGREE
# # -------------------------------------------------
# def classify_bull_bear(df: pd.DataFrame, inds: list):
#     if df.empty:
#         return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

#     close = df.get("Close")
#     if close is None or close.isna().all():
#         close = df.get("BB_Mid", df.get("SMA", np.nan))
#     close = pd.to_numeric(close, errors='coerce')

#     total_indicators = len(inds)
#     bull_count = pd.Series(0, index=df.index)
#     bear_count = pd.Series(0, index=df.index)

#     if "RSI" in inds and "RSI" in df.columns:
#         bull_count += (df["RSI"] > 50).astype(int)
#         bear_count += (df["RSI"] < 50).astype(int)

#     if "SMA" in inds and "SMA" in df.columns:
#         bull_count += (close > df["SMA"]).astype(int)
#         bear_count += (close < df["SMA"]).astype(int)

#     if "Bollinger Bands (BB)" in inds and "BB_Lower" in df.columns and "BB_Upper" in df.columns:
#         bull_count += (close > df["BB_Lower"]).astype(int)
#         bear_count += (close < df["BB_Upper"]).astype(int)

#     if "MACD" in inds and "MACD" in df.columns and "Signal" in df.columns:
#         bull_count += (df["MACD"] > df["Signal"]).astype(int)
#         bear_count += (df["MACD"] < df["Signal"]).astype(int)

#     if "Support/Resistance" in inds and "Support" in df.columns and "Resistance" in df.columns:
#         bull_count += (close > df["Support"]).astype(int)
#         bear_count += (close < df["Resistance"]).astype(int)

#     bull_mask = (bull_count == total_indicators) & (total_indicators > 0)
#     bear_mask = (bear_count == total_indicators) & (total_indicators > 0)
#     neutral_mask = ~(bull_mask | bear_mask)

#     return (
#         df[bull_mask].copy(),
#         df[bear_mask].copy(),
#         df[neutral_mask].copy()
#     )

# # -------------------------------------------------
# # INTERACTIVE CHART
# # -------------------------------------------------
# def plot_interactive_chart(symbol: str, inds: list, params: dict):
#     hist = fetch_historical_data(symbol)
#     if hist is None or hist.empty:
#         st.error(f"No data for {symbol}")
#         return

#     df = hist.copy()
#     close = df["Close"]

#     # Recompute indicators (same logic)
#     indicators = {}
#     if "RSI" in inds:
#         p = params["RSI"]["period"]
#         delta = close.diff()
#         gain = delta.clip(lower=0)
#         loss = -delta.clip(upper=0)
#         avg_gain = gain.rolling(p, min_periods=p).mean()
#         avg_loss = loss.rolling(p, min_periods=p).mean()
#         rs = avg_gain / avg_loss
#         indicators["RSI"] = 100 - (100 / (1 + rs))

#     if "SMA" in inds:
#         p = params["SMA"]["period"]
#         indicators["SMA"] = close.rolling(p, min_periods=p).mean()

#     if "Bollinger Bands (BB)" in inds:
#         p = params["Bollinger Bands (BB)"]["period"]
#         sd = params["Bollinger Bands (BB)"]["std_dev"]
#         mid = close.rolling(p, min_periods=p).mean()
#         std = close.rolling(p, min_periods=p).std()
#         indicators["BB_Upper"] = mid + std * sd
#         indicators["BB_Lower"] = mid - std * sd
#         indicators["BB_Mid"] = mid

#     if "MACD" in inds:
#         fast = params["MACD"]["fast"]
#         slow = params["MACD"]["slow"]
#         sig = params["MACD"]["signal"]
#         ema_fast = close.ewm(span=fast, adjust=False).mean()
#         ema_slow = close.ewm(span=slow, adjust=False).mean()
#         macd_line = ema_fast - ema_slow
#         signal_line = macd_line.ewm(span=sig, adjust=False).mean()
#         indicators["MACD"] = macd_line
#         indicators["Signal"] = signal_line
#         indicators["Hist"] = macd_line - signal_line

#     if "Support/Resistance" in inds:
#         lb = params["Support/Resistance"]["lookback"]
#         tol = params["Support/Resistance"]["tolerance"]
#         indicators["Support"] = df["Low"].rolling(lb, min_periods=lb).min() * (1 + tol)
#         indicators["Resistance"] = df["High"].rolling(lb, min_periods=lb).max() * (1 - tol)

#     # Plot
#     fig = make_subplots(
#         rows=3, cols=1,
#         shared_xaxes=True,
#         vertical_spacing=0.05,
#         subplot_titles=("Candlestick + Indicators", "MACD", "RSI"),
#         row_heights=[0.6, 0.2, 0.2]
#     )

#     # Candlestick
#     fig.add_trace(go.Candlestick(
#         x=df.index,
#         open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
#         name="Price"
#     ), row=1, col=1)

#     # SMA
#     if "SMA" in indicators:
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["SMA"], name="SMA", line=dict(color="orange")), row=1, col=1)

#     # Bollinger Bands
#     if "BB_Upper" in indicators:
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["BB_Upper"], name="BB Upper", line=dict(color="gray", dash="dot")), row=1, col=1)
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["BB_Lower"], name="BB Lower", line=dict(color="gray", dash="dot"), fill="tonexty"), row=1, col=1)

#     # Support/Resistance
#     if "Support" in indicators:
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["Support"], name="Support", line=dict(color="green", dash="dash")), row=1, col=1)
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["Resistance"], name="Resistance", line=dict(color="red", dash="dash")), row=1, col=1)

#     # MACD
#     if "MACD" in indicators:
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["MACD"], name="MACD"), row=2, col=1)
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["Signal"], name="Signal"), row=2, col=1)
#         fig.add_trace(go.Bar(x=df.index, y=indicators["Hist"], name="Hist"), row=2, col=1)

#     # RSI
#     if "RSI" in indicators:
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["RSI"], name="RSI"), row=3, col=1)
#         fig.add_hline(y=70, line_dash="dot", line_color="red", row=3, col=1)
#         fig.add_hline(y=30, line_dash="dot", line_color="green", row=3, col=1)

#     fig.update_layout(height=800, title_text=f"{symbol} - Interactive Chart", xaxis_rangeslider_visible=False)
#     st.plotly_chart(fig, use_container_width=True)

# # -------------------------------------------------
# # UI
# # -------------------------------------------------
# def main():
#     st.set_page_config(page_title="CBOE Screener", layout="wide")
#     st.title("CBOE Optionable Stock Screener")
#     st.caption("**Interactive Charts: Click any symbol to verify signals**")

#     col1, col2 = st.columns(2)
#     with col1:
#         min_vol = st.number_input("Min Avg Daily Volume", 100_000, 5_000_000, 500_000, 50_000)
#     with col2:
#         dry_run = st.checkbox("Dry Run (first 30 symbols)", value=True)

#     st.subheader("Technical Indicators")
#     all_inds = ["RSI", "SMA", "Bollinger Bands (BB)", "MACD", "Support/Resistance"]
#     selected = st.multiselect("Select", all_inds, default=[])

#     params = {}
#     for i in selected:
#         with st.expander(i, expanded=True):
#             if i == "RSI":
#                 params[i] = {"period": st.slider("Period", 5, 50, 14, key="rsi_p")}
#             elif i == "SMA":
#                 params[i] = {"period": st.slider("Period", 10, 200, 50, key="sma_p")}
#             elif i == "Bollinger Bands (BB)":
#                 p1 = st.slider("Period", 10, 50, 20, key="bb_p")
#                 p2 = st.slider("Std Dev", 1.0, 3.0, 2.0, 0.1, key="bb_sd")
#                 params[i] = {"period": p1, "std_dev": p2}
#             elif i == "MACD":
#                 f = st.slider("Fast EMA", 5, 30, 12, key="macd_f")
#                 s = st.slider("Slow EMA", 20, 50, 26, key="macd_s")
#                 sig = st.slider("Signal EMA", 5, 20, 9, key="macd_sig")
#                 params[i] = {"fast": f, "slow": s, "signal": sig}
#             elif i == "Support/Resistance":
#                 lb = st.slider("Lookback", 10, 60, 20, key="sr_lb")
#                 tol = st.slider("Tolerance (%)", 0.0, 10.0, 2.0, 0.1, key="sr_tol") / 100
#                 params[i] = {"lookback": lb, "tolerance": tol}

#     with st.spinner("Loading symbols..."):
#         sym_df = update_symbols()
#     symbols = sym_df["symbol"].dropna().unique().tolist()
#     if dry_run:
#         symbols = symbols[:30]
#         st.info(f"**Dry Run**: {len(symbols)} symbols")
#     else:
#         st.info(f"Scanning **{len(symbols):,}** symbols")

#     if st.button("Start Scan", type="primary"):
#         tuner.__init__()
#         start = time.time()
#         with st.spinner("Scanning..."):
#             df = compute_parallel(symbols, min_vol, selected, params)
#         elapsed = time.time() - start

#         if df.empty:
#             st.warning("No valid stocks.")
#             return

#         # Live close
#         closes = {}
#         for sym in df["symbol"]:
#             hist = yf_safe_history(sym, period="1d")
#             closes[sym] = hist["Close"].iloc[-1] if not hist.empty else np.nan
#         df["Close"] = df["symbol"].map(closes)

#         df["Avg Volume"] = df["Avg Volume"].apply(lambda x: f"{x:,.0f}")

#         bull_df, bear_df, neutral_df = classify_bull_bear(df, selected)

#         total = len(bull_df) + len(bear_df) + len(neutral_df)
#         st.success(
#             f"**Done in {elapsed:.1f}s** – "
#             f"{len(df)} valid | "
#             f"**{len(bull_df)} bull** | **{len(bear_df)} bear** | {len(neutral_df)} neutral "
#             f"({total} total)"
#         )

#         # Store results in session state
#         st.session_state.bull_df = bull_df
#         st.session_state.bear_df = bear_df
#         st.session_state.neutral_df = neutral_df
#         st.session_state.inds = selected
#         st.session_state.params = params

#     # --- Interactive Chart Viewer ---
#     if 'bull_df' in st.session_state:
#         st.markdown("---")
#         st.subheader("Interactive Chart Viewer")

#         col_a, col_b, col_c = st.columns(3)
#         with col_a:
#             bull_sym = st.selectbox("Bullish", options=[""] + st.session_state.bull_df["symbol"].tolist())
#         with col_b:
#             bear_sym = st.selectbox("Bearish", options=[""] + st.session_state.bear_df["symbol"].tolist())
#         with col_c:
#             neutral_sym = st.selectbox("Neutral", options=[""] + st.session_state.neutral_df["symbol"].tolist())

#         selected_sym = bull_sym or bear_sym or neutral_sym
#         if selected_sym:
#             with st.spinner("Loading chart..."):
#                 plot_interactive_chart(selected_sym, st.session_state.inds, st.session_state.params)

#     if st.button("Clear Cache"):
#         import shutil
#         if os.path.exists(HISTORY_CACHE_DIR):
#             shutil.rmtree(HISTORY_CACHE_DIR)
#         if os.path.exists(PARQUET_FILE):
#             os.remove(PARQUET_FILE)
#         st.success("Cache cleared!")

# if __name__ == "__main__":
#     main()


##### rsi fix

# #!/usr/bin/env python
# # -*- coding: utf-8 -*-

# """
# CBOE Optionable Stock Screener – v10.5 FINAL
# - ALL indicator values in Bull/Bear/Neutral tables
# - NO export, NO dark mode, NO sound, NO auto-refresh
# - Clean, minimal UI
# """

# import os
# import io
# import time
# import logging
# import warnings
# from datetime import datetime
# from concurrent.futures import ThreadPoolExecutor, as_completed

# import psutil
# import requests
# import pandas as pd
# import numpy as np
# import streamlit as st
# import yfinance as yf
# import plotly.graph_objects as go
# from plotly.subplots import make_subplots
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# # -------------------------------------------------
# # CONFIG
# # -------------------------------------------------
# PARQUET_FILE = "optionable_full.parquet"
# HISTORY_CACHE_DIR = "history_cache"
# CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"

# SCHEMA_VERSION = "10.5"
# HISTORY_TTL = 24 * 3600
# SYMBOLS_TTL = 7 * 24 * 3600

# CPU_COUNT = psutil.cpu_count(logical=False) or 4
# MAX_WORKERS = min(CPU_COUNT, 8)
# INITIAL_BATCH_SIZE = min(CPU_COUNT * 20, 200)

# os.makedirs(HISTORY_CACHE_DIR, exist_ok=True)

# # -------------------------------------------------
# # SILENCE YFINANCE 404s
# # -------------------------------------------------
# class YFinanceFilter:
#     def __enter__(self):
#         self.original_filters = warnings.filters[:]
#         warnings.filterwarnings("ignore", category=UserWarning, module="yfinance")
#         return self
#     def __exit__(self, exc_type, exc_val, exc_tb):
#         warnings.filters = self.original_filters

# def yf_safe_history(symbol: str, **kwargs):
#     with YFinanceFilter():
#         try:
#             return yf.Ticker(symbol).history(**kwargs)
#         except:
#             return pd.DataFrame()

# # -------------------------------------------------
# # TUNER
# # -------------------------------------------------
# class Tuner:
#     def __init__(self):
#         self.rate_limited = 0
#         self.last_rate_limit = 0
#         self.workers = MAX_WORKERS
#         self.batch_size = INITIAL_BATCH_SIZE
#         self.success_streak = 0

#     def record_failure(self):
#         self.rate_limited += 1
#         self.last_rate_limit = time.time()
#         self.success_streak = 0
#         if self.rate_limited > 5:
#             self.workers = 1
#             self.batch_size = max(10, self.batch_size // 2)
#         elif self.rate_limited > 2:
#             self.workers = max(1, self.workers // 2)
#             self.batch_size = max(20, self.batch_size // 2)

#     def record_success(self):
#         self.success_streak += 1
#         if self.success_streak > 30 and self.workers < MAX_WORKERS:
#             self.workers = min(MAX_WORKERS, self.workers + 1)
#             self.batch_size = min(INITIAL_BATCH_SIZE, self.batch_size * 2)

# tuner = Tuner()

# # -------------------------------------------------
# # CACHE
# # -------------------------------------------------
# def get_cached_history(symbol: str) -> pd.DataFrame | None:
#     path = os.path.join(HISTORY_CACHE_DIR, f"{symbol}.parquet")
#     if not os.path.exists(path):
#         return None
#     try:
#         df = pd.read_parquet(path)
#         req = ["Open", "High", "Low", "Close", "Volume"]
#         if not all(c in df.columns for c in req) or df[req].isna().any().any():
#             raise ValueError("corrupt")
#         if time.time() - os.path.getmtime(path) > HISTORY_TTL:
#             os.remove(path)
#             return None
#         return df
#     except Exception:
#         if os.path.exists(path):
#             os.remove(path)
#         return None

# def cache_history(symbol: str, df: pd.DataFrame):
#     path = os.path.join(HISTORY_CACHE_DIR, f"{symbol}.parquet")
#     try:
#         df.to_parquet(path, index=False)
#     except Exception:
#         pass

# def get_last_close(symbol: str) -> float:
#     cached = get_cached_history(symbol)
#     if cached is not None and not cached.empty:
#         return cached["Close"].iloc[-1]
#     return np.nan

# def get_prev_close(symbol: str) -> float:
#     cached = get_cached_history(symbol)
#     if cached is not None and len(cached) >= 2:
#         return cached["Close"].iloc[-2]
#     return np.nan

# # -------------------------------------------------
# # SYMBOLS
# # -------------------------------------------------
# @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=30))
# def fetch_cboe_symbols() -> pd.DataFrame:
#     r = requests.get(CBOE_URL, timeout=30)
#     r.raise_for_status()
#     df = pd.read_csv(io.StringIO(r.text))
#     col = next((c for c in df.columns if "symbol" in c.lower() or "root" in c.lower()), None)
#     if not col:
#         raise ValueError("No symbol column")
#     df = df[[col]].rename(columns={col: "symbol"})
#     df["symbol"] = df["symbol"].str.upper().str.strip()
#     df = df.drop_duplicates().assign(
#         updated_at=datetime.utcnow().isoformat(),
#         schema_version=SCHEMA_VERSION
#     )
#     return df

# def update_symbols() -> pd.DataFrame:
#     if os.path.exists(PARQUET_FILE):
#         try:
#             df = pd.read_parquet(PARQUET_FILE)
#             if df["schema_version"].iloc[0] == SCHEMA_VERSION:
#                 age = (datetime.utcnow() - pd.to_datetime(df["updated_at"].iloc[0])).total_seconds()
#                 if age < SYMBOLS_TTL:
#                     return df
#         except: pass
#     fresh = fetch_cboe_symbols()
#     tmp = PARQUET_FILE + ".tmp"
#     fresh.to_parquet(tmp, index=False)
#     os.replace(tmp, PARQUET_FILE)
#     return fresh

# # -------------------------------------------------
# # YFINANCE
# # -------------------------------------------------
# @retry(
#     stop=stop_after_attempt(3),
#     wait=wait_exponential(multiplier=2, min=30, max=120),
#     retry=retry_if_exception_type((requests.RequestException, ValueError)),
# )
# def fetch_historical_data(symbol: str) -> pd.DataFrame | None:
#     cached = get_cached_history(symbol)
#     if cached is not None:
#         tuner.record_success()
#         return cached

#     if tuner.rate_limited > 3 and time.time() - tuner.last_rate_limit < 120:
#         time.sleep(60)

#     try:
#         data = yf_safe_history(symbol, period="6mo", interval="1d", raise_errors=True, timeout=15)
#         if data.empty:
#             return None
#         data = data.reset_index()
#         data["symbol"] = symbol
#         cache_history(symbol, data)
#         time.sleep(0.08)
#         tuner.record_success()
#         return data
#     except Exception as e:
#         if "429" in str(e) or "rate limit" in str(e).lower():
#             tuner.record_failure()
#             logger.warning(f"Rate limited: {symbol}")
#         return None

# # -------------------------------------------------
# # VECTORIZED INDICATORS
# # -------------------------------------------------
# def compute_indicators_vectorized(df: pd.DataFrame, inds: list, params: dict) -> pd.DataFrame:
#     if df.empty:
#         return pd.DataFrame()

#     close = df["Close"]
#     high = df["High"]
#     low = df["Low"]
#     out = pd.DataFrame(index=df.index)
#     out["Close"] = close

#     if "RSI" in inds:
#         p = params["RSI"]["period"]
#         delta = close.diff()
#         gain = delta.clip(lower=0)
#         loss = -delta.clip(upper=0)
#         avg_gain = gain.rolling(p, min_periods=p).mean()
#         avg_loss = loss.rolling(p, min_periods=p).mean()
#         rs = avg_gain / avg_loss
#         out["RSI"] = 100 - (100 / (1 + rs))

#     if "SMA" in inds:
#         p = params["SMA"]["period"]
#         out["SMA"] = close.rolling(p, min_periods=p).mean()

#     if "Bollinger Bands (BB)" in inds:
#         p = params["Bollinger Bands (BB)"]["period"]
#         sd = params["Bollinger Bands (BB)"]["std_dev"]
#         mid = close.rolling(p, min_periods=p).mean()
#         std = close.rolling(p, min_periods=p).std()
#         out["BB_Mid"] = mid
#         out["BB_Upper"] = mid + std * sd
#         out["BB_Lower"] = mid - std * sd

#     if "MACD" in inds:
#         fast = params["MACD"]["fast"]
#         slow = params["MACD"]["slow"]
#         sig = params["MACD"]["signal"]
#         ema_fast = close.ewm(span=fast, adjust=False).mean()
#         ema_slow = close.ewm(span=slow, adjust=False).mean()
#         macd_line = ema_fast - ema_slow
#         signal_line = macd_line.ewm(span=sig, adjust=False).mean()
#         out["MACD"] = macd_line
#         out["Signal"] = signal_line
#         out["Hist"] = macd_line - signal_line

#     if "Support/Resistance" in inds:
#         lb = params["Support/Resistance"]["lookback"]
#         tol = params["Support/Resistance"]["tolerance"]
#         sup = low.rolling(lb, min_periods=lb).min() * (1 + tol)
#         res = high.rolling(lb, min_periods=lb).max() * (1 - tol)
#         out["Support"] = sup
#         out["Resistance"] = res

#     last = out.groupby(df["symbol"]).tail(1).reset_index(drop=True)
#     last["symbol"] = df["symbol"].groupby(df["symbol"]).tail(1).values
#     last["Avg Volume"] = df["Volume"].groupby(df["symbol"]).mean().values

#     return last

# # -------------------------------------------------
# # BATCH PROCESSOR
# # -------------------------------------------------
# def process_batch(symbols: list, min_vol: int, inds: list, params: dict) -> pd.DataFrame:
#     data_frames = []
#     for sym in symbols:
#         hist = fetch_historical_data(sym)
#         if hist is not None and len(hist) >= 100:
#             data_frames.append(hist)

#     if not data_frames:
#         return pd.DataFrame()

#     df = pd.concat(data_frames, ignore_index=True)

#     vol_mean = df.groupby("symbol")["Volume"].mean()
#     valid_symbols = vol_mean[vol_mean >= min_vol].index
#     df = df[df["symbol"].isin(valid_symbols)]
#     if df.empty:
#         return pd.DataFrame()

#     return compute_indicators_vectorized(df, inds, params)

# # -------------------------------------------------
# # PARALLEL DRIVER
# # -------------------------------------------------
# def compute_parallel(symbols: list, min_vol: int, inds: list, params: dict) -> pd.DataFrame:
#     batch_size = tuner.batch_size
#     batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
#     results = []

#     with ThreadPoolExecutor(max_workers=tuner.workers) as pool:
#         futures = [pool.submit(process_batch, b, min_vol, inds, params) for b in batches]
#         prog = st.progress(0)
#         status = st.empty()
#         for i, f in enumerate(as_completed(futures), 1):
#             batch_res = f.result()
#             if not batch_res.empty:
#                 results.append(batch_res)
#             prog.progress(i / len(futures))
#             status.text(
#                 f"Workers: {tuner.workers} | Batch: {batch_size} | "
#                 f"Valid: {sum(len(r) for r in results)}"
#             )

#     return pd.concat(results, ignore_index=True) if results else pd.DataFrame()

# # -------------------------------------------------
# # CLASSIFIER
# # -------------------------------------------------
# def classify_bull_bear(df: pd.DataFrame, inds: list, rsi_bull: float, rsi_bear: float):
#     if df.empty:
#         return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

#     close = df["Close"]
#     total_indicators = len(inds)
#     bull_count = pd.Series(0, index=df.index)
#     bear_count = pd.Series(0, index=df.index)

#     if "RSI" in inds and "RSI" in df.columns:
#         bull_count += (df["RSI"] > rsi_bull).astype(int)
#         bear_count += (df["RSI"] < rsi_bear).astype(int)

#     if "SMA" in inds and "SMA" in df.columns:
#         bull_count += (close > df["SMA"]).astype(int)
#         bear_count += (close < df["SMA"]).astype(int)

#     if "Bollinger Bands (BB)" in inds and "BB_Lower" in df.columns and "BB_Upper" in df.columns:
#         bull_count += (close > df["BB_Lower"]).astype(int)
#         bear_count += (close < df["BB_Upper"]).astype(int)

#     if "MACD" in inds and "MACD" in df.columns and "Signal" in df.columns:
#         bull_count += (df["MACD"] > df["Signal"]).astype(int)
#         bear_count += (df["MACD"] < df["Signal"]).astype(int)

#     if "Support/Resistance" in inds and "Support" in df.columns and "Resistance" in df.columns:
#         bull_count += (close > df["Support"]).astype(int)
#         bear_count += (close < df["Resistance"]).astype(int)

#     bull_mask = (bull_count == total_indicators) & (total_indicators > 0)
#     bear_mask = (bear_count == total_indicators) & (total_indicators > 0)
#     neutral_mask = ~(bull_mask | bear_mask)

#     return (
#         df[bull_mask].copy(),
#         df[bear_mask].copy(),
#         df[neutral_mask].copy()
#     )

# # -------------------------------------------------
# # INTERACTIVE CHART
# # -------------------------------------------------
# def plot_interactive_chart(symbol: str, inds: list, params: dict, bull_df, bear_df):
#     hist = fetch_historical_data(symbol)
#     if hist is None or hist.empty:
#         st.error(f"No data for {symbol}")
#         return

#     df = hist.copy()
#     close = df["Close"]

#     indicators = {}
#     if "RSI" in inds:
#         p = params["RSI"]["period"]
#         delta = close.diff()
#         gain = delta.clip(lower=0)
#         loss = -delta.clip(upper=0)
#         avg_gain = gain.rolling(p, min_periods=p).mean()
#         avg_loss = loss.rolling(p, min_periods=p).mean()
#         rs = avg_gain / avg_loss
#         indicators["RSI"] = 100 - (100 / (1 + rs))

#     if "SMA" in inds:
#         p = params["SMA"]["period"]
#         indicators["SMA"] = close.rolling(p, min_periods=p).mean()

#     if "Bollinger Bands (BB)" in inds:
#         p = params["Bollinger Bands (BB)"]["period"]
#         sd = params["Bollinger Bands (BB)"]["std_dev"]
#         mid = close.rolling(p, min_periods=p).mean()
#         std = close.rolling(p, min_periods=p).std()
#         indicators["BB_Upper"] = mid + std * sd
#         indicators["BB_Lower"] = mid - std * sd
#         indicators["BB_Mid"] = mid

#     if "MACD" in inds:
#         fast = params["MACD"]["fast"]
#         slow = params["MACD"]["slow"]
#         sig = params["MACD"]["signal"]
#         ema_fast = close.ewm(span=fast, adjust=False).mean()
#         ema_slow = close.ewm(span=slow, adjust=False).mean()
#         macd_line = ema_fast - ema_slow
#         signal_line = macd_line.ewm(span=sig, adjust=False).mean()
#         indicators["MACD"] = macd_line
#         indicators["Signal"] = signal_line
#         indicators["Hist"] = macd_line - signal_line

#     if "Support/Resistance" in inds:
#         lb = params["Support/Resistance"]["lookback"]
#         tol = params["Support/Resistance"]["tolerance"]
#         indicators["Support"] = df["Low"].rolling(lb, min_periods=lb).min() * (1 + tol)
#         indicators["Resistance"] = df["High"].rolling(lb, min_periods=lb).max() * (1 - tol)

#     if symbol in bull_df["symbol"].values:
#         signal, color = "Bullish", "green"
#     elif symbol in bear_df["symbol"].values:
#         signal, color = "Bearish", "red"
#     else:
#         signal, color = "Neutral", "gray"

#     fig = make_subplots(
#         rows=3, cols=1,
#         shared_xaxes=True,
#         vertical_spacing=0.05,
#         subplot_titles=("Candlestick + Indicators", "MACD", "RSI"),
#         row_heights=[0.6, 0.2, 0.2]
#     )

#     fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Price"), row=1, col=1)

#     if "SMA" in indicators:
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["SMA"], name="SMA", line=dict(color="orange")), row=1, col=1)

#     if "BB_Upper" in indicators:
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["BB_Upper"], name="BB Upper", line=dict(color="gray", dash="dot")), row=1, col=1)
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["BB_Lower"], name="BB Lower", line=dict(color="gray", dash="dot"), fill="tonexty"), row=1, col=1)

#     if "Support" in indicators:
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["Support"], name="Support", line=dict(color="green", dash="dash")), row=1, col=1)
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["Resistance"], name="Resistance", line=dict(color="red", dash="dash")), row=1, col=1)

#     if "MACD" in indicators:
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["MACD"], name="MACD"), row=2, col=1)
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["Signal"], name="Signal"), row=2, col=1)
#         fig.add_trace(go.Bar(x=df.index, y=indicators["Hist"], name="Hist"), row=2, col=1)

#     if "RSI" in indicators:
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["RSI"], name="RSI"), row=3, col=1)
#         fig.add_hline(y=70, line_dash="dot", line_color="red", row=3, col=1)
#         fig.add_hline(y=30, line_dash="dot", line_color="green", row=3, col=1)

#     fig.update_layout(
#         height=800,
#         title_text=f"{symbol} - <span style='color:{color}'>{signal}</span> Signal",
#         xaxis_rangeslider_visible=False,
#         template="plotly"
#     )
#     st.plotly_chart(fig, use_container_width=True)

# # -------------------------------------------------
# # UI
# # -------------------------------------------------
# def main():
#     st.set_page_config(page_title="CBOE Screener", layout="wide")
#     st.title("CBOE Optionable Stock Screener")
#     st.caption("**All selected indicator values shown in results**")

#     # === CONTROLS ===
#     col1, col2 = st.columns(2)
#     with col1:
#         min_vol = st.number_input("Min Avg Daily Volume", 100_000, 5_000_000, 500_000, 50_000)
#     with col2:
#         dry_run = st.checkbox("Dry Run (first 30 symbols)", value=True)

#     st.subheader("Technical Indicators")
#     all_inds = ["RSI", "SMA", "Bollinger Bands (BB)", "MACD", "Support/Resistance"]
#     selected = st.multiselect("Select Indicators", all_inds, default=[])

#     params = {}
#     for i in selected:
#         with st.expander(i, expanded=True):
#             if i == "RSI":
#                 p = st.slider("Period", 5, 50, 14, key="rsi_p")
#                 col_a, col_b = st.columns(2)
#                 with col_a:
#                     st.number_input("Bullish RSI >", 0, 100, 60, key="input_rsi_bull")
#                 with col_b:
#                     st.number_input("Bearish RSI <", 0, 100, 40, key="input_rsi_bear")
#                 params[i] = {"period": p}
#             elif i == "SMA":
#                 params[i] = {"period": st.slider("Period", 10, 200, 50, key="sma_p")}
#             elif i == "Bollinger Bands (BB)":
#                 p1 = st.slider("Period", 10, 50, 20, key="bb_p")
#                 p2 = st.slider("Std Dev", 1.0, 3.0, 2.0, 0.1, key="bb_sd")
#                 params[i] = {"period": p1, "std_dev": p2}
#             elif i == "MACD":
#                 f = st.slider("Fast EMA", 5, 30, 12, key="macd_f")
#                 s = st.slider("Slow EMA", 20, 50, 26, key="macd_s")
#                 sig = st.slider("Signal EMA", 5, 20, 9, key="macd_sig")
#                 params[i] = {"fast": f, "slow": s, "signal": sig}
#             elif i == "Support/Resistance":
#                 lb = st.slider("Lookback", 10, 60, 20, key="sr_lb")
#                 tol = st.slider("Tolerance (%)", 0.0, 10.0, 2.0, 0.1, key="sr_tol") / 100
#                 params[i] = {"lookback": lb, "tolerance": tol}

#     rsi_bull = st.session_state.get("input_rsi_bull", 60)
#     rsi_bear = st.session_state.get("input_rsi_bear", 40)

#     with st.spinner("Loading symbols..."):
#         sym_df = update_symbols()
#     symbols = sym_df["symbol"].dropna().unique().tolist()
#     if dry_run:
#         symbols = symbols[:30]
#         st.info(f"**Dry Run**: {len(symbols)} symbols")
#     else:
#         st.info(f"Scanning **{len(symbols):,}** symbols")

#     if st.button("Start Scan", type="primary"):
#         tuner.__init__()
#         start = time.time()
#         with st.spinner("Scanning..."):
#             df = compute_parallel(symbols, min_vol, selected, params)
#         elapsed = time.time() - start

#         if df.empty:
#             st.warning("No valid stocks.")
#             return

#         df["Close"] = df["symbol"].map(get_last_close)
#         df["Prev Close"] = df["symbol"].map(get_prev_close)
#         change_pct = np.where(
#             df["Prev Close"].notna() & (df["Prev Close"] != 0),
#             ((df["Close"] - df["Prev Close"]) / df["Prev Close"] * 100).round(2),
#             np.nan
#         )
#         df["Change %"] = change_pct
#         df["Avg Volume"] = df["Avg Volume"].apply(lambda x: f"{x:,.0f}")

#         bull_df, bear_df, neutral_df = classify_bull_bear(df, selected, rsi_bull, rsi_bear)

#         total = len(bull_df) + len(bear_df) + len(neutral_df)
#         st.success(
#             f"**Done in {elapsed:.1f}s** – "
#             f"{len(df)} valid | "
#             f"**{len(bull_df)} bull** | **{len(bear_df)} bear** | {len(neutral_df)} neutral "
#             f"({total} total)"
#         )

#         st.session_state.bull_df = bull_df
#         st.session_state.bear_df = bear_df
#         st.session_state.neutral_df = neutral_df
#         st.session_state.inds = selected
#         st.session_state.params = params

#     # === RESULTS ===
#     if 'bull_df' in st.session_state:
#         st.markdown("---")
#         st.subheader("Results")

#         # === BUILD DISPLAY COLUMNS WITH ALL INDICATORS ===
#         base_cols = ["symbol", "Close", "Change %", "Avg Volume"]
#         indicator_cols = []

#         for ind in st.session_state.inds:
#             if ind == "RSI" and "RSI" in st.session_state.bull_df.columns:
#                 indicator_cols.append("RSI")
#             elif ind == "SMA" and "SMA" in st.session_state.bull_df.columns:
#                 indicator_cols.append("SMA")
#             elif ind == "Bollinger Bands (BB)" and "BB_Mid" in st.session_state.bull_df.columns:
#                 indicator_cols.extend(["BB_Lower", "BB_Mid", "BB_Upper"])
#             elif ind == "MACD" and "MACD" in st.session_state.bull_df.columns:
#                 indicator_cols.extend(["MACD", "Signal", "Hist"])
#             elif ind == "Support/Resistance" and "Support" in st.session_state.bull_df.columns:
#                 indicator_cols.extend(["Support", "Resistance"])

#         display_cols = base_cols + indicator_cols

#         # Search
#         search = st.text_input("Search symbol", "")
#         def filter_df(df):
#             if search:
#                 return df[df["symbol"].str.contains(search, case=False)]
#             return df

#         # === TABLES IN EXPANDERS ===
#         with st.expander("Bullish Signals", expanded=True):
#             if st.session_state.bull_df.empty:
#                 st.info("No bullish signals.")
#             else:
#                 filtered = filter_df(st.session_state.bull_df)
#                 valid_cols = [c for c in display_cols if c in filtered.columns]
#                 st.dataframe(
#                     filtered[valid_cols].round(2).sort_values("Change %", ascending=False, na_position='last'),
#                     use_container_width=True
#                 )

#         with st.expander("Bearish Signals", expanded=True):
#             if st.session_state.bear_df.empty:
#                 st.info("No bearish signals.")
#             else:
#                 filtered = filter_df(st.session_state.bear_df)
#                 valid_cols = [c for c in display_cols if c in filtered.columns]
#                 st.dataframe(
#                     filtered[valid_cols].round(2).sort_values("Change %", ascending=False, na_position='last'),
#                     use_container_width=True
#                 )

#         with st.expander("Neutral", expanded=False):
#             if st.session_state.neutral_df.empty:
#                 st.info("No neutral signals.")
#             else:
#                 filtered = filter_df(st.session_state.neutral_df)
#                 valid_cols = [c for c in display_cols if c in filtered.columns]
#                 st.dataframe(filtered[valid_cols].head(20).round(2), use_container_width=True)

#         # === CHART ===
#         st.markdown("---")
#         st.subheader("Interactive Chart Viewer")
#         col_a, col_b, col_c = st.columns(3)
#         with col_a:
#             bull_sym = st.selectbox("Bullish", options=[""] + st.session_state.bull_df["symbol"].tolist())
#         with col_b:
#             bear_sym = st.selectbox("Bearish", options=[""] + st.session_state.bear_df["symbol"].tolist())
#         with col_c:
#             neutral_sym = st.selectbox("Neutral", options=[""] + st.session_state.neutral_df["symbol"].tolist())

#         selected_sym = bull_sym or bear_sym or neutral_sym
#         if selected_sym:
#             with st.spinner("Loading chart..."):
#                 plot_interactive_chart(
#                     selected_sym,
#                     st.session_state.inds,
#                     st.session_state.params,
#                     st.session_state.bull_df,
#                     st.session_state.bear_df
#                 )

#     st.caption(f"Data updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} | CBOE list: {len(symbols):,} symbols")

#     if st.button("Clear Cache"):
#         import shutil
#         if os.path.exists(HISTORY_CACHE_DIR):
#             shutil.rmtree(HISTORY_CACHE_DIR)
#         if os.path.exists(PARQUET_FILE):
#             os.remove(PARQUET_FILE)
#         st.success("Cache cleared!")
#         st.rerun()

# if __name__ == "__main__":
#     main()


###### reverse all signal and labels from bullish to bearish


# """
# CBOE Optionable Stock Screener – v10.6 FINAL
# - LOGIC REVERSED: Bullish = Bearish, Bearish = Bullish
# - All indicators, labels, sorting flipped
# """

# import os
# import io
# import time
# import logging
# import warnings
# from datetime import datetime
# from concurrent.futures import ThreadPoolExecutor, as_completed

# import psutil
# import requests
# import pandas as pd
# import numpy as np
# import streamlit as st
# import yfinance as yf
# import plotly.graph_objects as go
# from plotly.subplots import make_subplots
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# # -------------------------------------------------
# # CONFIG
# # -------------------------------------------------
# PARQUET_FILE = "optionable_full.parquet"
# HISTORY_CACHE_DIR = "history_cache"
# CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"

# SCHEMA_VERSION = "10.6"
# HISTORY_TTL = 24 * 3600
# SYMBOLS_TTL = 7 * 24 * 3600

# CPU_COUNT = psutil.cpu_count(logical=False) or 4
# MAX_WORKERS = min(CPU_COUNT, 8)
# INITIAL_BATCH_SIZE = min(CPU_COUNT * 20, 200)

# os.makedirs(HISTORY_CACHE_DIR, exist_ok=True)

# # -------------------------------------------------
# # SILENCE YFINANCE 404s
# # -------------------------------------------------
# class YFinanceFilter:
#     def __enter__(self):
#         self.original_filters = warnings.filters[:]
#         warnings.filterwarnings("ignore", category=UserWarning, module="yfinance")
#         return self
#     def __exit__(self, exc_type, exc_val, exc_tb):
#         warnings.filters = self.original_filters

# def yf_safe_history(symbol: str, **kwargs):
#     with YFinanceFilter():
#         try:
#             return yf.Ticker(symbol).history(**kwargs)
#         except:
#             return pd.DataFrame()

# # -------------------------------------------------
# # TUNER
# # -------------------------------------------------
# class Tuner:
#     def __init__(self):
#         self.rate_limited = 0
#         self.last_rate_limit = 0
#         self.workers = MAX_WORKERS
#         self.batch_size = INITIAL_BATCH_SIZE
#         self.success_streak = 0

#     def record_failure(self):
#         self.rate_limited += 1
#         self.last_rate_limit = time.time()
#         self.success_streak = 0
#         if self.rate_limited > 5:
#             self.workers = 1
#             self.batch_size = max(10, self.batch_size // 2)
#         elif self.rate_limited > 2:
#             self.workers = max(1, self.workers // 2)
#             self.batch_size = max(20, self.batch_size // 2)

#     def record_success(self):
#         self.success_streak += 1
#         if self.success_streak > 30 and self.workers < MAX_WORKERS:
#             self.workers = min(MAX_WORKERS, self.workers + 1)
#             self.batch_size = min(INITIAL_BATCH_SIZE, self.batch_size * 2)

# tuner = Tuner()

# # -------------------------------------------------
# # CACHE
# # -------------------------------------------------
# def get_cached_history(symbol: str) -> pd.DataFrame | None:
#     path = os.path.join(HISTORY_CACHE_DIR, f"{symbol}.parquet")
#     if not os.path.exists(path):
#         return None
#     try:
#         df = pd.read_parquet(path)
#         req = ["Open", "High", "Low", "Close", "Volume"]
#         if not all(c in df.columns for c in req) or df[req].isna().any().any():
#             raise ValueError("corrupt")
#         if time.time() - os.path.getmtime(path) > HISTORY_TTL:
#             os.remove(path)
#             return None
#         return df
#     except Exception:
#         if os.path.exists(path):
#             os.remove(path)
#         return None

# def cache_history(symbol: str, df: pd.DataFrame):
#     path = os.path.join(HISTORY_CACHE_DIR, f"{symbol}.parquet")
#     try:
#         df.to_parquet(path, index=False)
#     except Exception:
#         pass

# def get_last_close(symbol: str) -> float:
#     cached = get_cached_history(symbol)
#     if cached is not None and not cached.empty:
#         return cached["Close"].iloc[-1]
#     return np.nan

# def get_prev_close(symbol: str) -> float:
#     cached = get_cached_history(symbol)
#     if cached is not None and len(cached) >= 2:
#         return cached["Close"].iloc[-2]
#     return np.nan

# # -------------------------------------------------
# # SYMBOLS
# # -------------------------------------------------
# @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=30))
# def fetch_cboe_symbols() -> pd.DataFrame:
#     r = requests.get(CBOE_URL, timeout=30)
#     r.raise_for_status()
#     df = pd.read_csv(io.StringIO(r.text))
#     col = next((c for c in df.columns if "symbol" in c.lower() or "root" in c.lower()), None)
#     if not col:
#         raise ValueError("No symbol column")
#     df = df[[col]].rename(columns={col: "symbol"})
#     df["symbol"] = df["symbol"].str.upper().str.strip()
#     df = df.drop_duplicates().assign(
#         updated_at=datetime.utcnow().isoformat(),
#         schema_version=SCHEMA_VERSION
#     )
#     return df

# def update_symbols() -> pd.DataFrame:
#     if os.path.exists(PARQUET_FILE):
#         try:
#             df = pd.read_parquet(PARQUET_FILE)
#             if df["schema_version"].iloc[0] == SCHEMA_VERSION:
#                 age = (datetime.utcnow() - pd.to_datetime(df["updated_at"].iloc[0])).total_seconds()
#                 if age < SYMBOLS_TTL:
#                     return df
#         except: pass
#     fresh = fetch_cboe_symbols()
#     tmp = PARQUET_FILE + ".tmp"
#     fresh.to_parquet(tmp, index=False)
#     os.replace(tmp, PARQUET_FILE)
#     return fresh

# # -------------------------------------------------
# # YFINANCE
# # -------------------------------------------------
# @retry(
#     stop=stop_after_attempt(3),
#     wait=wait_exponential(multiplier=2, min=30, max=120),
#     retry=retry_if_exception_type((requests.RequestException, ValueError)),
# )
# def fetch_historical_data(symbol: str) -> pd.DataFrame | None:
#     cached = get_cached_history(symbol)
#     if cached is not None:
#         tuner.record_success()
#         return cached

#     if tuner.rate_limited > 3 and time.time() - tuner.last_rate_limit < 120:
#         time.sleep(60)

#     try:
#         data = yf_safe_history(symbol, period="6mo", interval="1d", raise_errors=True, timeout=15)
#         if data.empty:
#             return None
#         data = data.reset_index()
#         data["symbol"] = symbol
#         cache_history(symbol, data)
#         time.sleep(0.08)
#         tuner.record_success()
#         return data
#     except Exception as e:
#         if "429" in str(e) or "rate limit" in str(e).lower():
#             tuner.record_failure()
#             logger.warning(f"Rate limited: {symbol}")
#         return None

# # -------------------------------------------------
# # VECTORIZED INDICATORS
# # -------------------------------------------------
# def compute_indicators_vectorized(df: pd.DataFrame, inds: list, params: dict) -> pd.DataFrame:
#     if df.empty:
#         return pd.DataFrame()

#     close = df["Close"]
#     high = df["High"]
#     low = df["Low"]
#     out = pd.DataFrame(index=df.index)
#     out["Close"] = close

#     if "RSI" in inds:
#         p = params["RSI"]["period"]
#         delta = close.diff()
#         gain = delta.clip(lower=0)
#         loss = -delta.clip(upper=0)
#         avg_gain = gain.rolling(p, min_periods=p).mean()
#         avg_loss = loss.rolling(p, min_periods=p).mean()
#         rs = avg_gain / avg_loss
#         out["RSI"] = 100 - (100 / (1 + rs))

#     if "SMA" in inds:
#         p = params["SMA"]["period"]
#         out["SMA"] = close.rolling(p, min_periods=p).mean()

#     if "Bollinger Bands (BB)" in inds:
#         p = params["Bollinger Bands (BB)"]["period"]
#         sd = params["Bollinger Bands (BB)"]["std_dev"]
#         mid = close.rolling(p, min_periods=p).mean()
#         std = close.rolling(p, min_periods=p).std()
#         out["BB_Mid"] = mid
#         out["BB_Upper"] = mid + std * sd
#         out["BB_Lower"] = mid - std * sd

#     if "MACD" in inds:
#         fast = params["MACD"]["fast"]
#         slow = params["MACD"]["slow"]
#         sig = params["MACD"]["signal"]
#         ema_fast = close.ewm(span=fast, adjust=False).mean()
#         ema_slow = close.ewm(span=slow, adjust=False).mean()
#         macd_line = ema_fast - ema_slow
#         signal_line = macd_line.ewm(span=sig, adjust=False).mean()
#         out["MACD"] = macd_line
#         out["Signal"] = signal_line
#         out["Hist"] = macd_line - signal_line

#     if "Support/Resistance" in inds:
#         lb = params["Support/Resistance"]["lookback"]
#         tol = params["Support/Resistance"]["tolerance"]
#         sup = low.rolling(lb, min_periods=lb).min() * (1 + tol)
#         res = high.rolling(lb, min_periods=lb).max() * (1 - tol)
#         out["Support"] = sup
#         out["Resistance"] = res

#     last = out.groupby(df["symbol"]).tail(1).reset_index(drop=True)
#     last["symbol"] = df["symbol"].groupby(df["symbol"]).tail(1).values
#     last["Avg Volume"] = df["Volume"].groupby(df["symbol"]).mean().values

#     return last

# # -------------------------------------------------
# # BATCH PROCESSOR
# # -------------------------------------------------
# def process_batch(symbols: list, min_vol: int, inds: list, params: dict) -> pd.DataFrame:
#     data_frames = []
#     for sym in symbols:
#         hist = fetch_historical_data(sym)
#         if hist is not None and len(hist) >= 100:
#             data_frames.append(hist)

#     if not data_frames:
#         return pd.DataFrame()

#     df = pd.concat(data_frames, ignore_index=True)

#     vol_mean = df.groupby("symbol")["Volume"].mean()
#     valid_symbols = vol_mean[vol_mean >= min_vol].index
#     df = df[df["symbol"].isin(valid_symbols)]
#     if df.empty:
#         return pd.DataFrame()

#     return compute_indicators_vectorized(df, inds, params)

# # -------------------------------------------------
# # PARALLEL DRIVER
# # -------------------------------------------------
# def compute_parallel(symbols: list, min_vol: int, inds: list, params: dict) -> pd.DataFrame:
#     batch_size = tuner.batch_size
#     batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
#     results = []

#     with ThreadPoolExecutor(max_workers=tuner.workers) as pool:
#         futures = [pool.submit(process_batch, b, min_vol, inds, params) for b in batches]
#         prog = st.progress(0)
#         status = st.empty()
#         for i, f in enumerate(as_completed(futures), 1):
#             batch_res = f.result()
#             if not batch_res.empty:
#                 results.append(batch_res)
#             prog.progress(i / len(futures))
#             status.text(
#                 f"Workers: {tuner.workers} | Batch: {batch_size} | "
#                 f"Valid: {sum(len(r) for r in results)}"
#             )

#     return pd.concat(results, ignore_index=True) if results else pd.DataFrame()

# # -------------------------------------------------
# # CLASSIFIER – REVERSED LOGIC
# # -------------------------------------------------
# def classify_bull_bear(df: pd.DataFrame, inds: list, rsi_bull: float, rsi_bear: float):
#     if df.empty:
#         return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

#     close = df["Close"]
#     total_indicators = len(inds)
#     bull_count = pd.Series(0, index=df.index)  # Now: "Bullish" = likely DOWN
#     bear_count = pd.Series(0, index=df.index)  # Now: "Bearish" = likely UP

#     if "RSI" in inds and "RSI" in df.columns:
#         bull_count += (df["RSI"] < rsi_bull).astype(int)   # Low RSI → Bullish (down)
#         bear_count += (df["RSI"] > rsi_bear).astype(int)  # High RSI → Bearish (up)

#     if "SMA" in inds and "SMA" in df.columns:
#         bull_count += (close < df["SMA"]).astype(int)     # Below SMA → Bullish (down)
#         bear_count += (close > df["SMA"]).astype(int)     # Above SMA → Bearish (up)

#     if "Bollinger Bands (BB)" in inds and "BB_Lower" in df.columns and "BB_Upper" in df.columns:
#         bull_count += (close < df["BB_Lower"]).astype(int)  # Below lower → Bullish
#         bear_count += (close > df["BB_Upper"]).astype(int)  # Above upper → Bearish

#     if "MACD" in inds and "MACD" in df.columns and "Signal" in df.columns:
#         bull_count += (df["MACD"] < df["Signal"]).astype(int)  # MACD < Signal → Bullish
#         bear_count += (df["MACD"] > df["Signal"]).astype(int)  # MACD > Signal → Bearish

#     if "Support/Resistance" in inds and "Support" in df.columns and "Resistance" in df.columns:
#         bull_count += (close < df["Support"]).astype(int)     # Below support → Bullish
#         bear_count += (close > df["Resistance"]).astype(int)  # Above resistance → Bearish

#     bull_mask = (bull_count == total_indicators) & (total_indicators > 0)
#     bear_mask = (bear_count == total_indicators) & (total_indicators > 0)
#     neutral_mask = ~(bull_mask | bear_mask)

#     return (
#         df[bull_mask].copy(),  # "Bullish" = down
#         df[bear_mask].copy(),  # "Bearish" = up
#         df[neutral_mask].copy()
#     )

# # -------------------------------------------------
# # INTERACTIVE CHART – REVERSED COLORS
# # -------------------------------------------------
# def plot_interactive_chart(symbol: str, inds: list, params: dict, bull_df, bear_df):
#     hist = fetch_historical_data(symbol)
#     if hist is None or hist.empty:
#         st.error(f"No data for {symbol}")
#         return

#     df = hist.copy()
#     close = df["Close"]

#     indicators = {}
#     if "RSI" in inds:
#         p = params["RSI"]["period"]
#         delta = close.diff()
#         gain = delta.clip(lower=0)
#         loss = -delta.clip(upper=0)
#         avg_gain = gain.rolling(p, min_periods=p).mean()
#         avg_loss = loss.rolling(p, min_periods=p).mean()
#         rs = avg_gain / avg_loss
#         indicators["RSI"] = 100 - (100 / (1 + rs))

#     if "SMA" in inds:
#         p = params["SMA"]["period"]
#         indicators["SMA"] = close.rolling(p, min_periods=p).mean()

#     if "Bollinger Bands (BB)" in inds:
#         p = params["Bollinger Bands (BB)"]["period"]
#         sd = params["Bollinger Bands (BB)"]["std_dev"]
#         mid = close.rolling(p, min_periods=p).mean()
#         std = close.rolling(p, min_periods=p).std()
#         indicators["BB_Upper"] = mid + std * sd
#         indicators["BB_Lower"] = mid - std * sd
#         indicators["BB_Mid"] = mid

#     if "MACD" in inds:
#         fast = params["MACD"]["fast"]
#         slow = params["MACD"]["slow"]
#         sig = params["MACD"]["signal"]
#         ema_fast = close.ewm(span=fast, adjust=False).mean()
#         ema_slow = close.ewm(span=slow, adjust=False).mean()
#         macd_line = ema_fast - ema_slow
#         signal_line = macd_line.ewm(span=sig, adjust=False).mean()
#         indicators["MACD"] = macd_line
#         indicators["Signal"] = signal_line
#         indicators["Hist"] = macd_line - signal_line

#     if "Support/Resistance" in inds:
#         lb = params["Support/Resistance"]["lookback"]
#         tol = params["Support/Resistance"]["tolerance"]
#         indicators["Support"] = df["Low"].rolling(lb, min_periods=lb).min() * (1 + tol)
#         indicators["Resistance"] = df["High"].rolling(lb, min_periods=lb).max() * (1 - tol)

#     # REVERSED: Bullish = down → RED, Bearish = up → GREEN
#     if symbol in bull_df["symbol"].values:
#         signal, color = "Bullish", "red"      # down
#     elif symbol in bear_df["symbol"].values:
#         signal, color = "Bearish", "green"    # up
#     else:
#         signal, color = "Neutral", "gray"

#     fig = make_subplots(
#         rows=3, cols=1,
#         shared_xaxes=True,
#         vertical_spacing=0.05,
#         subplot_titles=("Candlestick + Indicators", "MACD", "RSI"),
#         row_heights=[0.6, 0.2, 0.2]
#     )

#     fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Price"), row=1, col=1)

#     if "SMA" in indicators:
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["SMA"], name="SMA", line=dict(color="orange")), row=1, col=1)

#     if "BB_Upper" in indicators:
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["BB_Upper"], name="BB Upper", line=dict(color="gray", dash="dot")), row=1, col=1)
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["BB_Lower"], name="BB Lower", line=dict(color="gray", dash="dot"), fill="tonexty"), row=1, col=1)

#     if "Support" in indicators:
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["Support"], name="Support", line=dict(color="green", dash="dash")), row=1, col=1)
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["Resistance"], name="Resistance", line=dict(color="red", dash="dash")), row=1, col=1)

#     if "MACD" in indicators:
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["MACD"], name="MACD"), row=2, col=1)
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["Signal"], name="Signal"), row=2, col=1)
#         fig.add_trace(go.Bar(x=df.index, y=indicators["Hist"], name="Hist"), row=2, col=1)

#     if "RSI" in indicators:
#         fig.add_trace(go.Scatter(x=df.index, y=indicators["RSI"], name="RSI"), row=3, col=1)
#         fig.add_hline(y=70, line_dash="dot", line_color="red", row=3, col=1)
#         fig.add_hline(y=30, line_dash="dot", line_color="green", row=3, col=1)

#     fig.update_layout(
#         height=800,
#         title_text=f"{symbol} - <span style='color:{color}'>{signal}</span> Signal",
#         xaxis_rangeslider_visible=False,
#         template="plotly"
#     )
#     st.plotly_chart(fig, use_container_width=True)

# # -------------------------------------------------
# # UI
# # -------------------------------------------------
# def main():
#     st.set_page_config(page_title="CBOE Screener (Reversed)", layout="wide")
#     st.title("CBOE Optionable Stock Screener (Reversed Logic)")
#     st.caption("**'Bullish' = Likely DOWN | 'Bearish' = Likely UP**")

#     # === CONTROLS ===
#     col1, col2 = st.columns(2)
#     with col1:
#         min_vol = st.number_input("Min Avg Daily Volume", 100_000, 5_000_000, 500_000, 50_000)
#     with col2:
#         dry_run = st.checkbox("Dry Run (first 30 symbols)", value=True)

#     st.subheader("Technical Indicators")
#     all_inds = ["RSI", "SMA", "Bollinger Bands (BB)", "MACD", "Support/Resistance"]
#     selected = st.multiselect("Select Indicators", all_inds, default=[])

#     params = {}
#     for i in selected:
#         with st.expander(i, expanded=True):
#             if i == "RSI":
#                 p = st.slider("Period", 5, 50, 14, key="rsi_p")
#                 col_a, col_b = st.columns(2)
#                 with col_a:
#                     st.number_input("Bullish RSI <", 0, 100, 40, key="input_rsi_bull")  # Low RSI
#                 with col_b:
#                     st.number_input("Bearish RSI >", 0, 100, 60, key="input_rsi_bear")  # High RSI
#                 params[i] = {"period": p}
#             elif i == "SMA":
#                 params[i] = {"period": st.slider("Period", 10, 200, 50, key="sma_p")}
#             elif i == "Bollinger Bands (BB)":
#                 p1 = st.slider("Period", 10, 50, 20, key="bb_p")
#                 p2 = st.slider("Std Dev", 1.0, 3.0, 2.0, 0.1, key="bb_sd")
#                 params[i] = {"period": p1, "std_dev": p2}
#             elif i == "MACD":
#                 f = st.slider("Fast EMA", 5, 30, 12, key="macd_f")
#                 s = st.slider("Slow EMA", 20, 50, 26, key="macd_s")
#                 sig = st.slider("Signal EMA", 5, 20, 9, key="macd_sig")
#                 params[i] = {"fast": f, "slow": s, "signal": sig}
#             elif i == "Support/Resistance":
#                 lb = st.slider("Lookback", 10, 60, 20, key="sr_lb")
#                 tol = st.slider("Tolerance (%)", 0.0, 10.0, 2.0, 0.1, key="sr_tol") / 100
#                 params[i] = {"lookback": lb, "tolerance": tol}

#     rsi_bull = st.session_state.get("input_rsi_bull", 40)  # Low RSI → Bullish
#     rsi_bear = st.session_state.get("input_rsi_bear", 60)  # High RSI → Bearish

#     with st.spinner("Loading symbols..."):
#         sym_df = update_symbols()
#     symbols = sym_df["symbol"].dropna().unique().tolist()
#     if dry_run:
#         symbols = symbols[:30]
#         st.info(f"**Dry Run**: {len(symbols)} symbols")
#     else:
#         st.info(f"Scanning **{len(symbols):,}** symbols")

#     if st.button("Start Scan", type="primary"):
#         tuner.__init__()
#         start = time.time()
#         with st.spinner("Scanning..."):
#             df = compute_parallel(symbols, min_vol, selected, params)
#         elapsed = time.time() - start

#         if df.empty:
#             st.warning("No valid stocks.")
#             return

#         df["Close"] = df["symbol"].map(get_last_close)
#         df["Prev Close"] = df["symbol"].map(get_prev_close)
#         change_pct = np.where(
#             df["Prev Close"].notna() & (df["Prev Close"] != 0),
#             ((df["Close"] - df["Prev Close"]) / df["Prev Close"] * 100).round(2),
#             np.nan
#         )
#         df["Change %"] = change_pct
#         df["Avg Volume"] = df["Avg Volume"].apply(lambda x: f"{x:,.0f}")

#         bull_df, bear_df, neutral_df = classify_bull_bear(df, selected, rsi_bull, rsi_bear)

#         total = len(bull_df) + len(bear_df) + len(neutral_df)
#         st.success(
#             f"**Done in {elapsed:.1f}s** – "
#             f"{len(df)} valid | "
#             f"**{len(bull_df)} Bullish (down)** | **{len(bear_df)} Bearish (up)** | {len(neutral_df)} neutral "
#             f"({total} total)"
#         )

#         st.session_state.bull_df = bull_df
#         st.session_state.bear_df = bear_df
#         st.session_state.neutral_df = neutral_df
#         st.session_state.inds = selected
#         st.session_state.params = params

#     # === RESULTS ===
#     if 'bull_df' in st.session_state:
#         st.markdown("---")
#         st.subheader("Results")

#         # === BUILD DISPLAY COLUMNS ===
#         base_cols = ["symbol", "Close", "Change %", "Avg Volume"]
#         indicator_cols = []
#         for ind in st.session_state.inds:
#             if ind == "RSI" and "RSI" in st.session_state.bull_df.columns:
#                 indicator_cols.append("RSI")
#             elif ind == "SMA" and "SMA" in st.session_state.bull_df.columns:
#                 indicator_cols.append("SMA")
#             elif ind == "Bollinger Bands (BB)" and "BB_Mid" in st.session_state.bull_df.columns:
#                 indicator_cols.extend(["BB_Lower", "BB_Mid", "BB_Upper"])
#             elif ind == "MACD" and "MACD" in st.session_state.bull_df.columns:
#                 indicator_cols.extend(["MACD", "Signal", "Hist"])
#             elif ind == "Support/Resistance" and "Support" in st.session_state.bull_df.columns:
#                 indicator_cols.extend(["Support", "Resistance"])
#         display_cols = base_cols + indicator_cols

#         # Search
#         search = st.text_input("Search symbol", "")
#         def filter_df(df):
#             if search:
#                 return df[df["symbol"].str.contains(search, case=False)]
#             return df

#         # === TABLES – REVERSED SORTING ===
#         with st.expander("Bearish Trade Signals", expanded=True):
#             if st.session_state.bull_df.empty:
#                 st.info("No bullish (down) signals.")
#             else:
#                 filtered = filter_df(st.session_state.bull_df)
#                 valid_cols = [c for c in display_cols if c in filtered.columns]
#                 st.dataframe(
#                     filtered[valid_cols].round(2).sort_values("Change %", ascending=True, na_position='last'),  # Most negative first
#                     use_container_width=True
#                 )

#         with st.expander("Bullish Trade Signals", expanded=True):
#             if st.session_state.bear_df.empty:
#                 st.info("No bearish (up) signals.")
#             else:
#                 filtered = filter_df(st.session_state.bear_df)
#                 valid_cols = [c for c in display_cols if c in filtered.columns]
#                 st.dataframe(
#                     filtered[valid_cols].round(2).sort_values("Change %", ascending=False, na_position='last'),  # Most positive first
#                     use_container_width=True
#                 )

#         with st.expander("Neutral", expanded=False):
#             if st.session_state.neutral_df.empty:
#                 st.info("No neutral signals.")
#             else:
#                 filtered = filter_df(st.session_state.neutral_df)
#                 valid_cols = [c for c in display_cols if c in filtered.columns]
#                 st.dataframe(filtered[valid_cols].head(20).round(2), use_container_width=True)

#         # === CHART ===
#         st.markdown("---")
#         st.subheader("Interactive Chart Viewer")
#         col_a, col_b, col_c = st.columns(3)
#         with col_a:
#             bull_sym = st.selectbox("Bearish Trades", options=[""] + st.session_state.bull_df["symbol"].tolist())
#         with col_b:
#             bear_sym = st.selectbox("Bullish Trades", options=[""] + st.session_state.bear_df["symbol"].tolist())
#         with col_c:
#             neutral_sym = st.selectbox("Neutral", options=[""] + st.session_state.neutral_df["symbol"].tolist())

#         selected_sym = bull_sym or bear_sym or neutral_sym
#         if selected_sym:
#             with st.spinner("Loading chart..."):
#                 plot_interactive_chart(
#                     selected_sym,
#                     st.session_state.inds,
#                     st.session_state.params,
#                     st.session_state.bull_df,
#                     st.session_state.bear_df
#                 )

#     st.caption(f"Data updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} | CBOE list: {len(symbols):,} symbols")

#     if st.button("Clear Cache"):
#         import shutil
#         if os.path.exists(HISTORY_CACHE_DIR):
#             shutil.rmtree(HISTORY_CACHE_DIR)
#         if os.path.exists(PARQUET_FILE):
#             os.remove(PARQUET_FILE)
#         st.success("Cache cleared!")
#         st.rerun()

# if __name__ == "__main__":
#     main()


##### remove search symbol


#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
CBOE Optionable Stock Screener – v10.7 FINAL
- LOGIC REVERSED: Bullish = Likely DOWN, Bearish = Likely UP
- NO SEARCH, NO EXPORT, NO DARK MODE, NO SOUND, NO AUTO-REFRESH
"""

import os
import io
import time
import warnings
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import psutil
import requests
import pandas as pd
import numpy as np
import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# -------------------------------------------------
# CONFIG
# -------------------------------------------------
PARQUET_FILE = "optionable_full.parquet"
HISTORY_CACHE_DIR = "history_cache"
CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"

SCHEMA_VERSION = "10.7"
HISTORY_TTL = 24 * 3600
SYMBOLS_TTL = 7 * 24 * 3600

CPU_COUNT = psutil.cpu_count(logical=False) or 4
MAX_WORKERS = min(CPU_COUNT, 8)
INITIAL_BATCH_SIZE = min(CPU_COUNT * 20, 200)

os.makedirs(HISTORY_CACHE_DIR, exist_ok=True)

# -------------------------------------------------
# SILENCE YFINANCE 404s
# -------------------------------------------------
class YFinanceFilter:
    def __enter__(self):
        self.original_filters = warnings.filters[:]
        warnings.filterwarnings("ignore", category=UserWarning, module="yfinance")
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        warnings.filters = self.original_filters

def yf_safe_history(symbol: str, **kwargs):
    with YFinanceFilter():
        try:
            return yf.Ticker(symbol).history(**kwargs)
        except:
            return pd.DataFrame()

# -------------------------------------------------
# TUNER
# -------------------------------------------------
class Tuner:
    def __init__(self):
        self.rate_limited = 0
        self.last_rate_limit = 0
        self.workers = MAX_WORKERS
        self.batch_size = INITIAL_BATCH_SIZE
        self.success_streak = 0

    def record_failure(self):
        self.rate_limited += 1
        self.last_rate_limit = time.time()
        self.success_streak = 0
        if self.rate_limited > 5:
            self.workers = 1
            self.batch_size = max(10, self.batch_size // 2)
        elif self.rate_limited > 2:
            self.workers = max(1, self.workers // 2)
            self.batch_size = max(20, self.batch_size // 2)

    def record_success(self):
        self.success_streak += 1
        if self.success_streak > 30 and self.workers < MAX_WORKERS:
            self.workers = min(MAX_WORKERS, self.workers + 1)
            self.batch_size = min(INITIAL_BATCH_SIZE, self.batch_size * 2)

tuner = Tuner()

# -------------------------------------------------
# CACHE
# -------------------------------------------------
def get_cached_history(symbol: str) -> pd.DataFrame | None:
    path = os.path.join(HISTORY_CACHE_DIR, f"{symbol}.parquet")
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_parquet(path)
        req = ["Open", "High", "Low", "Close", "Volume"]
        if not all(c in df.columns for c in req) or df[req].isna().any().any():
            raise ValueError("corrupt")
        if time.time() - os.path.getmtime(path) > HISTORY_TTL:
            os.remove(path)
            return None
        return df
    except Exception:
        if os.path.exists(path):
            os.remove(path)
        return None

def cache_history(symbol: str, df: pd.DataFrame):
    path = os.path.join(HISTORY_CACHE_DIR, f"{symbol}.parquet")
    try:
        df.to_parquet(path, index=False)
    except Exception:
        pass

def get_last_close(symbol: str) -> float:
    cached = get_cached_history(symbol)
    if cached is not None and not cached.empty:
        return cached["Close"].iloc[-1]
    return np.nan

def get_prev_close(symbol: str) -> float:
    cached = get_cached_history(symbol)
    if cached is not None and len(cached) >= 2:
        return cached["Close"].iloc[-2]
    return np.nan

# -------------------------------------------------
# SYMBOLS
# -------------------------------------------------
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=30))
def fetch_cboe_symbols() -> pd.DataFrame:
    r = requests.get(CBOE_URL, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    col = next((c for c in df.columns if "symbol" in c.lower() or "root" in c.lower()), None)
    if not col:
        raise ValueError("No symbol column")
    df = df[[col]].rename(columns={col: "symbol"})
    df["symbol"] = df["symbol"].str.upper().str.strip()
    df = df.drop_duplicates().assign(
        updated_at=datetime.utcnow().isoformat(),
        schema_version=SCHEMA_VERSION
    )
    return df

def update_symbols() -> pd.DataFrame:
    if os.path.exists(PARQUET_FILE):
        try:
            df = pd.read_parquet(PARQUET_FILE)
            if df["schema_version"].iloc[0] == SCHEMA_VERSION:
                age = (datetime.utcnow() - pd.to_datetime(df["updated_at"].iloc[0])).total_seconds()
                if age < SYMBOLS_TTL:
                    return df
        except: pass
    fresh = fetch_cboe_symbols()
    tmp = PARQUET_FILE + ".tmp"
    fresh.to_parquet(tmp, index=False)
    os.replace(tmp, PARQUET_FILE)
    return fresh

# -------------------------------------------------
# YFINANCE
# -------------------------------------------------
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=30, max=120),
    retry=retry_if_exception_type((requests.RequestException, ValueError)),
)
def fetch_historical_data(symbol: str) -> pd.DataFrame | None:
    cached = get_cached_history(symbol)
    if cached is not None:
        tuner.record_success()
        return cached

    if tuner.rate_limited > 3 and time.time() - tuner.last_rate_limit < 120:
        time.sleep(60)

    try:
        data = yf_safe_history(symbol, period="6mo", interval="1d", raise_errors=True, timeout=15)
        if data.empty:
            return None
        data = data.reset_index()
        data["symbol"] = symbol
        cache_history(symbol, data)
        time.sleep(0.08)
        tuner.record_success()
        return data
    except Exception as e:
        if "429" in str(e) or "rate limit" in str(e).lower():
            tuner.record_failure()
        return None

# -------------------------------------------------
# VECTORIZED INDICATORS
# -------------------------------------------------
def compute_indicators_vectorized(df: pd.DataFrame, inds: list, params: dict) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    out = pd.DataFrame(index=df.index)
    out["Close"] = close

    if "RSI" in inds:
        p = params["RSI"]["period"]
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(p, min_periods=p).mean()
        avg_loss = loss.rolling(p, min_periods=p).mean()
        rs = avg_gain / avg_loss
        out["RSI"] = 100 - (100 / (1 + rs))

    if "SMA" in inds:
        p = params["SMA"]["period"]
        out["SMA"] = close.rolling(p, min_periods=p).mean()

    if "Bollinger Bands (BB)" in inds:
        p = params["Bollinger Bands (BB)"]["period"]
        sd = params["Bollinger Bands (BB)"]["std_dev"]
        mid = close.rolling(p, min_periods=p).mean()
        std = close.rolling(p, min_periods=p).std()
        out["BB_Mid"] = mid
        out["BB_Upper"] = mid + std * sd
        out["BB_Lower"] = mid - std * sd

    if "MACD" in inds:
        fast = params["MACD"]["fast"]
        slow = params["MACD"]["slow"]
        sig = params["MACD"]["signal"]
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=sig, adjust=False).mean()
        out["MACD"] = macd_line
        out["Signal"] = signal_line
        out["Hist"] = macd_line - signal_line

    if "Support/Resistance" in inds:
        lb = params["Support/Resistance"]["lookback"]
        tol = params["Support/Resistance"]["tolerance"]
        sup = low.rolling(lb, min_periods=lb).min() * (1 + tol)
        res = high.rolling(lb, min_periods=lb).max() * (1 - tol)
        out["Support"] = sup
        out["Resistance"] = res

    last = out.groupby(df["symbol"]).tail(1).reset_index(drop=True)
    last["symbol"] = df["symbol"].groupby(df["symbol"]).tail(1).values
    last["Avg Volume"] = df["Volume"].groupby(df["symbol"]).mean().values

    return last

# -------------------------------------------------
# BATCH PROCESSOR
# -------------------------------------------------
def process_batch(symbols: list, min_vol: int, inds: list, params: dict) -> pd.DataFrame:
    data_frames = []
    for sym in symbols:
        hist = fetch_historical_data(sym)
        if hist is not None and len(hist) >= 100:
            data_frames.append(hist)

    if not data_frames:
        return pd.DataFrame()

    df = pd.concat(data_frames, ignore_index=True)

    vol_mean = df.groupby("symbol")["Volume"].mean()
    valid_symbols = vol_mean[vol_mean >= min_vol].index
    df = df[df["symbol"].isin(valid_symbols)]
    if df.empty:
        return pd.DataFrame()

    return compute_indicators_vectorized(df, inds, params)

# -------------------------------------------------
# PARALLEL DRIVER
# -------------------------------------------------
def compute_parallel(symbols: list, min_vol: int, inds: list, params: dict) -> pd.DataFrame:
    batch_size = tuner.batch_size
    batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
    results = []

    with ThreadPoolExecutor(max_workers=tuner.workers) as pool:
        futures = [pool.submit(process_batch, b, min_vol, inds, params) for b in batches]
        prog = st.progress(0)
        status = st.empty()
        for i, f in enumerate(as_completed(futures), 1):
            batch_res = f.result()
            if not batch_res.empty:
                results.append(batch_res)
            prog.progress(i / len(futures))
            status.text(
                f"Workers: {tuner.workers} | Batch: {batch_size} | "
                f"Valid: {sum(len(r) for r in results)}"
            )

    return pd.concat(results, ignore_index=True) if results else pd.DataFrame()

# -------------------------------------------------
# CLASSIFIER – REVERSED LOGIC
# -------------------------------------------------
def classify_bull_bear(df: pd.DataFrame, inds: list, rsi_bull: float, rsi_bear: float):
    if df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    close = df["Close"]
    total_indicators = len(inds)
    bull_count = pd.Series(0, index=df.index)  # Bullish = DOWN
    bear_count = pd.Series(0, index=df.index)  # Bearish = UP

    if "RSI" in inds and "RSI" in df.columns:
        bull_count += (df["RSI"] < rsi_bull).astype(int)
        bear_count += (df["RSI"] > rsi_bear).astype(int)

    if "SMA" in inds and "SMA" in df.columns:
        bull_count += (close < df["SMA"]).astype(int)
        bear_count += (close > df["SMA"]).astype(int)

    if "Bollinger Bands (BB)" in inds and "BB_Lower" in df.columns and "BB_Upper" in df.columns:
        bull_count += (close < df["BB_Lower"]).astype(int)
        bear_count += (close > df["BB_Upper"]).astype(int)

    if "MACD" in inds and "MACD" in df.columns and "Signal" in df.columns:
        bull_count += (df["MACD"] < df["Signal"]).astype(int)
        bear_count += (df["MACD"] > df["Signal"]).astype(int)

    if "Support/Resistance" in inds and "Support" in df.columns and "Resistance" in df.columns:
        bull_count += (close < df["Support"]).astype(int)
        bear_count += (close > df["Resistance"]).astype(int)

    bull_mask = (bull_count == total_indicators) & (total_indicators > 0)
    bear_mask = (bear_count == total_indicators) & (total_indicators > 0)
    neutral_mask = ~(bull_mask | bear_mask)

    return (
        df[bull_mask].copy(),
        df[bear_mask].copy(),
        df[neutral_mask].copy()
    )

# -------------------------------------------------
# INTERACTIVE CHART – REVERSED COLORS
# -------------------------------------------------
def plot_interactive_chart(symbol: str, inds: list, params: dict, bull_df, bear_df):
    hist = fetch_historical_data(symbol)
    if hist is None or hist.empty:
        st.error(f"No data for {symbol}")
        return

    df = hist.copy()
    close = df["Close"]

    indicators = {}
    if "RSI" in inds:
        p = params["RSI"]["period"]
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(p, min_periods=p).mean()
        avg_loss = loss.rolling(p, min_periods=p).mean()
        rs = avg_gain / avg_loss
        indicators["RSI"] = 100 - (100 / (1 + rs))

    if "SMA" in inds:
        p = params["SMA"]["period"]
        indicators["SMA"] = close.rolling(p, min_periods=p).mean()

    if "Bollinger Bands (BB)" in inds:
        p = params["Bollinger Bands (BB)"]["period"]
        sd = params["Bollinger Bands (BB)"]["std_dev"]
        mid = close.rolling(p, min_periods=p).mean()
        std = close.rolling(p, min_periods=p).std()
        indicators["BB_Upper"] = mid + std * sd
        indicators["BB_Lower"] = mid - std * sd
        indicators["BB_Mid"] = mid

    if "MACD" in inds:
        fast = params["MACD"]["fast"]
        slow = params["MACD"]["slow"]
        sig = params["MACD"]["signal"]
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=sig, adjust=False).mean()
        indicators["MACD"] = macd_line
        indicators["Signal"] = signal_line
        indicators["Hist"] = macd_line - signal_line

    if "Support/Resistance" in inds:
        lb = params["Support/Resistance"]["lookback"]
        tol = params["Support/Resistance"]["tolerance"]
        indicators["Support"] = df["Low"].rolling(lb, min_periods=lb).min() * (1 + tol)
        indicators["Resistance"] = df["High"].rolling(lb, min_periods=lb).max() * (1 - tol)

    if symbol in bull_df["symbol"].values:
        signal, color = "Bullish", "red"
    elif symbol in bear_df["symbol"].values:
        signal, color = "Bearish", "green"
    else:
        signal, color = "Neutral", "gray"

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=("Candlestick + Indicators", "MACD", "RSI"),
        row_heights=[0.6, 0.2, 0.2]
    )

    fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Price"), row=1, col=1)

    if "SMA" in indicators:
        fig.add_trace(go.Scatter(x=df.index, y=indicators["SMA"], name="SMA", line=dict(color="orange")), row=1, col=1)

    if "BB_Upper" in indicators:
        fig.add_trace(go.Scatter(x=df.index, y=indicators["BB_Upper"], name="BB Upper", line=dict(color="gray", dash="dot")), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=indicators["BB_Lower"], name="BB Lower", line=dict(color="gray", dash="dot"), fill="tonexty"), row=1, col=1)

    if "Support" in indicators:
        fig.add_trace(go.Scatter(x=df.index, y=indicators["Support"], name="Support", line=dict(color="green", dash="dash")), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=indicators["Resistance"], name="Resistance", line=dict(color="red", dash="dash")), row=1, col=1)

    if "MACD" in indicators:
        fig.add_trace(go.Scatter(x=df.index, y=indicators["MACD"], name="MACD"), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=indicators["Signal"], name="Signal"), row=2, col=1)
        fig.add_trace(go.Bar(x=df.index, y=indicators["Hist"], name="Hist"), row=2, col=1)

    if "RSI" in indicators:
        fig.add_trace(go.Scatter(x=df.index, y=indicators["RSI"], name="RSI"), row=3, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="red", row=3, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="green", row=3, col=1)

    fig.update_layout(
        height=800,
        title_text=f"{symbol} - <span style='color:{color}'>{signal}</span> Signal",
        xaxis_rangeslider_visible=False,
        template="plotly"
    )
    st.plotly_chart(fig, use_container_width=True)

# -------------------------------------------------
# UI – NO SEARCH
# -------------------------------------------------
def main():
    st.set_page_config(page_title="CBOE Screener (Reversed)", layout="wide")
    st.title("CBOE Optionable Stock Screener (Reversed Logic)")
    st.caption("**'Bullish' = Likely DOWN | 'Bearish' = Likely UP**")

    # === CONTROLS ===
    col1, col2 = st.columns(2)
    with col1:
        min_vol = st.number_input("Min Avg Daily Volume", 100_000, 5_000_000, 500_000, 50_000)
    with col2:
        dry_run = st.checkbox("Dry Run (first 30 symbols)", value=True)

    st.subheader("Technical Indicators")
    all_inds = ["RSI", "SMA", "Bollinger Bands (BB)", "MACD", "Support/Resistance"]
    selected = st.multiselect("Select Indicators", all_inds, default=[])

    params = {}
    for i in selected:
        with st.expander(i, expanded=True):
            if i == "RSI":
                p = st.slider("Period", 5, 50, 14, key="rsi_p")
                col_a, col_b = st.columns(2)
                with col_a:
                    st.number_input("Bullish RSI <", 0, 100, 30, key="input_rsi_bull")
                with col_b:
                    st.number_input("Bearish RSI >", 0, 100, 70, key="input_rsi_bear")
                params[i] = {"period": p}
            elif i == "SMA":
                params[i] = {"period": st.slider("Period", 10, 200, 50, key="sma_p")}
            elif i == "Bollinger Bands (BB)":
                p1 = st.slider("Period", 10, 50, 20, key="bb_p")
                p2 = st.slider("Std Dev", 1.0, 3.0, 2.0, 0.1, key="bb_sd")
                params[i] = {"period": p1, "std_dev": p2}
            elif i == "MACD":
                f = st.slider("Fast EMA", 5, 30, 12, key="macd_f")
                s = st.slider("Slow EMA", 20, 50, 26, key="macd_s")
                sig = st.slider("Signal EMA", 5, 20, 9, key="macd_sig")
                params[i] = {"fast": f, "slow": s, "signal": sig}
            elif i == "Support/Resistance":
                lb = st.slider("Lookback", 10, 60, 20, key="sr_lb")
                tol = st.slider("Tolerance (%)", 0.0, 10.0, 2.0, 0.1, key="sr_tol") / 100
                params[i] = {"lookback": lb, "tolerance": tol}

    rsi_bull = st.session_state.get("input_rsi_bull", 40)
    rsi_bear = st.session_state.get("input_rsi_bear", 60)

    with st.spinner("Loading symbols..."):
        sym_df = update_symbols()
    symbols = sym_df["symbol"].dropna().unique().tolist()
    if dry_run:
        symbols = symbols[:30]
        st.info(f"**Dry Run**: {len(symbols)} symbols")
    else:
        st.info(f"Scanning **{len(symbols):,}** symbols")

    if st.button("Start Scan", type="primary"):
        tuner.__init__()
        start = time.time()
        with st.spinner("Scanning..."):
            df = compute_parallel(symbols, min_vol, selected, params)
        elapsed = time.time() - start

        if df.empty:
            st.warning("No valid stocks.")
            return

        df["Close"] = df["symbol"].map(get_last_close)
        df["Prev Close"] = df["symbol"].map(get_prev_close)
        change_pct = np.where(
            df["Prev Close"].notna() & (df["Prev Close"] != 0),
            ((df["Close"] - df["Prev Close"]) / df["Prev Close"] * 100).round(2),
            np.nan
        )
        df["Change %"] = change_pct
        df["Avg Volume"] = df["Avg Volume"].apply(lambda x: f"{x:,.0f}")

        bull_df, bear_df, neutral_df = classify_bull_bear(df, selected, rsi_bull, rsi_bear)

        total = len(bull_df) + len(bear_df) + len(neutral_df)
        st.success(
            f"**Done in {elapsed:.1f}s** – "
            f"{len(df)} valid | "
            f"**{len(bull_df)} Bullish (down)** | **{len(bear_df)} Bearish (up)** | {len(neutral_df)} neutral "
            f"({total} total)"
        )

        st.session_state.bull_df = bull_df
        st.session_state.bear_df = bear_df
        st.session_state.neutral_df = neutral_df
        st.session_state.inds = selected
        st.session_state.params = params

    # === RESULTS – NO SEARCH ===
    if 'bull_df' in st.session_state:
        st.markdown("---")
        st.subheader("Results")

        base_cols = ["symbol", "Close", "Change %", "Avg Volume"]
        indicator_cols = []
        for ind in st.session_state.inds:
            if ind == "RSI" and "RSI" in st.session_state.bull_df.columns:
                indicator_cols.append("RSI")
            elif ind == "SMA" and "SMA" in st.session_state.bull_df.columns:
                indicator_cols.append("SMA")
            elif ind == "Bollinger Bands (BB)" and "BB_Mid" in st.session_state.bull_df.columns:
                indicator_cols.extend(["BB_Lower", "BB_Mid", "BB_Upper"])
            elif ind == "MACD" and "MACD" in st.session_state.bull_df.columns:
                indicator_cols.extend(["MACD", "Signal", "Hist"])
            elif ind == "Support/Resistance" and "Support" in st.session_state.bull_df.columns:
                indicator_cols.extend(["Support", "Resistance"])
        display_cols = base_cols + indicator_cols

        with st.expander("Bullish Trade Signals", expanded=True):
            if st.session_state.bull_df.empty:
                st.info("No Bullish Trade Signals.")
            else:
                valid_cols = [c for c in display_cols if c in st.session_state.bull_df.columns]
                st.dataframe(
                    st.session_state.bull_df[valid_cols].round(2).sort_values("Change %", ascending=True, na_position='last'),
                    use_container_width=True
                )

        with st.expander("Bearish Trade Signals", expanded=True):
            if st.session_state.bear_df.empty:
                st.info("No Bearish Trade Signals.")
            else:
                valid_cols = [c for c in display_cols if c in st.session_state.bear_df.columns]
                st.dataframe(
                    st.session_state.bear_df[valid_cols].round(2).sort_values("Change %", ascending=False, na_position='last'),
                    use_container_width=True
                )

        with st.expander("Neutral", expanded=False):
            if st.session_state.neutral_df.empty:
                st.info("No neutral signals.")
            else:
                valid_cols = [c for c in display_cols if c in st.session_state.neutral_df.columns]
                st.dataframe(st.session_state.neutral_df[valid_cols].head(20).round(2), use_container_width=True)

        # === CHART ===
        st.markdown("---")
        st.subheader("Interactive Chart Viewer")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            bull_sym = st.selectbox("Bullish Trade Signals", options=[""] + st.session_state.bull_df["symbol"].tolist())
        with col_b:
            bear_sym = st.selectbox("Bearish Trade Signals", options=[""] + st.session_state.bear_df["symbol"].tolist())
        with col_c:
            neutral_sym = st.selectbox("Neutral", options=[""] + st.session_state.neutral_df["symbol"].tolist())

        selected_sym = bull_sym or bear_sym or neutral_sym
        if selected_sym:
            with st.spinner("Loading chart..."):
                plot_interactive_chart(
                    selected_sym,
                    st.session_state.inds,
                    st.session_state.params,
                    st.session_state.bull_df,
                    st.session_state.bear_df
                )

    st.caption(f"Data updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} | CBOE list: {len(symbols):,} symbols")

    if st.button("Clear Cache"):
        import shutil
        if os.path.exists(HISTORY_CACHE_DIR):
            shutil.rmtree(HISTORY_CACHE_DIR)
        if os.path.exists(PARQUET_FILE):
            os.remove(PARQUET_FILE)
        st.success("Cache cleared!")
        st.rerun()

if __name__ == "__main__":
    main()