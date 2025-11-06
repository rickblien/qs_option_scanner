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


# #!/usr/bin/env python
# # -*- coding: utf-8 -*-

# """
# CBOE Optionable Stock Screener – v10.7 FINAL
# - LOGIC REVERSED: Bullish = Likely DOWN, Bearish = Likely UP
# - NO SEARCH, NO EXPORT, NO DARK MODE, NO SOUND, NO AUTO-REFRESH
# """

# import os
# import io
# import time
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

# SCHEMA_VERSION = "10.7"
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
#     bull_count = pd.Series(0, index=df.index)  # Bullish = DOWN
#     bear_count = pd.Series(0, index=df.index)  # Bearish = UP

#     if "RSI" in inds and "RSI" in df.columns:
#         bull_count += (df["RSI"] < rsi_bull).astype(int)
#         bear_count += (df["RSI"] > rsi_bear).astype(int)

#     if "SMA" in inds and "SMA" in df.columns:
#         bull_count += (close < df["SMA"]).astype(int)
#         bear_count += (close > df["SMA"]).astype(int)

#     if "Bollinger Bands (BB)" in inds and "BB_Lower" in df.columns and "BB_Upper" in df.columns:
#         bull_count += (close < df["BB_Lower"]).astype(int)
#         bear_count += (close > df["BB_Upper"]).astype(int)

#     if "MACD" in inds and "MACD" in df.columns and "Signal" in df.columns:
#         bull_count += (df["MACD"] < df["Signal"]).astype(int)
#         bear_count += (df["MACD"] > df["Signal"]).astype(int)

#     if "Support/Resistance" in inds and "Support" in df.columns and "Resistance" in df.columns:
#         bull_count += (close < df["Support"]).astype(int)
#         bear_count += (close > df["Resistance"]).astype(int)

#     bull_mask = (bull_count == total_indicators) & (total_indicators > 0)
#     bear_mask = (bear_count == total_indicators) & (total_indicators > 0)
#     neutral_mask = ~(bull_mask | bear_mask)

#     return (
#         df[bull_mask].copy(),
#         df[bear_mask].copy(),
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

#     if symbol in bull_df["symbol"].values:
#         signal, color = "Bullish", "red"
#     elif symbol in bear_df["symbol"].values:
#         signal, color = "Bearish", "green"
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
# # UI – NO SEARCH
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
#                     st.number_input("Bullish RSI <", 0, 100, 30, key="input_rsi_bull")
#                 with col_b:
#                     st.number_input("Bearish RSI >", 0, 100, 70, key="input_rsi_bear")
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

#     rsi_bull = st.session_state.get("input_rsi_bull", 40)
#     rsi_bear = st.session_state.get("input_rsi_bear", 60)

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

#     # === RESULTS – NO SEARCH ===
#     if 'bull_df' in st.session_state:
#         st.markdown("---")
#         st.subheader("Results")

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

#         with st.expander("Bullish Trade Signals", expanded=True):
#             if st.session_state.bull_df.empty:
#                 st.info("No Bullish Trade Signals.")
#             else:
#                 valid_cols = [c for c in display_cols if c in st.session_state.bull_df.columns]
#                 st.dataframe(
#                     st.session_state.bull_df[valid_cols].round(2).sort_values("Change %", ascending=True, na_position='last'),
#                     use_container_width=True
#                 )

#         with st.expander("Bearish Trade Signals", expanded=True):
#             if st.session_state.bear_df.empty:
#                 st.info("No Bearish Trade Signals.")
#             else:
#                 valid_cols = [c for c in display_cols if c in st.session_state.bear_df.columns]
#                 st.dataframe(
#                     st.session_state.bear_df[valid_cols].round(2).sort_values("Change %", ascending=False, na_position='last'),
#                     use_container_width=True
#                 )

#         with st.expander("Neutral", expanded=False):
#             if st.session_state.neutral_df.empty:
#                 st.info("No neutral signals.")
#             else:
#                 valid_cols = [c for c in display_cols if c in st.session_state.neutral_df.columns]
#                 st.dataframe(st.session_state.neutral_df[valid_cols].head(20).round(2), use_container_width=True)

#         # === CHART ===
#         st.markdown("---")
#         st.subheader("Interactive Chart Viewer")
#         col_a, col_b, col_c = st.columns(3)
#         with col_a:
#             bull_sym = st.selectbox("Bullish Trade Signals", options=[""] + st.session_state.bull_df["symbol"].tolist())
#         with col_b:
#             bear_sym = st.selectbox("Bearish Trade Signals", options=[""] + st.session_state.bear_df["symbol"].tolist())
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

##### add backktest features

# #!/usr/bin/env python
# # -*- coding: utf-8 -*-

# """
# CBOE Optionable Stock Screener – v10.10 FINAL
# - LOGIC REVERSED: Bullish = DOWN, Bearish = UP
# - BACKTEST FIXED: NO SERIES AMBIGUITY
# - SCALAR-ONLY COMPARISONS
# """

# import os
# import io
# import time
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

# SCHEMA_VERSION = "10.10"
# HISTORY_TTL = 24 * 3600
# SYMBOLS_TTL = 7 * 24 * 3600

# CPU_COUNT = psutil.cpu_count(logical=False) or 4
# MAX_WORKERS = min(CPU_COUNT, 8)
# INITIAL_BATCH_SIZE = min(CPU_COUNT * 20, 200)

# os.makedirs(HISTORY_CACHE_DIR, exist_ok=True)

# # -------------------------------------------------
# # SILENCE YFINANCE
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
# def get_cached_history(symbol: str, period: str = "6mo") -> pd.DataFrame | None:
#     path = os.path.join(HISTORY_CACHE_DIR, f"{symbol}_{period}.parquet")
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

# def cache_history(symbol: str, df: pd.DataFrame, period: str):
#     path = os.path.join(HISTORY_CACHE_DIR, f"{symbol}_{period}.parquet")
#     try:
#         df.to_parquet(path, index=False)
#     except Exception:
#         pass

# def get_last_close(symbol: str) -> float:
#     cached = get_cached_history(symbol, "6mo")
#     if cached is not None and not cached.empty:
#         return cached["Close"].iloc[-1]
#     return np.nan

# def get_prev_close(symbol: str) -> float:
#     cached = get_cached_history(symbol, "6mo")
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
# def fetch_historical_data(symbol: str, period: str = "6mo") -> pd.DataFrame | None:
#     cached = get_cached_history(symbol, period)
#     if cached is not None:
#         tuner.record_success()
#         return cached

#     try:
#         data = yf_safe_history(symbol, period=period, interval="1d", raise_errors=True, timeout=15)
#         if data.empty:
#             return None
#         data = data.reset_index()
#         data["symbol"] = symbol
#         cache_history(symbol, data, period)
#         time.sleep(0.08)
#         tuner.record_success()
#         return data
#     except Exception as e:
#         if "429" in str(e) or "rate limit" in str(e).lower():
#             tuner.record_failure()
#         return None

# # -------------------------------------------------
# # INDICATORS
# # -------------------------------------------------
# def compute_indicators(df: pd.DataFrame, inds: list, params: dict) -> pd.DataFrame:
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

#     if "Support/Resistance" in inds:
#         lb = params["Support/Resistance"]["lookback"]
#         tol = params["Support/Resistance"]["tolerance"]
#         out["Support"] = low.rolling(lb, min_periods=lb).min() * (1 + tol)
#         out["Resistance"] = high.rolling(lb, min_periods=lb).max() * (1 - tol)

#     return out

# # -------------------------------------------------
# # BACKTEST – SCALAR-ONLY (FIXED)
# # -------------------------------------------------
# def backtest_symbol(symbol: str, inds: list, params: dict, rsi_bull: float, rsi_bear: float,
#                    backtest_period: str, forward_days: int, min_trades: int, min_accuracy: float) -> dict:
#     hist = fetch_historical_data(symbol, period=backtest_period)
#     if hist is None or len(hist) < 100:
#         return {"symbol": symbol, "valid": False}

#     df = hist.copy()
#     indicators = compute_indicators(df, inds, params)
#     df = pd.concat([df[["Close"]], indicators], axis=1).dropna().reset_index(drop=True)

#     if df.empty or len(df) <= forward_days:
#         return {"symbol": symbol, "valid": False}

#     close = df["Close"]
#     total_indicators = len(inds)
#     bull_signals = []
#     bear_signals = []

#     for i in range(len(df) - forward_days):
#         bull_count = 0
#         bear_count = 0

#         # Use .iloc[i] + .item() for guaranteed scalar
#         if "RSI" in inds and pd.notna(df.iloc[i]["RSI"]):
#             rsi_val = df.iloc[i]["RSI"].item()
#             if rsi_val < rsi_bull: bull_count += 1
#             if rsi_val > rsi_bear: bear_count += 1

#         if "SMA" in inds and pd.notna(df.iloc[i]["SMA"]):
#             sma_val = df.iloc[i]["SMA"].item()
#             close_val = close.iloc[i].item()
#             if close_val < sma_val: bull_count += 1
#             if close_val > sma_val: bear_count += 1

#         if "Bollinger Bands (BB)" in inds and pd.notna(df.iloc[i]["BB_Lower"]) and pd.notna(df.iloc[i]["BB_Upper"]):
#             lower = df.iloc[i]["BB_Lower"].item()
#             upper = df.iloc[i]["BB_Upper"].item()
#             close_val = close.iloc[i].item()
#             if close_val < lower: bull_count += 1
#             if close_val > upper: bear_count += 1

#         if "MACD" in inds and pd.notna(df.iloc[i]["MACD"]) and pd.notna(df.iloc[i]["Signal"]):
#             macd = df.iloc[i]["MACD"].item()
#             signal = df.iloc[i]["Signal"].item()
#             if macd < signal: bull_count += 1
#             if macd > signal: bear_count += 1

#         if "Support/Resistance" in inds and pd.notna(df.iloc[i]["Support"]) and pd.notna(df.iloc[i]["Resistance"]):
#             support = df.iloc[i]["Support"].item()
#             resistance = df.iloc[i]["Resistance"].item()
#             close_val = close.iloc[i].item()
#             if close_val < support: bull_count += 1
#             if close_val > resistance: bear_count += 1

#         if bull_count == total_indicators and total_indicators > 0:
#             future_return = (close.iloc[i + forward_days].item() - close.iloc[i].item()) / close.iloc[i].item()
#             bull_signals.append(future_return < 0)

#         if bear_count == total_indicators and total_indicators > 0:
#             future_return = (close.iloc[i + forward_days].item() - close.iloc[i].item()) / close.iloc[i].item()
#             bear_signals.append(future_return > 0)

#     bull_accuracy = np.mean(bull_signals) if bull_signals else 0
#     bear_accuracy = np.mean(bear_signals) if bear_signals else 0

#     valid_bull = len(bull_signals) >= min_trades and bull_accuracy >= min_accuracy
#     valid_bear = len(bear_signals) >= min_trades and bear_accuracy >= min_accuracy

#     return {
#         "symbol": symbol,
#         "valid": True,
#         "bull_accuracy": bull_accuracy,
#         "bear_accuracy": bear_accuracy,
#         "bull_trades": len(bull_signals),
#         "bear_trades": len(bear_signals),
#         "valid_bull": valid_bull,
#         "valid_bear": valid_bear
#     }

# # -------------------------------------------------
# # PARALLEL BACKTEST
# # -------------------------------------------------
# def run_backtest_parallel(symbols: list, inds: list, params: dict, rsi_bull: float, rsi_bear: float,
#                           backtest_period: str, forward_days: int, min_trades: int, min_accuracy: float) -> pd.DataFrame:
#     results = []
#     with ThreadPoolExecutor(max_workers=min(4, tuner.workers)) as pool:
#         futures = [
#             pool.submit(backtest_symbol, sym, inds, params, rsi_bull, rsi_bear,
#                         backtest_period, forward_days, min_trades, min_accuracy)
#             for sym in symbols
#         ]
#         prog = st.progress(0)
#         for i, f in enumerate(as_completed(futures), 1):
#             res = f.result()
#             if res["valid"]:
#                 results.append(res)
#             prog.progress(i / len(futures))
#     return pd.DataFrame(results) if results else pd.DataFrame()

# # -------------------------------------------------
# # LIVE SCAN
# # -------------------------------------------------
# def compute_live_scan(symbols: list, min_vol: int, inds: list, params: dict) -> pd.DataFrame:
#     data_frames = []
#     for sym in symbols:
#         hist = fetch_historical_data(sym, period="6mo")
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

#     indicators = compute_indicators(df, inds, params)
#     df = pd.concat([df[["Close", "Volume", "symbol"]], indicators], axis=1).dropna()
#     last = df.groupby("symbol").tail(1).reset_index(drop=True)
#     last["Avg Volume"] = df.groupby("symbol")["Volume"].mean().values
#     return last

# # -------------------------------------------------
# # CLASSIFIER WITH BACKTEST (SCALAR-SAFE)
# # -------------------------------------------------
# def classify_with_backtest(live_df: pd.DataFrame, backtest_df: pd.DataFrame, inds: list,
#                            rsi_bull: float, rsi_bear: float) -> tuple:
#     if live_df.empty:
#         return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

#     total_indicators = len(inds)
#     bull_mask = []
#     bear_mask = []

#     for i in range(len(live_df)):
#         row = live_df.iloc[i]
#         bull_count = 0
#         bear_count = 0

#         if "RSI" in inds and pd.notna(row["RSI"]):
#             if row["RSI"].item() < rsi_bull: bull_count += 1
#             if row["RSI"].item() > rsi_bear: bear_count += 1

#         if "SMA" in inds and pd.notna(row["SMA"]):
#             close_val = row["Close"].item()
#             sma_val = row["SMA"].item()
#             if close_val < sma_val: bull_count += 1
#             if close_val > sma_val: bear_count += 1

#         if "Bollinger Bands (BB)" in inds and pd.notna(row["BB_Lower"]) and pd.notna(row["BB_Upper"]):
#             close_val = row["Close"].item()
#             if close_val < row["BB_Lower"].item(): bull_count += 1
#             if close_val > row["BB_Upper"].item(): bear_count += 1

#         if "MACD" in inds and pd.notna(row["MACD"]) and pd.notna(row["Signal"]):
#             if row["MACD"].item() < row["Signal"].item(): bull_count += 1
#             if row["MACD"].item() > row["Signal"].item(): bear_count += 1

#         if "Support/Resistance" in inds and pd.notna(row["Support"]) and pd.notna(row["Resistance"]):
#             close_val = row["Close"].item()
#             if close_val < row["Support"].item(): bull_count += 1
#             if close_val > row["Resistance"].item(): bear_count += 1

#         sym = row["symbol"]
#         bt = backtest_df[backtest_df["symbol"] == sym]

#         is_bull = (bull_count == total_indicators and total_indicators > 0 and
#                    not bt.empty and bt["valid_bull"].iloc[0])
#         is_bear = (bear_count == total_indicators and total_indicators > 0 and
#                    not bt.empty and bt["valid_bear"].iloc[0])

#         bull_mask.append(is_bull)
#         bear_mask.append(is_bear)

#     bull_df = live_df[bull_mask].copy()
#     bear_df = live_df[bear_mask].copy()
#     neutral_df = live_df[~(pd.Series(bull_mask) | pd.Series(bear_mask))].copy()

#     return bull_df, bear_df, neutral_df

# # -------------------------------------------------
# # CHART (unchanged)
# # -------------------------------------------------
# def plot_interactive_chart(symbol: str, inds: list, params: dict, bull_df, bear_df):
#     hist = fetch_historical_data(symbol, "6mo")
#     if hist is None or hist.empty:
#         st.error(f"No data for {symbol}")
#         return

#     df = hist.copy()
#     indicators = compute_indicators(df, inds, params)
#     df = pd.concat([df[["Close", "Open", "High", "Low"]], indicators], axis=1).dropna()

#     if symbol in bull_df["symbol"].values:
#         signal, color = "Bullish", "red"
#     elif symbol in bear_df["symbol"].values:
#         signal, color = "Bearish", "green"
#     else:
#         signal, color = "Neutral", "gray"

#     fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
#                         subplot_titles=("Price", "MACD", "RSI"), row_heights=[0.6, 0.2, 0.2])

#     fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Price"), row=1, col=1)

#     if "SMA" in inds and "SMA" in df.columns:
#         fig.add_trace(go.Scatter(x=df.index, y=df["SMA"], name="SMA", line=dict(color="orange")), row=1, col=1)

#     if "Bollinger Bands (BB)" in inds:
#         fig.add_trace(go.Scatter(x=df.index, y=df["BB_Upper"], name="BB Upper", line=dict(color="gray", dash="dot")), row=1, col=1)
#         fig.add_trace(go.Scatter(x=df.index, y=df["BB_Lower"], name="BB Lower", line=dict(color="gray", dash="dot"), fill="tonexty"), row=1, col=1)

#     if "MACD" in inds:
#         fig.add_trace(go.Scatter(x=df.index, y=df["MACD"], name="MACD"), row=2, col=1)
#         fig.add_trace(go.Scatter(x=df.index, y=df["Signal"], name="Signal"), row=2, col=1)

#     if "RSI" in inds:
#         fig.add_trace(go.Scatter(x=df.index, y=df["RSI"], name="RSI"), row=3, col=1)
#         fig.add_hline(y=70, line_dash="dot", line_color="red", row=3, col=1)
#         fig.add_hline(y=30, line_dash="dot", line_color="green", row=3, col=1)

#     fig.update_layout(height=800, title_text=f"{symbol} - <span style='color:{color}'>{signal}</span>", template="plotly")
#     st.plotly_chart(fig, use_container_width=True)

# # -------------------------------------------------
# # UI
# # -------------------------------------------------
# def main():
#     st.set_page_config(page_title="CBOE Screener + Backtest", layout="wide")
#     st.title("CBOE Optionable Stock Screener + Backtest")
#     st.caption("**'Bullish' = Likely DOWN | 'Bearish' = Likely UP | Backtested Accuracy**")

#     col1, col2 = st.columns(2)
#     with col1:
#         min_vol = st.number_input("Min Avg Daily Volume", 100_000, 5_000_000, 500_000, 50_000)
#     with col2:
#         dry_run = st.checkbox("Dry Run (first 30 symbols)", value=True)

#     st.subheader("Backtest Settings")
#     col_a, col_b = st.columns(2)
#     with col_a:
#         backtest_period = st.selectbox("Backtest Period", ["3mo", "6mo", "1y"], index=1)
#         forward_days = st.slider("Forward Return (days)", 1, 30, 5)
#     with col_b:
#         min_trades = st.slider("Min Historical Trades", 3, 20, 5)
#         min_accuracy = st.slider("Min Accuracy %", 50, 100, 70) / 100

#     st.subheader("Technical Indicators")
#     all_inds = ["RSI", "SMA", "Bollinger Bands (BB)", "MACD", "Support/Resistance"]
#     selected = st.multiselect("Select Indicators", all_inds, default=[])

#     params = {}
#     for i in selected:
#         with st.expander(i, expanded=True):
#             if i == "RSI":
#                 p = st.slider("Period", 5, 50, 14, key="rsi_p")
#                 col_a, col_b = st.columns(2)
#                 with col_a: st.number_input("Bullish RSI <", 0, 100, 40, key="input_rsi_bull")
#                 with col_b: st.number_input("Bearish RSI >", 0, 100, 60, key="input_rsi_bear")
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

#     rsi_bull = st.session_state.get("input_rsi_bull", 40)
#     rsi_bear = st.session_state.get("input_rsi_bear", 60)

#     with st.spinner("Loading symbols..."):
#         sym_df = update_symbols()
#     symbols = sym_df["symbol"].dropna().unique().tolist()
#     if dry_run:
#         symbols = symbols[:30]
#         st.info(f"**Dry Run**: {len(symbols)} symbols")
#     else:
#         st.info(f"Scanning **{len(symbols):,}** symbols")

#     if st.button("Start Backtest + Scan", type="primary"):
#         tuner.__init__()
#         start = time.time()

#         with st.spinner("Backtesting symbols..."):
#             backtest_df = run_backtest_parallel(
#                 symbols, selected, params, rsi_bull, rsi_bear,
#                 backtest_period, forward_days, min_trades, min_accuracy
#             )

#         with st.spinner("Running live scan..."):
#             live_df = compute_live_scan(symbols, min_vol, selected, params)

#         if live_df.empty:
#             st.warning("No valid stocks in live scan.")
#             return

#         live_df["Close"] = live_df["symbol"].map(get_last_close)
#         live_df["Prev Close"] = live_df["symbol"].map(get_prev_close)
#         change_pct = np.where(
#             live_df["Prev Close"].notna() & (live_df["Prev Close"] != 0),
#             ((live_df["Close"] - live_df["Prev Close"]) / live_df["Prev Close"] * 100).round(2),
#             np.nan
#         )
#         live_df["Change %"] = change_pct
#         live_df["Avg Volume"] = live_df["Avg Volume"].apply(lambda x: f"{x:,.0f}")

#         bull_df, bear_df, neutral_df = classify_with_backtest(live_df, backtest_df, selected, rsi_bull, rsi_bear)

#         elapsed = time.time() - start
#         st.success(
#             f"**Done in {elapsed:.1f}s** – "
#             f"{len(live_df)} scanned | "
#             f"**{len(bull_df)} Bullish (down)** | **{len(bear_df)} Bearish (up)** "
#             f"| {len(backtest_df)} backtested"
#         )

#         st.session_state.bull_df = bull_df
#         st.session_state.bear_df = bear_df
#         st.session_state.neutral_df = neutral_df
#         st.session_state.inds = selected
#         st.session_state.params = params

#     if 'bull_df' in st.session_state:
#         st.markdown("---")
#         st.subheader("Backtested High-Confidence Signals")

#         base_cols = ["symbol", "Close", "Change %", "Avg Volume"]
#         indicator_cols = []
#         for ind in st.session_state.inds:
#             if ind == "RSI": indicator_cols.append("RSI")
#             elif ind == "SMA": indicator_cols.append("SMA")
#             elif ind == "Bollinger Bands (BB)": indicator_cols.extend(["BB_Lower", "BB_Mid", "BB_Upper"])
#             elif ind == "MACD": indicator_cols.extend(["MACD", "Signal"])
#             elif ind == "Support/Resistance": indicator_cols.extend(["Support", "Resistance"])
#         display_cols = base_cols + indicator_cols

#         with st.expander("Bullish Signals (Likely DOWN)", expanded=True):
#             if st.session_state.bull_df.empty:
#                 st.info("No high-confidence bearish signals.")
#             else:
#                 valid_cols = [c for c in display_cols if c in st.session_state.bull_df.columns]
#                 st.dataframe(
#                     st.session_state.bull_df[valid_cols].round(2).sort_values("Change %", ascending=True),
#                     use_container_width=True
#                 )

#         with st.expander("Bearish Signals (Likely UP)", expanded=True):
#             if st.session_state.bear_df.empty:
#                 st.info("No high-confidence bullish signals.")
#             else:
#                 valid_cols = [c for c in display_cols if c in st.session_state.bear_df.columns]
#                 st.dataframe(
#                     st.session_state.bear_df[valid_cols].round(2).sort_values("Change %", ascending=False),
#                     use_container_width=True
#                 )

#         st.markdown("---")
#         st.subheader("Chart Viewer")
#         col_a, col_b = st.columns(2)
#         with col_a:
#             bull_sym = st.selectbox("Bullish", options=[""] + st.session_state.bull_df["symbol"].tolist())
#         with col_b:
#             bear_sym = st.selectbox("Bearish", options=[""] + st.session_state.bear_df["symbol"].tolist())
#         if bull_sym or bear_sym:
#             sym = bull_sym or bear_sym
#             with st.spinner("Loading chart..."):
#                 plot_interactive_chart(sym, st.session_state.inds, st.session_state.params,
#                                      st.session_state.bull_df, st.session_state.bear_df)

#     st.caption(f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} | CBOE: {len(symbols):,} symbols")

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


# ##### add backtest graph

# #!/usr/bin/env python
# # -*- coding: utf-8 -*-

# """
# CBOE Optionable Stock Screener – v11.0 FINAL
# - LOGIC REVERSED: Bullish = DOWN, Bearish = UP
# - FULL EQUITY CURVE + GRID SEARCH + FORWARD TEST
# - SCALAR-ONLY COMPARISONS
# """

# import os
# import io
# import time
# import warnings
# import shutil
# from datetime import datetime
# from concurrent.futures import ThreadPoolExecutor, as_completed
# from itertools import product
# from typing import Iterable, Dict, Any

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

# SCHEMA_VERSION = "11.0"
# HISTORY_TTL = 24 * 3600
# SYMBOLS_TTL = 7 * 24 * 3600

# CPU_COUNT = psutil.cpu_count(logical=False) or 4
# MAX_WORKERS = min(CPU_COUNT, 8)
# INITIAL_BATCH_SIZE = min(CPU_COUNT * 20, 200)

# os.makedirs(HISTORY_CACHE_DIR, exist_ok=True)

# # -------------------------------------------------
# # SILENCE YFINANCE
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
# def get_cached_history(symbol: str, period: str = "6mo") -> pd.DataFrame | None:
#     path = os.path.join(HISTORY_CACHE_DIR, f"{symbol}_{period}.parquet")
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

# def cache_history(symbol: str, df: pd.DataFrame, period: str):
#     path = os.path.join(HISTORY_CACHE_DIR, f"{symbol}_{period}.parquet")
#     try:
#         df.to_parquet(path, index=False)
#     except Exception:
#         pass

# def get_last_close(symbol: str) -> float:
#     cached = get_cached_history(symbol, "6mo")
#     if cached is not None and not cached.empty:
#         return cached["Close"].iloc[-1]
#     return np.nan

# def get_prev_close(symbol: str) -> float:
#     cached = get_cached_history(symbol, "6mo")
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
# def fetch_historical_data(symbol: str, period: str = "6mo") -> pd.DataFrame | None:
#     cached = get_cached_history(symbol, period)
#     if cached is not None:
#         tuner.record_success()
#         return cached

#     try:
#         data = yf_safe_history(symbol, period=period, interval="1d", raise_errors=True, timeout=15)
#         if data.empty:
#             return None
#         data = data.reset_index()
#         data["symbol"] = symbol
#         cache_history(symbol, data, period)
#         time.sleep(0.08)
#         tuner.record_success()
#         return data
#     except Exception as e:
#         if "429" in str(e) or "rate limit" in str(e).lower():
#             tuner.record_failure()
#         return None

# # -------------------------------------------------
# # INDICATORS
# # -------------------------------------------------
# def compute_indicators(df: pd.DataFrame, inds: list, params: dict) -> pd.DataFrame:
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

#     if "Support/Resistance" in inds:
#         lb = params["Support/Resistance"]["lookback"]
#         tol = params["Support/Resistance"]["tolerance"]
#         out["Support"] = low.rolling(lb, min_periods=lb).min() * (1 + tol)
#         out["Resistance"] = high.rolling(lb, min_periods=lb).max() * (1 - tol)

#     return out

# # -------------------------------------------------
# # EQUITY CURVE & METRICS
# # -------------------------------------------------
# def equity_curve_from_signals(close: pd.Series, signals: list, forward_days: int) -> pd.Series:
#     equity = pd.Series(1.0, index=close.index)
#     capital = 1.0
#     for entry_idx, ret in signals:
#         exit_idx = entry_idx + forward_days
#         if exit_idx >= len(close):
#             continue
#         capital *= (1 + ret)
#         equity.iloc[exit_idx:] = capital
#     equity = equity.ffill()
#     return equity

# def compute_strategy_metrics(close: pd.Series, signals: list, forward_days: int, risk_free: float = 0.0):
#     if not signals:
#         return {k: np.nan for k in ("net_profit", "max_dd", "sharpe", "win_rate", "profit_factor", "trades")}

#     rets = [ret for _, ret in signals]
#     equity = equity_curve_from_signals(close, signals, forward_days)

#     net_profit = equity.iloc[-1] - 1.0
#     roll_max = equity.cummax()
#     drawdown = equity / roll_max - 1.0
#     max_dd = drawdown.min()

#     daily_ret = equity.pct_change().dropna()
#     excess = daily_ret - risk_free / 252
#     sharpe = np.sqrt(252) * excess.mean() / excess.std() if excess.std() != 0 else np.nan

#     wins = sum(r > 0 for r in rets)
#     win_rate = wins / len(rets) if rets else np.nan
#     gross_profit = sum(r for r in rets if r > 0)
#     gross_loss = -sum(r for r in rets if r < 0)
#     profit_factor = gross_profit / gross_loss if gross_loss != 0 else np.nan

#     return {
#         "net_profit": net_profit,
#         "max_dd": max_dd,
#         "sharpe": sharpe,
#         "win_rate": win_rate,
#         "profit_factor": profit_factor,
#         "trades": len(rets),
#     }

# # -------------------------------------------------
# # BACKTEST WITH EQUITY
# # -------------------------------------------------
# def backtest_symbol_with_equity(symbol: str, inds: list, params: dict,
#                                 rsi_bull: float, rsi_bear: float,
#                                 backtest_period: str, forward_days: int,
#                                 min_trades: int, min_accuracy: float) -> dict:
#     hist = fetch_historical_data(symbol, period=backtest_period)
#     if hist is None or len(hist) < 100:
#         return {"symbol": symbol, "valid": False}

#     df = hist.copy()
#     indicators = compute_indicators(df, inds, params)
#     df = pd.concat([df[["Close"]], indicators], axis=1).dropna().reset_index(drop=True)

#     if df.empty or len(df) <= forward_days:
#         return {"symbol": symbol, "valid": False}

#     close = df["Close"]
#     total_indicators = len(inds)
#     bull_signals = []
#     bear_signals = []

#     for i in range(len(df) - forward_days):
#         bull_count = bear_count = 0

#         if "RSI" in inds and pd.notna(df.iloc[i]["RSI"]):
#             rsi = df.iloc[i]["RSI"].item()
#             if rsi < rsi_bull: bull_count += 1
#             if rsi > rsi_bear: bear_count += 1

#         if "SMA" in inds and pd.notna(df.iloc[i]["SMA"]):
#             if close.iloc[i].item() < df.iloc[i]["SMA"].item(): bull_count += 1
#             if close.iloc[i].item() > df.iloc[i]["SMA"].item(): bear_count += 1

#         if "Bollinger Bands (BB)" in inds and pd.notna(df.iloc[i]["BB_Lower"]) and pd.notna(df.iloc[i]["BB_Upper"]):
#             c = close.iloc[i].item()
#             if c < df.iloc[i]["BB_Lower"].item(): bull_count += 1
#             if c > df.iloc[i]["BB_Upper"].item(): bear_count += 1

#         if "MACD" in inds and pd.notna(df.iloc[i]["MACD"]) and pd.notna(df.iloc[i]["Signal"]):
#             if df.iloc[i]["MACD"].item() < df.iloc[i]["Signal"].item(): bull_count += 1
#             if df.iloc[i]["MACD"].item() > df.iloc[i]["Signal"].item(): bear_count += 1

#         if "Support/Resistance" in inds and pd.notna(df.iloc[i]["Support"]) and pd.notna(df.iloc[i]["Resistance"]):
#             c = close.iloc[i].item()
#             if c < df.iloc[i]["Support"].item(): bull_count += 1
#             if c > df.iloc[i]["Resistance"].item(): bear_count += 1

#         if bull_count == total_indicators and total_indicators:
#             future_ret = (close.iloc[i + forward_days].item() - close.iloc[i].item()) / close.iloc[i].item()
#             bull_signals.append((i, future_ret))

#         if bear_count == total_indicators and total_indicators:
#             future_ret = (close.iloc[i + forward_days].item() - close.iloc[i].item()) / close.iloc[i].item()
#             bear_signals.append((i, future_ret))

#     bull_acc = np.mean([r < 0 for _, r in bull_signals]) if bull_signals else 0
#     bear_acc = np.mean([r > 0 for _, r in bear_signals]) if bear_signals else 0

#     valid_bull = len(bull_signals) >= min_trades and bull_acc >= min_accuracy
#     valid_bear = len(bear_signals) >= min_trades and bear_acc >= min_accuracy

#     bull_eq = equity_curve_from_signals(close, bull_signals, forward_days) if bull_signals else pd.Series()
#     bear_eq = equity_curve_from_signals(close, bear_signals, forward_days) if bear_signals else pd.Series()

#     bull_metrics = compute_strategy_metrics(close, bull_signals, forward_days)
#     bear_metrics = compute_strategy_metrics(close, bear_signals, forward_days)

#     return {
#         "symbol": symbol,
#         "valid": True,
#         "bull_accuracy": bull_acc,
#         "bear_accuracy": bear_acc,
#         "bull_trades": len(bull_signals),
#         "bear_trades": len(bear_signals),
#         "valid_bull": valid_bull,
#         "valid_bear": valid_bear,
#         "bull_signals": bull_signals,
#         "bear_signals": bear_signals,
#         "bull_equity": bull_eq,
#         "bear_equity": bear_eq,
#         "bull_metrics": bull_metrics,
#         "bear_metrics": bear_metrics,
#         "close_series": close,
#         "dates": df.index
#     }

# # -------------------------------------------------
# # GRID SEARCH
# # -------------------------------------------------
# def param_grid(selected: list, params: dict) -> Iterable[Dict[str, Any]]:
#     grids = {}
#     for ind in selected:
#         if ind == "RSI":
#             grids[ind] = [
#                 {"period": p, "rsi_bull": rb, "rsi_bear": re}
#                 for p, rb, re in product([10, 14, 20], [30, 35, 40], [60, 65, 70])
#             ]
#         elif ind == "SMA":
#             grids[ind] = [{"period": p} for p in [20, 50, 100]]
#         elif ind == "Bollinger Bands (BB)":
#             grids[ind] = [
#                 {"period": p, "std_dev": s}
#                 for p, s in product([15, 20, 25], [1.5, 2.0, 2.5])
#             ]
#         elif ind == "MACD":
#             grids[ind] = [
#                 {"fast": f, "slow": s, "signal": sig}
#                 for f, s, sig in product([8, 12], [17, 26], [5, 9])
#             ]
#         elif ind == "Support/Resistance":
#             grids[ind] = [
#                 {"lookback": lb, "tolerance": t/100}
#                 for lb, t in product([15, 20, 30], [1.0, 2.0, 3.0])
#             ]

#     for combo in product(*[grids.get(i, [{}]) for i in selected]):
#         merged = {}
#         for d in combo:
#             merged.update(d)
#         yield {ind: {k: v for k, v in merged.items() if k in params.get(ind, {})} for ind in selected}

# def evaluate_grid(symbol: str, inds: list, base_params: dict,
#                   rsi_bull: float, rsi_bear: float,
#                   backtest_period: str, forward_days: int,
#                   min_trades: int, min_accuracy: float,
#                   metric: str = "sharpe") -> dict:
#     best = None
#     best_score = -np.inf

#     for param_set in param_grid(inds, base_params):
#         rsi_b = param_set.get("RSI", {}).get("rsi_bull", rsi_bull)
#         rsi_e = param_set.get("RSI", {}).get("rsi_bear", rsi_bear)

#         res = backtest_symbol_with_equity(
#             symbol, inds, param_set, rsi_b, rsi_e,
#             backtest_period, forward_days, min_trades, min_accuracy
#         )
#         if not res["valid"]:
#             continue

#         bull_m = res["bull_metrics"]
#         bear_m = res["bear_metrics"]
#         score_bull = bull_m.get(metric, -np.inf)
#         score_bear = bear_m.get(metric, -np.inf)

#         if score_bull > score_bear:
#             score, direction, metrics, equity, signals = score_bull, "bull", bull_m, res["bull_equity"], res["bull_signals"]
#         else:
#             score, direction, metrics, equity, signals = score_bear, "bear", bear_m, res["bear_equity"], res["bear_signals"]

#         if score > best_score:
#             best_score = score
#             best = {
#                 "symbol": symbol,
#                 "params": param_set,
#                 "rsi_bull": rsi_b,
#                 "rsi_bear": rsi_e,
#                 "direction": direction,
#                 "score": score,
#                 "metrics": metrics,
#                 "equity": equity,
#                 "signals": signals,
#                 "close_series": res["close_series"],
#                 "dates": res["dates"],
#             }
#     return best

# # -------------------------------------------------
# # PARALLEL RUNNERS
# # -------------------------------------------------
# def run_backtest_parallel_rich(symbols, *args, **kwargs):
#     results = []
#     with ThreadPoolExecutor(max_workers=min(4, tuner.workers)) as pool:
#         futures = [pool.submit(backtest_symbol_with_equity, sym, *args, **kwargs) for sym in symbols]
#         prog = st.progress(0)
#         for i, f in enumerate(as_completed(futures), 1):
#             res = f.result()
#             if res["valid"]:
#                 results.append(res)
#             prog.progress(i / len(futures))
#     return results

# def run_grid_search_parallel(symbols, inds, base_params, rsi_bull, rsi_bear,
#                             backtest_period, forward_days, min_trades, min_accuracy,
#                             metric="sharpe"):
#     results = []
#     with ThreadPoolExecutor(max_workers=min(4, tuner.workers)) as pool:
#         futures = [
#             pool.submit(evaluate_grid, sym, inds, base_params, rsi_bull, rsi_bear,
#                         backtest_period, forward_days, min_trades, min_accuracy, metric)
#             for sym in symbols
#         ]
#         prog = st.progress(0)
#         for i, f in enumerate(as_completed(futures), 1):
#             res = f.result()
#             if res:
#                 results.append(res)
#             prog.progress(i / len(futures))
#     return results

# # -------------------------------------------------
# # FORWARD TEST
# # -------------------------------------------------
# def forward_test(symbol: str, signals: list, close: pd.Series, forward_days: int):
#     if not signals:
#         return np.nan
#     last_entry = max(idx for idx, _ in signals if idx + forward_days < len(close))
#     ret = (close.iloc[last_entry + forward_days] - close.iloc[last_entry]) / close.iloc[last_entry]
#     return ret

# # -------------------------------------------------
# # LIVE SCAN
# # -------------------------------------------------
# def compute_live_scan(symbols: list, min_vol: int, inds: list, params: dict) -> pd.DataFrame:
#     data_frames = []
#     for sym in symbols:
#         hist = fetch_historical_data(sym, period="6mo")
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

#     indicators = compute_indicators(df, inds, params)
#     df = pd.concat([df[["Close", "Volume", "symbol"]], indicators], axis=1).dropna()
#     last = df.groupby("symbol").tail(1).reset_index(drop=True)
#     last["Avg Volume"] = df.groupby("symbol")["Volume"].mean().values
#     return last

# # -------------------------------------------------
# # CLASSIFIER
# # -------------------------------------------------
# def classify_with_backtest(live_df: pd.DataFrame, backtest_df: pd.DataFrame, inds: list,
#                            rsi_bull: float, rsi_bear: float) -> tuple:
#     if live_df.empty:
#         return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

#     total_indicators = len(inds)
#     bull_mask = []
#     bear_mask = []

#     for i in range(len(live_df)):
#         row = live_df.iloc[i]
#         bull_count = bear_count = 0

#         if "RSI" in inds and pd.notna(row["RSI"]):
#             if row["RSI"].item() < rsi_bull: bull_count += 1
#             if row["RSI"].item() > rsi_bear: bear_count += 1

#         if "SMA" in inds and pd.notna(row["SMA"]):
#             close_val = row["Close"].item()
#             sma_val = row["SMA"].item()
#             if close_val < sma_val: bull_count += 1
#             if close_val > sma_val: bear_count += 1

#         if "Bollinger Bands (BB)" in inds and pd.notna(row["BB_Lower"]) and pd.notna(row["BB_Upper"]):
#             close_val = row["Close"].item()
#             if close_val < row["BB_Lower"].item(): bull_count += 1
#             if close_val > row["BB_Upper"].item(): bear_count += 1

#         if "MACD" in inds and pd.notna(row["MACD"]) and pd.notna(row["Signal"]):
#             if row["MACD"].item() < row["Signal"].item(): bull_count += 1
#             if row["MACD"].item() > row["Signal"].item(): bear_count += 1

#         if "Support/Resistance" in inds and pd.notna(row["Support"]) and pd.notna(row["Resistance"]):
#             close_val = row["Close"].item()
#             if close_val < row["Support"].item(): bull_count += 1
#             if close_val > row["Resistance"].item(): bear_count += 1

#         sym = row["symbol"]
#         bt = backtest_df[backtest_df["symbol"] == sym]

#         is_bull = (bull_count == total_indicators and total_indicators > 0 and
#                    not bt.empty and bt["valid_bull"].iloc[0])
#         is_bear = (bear_count == total_indicators and total_indicators > 0 and
#                    not bt.empty and bt["valid_bear"].iloc[0])

#         bull_mask.append(is_bull)
#         bear_mask.append(is_bear)

#     bull_df = live_df[bull_mask].copy()
#     bear_df = live_df[bear_mask].copy()
#     neutral_df = live_df[~(pd.Series(bull_mask) | pd.Series(bear_mask))].copy()

#     return bull_df, bear_df, neutral_df

# # -------------------------------------------------
# # CHART
# # -------------------------------------------------
# def plot_interactive_chart(symbol: str, inds: list, params: dict, bull_df, bear_df):
#     hist = fetch_historical_data(symbol, "6mo")
#     if hist is None or hist.empty:
#         st.error(f"No data for {symbol}")
#         return

#     df = hist.copy()
#     indicators = compute_indicators(df, inds, params)
#     df = pd.concat([df[["Close", "Open", "High", "Low"]], indicators], axis=1).dropna()

#     signal = "Bullish" if symbol in bull_df["symbol"].values else "Bearish" if symbol in bear_df["symbol"].values else "Neutral"
#     color = "red" if signal == "Bullish" else "green" if signal == "Bearish" else "gray"

#     fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
#                         subplot_titles=("Price", "MACD", "RSI"), row_heights=[0.6, 0.2, 0.2])

#     fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Price"), row=1, col=1)

#     if "SMA" in inds and "SMA" in df.columns:
#         fig.add_trace(go.Scatter(x=df.index, y=df["SMA"], name="SMA", line=dict(color="orange")), row=1, col=1)

#     if "Bollinger Bands (BB)" in inds:
#         fig.add_trace(go.Scatter(x=df.index, y=df["BB_Upper"], name="BB Upper", line=dict(color="gray", dash="dot")), row=1, col=1)
#         fig.add_trace(go.Scatter(x=df.index, y=df["BB_Lower"], name="BB Lower", line=dict(color="gray", dash="dot"), fill="tonexty"), row=1, col=1)

#     if "MACD" in inds:
#         fig.add_trace(go.Scatter(x=df.index, y=df["MACD"], name="MACD"), row=2, col=1)
#         fig.add_trace(go.Scatter(x=df.index, y=df["Signal"], name="Signal"), row=2, col=1)

#     if "RSI" in inds:
#         fig.add_trace(go.Scatter(x=df.index, y=df["RSI"], name="RSI"), row=3, col=1)
#         fig.add_hline(y=70, line_dash="dot", line_color="red", row=3, col=1)
#         fig.add_hline(y=30, line_dash="dot", line_color="green", row=3, col=1)

#     fig.update_layout(height=800, title_text=f"{symbol} - <span style='color:{color}'>{signal}</span>", template="plotly")
#     st.plotly_chart(fig, use_container_width=True)

# # -------------------------------------------------
# # MAIN UI
# # -------------------------------------------------
# def main():
#     st.set_page_config(page_title="CBOE Screener + Backtest + Grid Search", layout="wide")
#     st.title("CBOE Optionable Stock Screener + Backtest + Grid Search")
#     st.caption("**'Bullish' = Likely DOWN | 'Bearish' = Likely UP | Backtested + Forward-Tested + Auto-Optimized**")

#     col1, col2 = st.columns(2)
#     with col1:
#         min_vol = st.number_input("Min Avg Daily Volume", 100_000, 5_000_000, 500_000, 50_000)
#     with col2:
#         dry_run = st.checkbox("Dry Run (first 30 symbols)", value=True)

#     st.subheader("Backtest Settings")
#     col_a, col_b = st.columns(2)
#     with col_a:
#         backtest_period = st.selectbox("Backtest Period", ["3mo", "6mo", " 1y"], index=1)
#         forward_days = st.slider("Forward Return (days)", 1, 30, 5)
#     with col_b:
#         min_trades = st.slider("Min Historical Trades", 3, 20, 5)
#         min_accuracy = st.slider("Min Accuracy %", 50, 100, 70) / 100

#     st.subheader("Technical Indicators")
#     all_inds = ["RSI", "SMA", "Bollinger Bands (BB)", "MACD", "Support/Resistance"]
#     selected = st.multiselect("Select Indicators", all_inds, default=[])

#     params = {}
#     for i in selected:
#         with st.expander(i, expanded=True):
#             if i == "RSI":
#                 p = st.slider("Period", 5, 50, 14, key="rsi_p")
#                 col_a, col_b = st.columns(2)
#                 with col_a: st.number_input("Bullish RSI <", 0, 100, 40, key="input_rsi_bull")
#                 with col_b: st.number_input("Bearish RSI >", 0, 100, 60, key="input_rsi_bear")
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

#     rsi_bull = st.session_state.get("input_rsi_bull", 40)
#     rsi_bear = st.session_state.get("input_rsi_bear", 60)

#     with st.spinner("Loading symbols..."):
#         sym_df = update_symbols()
#     symbols = sym_df["symbol"].dropna().unique().tolist()
#     if dry_run:
#         symbols = symbols[:30]
#         st.info(f"**Dry Run**: {len(symbols)} symbols")
#     else:
#         st.info(f"Scanning **{len(symbols):,}** symbols")

#     if st.button("Start Backtest + Scan", type="primary"):
#         tuner.__init__()
#         start = time.time()

#         with st.spinner("Backtesting symbols (with equity curves)…"):
#             backtest_raw = run_backtest_parallel_rich(
#                 symbols, selected, params, rsi_bull, rsi_bear,
#                 backtest_period, forward_days, min_trades, min_accuracy
#             )
#         backtest_df = pd.DataFrame([{
#             "symbol": r["symbol"],
#             "bull_accuracy": r["bull_accuracy"],
#             "bear_accuracy": r["bear_accuracy"],
#             "bull_trades": r["bull_trades"],
#             "bear_trades": r["bear_trades"],
#             "valid_bull": r["valid_bull"],
#             "valid_bear": r["valid_bear"]
#         } for r in backtest_raw])

#         with st.spinner("Running live scan..."):
#             live_df = compute_live_scan(symbols, min_vol, selected, params)

#         if live_df.empty:
#             st.warning("No valid stocks in live scan.")
#             return

#         live_df["Close"] = live_df["symbol"].map(get_last_close)
#         live_df["Prev Close"] = live_df["symbol"].map(get_prev_close)
#         change_pct = np.where(
#             live_df["Prev Close"].notna() & (live_df["Prev Close"] != 0),
#             ((live_df["Close"] - live_df["Prev Close"]) / live_df["Prev Close"] * 100).round(2),
#             np.nan
#         )
#         live_df["Change %"] = change_pct
#         live_df["Avg Volume"] = live_df["Avg Volume"].apply(lambda x: f"{x:,.0f}")

#         bull_df, bear_df, neutral_df = classify_with_backtest(live_df, backtest_df, selected, rsi_bull, rsi_bear)

#         elapsed = time.time() - start
#         st.success(
#             f"**Done in {elapsed:.1f}s** – "
#             f"{len(live_df)} scanned | "
#             f"**{len(bull_df)} Bullish (down)** | **{len(bear_df)} Bearish (up)** "
#             f"| {len(backtest_raw)} backtested"
#         )

#         st.session_state.backtest_raw = backtest_raw
#         st.session_state.bull_df = bull_df
#         st.session_state.bear_df = bear_df
#         st.session_state.neutral_df = neutral_df
#         st.session_state.inds = selected
#         st.session_state.params = params

#     # -------------------------------------------------
#     # DISPLAY RESULTS
#     # -------------------------------------------------
#     if 'backtest_raw' in st.session_state:
#         st.markdown("---")
#         st.subheader("Backtested High-Confidence Signals")

#         base_cols = ["symbol", "Close", "Change %", "Avg Volume"]
#         indicator_cols = []
#         for ind in st.session_state.inds:
#             if ind == "RSI": indicator_cols.append("RSI")
#             elif ind == "SMA": indicator_cols.append("SMA")
#             elif ind == "Bollinger Bands (BB)": indicator_cols.extend(["BB_Lower", "BB_Mid", "BB_Upper"])
#             elif ind == "MACD": indicator_cols.extend(["MACD", "Signal"])
#             elif ind == "Support/Resistance": indicator_cols.extend(["Support", "Resistance"])
#         display_cols = base_cols + indicator_cols

#         with st.expander("Bullish Signals (Likely DOWN)", expanded=True):
#             if st.session_state.bull_df.empty:
#                 st.info("No high-confidence bearish signals.")
#             else:
#                 valid_cols = [c for c in display_cols if c in st.session_state.bull_df.columns]
#                 st.dataframe(
#                     st.session_state.bull_df[valid_cols].round(2).sort_values("Change %", ascending=True),
#                     use_container_width=True
#                 )

#         with st.expander("Bearish Signals (Likely UP)", expanded=True):
#             if st.session_state.bear_df.empty:
#                 st.info("No high-confidence bullish signals.")
#             else:
#                 valid_cols = [c for c in display_cols if c in st.session_state.bear_df.columns]
#                 st.dataframe(
#                     st.session_state.bear_df[valid_cols].round(2).sort_values("Change %", ascending=False),
#                     use_container_width=True
#                 )

#         # -------------------------------------------------
#         # EQUITY CURVE DASHBOARD
#         # -------------------------------------------------
#         st.markdown("---")
#         st.subheader("Equity-Curve Overlay & Performance Dashboard")

#         chosen = st.selectbox(
#             "Select a symbol to overlay its equity curves",
#             options=[""] + [r["symbol"] for r in st.session_state.backtest_raw]
#         )

#         if chosen:
#             rec = next(r for r in st.session_state.backtest_raw if r["symbol"] == chosen)

#             # Equity curves
#             fig_eq = go.Figure()
#             if not rec["bull_equity"].empty:
#                 fig_eq.add_trace(go.Scatter(x=rec["dates"], y=rec["bull_equity"], name="Bull (DOWN) Equity", line=dict(color="red")))
#             if not rec["bear_equity"].empty:
#                 fig_eq.add_trace(go.Scatter(x=rec["dates"], y=rec["bear_equity"], name="Bear (UP) Equity", line=dict(color="green")))
#             fig_eq.update_layout(title=f"{chosen} – Equity Curve (Back-test)", xaxis_title="Date", yaxis_title="Capital (1.0)", template="plotly_white", height=500)
#             st.plotly_chart(fig_eq, use_container_width=True)

#             # Forward test
#             if rec["valid_bull"]:
#                 fwd_bull = forward_test(chosen, rec["bull_signals"], rec["close_series"], forward_days)
#                 st.metric("Forward Bull (last signal)", f"{fwd_bull*100:+.2f}%" if not np.isnan(fwd_bull) else "N/A")
#             if rec["valid_bear"]:
#                 fwd_bear = forward_test(chosen, rec["bear_signals"], rec["close_series"], forward_days)
#                 st.metric("Forward Bear (last signal)", f"{fwd_bear*100:+.2f}%" if not np.isnan(fwd_bear) else "N/A")

#             # Metrics bar chart
#             metrics_df = pd.DataFrame({"Bull": rec["bull_metrics"], "Bear": rec["bear_metrics"]}).T
#             fig_bar = go.Figure()
#             for col in ["net_profit", "max_dd", "sharpe", "win_rate", "profit_factor"]:
#                 fig_bar.add_trace(go.Bar(name=col.replace("_", " ").title(), x=["Bull", "Bear"], y=metrics_df[col]))
#             fig_bar.update_layout(barmode="group", title="Key Performance Metrics", height=400)
#             st.plotly_chart(fig_bar, use_container_width=True)

#             # Drawdown
#             if not rec["bull_equity"].empty:
#                 dd_bull = (rec["bull_equity"] / rec["bull_equity"].cummax() - 1)
#                 fig_dd = go.Figure()
#                 fig_dd.add_trace(go.Scatter(x=rec["dates"], y=dd_bull, name="Bull Draw-down", fill="tozeroy", line=dict(color="red")))
#                 if not rec["bear_equity"].empty:
#                     dd_bear = (rec["bear_equity"] / rec["bear_equity"].cummax() - 1)
#                     fig_dd.add_trace(go.Scatter(x=rec["dates"], y=dd_bear, name="Bear Draw-down", fill="tozeroy", line=dict(color="green")))
#                 fig_dd.update_layout(title="Draw-down Waterfall", yaxis_tickformat=".1%")
#                 st.plotly_chart(fig_dd, use_container_width=True)

#             # Trade distribution
#             bull_rets = [r for _, r in rec["bull_signals"]]
#             bear_rets = [r for _, r in rec["bear_signals"]]
#             fig_dist = go.Figure()
#             if bull_rets:
#                 fig_dist.add_trace(go.Histogram(x=bull_rets, name="Bull P&L", opacity=0.7, nbinsx=30))
#             if bear_rets:
#                 fig_dist.add_trace(go.Histogram(x=bear_rets, name="Bear P&L", opacity=0.7, nbinsx=30))
#             fig_dist.update_layout(barmode="overlay", title="Trade P&L Distribution", xaxis_title="Return")
#             st.plotly_chart(fig_dist, use_container_width=True)

#             # Price with signals
#             hist = fetch_historical_data(chosen, "6mo")
#             if hist is not None:
#                 df = hist.copy()
#                 ind = compute_indicators(df, selected, params)
#                 df = pd.concat([df[["Open","High","Low","Close"]], ind], axis=1).dropna()

#                 fig_price = make_subplots(rows=1, cols=1)
#                 fig_price.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Price"))

#                 bull_idx = [df.index[i] for i, _ in rec["bull_signals"]]
#                 if bull_idx:
#                     fig_price.add_trace(go.Scatter(x=bull_idx, y=df.loc[bull_idx, "Close"], mode="markers", marker=dict(color="red", size=10, symbol="triangle-down"), name="Bull Entry"))

#                 bear_idx = [df.index[i] for i, _ in rec["bear_signals"]]
#                 if bear_idx:
#                     fig_price.add_trace(go.Scatter(x=bear_idx, y=df.loc[bear_idx, "Close"], mode="markers", marker=dict(color="green", size=10, symbol="triangle-up"), name="Bear Entry"))

#                 fig_price.update_layout(title=f"{chosen} – Signals on Price", height=600)
#                 st.plotly_chart(fig_price, use_container_width=True)

#         # -------------------------------------------------
#         # GRID SEARCH
#         # -------------------------------------------------
#         st.markdown("---")
#         st.subheader("Automatic Parameter Grid-Search")

#         col_g1, col_g2 = st.columns(2)
#         with col_g1:
#             gs_metric = st.selectbox("Optimization goal", options=["sharpe", "net_profit", "profit_factor"], index=0)
#         with col_g2:
#             gs_dry = st.checkbox("Dry-run (first 10 symbols)", value=True)

#         if st.button("Run Grid Search", type="secondary"):
#             search_symbols = symbols[:10] if gs_dry else symbols
#             with st.spinner(f"Grid-searching {len(search_symbols)} symbols…"):
#                 grid_results = run_grid_search_parallel(
#                     search_symbols, selected, params, rsi_bull, rsi_bear,
#                     backtest_period, forward_days, min_trades, min_accuracy,
#                     metric=gs_metric
#                 )
#             st.session_state.grid_results = grid_results
#             st.success(f"Grid-search finished – {len(grid_results)} symbols improved.")

#         if "grid_results" in st.session_state and st.session_state.grid_results:
#             st.markdown("#### Best-Adjusted Equity Curves (vs Original)")

#             best_sym = st.selectbox("Symbol for overlay", options=[""] + [r["symbol"] for r in st.session_state.grid_results])

#             if best_sym:
#                 adj = next(r for r in st.session_state.grid_results if r["symbol"] == best_sym)
#                 orig = next((r for r in st.session_state.backtest_raw if r["symbol"] == best_sym), None)

#                 fig = go.Figure()

#                 if orig:
#                     dir_orig = "bull" if orig["valid_bull"] else "bear" if orig["valid_bear"] else None
#                     if dir_orig:
#                         orig_eq = orig[f"{dir_orig}_equity"]
#                         fig.add_trace(go.Scatter(x=orig["dates"], y=orig_eq, name=f"Original {dir_orig.capitalize()}", line=dict(dash="dot", width=2)))

#                 adj_eq = adj["equity"]
#                 color = "red" if adj["direction"] == "bull" else "green"
#                 fig.add_trace(go.Scatter(x=adj["dates"], y=adj_eq, name=f"Adjusted {adj['direction'].capitalize()} (Best {gs_metric})", line=dict(color=color, width=3)))

#                 fig.update_layout(title=f"{best_sym} – Original vs Best-Adjusted Equity", xaxis_title="Date", yaxis_title="Capital (1.0)", template="plotly_white", height=550)
#                 st.plotly_chart(fig, use_container_width=True)

#                 col_m1, col_m2 = st.columns(2)
#                 with col_m1:
#                     st.metric("Original Net-Profit", f"{orig['bull_metrics' if orig and orig['valid_bull'] else 'bear_metrics']['net_profit']:+.1%}" if orig else "—")
#                     st.metric("Adjusted Net-Profit", f"{adj['metrics']['net_profit']:+.1%}")
#                 with col_m2:
#                     st.metric("Original Sharpe", f"{orig['bull_metrics' if orig and orig['valid_bull'] else 'bear_metrics']['sharpe']:.2f}" if orig else "—")
#                     st.metric("Adjusted Sharpe", f"{adj['metrics']['sharpe']:.2f}")

#                 with st.expander("Winning Parameter Set", expanded=False):
#                     st.json(adj["params"], expanded=False)
#                     st.caption(f"RSI thresholds: Bull < {adj['rsi_bull']}, Bear > {adj['rsi_bear']}")

#                     if st.button("Export all best parameters to CSV"):
#                         export_df = pd.DataFrame([{
#                             "symbol": r["symbol"],
#                             "direction": r["direction"],
#                             "score": r["score"],
#                             "net_profit": r["metrics"]["net_profit"],
#                             "sharpe": r["metrics"]["sharpe"],
#                             **{f"{k}_{p}": v for k, d in r["params"].items() for p, v in d.items()},
#                             "rsi_bull": r["rsi_bull"],
#                             "rsi_bear": r["rsi_bear"]
#                         } for r in st.session_state.grid_results])
#                         csv = export_df.to_csv(index=False).encode()
#                         st.download_button(
#                             label="Download CSV",
#                             data=csv,
#                             file_name=f"best_params_{gs_metric}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv",
#                             mime="text/csv"
#                         )

#         # -------------------------------------------------
#         # CHART VIEWER
#         # -------------------------------------------------
#         st.markdown("---")
#         st.subheader("Chart Viewer")
#         col_a, col_b = st.columns(2)
#         with col_a:
#             bull_sym = st.selectbox("Bullish", options=[""] + st.session_state.bull_df["symbol"].tolist())
#         with col_b:
#             bear_sym = st.selectbox("Bearish", options=[""] + st.session_state.bear_df["symbol"].tolist())
#         if bull_sym or bear_sym:
#             sym = bull_sym or bear_sym
#             with st.spinner("Loading chart..."):
#                 plot_interactive_chart(sym, st.session_state.inds, st.session_state.params,
#                                      st.session_state.bull_df, st.session_state.bear_df)

#     st.caption(f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} | CBOE: {len(symbols):,} symbols")

#     if st.button("Clear Cache"):
#         if os.path.exists(HISTORY_CACHE_DIR):
#             shutil.rmtree(HISTORY_CACHE_DIR)
#         if os.path.exists(PARQUET_FILE):
#             os.remove(PARQUET_FILE)
#         st.success("Cache cleared!")
#         st.rerun()

# if __name__ == "__main__":
#     main()


###### vectorize everything


# #!/usr/bin/env python
# # -*- coding: utf-8 -*-

# """
# CBOE Optionable Stock Screener – v12.0 FINAL
# - LOGIC REVERSED: Bullish = DOWN, Bearish = UP
# - 100 % VECTORISED + NUMBA + GRID SEARCH + EQUITY CURVES
# - SCALAR-ONLY, CACHED, PARALLEL
# """

# import os
# import io
# import time
# import warnings
# import shutil
# import hashlib
# import joblib
# from datetime import datetime
# from concurrent.futures import ThreadPoolExecutor, as_completed
# from itertools import product
# from typing import Iterable, Dict, Any
# from pathlib import Path

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
# # NUMBA (optional but ~5x faster)
# # -------------------------------------------------
# try:
#     from numba import njit
# except Exception:
#     def njit(*args, **kwargs):
#         def _decorator(func):
#             return func
#         return _decorator

# # -------------------------------------------------
# # CONFIG
# # -------------------------------------------------
# PARQUET_FILE = "optionable_full.parquet"
# HISTORY_CACHE_DIR = "history_cache"
# BACKTEST_CACHE_DIR = "backtest_cache"
# CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"

# SCHEMA_VERSION = "12.0"
# HISTORY_TTL = 24 * 3600
# SYMBOLS_TTL = 7 * 24 * 3600

# CPU_COUNT = psutil.cpu_count(logical=False) or 4
# MAX_WORKERS = min(CPU_COUNT, 8)
# INITIAL_BATCH_SIZE = min(CPU_COUNT * 20, 200)

# os.makedirs(HISTORY_CACHE_DIR, exist_ok=True)
# os.makedirs(BACKTEST_CACHE_DIR, exist_ok=True)

# # -------------------------------------------------
# # SILENCE YFINANCE
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
# def get_cached_history(symbol: str, period: str = "6mo") -> pd.DataFrame | None:
#     path = os.path.join(HISTORY_CACHE_DIR, f"{symbol}_{period}.parquet")
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

# def cache_history(symbol: str, df: pd.DataFrame, period: str):
#     path = os.path.join(HISTORY_CACHE_DIR, f"{symbol}_{period}.parquet")
#     try:
#         df.to_parquet(path, index=False)
#     except Exception:
#         pass

# def get_last_close(symbol: str) -> float:
#     cached = get_cached_history(symbol, "6mo")
#     if cached is not None and not cached.empty:
#         return cached["Close"].iloc[-1]
#     return np.nan

# def get_prev_close(symbol: str) -> float:
#     cached = get_cached_history(symbol, "6mo")
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
# def fetch_historical_data(symbol: str, period: str = "6mo") -> pd.DataFrame | None:
#     cached = get_cached_history(symbol, period)
#     if cached is not None:
#         tuner.record_success()
#         return cached

#     try:
#         data = yf_safe_history(symbol, period=period, interval="1d", raise_errors=True, timeout=15)
#         if data.empty:
#             return None
#         data = data.reset_index()
#         data["symbol"] = symbol
#         cache_history(symbol, data, period)
#         time.sleep(0.08)
#         tuner.record_success()
#         return data
#     except Exception as e:
#         if "429" in str(e) or "rate limit" in str(e).lower():
#             tuner.record_failure()
#         return None

# # -------------------------------------------------
# # INDICATORS
# # -------------------------------------------------
# def compute_indicators(df: pd.DataFrame, inds: list, params: dict) -> pd.DataFrame:
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

#     if "Support/Resistance" in inds:
#         lb = params["Support/Resistance"]["lookback"]
#         tol = params["Support/Resistance"]["tolerance"]
#         out["Support"] = low.rolling(lb, min_periods=lb).min() * (1 + tol)
#         out["Resistance"] = high.rolling(lb, min_periods=lb).max() * (1 - tol)

#     return out

# # -------------------------------------------------
# # VECTORISED BACKTEST + NUMBA
# # -------------------------------------------------
# @njit
# def _signal_loop(close_arr, ind_arr, forward_days, total_inds):
#     n = len(close_arr)
#     bull = []
#     bear = []
#     for i in range(n - forward_days):
#         bull_cnt = bear_cnt = 0
#         if total_inds >= 1 and not np.isnan(ind_arr[i, 0]):
#             if ind_arr[i, 0] < ind_arr[i, 8]: bull_cnt += 1
#             if ind_arr[i, 0] > ind_arr[i, 9]: bear_cnt += 1
#         if total_inds >= 2 and not np.isnan(ind_arr[i, 1]):
#             if close_arr[i] < ind_arr[i, 1]: bull_cnt += 1
#             if close_arr[i] > ind_arr[i, 1]: bear_cnt += 1
#         if total_inds >= 3 and not np.isnan(ind_arr[i, 2]):
#             if close_arr[i] < ind_arr[i, 2]: bull_cnt += 1
#         if total_inds >= 3 and not np.isnan(ind_arr[i, 3]):
#             if close_arr[i] > ind_arr[i, 3]: bear_cnt += 1
#         if total_inds >= 4 and not np.isnan(ind_arr[i, 4]):
#             if ind_arr[i, 4] < ind_arr[i, 5]: bull_cnt += 1
#             if ind_arr[i, 4] > ind_arr[i, 5]: bear_cnt += 1
#         if total_inds >= 5 and not np.isnan(ind_arr[i, 6]):
#             if close_arr[i] < ind_arr[i, 6]: bull_cnt += 1
#         if total_inds >= 5 and not np.isnan(ind_arr[i, 7]):
#             if close_arr[i] > ind_arr[i, 7]: bear_cnt += 1

#         if bull_cnt == total_inds and total_inds:
#             ret = (close_arr[i + forward_days] - close_arr[i]) / close_arr[i]
#             bull.append((i, ret))
#         if bear_cnt == total_inds and total_inds:
#             ret = (close_arr[i + forward_days] - close_arr[i]) / close_arr[i]
#             bear.append((i, ret))
#     return bull, bear

# def backtest_symbol_vectorised(symbol: str, inds: list, params: dict,
#                                rsi_bull: float, rsi_bear: float,
#                                backtest_period: str, forward_days: int,
#                                min_trades: int, min_accuracy: float) -> dict:
#     hist = fetch_historical_data(symbol, period=backtest_period)
#     if hist is None or len(hist) < 100:
#         return {"symbol": symbol, "valid": False}

#     df = hist.copy()
#     indicators = compute_indicators(df, inds, params)
#     df = pd.concat([df[["Close"]], indicators], axis=1).dropna().reset_index(drop=True)

#     if df.empty or len(df) <= forward_days:
#         return {"symbol": symbol, "valid": False}

#     close = df["Close"].values.astype(np.float64)
#     total_inds = len(inds)
#     ind_mat = np.full((len(df), 10), np.nan, dtype=np.float64)
#     col = 0

#     if "RSI" in inds:
#         ind_mat[:, col] = df["RSI"].values
#         col += 1
#     if "SMA" in inds:
#         ind_mat[:, col] = df["SMA"].values
#         col += 1
#     if "Bollinger Bands (BB)" in inds:
#         ind_mat[:, col] = df["BB_Lower"].values
#         col += 1
#         ind_mat[:, col] = df["BB_Upper"].values
#         col += 1
#     if "MACD" in inds:
#         ind_mat[:, col] = df["MACD"].values
#         col += 1
#         ind_mat[:, col] = df["Signal"].values
#         col += 1
#     if "Support/Resistance" in inds:
#         ind_mat[:, col] = df["Support"].values
#         col += 1
#         ind_mat[:, col] = df["Resistance"].values
#         col += 1

#     ind_mat[:, 8] = rsi_bull
#     ind_mat[:, 9] = rsi_bear

#     bull_sig, bear_sig = _signal_loop(close, ind_mat, forward_days, total_inds)

#     bull_rets = np.array([r for _, r in bull_sig])
#     bear_rets = np.array([r for _, r in bear_sig])

#     bull_acc = (bull_rets < 0).mean() if len(bull_rets) else 0.0
#     bear_acc = (bear_rets > 0).mean() if len(bear_rets) else 0.0

#     valid_bull = len(bull_rets) >= min_trades and bull_acc >= min_accuracy
#     valid_bear = len(bear_rets) >= min_trades and bear_acc >= min_accuracy

#     def build_equity(signals):
#         if not signals:
#             return pd.Series(dtype=float)
#         idx, ret = zip(*signals)
#         equity = np.ones(len(close))
#         capital = 1.0
#         for i, r in zip(idx, ret):
#             exit_i = i + forward_days
#             if exit_i >= len(close):
#                 continue
#             capital *= (1 + r)
#             equity[exit_i:] = capital
#         equity[: min(idx) + forward_days] = np.nan
#         return pd.Series(equity, index=df.index).ffill().fillna(1.0)

#     bull_eq = build_equity(bull_sig)
#     bear_eq = build_equity(bear_sig)

#     def compute_metrics(signals):
#         if not signals:
#             return {k: np.nan for k in ("net_profit", "max_dd", "sharpe", "win_rate", "profit_factor", "trades")}
#         rets = [r for _, r in signals]
#         equity = build_equity(signals)
#         net_profit = equity.iloc[-1] - 1.0
#         roll_max = equity.cummax()
#         drawdown = equity / roll_max - 1.0
#         max_dd = drawdown.min()
#         daily_ret = equity.pct_change().dropna()
#         excess = daily_ret - 0.0 / 252
#         sharpe = np.sqrt(252) * excess.mean() / excess.std() if excess.std() != 0 else np.nan
#         wins = sum(r > 0 for r in rets)
#         win_rate = wins / len(rets) if rets else np.nan
#         gross_profit = sum(r for r in rets if r > 0)
#         gross_loss = -sum(r for r in rets if r < 0)
#         profit_factor = gross_profit / gross_loss if gross_loss != 0 else np.nan
#         return {
#             "net_profit": net_profit,
#             "max_dd": max_dd,
#             "sharpe": sharpe,
#             "win_rate": win_rate,
#             "profit_factor": profit_factor,
#             "trades": len(rets),
#         }

#     bull_metrics = compute_metrics(bull_sig)
#     bear_metrics = compute_metrics(bear_sig)

#     return {
#         "symbol": symbol,
#         "valid": True,
#         "bull_accuracy": bull_acc,
#         "bear_accuracy": bear_acc,
#         "bull_trades": len(bull_sig),
#         "bear_trades": len(bear_sig),
#         "valid_bull": valid_bull,
#         "valid_bear": valid_bear,
#         "bull_signals": bull_sig,
#         "bear_signals": bear_sig,
#         "bull_equity": bull_eq,
#         "bear_equity": bear_eq,
#         "bull_metrics": bull_metrics,
#         "bear_metrics": bear_metrics,
#         "close_series": df["Close"],
#         "dates": df.index
#     }

# # -------------------------------------------------
# # CACHING WRAPPER
# # -------------------------------------------------
# def backtest_cached(symbol: str, *args, **kwargs):
#     key = hashlib.md5(f"{symbol}{args}{kwargs}".encode()).hexdigest()
#     path = Path(BACKTEST_CACHE_DIR) / f"{key}.pkl"
#     if path.exists():
#         return joblib.load(path)
#     res = backtest_symbol_vectorised(symbol, *args, **kwargs)
#     joblib.dump(res, path)
#     return res

# # -------------------------------------------------
# # GRID SEARCH
# # -------------------------------------------------
# def param_grid(selected: list, params: dict) -> Iterable[Dict[str, Any]]:
#     grids = {}
#     for ind in selected:
#         if ind == "RSI":
#             grids[ind] = [
#                 {"period": p, "rsi_bull": rb, "rsi_bear": re}
#                 for p, rb, re in product([10, 14, 20], [30, 35, 40], [60, 65, 70])
#             ]
#         elif ind == "SMA":
#             grids[ind] = [{"period": p} for p in [20, 50, 100]]
#         elif ind == "Bollinger Bands (BB)":
#             grids[ind] = [
#                 {"period": p, "std_dev": s}
#                 for p, s in product([15, 20, 25], [1.5, 2.0, 2.5])
#             ]
#         elif ind == "MACD":
#             grids[ind] = [
#                 {"fast": f, "slow": s, "signal": sig}
#                 for f, s, sig in product([8, 12], [17, 26], [5, 9])
#             ]
#         elif ind == "Support/Resistance":
#             grids[ind] = [
#                 {"lookback": lb, "tolerance": t/100}
#                 for lb, t in product([15, 20, 30], [1.0, 2.0, 3.0])
#             ]

#     for combo in product(*[grids.get(i, [{}]) for i in selected]):
#         merged = {}
#         for d in combo:
#             merged.update(d)
#         yield {ind: {k: v for k, v in merged.items() if k in params.get(ind, {})} for ind in selected}

# def evaluate_grid(symbol: str, inds: list, base_params: dict,
#                   rsi_bull: float, rsi_bear: float,
#                   backtest_period: str, forward_days: int,
#                   min_trades: int, min_accuracy: float,
#                   metric: str = "sharpe") -> dict:
#     best = None
#     best_score = -np.inf

#     for param_set in param_grid(inds, base_params):
#         rsi_b = param_set.get("RSI", {}).get("rsi_bull", rsi_bull)
#         rsi_e = param_set.get("RSI", {}).get("rsi_bear", rsi_bear)

#         res = backtest_cached(
#             symbol, inds, param_set, rsi_b, rsi_e,
#             backtest_period, forward_days, min_trades, min_accuracy
#         )
#         if not res["valid"]:
#             continue

#         bull_m = res["bull_metrics"]
#         bear_m = res["bear_metrics"]
#         score_bull = bull_m.get(metric, -np.inf)
#         score_bear = bear_m.get(metric, -np.inf)

#         if score_bull > score_bear:
#             score, direction, metrics, equity, signals = score_bull, "bull", bull_m, res["bull_equity"], res["bull_signals"]
#         else:
#             score, direction, metrics, equity, signals = score_bear, "bear", bear_m, res["bear_equity"], res["bear_signals"]

#         if score > best_score:
#             best_score = score
#             best = {
#                 "symbol": symbol,
#                 "params": param_set,
#                 "rsi_bull": rsi_b,
#                 "rsi_bear": rsi_e,
#                 "direction": direction,
#                 "score": score,
#                 "metrics": metrics,
#                 "equity": equity,
#                 "signals": signals,
#                 "close_series": res["close_series"],
#                 "dates": res["dates"],
#             }
#     return best

# # -------------------------------------------------
# # PARALLEL RUNNERS
# # -------------------------------------------------
# def run_backtest_parallel_vectorised(symbols, *args, **kwargs):
#     results = []
#     with ThreadPoolExecutor(max_workers=min(4, tuner.workers)) as pool:
#         futures = [pool.submit(backtest_cached, sym, *args, **kwargs) for sym in symbols]
#         prog = st.progress(0)
#         for i, f in enumerate(as_completed(futures), 1):
#             res = f.result()
#             if res["valid"]:
#                 results.append(res)
#             prog.progress(i / len(futures))
#     return results

# def run_grid_search_parallel_vectorised(symbols, inds, base_params, rsi_bull, rsi_bear,
#                                         backtest_period, forward_days, min_trades, min_accuracy,
#                                         metric="sharpe"):
#     results = []
#     with ThreadPoolExecutor(max_workers=min(4, tuner.workers)) as pool:
#         futures = [
#             pool.submit(evaluate_grid, sym, inds, base_params, rsi_bull, rsi_bear,
#                         backtest_period, forward_days, min_trades, min_accuracy, metric)
#             for sym in symbols
#         ]
#         prog = st.progress(0)
#         for i, f in enumerate(as_completed(futures), 1):
#             res = f.result()
#             if res:
#                 results.append(res)
#             prog.progress(i / len(futures))
#     return results

# # -------------------------------------------------
# # FORWARD TEST
# # -------------------------------------------------
# def forward_test(symbol: str, signals: list, close: pd.Series, forward_days: int):
#     if not signals:
#         return np.nan
#     last_entry = max(idx for idx, _ in signals if idx + forward_days < len(close))
#     ret = (close.iloc[last_entry + forward_days] - close.iloc[last_entry]) / close.iloc[last_entry]
#     return ret

# # -------------------------------------------------
# # LIVE SCAN
# # -------------------------------------------------
# def compute_live_scan(symbols: list, min_vol: int, inds: list, params: dict) -> pd.DataFrame:
#     data_frames = []
#     for sym in symbols:
#         hist = fetch_historical_data(sym, period="6mo")
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

#     indicators = compute_indicators(df, inds, params)
#     df = pd.concat([df[["Close", "Volume", "symbol"]], indicators], axis=1).dropna()
#     last = df.groupby("symbol").tail(1).reset_index(drop=True)
#     last["Avg Volume"] = df.groupby("symbol")["Volume"].mean().values
#     return last

# # -------------------------------------------------
# # CLASSIFIER
# # -------------------------------------------------
# def classify_with_backtest(live_df: pd.DataFrame, backtest_df: pd.DataFrame, inds: list,
#                            rsi_bull: float, rsi_bear: float) -> tuple:
#     if live_df.empty:
#         return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

#     total_indicators = len(inds)
#     bull_mask = []
#     bear_mask = []

#     for i in range(len(live_df)):
#         row = live_df.iloc[i]
#         bull_count = bear_count = 0

#         if "RSI" in inds and pd.notna(row["RSI"]):
#             if row["RSI"].item() < rsi_bull: bull_count += 1
#             if row["RSI"].item() > rsi_bear: bear_count += 1

#         if "SMA" in inds and pd.notna(row["SMA"]):
#             close_val = row["Close"].item()
#             sma_val = row["SMA"].item()
#             if close_val < sma_val: bull_count += 1
#             if close_val > sma_val: bear_count += 1

#         if "Bollinger Bands (BB)" in inds and pd.notna(row["BB_Lower"]) and pd.notna(row["BB_Upper"]):
#             close_val = row["Close"].item()
#             if close_val < row["BB_Lower"].item(): bull_count += 1
#             if close_val > row["BB_Upper"].item(): bear_count += 1

#         if "MACD" in inds and pd.notna(row["MACD"]) and pd.notna(row["Signal"]):
#             if row["MACD"].item() < row["Signal"].item(): bull_count += 1
#             if row["MACD"].item() > row["Signal"].item(): bear_count += 1

#         if "Support/Resistance" in inds and pd.notna(row["Support"]) and pd.notna(row["Resistance"]):
#             close_val = row["Close"].item()
#             if close_val < row["Support"].item(): bull_count += 1
#             if close_val > row["Resistance"].item(): bear_count += 1

#         sym = row["symbol"]
#         bt = backtest_df[backtest_df["symbol"] == sym]

#         is_bull = (bull_count == total_indicators and total_indicators > 0 and
#                    not bt.empty and bt["valid_bull"].iloc[0])
#         is_bear = (bear_count == total_indicators and total_indicators > 0 and
#                    not bt.empty and bt["valid_bear"].iloc[0])

#         bull_mask.append(is_bull)
#         bear_mask.append(is_bear)

#     bull_df = live_df[bull_mask].copy()
#     bear_df = live_df[bear_mask].copy()
#     neutral_df = live_df[~(pd.Series(bull_mask) | pd.Series(bear_mask))].copy()

#     return bull_df, bear_df, neutral_df

# # -------------------------------------------------
# # CHART
# # -------------------------------------------------
# def plot_interactive_chart(symbol: str, inds: list, params: dict, bull_df, bear_df):
#     hist = fetch_historical_data(symbol, "6mo")
#     if hist is None or hist.empty:
#         st.error(f"No data for {symbol}")
#         return

#     df = hist.copy()
#     indicators = compute_indicators(df, inds, params)
#     df = pd.concat([df[["Close", "Open", "High", "Low"]], indicators], axis=1).dropna()

#     signal = "Bullish" if symbol in bull_df["symbol"].values else "Bearish" if symbol in bear_df["symbol"].values else "Neutral"
#     color = "red" if signal == "Bullish" else "green" if signal == "Bearish" else "gray"

#     fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
#                         subplot_titles=("Price", "MACD", "RSI"), row_heights=[0.6, 0.2, 0.2])

#     fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Price"), row=1, col=1)

#     if "SMA" in inds and "SMA" in df.columns:
#         fig.add_trace(go.Scatter(x=df.index, y=df["SMA"], name="SMA", line=dict(color="orange")), row=1, col=1)

#     if "Bollinger Bands (BB)" in inds:
#         fig.add_trace(go.Scatter(x=df.index, y=df["BB_Upper"], name="BB Upper", line=dict(color="gray", dash="dot")), row=1, col=1)
#         fig.add_trace(go.Scatter(x=df.index, y=df["BB_Lower"], name="BB Lower", line=dict(color="gray", dash="dot"), fill="tonexty"), row=1, col=1)

#     if "MACD" in inds:
#         fig.add_trace(go.Scatter(x=df.index, y=df["MACD"], name="MACD"), row=2, col=1)
#         fig.add_trace(go.Scatter(x=df.index, y=df["Signal"], name="Signal"), row=2, col=1)

#     if "RSI" in inds:
#         fig.add_trace(go.Scatter(x=df.index, y=df["RSI"], name="RSI"), row=3, col=1)
#         fig.add_hline(y=70, line_dash="dot", line_color="red", row=3, col=1)
#         fig.add_hline(y=30, line_dash="dot", line_color="green", row=3, col=1)

#     fig.update_layout(height=800, title_text=f"{symbol} - <span style='color:{color}'>{signal}</span>", template="plotly")
#     st.plotly_chart(fig, use_container_width=True)

# # -------------------------------------------------
# # MAIN UI
# # -------------------------------------------------
# def main():
#     st.set_page_config(page_title="CBOE Screener + Vectorised Backtest", layout="wide")
#     st.title("CBOE Optionable Stock Screener + Vectorised Backtest")
#     st.caption("**'Bullish' = Likely DOWN | 'Bearish' = Likely UP | 100 % Vectorised + Grid Search**")

#     col1, col2 = st.columns(2)
#     with col1:
#         min_vol = st.number_input("Min Avg Daily Volume", 100_000, 5_000_000, 500_000, 50_000)
#     with col2:
#         dry_run = st.checkbox("Dry Run (first 30 symbols)", value=True)

#     st.subheader("Backtest Settings")
#     col_a, col_b = st.columns(2)
#     with col_a:
#         backtest_period = st.selectbox("Backtest Period", ["3mo", "6mo", "1y"], index=1)
#         forward_days = st.slider("Forward Return (days)", 1, 30, 5)
#     with col_b:
#         min_trades = st.slider("Min Historical Trades", 3, 20, 5)
#         min_accuracy = st.slider("Min Accuracy %", 50, 100, 70) / 100

#     st.subheader("Technical Indicators")
#     all_inds = ["RSI", "SMA", "Bollinger Bands (BB)", "MACD", "Support/Resistance"]
#     selected = st.multiselect("Select Indicators", all_inds, default=[])

#     params = {}
#     for i in selected:
#         with st.expander(i, expanded=True):
#             if i == "RSI":
#                 p = st.slider("Period", 5, 50, 14, key="rsi_p")
#                 col_a, col_b = st.columns(2)
#                 with col_a: st.number_input("Bullish RSI <", 0, 100, 40, key="input_rsi_bull")
#                 with col_b: st.number_input("Bearish RSI >", 0, 100, 60, key="input_rsi_bear")
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

#     rsi_bull = st.session_state.get("input_rsi_bull", 40)
#     rsi_bear = st.session_state.get("input_rsi_bear", 60)

#     with st.spinner("Loading symbols..."):
#         sym_df = update_symbols()
#     symbols = sym_df["symbol"].dropna().unique().tolist()
#     if dry_run:
#         symbols = symbols[:30]
#         st.info(f"**Dry Run**: {len(symbols)} symbols")
#     else:
#         st.info(f"Scanning **{len(symbols):,}** symbols")

#     if st.button("Start Backtest + Scan", type="primary"):
#         tuner.__init__()
#         start = time.time()

#         with st.spinner("Backtesting symbols (vectorised)…"):
#             backtest_raw = run_backtest_parallel_vectorised(
#                 symbols, selected, params, rsi_bull, rsi_bear,
#                 backtest_period, forward_days, min_trades, min_accuracy
#             )
#         backtest_df = pd.DataFrame([{
#             "symbol": r["symbol"],
#             "bull_accuracy": r["bull_accuracy"],
#             "bear_accuracy": r["bear_accuracy"],
#             "bull_trades": r["bull_trades"],
#             "bear_trades": r["bear_trades"],
#             "valid_bull": r["valid_bull"],
#             "valid_bear": r["valid_bear"]
#         } for r in backtest_raw])

#         with st.spinner("Running live scan..."):
#             live_df = compute_live_scan(symbols, min_vol, selected, params)

#         if live_df.empty:
#             st.warning("No valid stocks in live scan.")
#             return

#         live_df["Close"] = live_df["symbol"].map(get_last_close)
#         live_df["Prev Close"] = live_df["symbol"].map(get_prev_close)
#         change_pct = np.where(
#             live_df["Prev Close"].notna() & (live_df["Prev Close"] != 0),
#             ((live_df["Close"] - live_df["Prev Close"]) / live_df["Prev Close"] * 100).round(2),
#             np.nan
#         )
#         live_df["Change %"] = change_pct
#         live_df["Avg Volume"] = live_df["Avg Volume"].apply(lambda x: f"{x:,.0f}")

#         bull_df, bear_df, neutral_df = classify_with_backtest(live_df, backtest_df, selected, rsi_bull, rsi_bear)

#         elapsed = time.time() - start
#         st.success(
#             f"**Done in {elapsed:.1f}s** – "
#             f"{len(live_df)} scanned | "
#             f"**{len(bull_df)} Bullish (down)** | **{len(bear_df)} Bearish (up)** "
#             f"| {len(backtest_raw)} backtested"
#         )

#         st.session_state.backtest_raw = backtest_raw
#         st.session_state.bull_df = bull_df
#         st.session_state.bear_df = bear_df
#         st.session_state.neutral_df = neutral_df
#         st.session_state.inds = selected
#         st.session_state.params = params

#     # -------------------------------------------------
#     # DISPLAY RESULTS
#     # -------------------------------------------------
#     if 'backtest_raw' in st.session_state:
#         st.markdown("---")
#         st.subheader("Backtested High-Confidence Signals")

#         base_cols = ["symbol", "Close", "Change %", "Avg Volume"]
#         indicator_cols = []
#         for ind in st.session_state.inds:
#             if ind == "RSI": indicator_cols.append("RSI")
#             elif ind == "SMA": indicator_cols.append("SMA")
#             elif ind == "Bollinger Bands (BB)": indicator_cols.extend(["BB_Lower", "BB_Mid", "BB_Upper"])
#             elif ind == "MACD": indicator_cols.extend(["MACD", "Signal"])
#             elif ind == "Support/Resistance": indicator_cols.extend(["Support", "Resistance"])
#         display_cols = base_cols + indicator_cols

#         with st.expander("Bullish Signals (Likely DOWN)", expanded=True):
#             if st.session_state.bull_df.empty:
#                 st.info("No high-confidence bearish signals.")
#             else:
#                 valid_cols = [c for c in display_cols if c in st.session_state.bull_df.columns]
#                 st.dataframe(
#                     st.session_state.bull_df[valid_cols].round(2).sort_values("Change %", ascending=True),
#                     use_container_width=True
#                 )

#         with st.expander("Bearish Signals (Likely UP)", expanded=True):
#             if st.session_state.bear_df.empty:
#                 st.info("No high-confidence bullish signals.")
#             else:
#                 valid_cols = [c for c in display_cols if c in st.session_state.bear_df.columns]
#                 st.dataframe(
#                     st.session_state.bear_df[valid_cols].round(2).sort_values("Change %", ascending=False),
#                     use_container_width=True
#                 )

#         # -------------------------------------------------
#         # EQUITY CURVE DASHBOARD
#         # -------------------------------------------------
#         st.markdown("---")
#         st.subheader("Equity-Curve Overlay & Performance Dashboard")

#         chosen = st.selectbox(
#             "Select a symbol to overlay its equity curves",
#             options=[""] + [r["symbol"] for r in st.session_state.backtest_raw]
#         )

#         if chosen:
#             rec = next(r for r in st.session_state.backtest_raw if r["symbol"] == chosen)

#             fig_eq = go.Figure()
#             if not rec["bull_equity"].empty:
#                 fig_eq.add_trace(go.Scatter(x=rec["dates"], y=rec["bull_equity"], name="Bull (DOWN) Equity", line=dict(color="red")))
#             if not rec["bear_equity"].empty:
#                 fig_eq.add_trace(go.Scatter(x=rec["dates"], y=rec["bear_equity"], name="Bear (UP) Equity", line=dict(color="green")))
#             fig_eq.update_layout(title=f"{chosen} – Equity Curve (Back-test)", xaxis_title="Date", yaxis_title="Capital (1.0)", template="plotly_white", height=500)
#             st.plotly_chart(fig_eq, use_container_width=True)

#             if rec["valid_bull"]:
#                 fwd_bull = forward_test(chosen, rec["bull_signals"], rec["close_series"], forward_days)
#                 st.metric("Forward Bull (last signal)", f"{fwd_bull*100:+.2f}%" if not np.isnan(fwd_bull) else "N/A")
#             if rec["valid_bear"]:
#                 fwd_bear = forward_test(chosen, rec["bear_signals"], rec["close_series"], forward_days)
#                 st.metric("Forward Bear (last signal)", f"{fwd_bear*100:+.2f}%" if not np.isnan(fwd_bear) else "N/A")

#             metrics_df = pd.DataFrame({"Bull": rec["bull_metrics"], "Bear": rec["bear_metrics"]}).T
#             fig_bar = go.Figure()
#             for col in ["net_profit", "max_dd", "sharpe", "win_rate", "profit_factor"]:
#                 fig_bar.add_trace(go.Bar(name=col.replace("_", " ").title(), x=["Bull", "Bear"], y=metrics_df[col]))
#             fig_bar.update_layout(barmode="group", title="Key Performance Metrics", height=400)
#             st.plotly_chart(fig_bar, use_container_width=True)

#             if not rec["bull_equity"].empty:
#                 dd_bull = (rec["bull_equity"] / rec["bull_equity"].cummax() - 1)
#                 fig_dd = go.Figure()
#                 fig_dd.add_trace(go.Scatter(x=rec["dates"], y=dd_bull, name="Bull Draw-down", fill="tozeroy", line=dict(color="red")))
#                 if not rec["bear_equity"].empty:
#                     dd_bear = (rec["bear_equity"] / rec["bear_equity"].cummax() - 1)
#                     fig_dd.add_trace(go.Scatter(x=rec["dates"], y=dd_bear, name="Bear Draw-down", fill="tozeroy", line=dict(color="green")))
#                 fig_dd.update_layout(title="Draw-down Waterfall", yaxis_tickformat=".1%")
#                 st.plotly_chart(fig_dd, use_container_width=True)

#             bull_rets = [r for _, r in rec["bull_signals"]]
#             bear_rets = [r for _, r in rec["bear_signals"]]
#             fig_dist = go.Figure()
#             if bull_rets:
#                 fig_dist.add_trace(go.Histogram(x=bull_rets, name="Bull P&L", opacity=0.7, nbinsx=30))
#             if bear_rets:
#                 fig_dist.add_trace(go.Histogram(x=bear_rets, name="Bear P&L", opacity=0.7, nbinsx=30))
#             fig_dist.update_layout(barmode="overlay", title="Trade P&L Distribution", xaxis_title="Return")
#             st.plotly_chart(fig_dist, use_container_width=True)

#             hist = fetch_historical_data(chosen, "6mo")
#             if hist is not None:
#                 df = hist.copy()
#                 ind = compute_indicators(df, selected, params)
#                 df = pd.concat([df[["Open","High","Low","Close"]], ind], axis=1).dropna()

#                 fig_price = make_subplots(rows=1, cols=1)
#                 fig_price.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Price"))

#                 bull_idx = [df.index[i] for i, _ in rec["bull_signals"]]
#                 if bull_idx:
#                     fig_price.add_trace(go.Scatter(x=bull_idx, y=df.loc[bull_idx, "Close"], mode="markers", marker=dict(color="red", size=10, symbol="triangle-down"), name="Bull Entry"))

#                 bear_idx = [df.index[i] for i, _ in rec["bear_signals"]]
#                 if bear_idx:
#                     fig_price.add_trace(go.Scatter(x=bear_idx, y=df.loc[bear_idx, "Close"], mode="markers", marker=dict(color="green", size=10, symbol="triangle-up"), name="Bear Entry"))

#                 fig_price.update_layout(title=f"{chosen} – Signals on Price", height=600)
#                 st.plotly_chart(fig_price, use_container_width=True)

#         # -------------------------------------------------
#         # GRID SEARCH
#         # -------------------------------------------------
#         st.markdown("---")
#         st.subheader("Automatic Parameter Grid-Search")

#         col_g1, col_g2 = st.columns(2)
#         with col_g1:
#             gs_metric = st.selectbox("Optimization goal", options=["sharpe", "net_profit", "profit_factor"], index=0)
#         with col_g2:
#             gs_dry = st.checkbox("Dry-run (first 10 symbols)", value=True)

#         if st.button("Run Grid Search", type="secondary"):
#             search_symbols = symbols[:10] if gs_dry else symbols
#             with st.spinner(f"Grid-searching {len(search_symbols)} symbols (vectorised)…"):
#                 grid_results = run_grid_search_parallel_vectorised(
#                     search_symbols, selected, params, rsi_bull, rsi_bear,
#                     backtest_period, forward_days, min_trades, min_accuracy,
#                     metric=gs_metric
#                 )
#             st.session_state.grid_results = grid_results
#             st.success(f"Grid-search finished – {len(grid_results)} symbols improved.")

#         if "grid_results" in st.session_state and st.session_state.grid_results:
#             st.markdown("#### Best-Adjusted Equity Curves (vs Original)")

#             best_sym = st.selectbox("Symbol for overlay", options=[""] + [r["symbol"] for r in st.session_state.grid_results])

#             if best_sym:
#                 adj = next(r for r in st.session_state.grid_results if r["symbol"] == best_sym)
#                 orig = next((r for r in st.session_state.backtest_raw if r["symbol"] == best_sym), None)

#                 fig = go.Figure()

#                 if orig:
#                     dir_orig = "bull" if orig["valid_bull"] else "bear" if orig["valid_bear"] else None
#                     if dir_orig:
#                         orig_eq = orig[f"{dir_orig}_equity"]
#                         fig.add_trace(go.Scatter(x=orig["dates"], y=orig_eq, name=f"Original {dir_orig.capitalize()}", line=dict(dash="dot", width=2)))

#                 adj_eq = adj["equity"]
#                 color = "red" if adj["direction"] == "bull" else "green"
#                 fig.add_trace(go.Scatter(x=adj["dates"], y=adj_eq, name=f"Adjusted {adj['direction'].capitalize()} (Best {gs_metric})", line=dict(color=color, width=3)))

#                 fig.update_layout(title=f"{best_sym} – Original vs Best-Adjusted Equity", xaxis_title="Date", yaxis_title="Capital (1.0)", template="plotly_white", height=550)
#                 st.plotly_chart(fig, use_container_width=True)

#                 col_m1, col_m2 = st.columns(2)
#                 with col_m1:
#                     st.metric("Original Net-Profit", f"{orig['bull_metrics' if orig and orig['valid_bull'] else 'bear_metrics']['net_profit']:+.1%}" if orig else "—")
#                     st.metric("Adjusted Net-Profit", f"{adj['metrics']['net_profit']:+.1%}")
#                 with col_m2:
#                     st.metric("Original Sharpe", f"{orig['bull_metrics' if orig and orig['valid_bull'] else 'bear_metrics']['sharpe']:.2f}" if orig else "—")
#                     st.metric("Adjusted Sharpe", f"{adj['metrics']['sharpe']:.2f}")

#                 with st.expander("Winning Parameter Set", expanded=False):
#                     st.json(adj["params"], expanded=False)
#                     st.caption(f"RSI thresholds: Bull < {adj['rsi_bull']}, Bear > {adj['rsi_bear']}")

#                     if st.button("Export all best parameters to CSV"):
#                         export_df = pd.DataFrame([{
#                             "symbol": r["symbol"],
#                             "direction": r["direction"],
#                             "score": r["score"],
#                             "net_profit": r["metrics"]["net_profit"],
#                             "sharpe": r["metrics"]["sharpe"],
#                             **{f"{k}_{p}": v for k, d in r["params"].items() for p, v in d.items()},
#                             "rsi_bull": r["rsi_bull"],
#                             "rsi_bear": r["rsi_bear"]
#                         } for r in st.session_state.grid_results])
#                         csv = export_df.to_csv(index=False).encode()
#                         st.download_button(
#                             label="Download CSV",
#                             data=csv,
#                             file_name=f"best_params_{gs_metric}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv",
#                             mime="text/csv"
#                         )

#         # -------------------------------------------------
#         # CHART VIEWER
#         # -------------------------------------------------
#         st.markdown("---")
#         st.subheader("Chart Viewer")
#         col_a, col_b = st.columns(2)
#         with col_a:
#             bull_sym = st.selectbox("Bullish", options=[""] + st.session_state.bull_df["symbol"].tolist())
#         with col_b:
#             bear_sym = st.selectbox("Bearish", options=[""] + st.session_state.bear_df["symbol"].tolist())
#         if bull_sym or bear_sym:
#             sym = bull_sym or bear_sym
#             with st.spinner("Loading chart..."):
#                 plot_interactive_chart(sym, st.session_state.inds, st.session_state.params,
#                                      st.session_state.bull_df, st.session_state.bear_df)

#     st.caption(f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} | CBOE: {len(symbols):,} symbols")

#     if st.button("Clear Cache"):
#         for d in [HISTORY_CACHE_DIR, BACKTEST_CACHE_DIR]:
#             if os.path.exists(d):
#                 shutil.rmtree(d)
#                 os.makedirs(d, exist_ok=True)
#         if os.path.exists(PARQUET_FILE):
#             os.remove(PARQUET_FILE)
#         st.success("All cache cleared!")
#         st.rerun()

# if __name__ == "__main__":
#     main()



##### ver 2 add baysian optimization #####


# """
# CBOE Optionable Stock Screener – v10.8 (Bayesian Hyper-parameter Tuning)
# - LOGIC REVERSED: Bullish = Likely DOWN, Bearish = Likely UP
# - NEW: Bayesian optimisation of indicator parameters per symbol
# """

# import os
# import io
# import time
# import warnings
# from datetime import datetime
# from concurrent.futures import ThreadPoolExecutor, as_completed
# from typing import Dict, Any, Tuple

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
# # CORRECT BAYESIAN OPTIMIZATION IMPORT
# # -------------------------------------------------
# from bayes_opt import BayesianOptimization

# # -------------------------------------------------
# # CONFIG
# # -------------------------------------------------
# PARQUET_FILE = "optionable_full.parquet"
# HISTORY_CACHE_DIR = "history_cache"
# CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"

# SCHEMA_VERSION = "10.8"
# HISTORY_TTL = 24 * 3600
# SYMBOLS_TTL = 7 * 24 * 3600

# CPU_COUNT = psutil.cpu_count(logical=False) or 4
# MAX_WORKERS = min(CPU_COUNT, 8)
# INITIAL_BATCH_SIZE = min(CPU_COUNT * 20, 200)

# # Bayesian optimisation limits (per symbol)
# MAX_BAYES_TRIALS = 20
# BAYES_INIT_POINTS = 5

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
# # TUNER (rate-limit handling)
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
#     bull_count = pd.Series(0, index=df.index)  # Bullish = DOWN
#     bear_count = pd.Series(0, index=df.index)  # Bearish = UP

#     if "RSI" in inds and "RSI" in df.columns:
#         bull_count += (df["RSI"] < rsi_bull).astype(int)
#         bear_count += (df["RSI"] > rsi_bear).astype(int)

#     if "SMA" in inds and "SMA" in df.columns:
#         bull_count += (close < df["SMA"]).astype(int)
#         bear_count += (close > df["SMA"]).astype(int)

#     if "Bollinger Bands (BB)" in inds and "BB_Lower" in df.columns and "BB_Upper" in df.columns:
#         bull_count += (close < df["BB_Lower"]).astype(int)
#         bear_count += (close > df["BB_Upper"]).astype(int)

#     if "MACD" in inds and "MACD" in df.columns and "Signal" in df.columns:
#         bull_count += (df["MACD"] < df["Signal"]).astype(int)
#         bear_count += (df["MACD"] > df["Signal"]).astype(int)

#     if "Support/Resistance" in inds and "Support" in df.columns and "Resistance" in df.columns:
#         bull_count += (close < df["Support"]).astype(int)
#         bear_count += (close > df["Resistance"]).astype(int)

#     bull_mask = (bull_count == total_indicators) & (total_indicators > 0)
#     bear_mask = (bear_count == total_indicators) & (total_indicators > 0)
#     neutral_mask = ~(bull_mask | bear_mask)

#     return (
#         df[bull_mask].copy(),
#         df[bear_mask].copy(),
#         df[neutral_mask].copy()
#     )

# # -------------------------------------------------
# # BACKTEST & BAYESIAN OPTIMIZER
# # -------------------------------------------------
# def _default_params(selected_inds: list) -> Dict[str, Dict[str, Any]]:
#     defaults = {}
#     for i in selected_inds:
#         if i == "RSI":
#             defaults[i] = {"period": 14}
#         elif i == "SMA":
#             defaults[i] = {"period": 50}
#         elif i == "Bollinger Bands (BB)":
#             defaults[i] = {"period": 20, "std_dev": 2.0}
#         elif i == "MACD":
#             defaults[i] = {"fast": 12, "slow": 26, "signal": 9}
#         elif i == "Support/Resistance":
#             defaults[i] = {"lookback": 20, "tolerance": 0.02}
#     return defaults

# def _sharpe_from_signals(df: pd.DataFrame, inds: list, params: dict) -> float:
#     close = df["Close"]
#     signals = pd.Series(0, index=df.index)

#     if "RSI" in inds:
#         p = int(params["RSI"]["period"])
#         delta = close.diff()
#         gain = delta.clip(lower=0).rolling(p).mean()
#         loss = -delta.clip(upper=0).rolling(p).mean()
#         rs = gain / loss
#         rsi = 100 - (100 / (1 + rs))
#         signals += (rsi < 30).astype(int) * 1
#         signals += (rsi > 70).astype(int) * (-1)

#     if "SMA" in inds:
#         p = int(params["SMA"]["period"])
#         sma = close.rolling(p).mean()
#         signals += (close > sma).astype(int) * 1
#         signals += (close < sma).astype(int) * (-1)

#     if "Bollinger Bands (BB)" in inds:
#         p = int(params["Bollinger Bands (BB)"]["period"])
#         sd = params["Bollinger Bands (BB)"]["std_dev"]
#         mid = close.rolling(p).mean()
#         std = close.rolling(p).std()
#         signals += (close < mid - sd*std).astype(int) * 1
#         signals += (close > mid + sd*std).astype(int) * (-1)

#     if "MACD" in inds:
#         fast = int(params["MACD"]["fast"])
#         slow = int(params["MACD"]["slow"])
#         sig = int(params["MACD"]["signal"])
#         ema_f = close.ewm(span=fast, adjust=False).mean()
#         ema_s = close.ewm(span=slow, adjust=False).mean()
#         macd = ema_f - ema_s
#         signal_line = macd.ewm(span=sig, adjust=False).mean()
#         signals += (macd > signal_line).astype(int) * 1
#         signals += (macd < signal_line).astype(int) * (-1)

#     if "Support/Resistance" in inds:
#         lb = int(params["Support/Resistance"]["lookback"])
#         tol = params["Support/Resistance"]["tolerance"]
#         sup = df["Low"].rolling(lb).min() * (1 + tol)
#         res = df["High"].rolling(lb).max() * (1 - tol)
#         signals += (close < sup).astype(int) * 1
#         signals += (close > res).astype(int) * (-1)

#     daily_ret = close.pct_change().shift(-1)
#     strat_ret = signals * daily_ret
#     strat_ret = strat_ret.dropna()
#     if len(strat_ret) < 20:
#         return -np.inf
#     sharpe = strat_ret.mean() / strat_ret.std() * np.sqrt(252)
#     return sharpe if np.isfinite(sharpe) else -np.inf

# def optimise_symbol(symbol: str, hist: pd.DataFrame, inds: list, default_params: dict) -> Tuple[dict, float, dict, float]:
#     default_sharpe = _sharpe_from_signals(hist, inds, default_params)

#     pbounds = {}
#     param_names = []
#     for i in inds:
#         if i == "RSI":
#             pbounds["rsi_period"] = (5, 50)
#             param_names.append(("RSI", "period", "rsi_period"))
#         elif i == "SMA":
#             pbounds["sma_period"] = (10, 200)
#             param_names.append(("SMA", "period", "sma_period"))
#         elif i == "Bollinger Bands (BB)":
#             pbounds["bb_period"] = (10, 50)
#             pbounds["bb_sd"] = (1.0, 3.0)
#             param_names.extend([("Bollinger Bands (BB)", "period", "bb_period"),
#                                 ("Bollinger Bands (BB)", "std_dev", "bb_sd")])
#         elif i == "MACD":
#             pbounds["macd_fast"] = (5, 30)
#             pbounds["macd_slow"] = (20, 50)
#             pbounds["macd_sig"] = (5, 20)
#             param_names.extend([("MACD", "fast", "macd_fast"),
#                                 ("MACD", "slow", "macd_slow"),
#                                 ("MACD", "signal", "macd_sig")])
#         elif i == "Support/Resistance":
#             pbounds["sr_lookback"] = (10, 60)
#             pbounds["sr_tol"] = (0.0, 0.10)
#             param_names.extend([("Support/Resistance", "lookback", "sr_lookback"),
#                                 ("Support/Resistance", "tolerance", "sr_tol")])

#     if not pbounds:
#         return default_params, default_sharpe, default_params, default_sharpe

#     def _objective(**kwargs):
#         cur = {k: v.copy() for k, v in default_params.items()}
#         for ind, field, key in param_names:
#             cur[ind][field] = kwargs[key]
#         return _sharpe_from_signals(hist, inds, cur)

#     optimizer = BayesianOptimization(f=_objective, pbounds=pbounds, random_state=42, verbose=0)
#     optimizer.maximize(init_points=BAYES_INIT_POINTS, n_iter=MAX_BAYES_TRIALS - BAYES_INIT_POINTS)

#     best = optimizer.max["params"]
#     best_params = {k: v.copy() for k, v in default_params.items()}
#     for ind, field, key in param_names:
#         best_params[ind][field] = best[key]

#     best_sharpe = optimizer.max["target"]
#     return best_params, best_sharpe, default_params, default_sharpe

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

#     signal = "Neutral"
#     color = "gray"
#     if symbol in bull_df["symbol"].values:
#         signal, color = "Bullish", "red"
#     elif symbol in bear_df["symbol"].values:
#         signal, color = "Bearish", "green"

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
# # MAIN UI
# # -------------------------------------------------
# def main():
#     st.set_page_config(page_title="CBOE Screener + Bayes", layout="wide")
#     st.title("CBOE Optionable Stock Screener – v10.8")
#     st.caption("**'Bullish' = Likely DOWN | 'Bearish' = Likely UP** | **Bayesian hyper-parameter tuning per symbol**")

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
#                     st.number_input("Bullish RSI <", 0, 100, 30, key="input_rsi_bull")
#                 with col_b:
#                     st.number_input("Bearish RSI >", 0, 100, 70, key="input_rsi_bear")
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

#     rsi_bull = st.session_state.get("input_rsi_bull", 40)
#     rsi_bear = st.session_state.get("input_rsi_bear", 60)

#     with st.spinner("Loading symbols..."):
#         sym_df = update_symbols()
#     symbols = sym_df["symbol"].dropna().unique().tolist()
#     if dry_run:
#         symbols = symbols[:30]
#         st.info(f"**Dry Run**: {len(symbols)} symbols")
#     else:
#         st.info(f"Scanning **{len(symbols):,}** symbols")

#     if st.button("Start Scan & Bayesian Tune", type="primary"):
#         tuner.__init__()
#         start_all = time.time()

#         with st.spinner("Running default scan..."):
#             df_default = compute_parallel(symbols, min_vol, selected, params)

#         if df_default.empty:
#             st.warning("No stocks passed volume filter.")
#             return

#         df_default["Close"] = df_default["symbol"].map(get_last_close)
#         df_default["Prev Close"] = df_default["symbol"].map(get_prev_close)
#         df_default["Change %"] = np.where(
#             df_default["Prev Close"].notna() & (df_default["Prev Close"] != 0),
#             ((df_default["Close"] - df_default["Prev Close"]) / df_default["Prev Close"] * 100).round(2),
#             np.nan
#         )
#         df_default["Avg Volume"] = df_default["Avg Volume"].apply(lambda x: f"{x:,.0f}")

#         bull_df, bear_df, neutral_df = classify_bull_bear(df_default, selected, rsi_bull, rsi_bear)

#         opt_results = []
#         valid_symbols = df_default["symbol"].tolist()

#         prog_opt = st.progress(0)
#         status_opt = st.empty()

#         def _optimise_one(sym):
#             hist = fetch_historical_data(sym)
#             if hist is None or len(hist) < 100:
#                 return None
#             default_p = _default_params(selected)
#             try:
#                 best_p, best_s, def_p, def_s = optimise_symbol(sym, hist, selected, default_p)
#                 return {
#                     "symbol": sym,
#                     "default_sharpe": round(def_s, 3),
#                     "optimised_sharpe": round(best_s, 3),
#                     "default_params": def_p,
#                     "optimised_params": best_p,
#                     "avg_volume": hist["Volume"].mean()
#                 }
#             except:
#                 return None

#         with ThreadPoolExecutor(max_workers=min(4, MAX_WORKERS)) as pool_opt:
#             futures = {pool_opt.submit(_optimise_one, s): s for s in valid_symbols}
#             for i, f in enumerate(as_completed(futures), 1):
#                 res = f.result()
#                 if res:
#                     opt_results.append(res)
#                 prog_opt.progress(i / len(futures))
#                 status_opt.text(f"Optimising… {i}/{len(futures)}")

#         opt_df = pd.DataFrame(opt_results)
#         if not opt_df.empty:
#             min_vol_sym = opt_df.loc[opt_df["avg_volume"].idxmin()]["symbol"]
#             st.info(f"**Lowest-average-volume symbol:** `{min_vol_sym}`")

#         elapsed_all = time.time() - start_all
#         st.success(f"**Done in {elapsed_all:.1f}s** – {len(df_default)} valid | {len(opt_df)} tuned")

#         st.session_state.update({
#             "bull_df": bull_df, "bear_df": bear_df, "neutral_df": neutral_df,
#             "default_df": df_default, "opt_df": opt_df,
#             "inds": selected, "params": params
#         })

#     # === RESULTS ===
#     if "opt_df" in st.session_state and not st.session_state.opt_df.empty:
#         st.markdown("---")
#         st.subheader("Bayesian Optimisation Results")

#         table = st.session_state.opt_df[["symbol", "avg_volume", "default_sharpe", "optimised_sharpe"]].copy()
#         table["avg_volume"] = table["avg_volume"].apply(lambda x: f"{x:,.0f}")
#         table = table.rename(columns={"avg_volume": "Avg Volume", "default_sharpe": "Default Sharpe", "optimised_sharpe": "Optimised Sharpe"})
#         st.dataframe(table.round(3), use_container_width=True)

#         chart_df = table.melt(id_vars=["symbol"], value_vars=["Default Sharpe", "Optimised Sharpe"], var_name="Set", value_name="Sharpe")
#         fig = go.Figure()
#         for lbl, color in zip(["Default Sharpe", "Optimised Sharpe"], ["steelblue", "orange"]):
#             sub = chart_df[chart_df["Set"] == lbl]
#             fig.add_trace(go.Bar(name=lbl, x=sub["symbol"], y=sub["Sharpe"], marker_color=color, text=sub["Sharpe"], textposition="outside"))
#         fig.update_layout(barmode="group", title="Default vs Optimised Sharpe", xaxis_title="Symbol", yaxis_title="Sharpe", height=600)
#         st.plotly_chart(fig, use_container_width=True)

#         with st.expander("Parameter Comparison"):
#             sym = st.selectbox("Symbol", st.session_state.opt_df["symbol"])
#             row = st.session_state.opt_df[st.session_state.opt_df["symbol"] == sym].iloc[0]
#             comp = []
#             for ind in selected:
#                 d = row["default_params"].get(ind, {})
#                 o = row["optimised_params"].get(ind, {})
#                 for k in d:
#                     comp.append({"Indicator": ind, "Param": k, "Default": d[k], "Optimised": o.get(k)})
#             st.dataframe(pd.DataFrame(comp), use_container_width=True)

#     if 'bull_df' in st.session_state:
#         st.markdown("---")
#         st.subheader("Classic Signals (Default Params)")
#         # ... (same as original) ...
#         # (omitted for brevity — keep your original result display code here)

#     st.caption(f"Updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

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


##### add equity curve graph




# """
# CBOE Optionable Stock Screener – v10.9 (Equity-Curve Overlay)
# - LOGIC REVERSED: Bullish = Likely DOWN, Bearish = Likely UP
# - Bayesian hyper-parameter tuning per symbol
# - NEW: Equity-curve overlay (default vs optimised) + performance table
# """

# import os
# import io
# import time
# import warnings
# from datetime import datetime
# from concurrent.futures import ThreadPoolExecutor, as_completed
# from typing import Dict, Any, Tuple, List

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
# # BAYESIAN OPTIMISATION
# # -------------------------------------------------
# from bayes_opt import BayesianOptimization

# # -------------------------------------------------
# # CONFIG
# # -------------------------------------------------
# PARQUET_FILE = "optionable_full.parquet"
# HISTORY_CACHE_DIR = "history_cache"
# CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"

# SCHEMA_VERSION = "10.9"
# HISTORY_TTL = 24 * 3600
# SYMBOLS_TTL = 7 * 24 * 3600

# CPU_COUNT = psutil.cpu_count(logical=False) or 4
# MAX_WORKERS = min(CPU_COUNT, 8)
# INITIAL_BATCH_SIZE = min(CPU_COUNT * 20, 200)

# MAX_BAYES_TRIALS = 20
# BAYES_INIT_POINTS = 5

# os.makedirs(HISTORY_CACHE_DIR, exist_ok=True)

# # -------------------------------------------------
# # YFINANCE HELPERS
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
# # RATE-LIMIT TUNER
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
# # YFINANCE FETCH
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
#         return None

# # -------------------------------------------------
# # INDICATORS (vectorised)
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
# # CLASSIFIER (reversed logic)
# # -------------------------------------------------
# def classify_bull_bear(df: pd.DataFrame, inds: list, rsi_bull: float, rsi_bear: float):
#     if df.empty:
#         return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

#     close = df["Close"]
#     total_indicators = len(inds)
#     bull_count = pd.Series(0, index=df.index)   # Bullish = DOWN
#     bear_count = pd.Series(0, index=df.index)   # Bearish = UP

#     if "RSI" in inds and "RSI" in df.columns:
#         bull_count += (df["RSI"] < rsi_bull).astype(int)
#         bear_count += (df["RSI"] > rsi_bear).astype(int)

#     if "SMA" in inds and "SMA" in df.columns:
#         bull_count += (close < df["SMA"]).astype(int)
#         bear_count += (close > df["SMA"]).astype(int)

#     if "Bollinger Bands (BB)" in inds and "BB_Lower" in df.columns and "BB_Upper" in df.columns:
#         bull_count += (close < df["BB_Lower"]).astype(int)
#         bear_count += (close > df["BB_Upper"]).astype(int)

#     if "MACD" in inds and "MACD" in df.columns and "Signal" in df.columns:
#         bull_count += (df["MACD"] < df["Signal"]).astype(int)
#         bear_count += (df["MACD"] > df["Signal"]).astype(int)

#     if "Support/Resistance" in inds and "Support" in df.columns and "Resistance" in df.columns:
#         bull_count += (close < df["Support"]).astype(int)
#         bear_count += (close > df["Resistance"]).astype(int)

#     bull_mask = (bull_count == total_indicators) & (total_indicators > 0)
#     bear_mask = (bear_count == total_indicators) & (total_indicators > 0)
#     neutral_mask = ~(bull_mask | bear_mask)

#     return (
#         df[bull_mask].copy(),
#         df[bear_mask].copy(),
#         df[neutral_mask].copy()
#     )

# # -------------------------------------------------
# # BACK-TEST ENGINE (returns equity series + metrics)
# # -------------------------------------------------
# def backtest_equity(df: pd.DataFrame, inds: list, params: dict) -> Tuple[pd.Series, dict]:
#     """
#     Returns:
#         equity_series (pd.Series with DatetimeIndex)
#         metrics dict: {'total_return', 'sharpe', 'max_dd'}
#     """
#     close = df["Close"]
#     signals = pd.Series(0, index=df.index)   #  1 = long, -1 = short, 0 = flat

#     # ----- generate daily signals (same logic as optimisation) -----
#     if "RSI" in inds:
#         p = int(params["RSI"]["period"])
#         delta = close.diff()
#         gain = delta.clip(lower=0).rolling(p).mean()
#         loss = -delta.clip(upper=0).rolling(p).mean()
#         rs = gain / loss
#         rsi = 100 - (100 / (1 + rs))
#         signals += (rsi < 30).astype(int) * 1
#         signals += (rsi > 70).astype(int) * (-1)

#     if "SMA" in inds:
#         p = int(params["SMA"]["period"])
#         sma = close.rolling(p).mean()
#         signals += (close > sma).astype(int) * 1
#         signals += (close < sma).astype(int) * (-1)

#     if "Bollinger Bands (BB)" in inds:
#         p = int(params["Bollinger Bands (BB)"]["period"])
#         sd = params["Bollinger Bands (BB)"]["std_dev"]
#         mid = close.rolling(p).mean()
#         std = close.rolling(p).std()
#         signals += (close < mid - sd*std).astype(int) * 1
#         signals += (close > mid + sd*std).astype(int) * (-1)

#     if "MACD" in inds:
#         fast = int(params["MACD"]["fast"])
#         slow = int(params["MACD"]["slow"])
#         sig = int(params["MACD"]["signal"])
#         ema_f = close.ewm(span=fast, adjust=False).mean()
#         ema_s = close.ewm(span=slow, adjust=False).mean()
#         macd = ema_f - ema_s
#         signal_line = macd.ewm(span=sig, adjust=False).mean()
#         signals += (macd > signal_line).astype(int) * 1
#         signals += (macd < signal_line).astype(int) * (-1)

#     if "Support/Resistance" in inds:
#         lb = int(params["Support/Resistance"]["lookback"])
#         tol = params["Support/Resistance"]["tolerance"]
#         sup = df["Low"].rolling(lb).min() * (1 + tol)
#         res = df["High"].rolling(lb).max() * (1 - tol)
#         signals += (close < sup).astype(int) * 1
#         signals += (close > res).astype(int) * (-1)

#     # ----- daily P&L -----
#     daily_ret = close.pct_change().shift(-1)          # tomorrow's return
#     strat_ret = signals * daily_ret
#     strat_ret = strat_ret.dropna()

#     if len(strat_ret) < 20:
#         equity = pd.Series([1.0], index=[df.index[-1]])
#         metrics = {"total_return": 0.0, "sharpe": -np.inf, "max_dd": 0.0}
#         return equity, metrics

#     # equity curve (starting at 1.0)
#     equity = (1 + strat_ret).cumprod()
#     equity = equity.reindex(df.index, method="ffill").fillna(1.0)

#     # metrics
#     total_ret = equity.iloc[-1] - 1.0
#     sharpe = strat_ret.mean() / strat_ret.std() * np.sqrt(252) if strat_ret.std() != 0 else -np.inf
#     rolling_max = equity.cummax()
#     drawdown = equity / rolling_max - 1.0
#     max_dd = drawdown.min()

#     metrics = {
#         "total_return": round(total_ret, 4),
#         "sharpe": round(sharpe, 3),
#         "max_dd": round(max_dd, 4)
#     }
#     return equity, metrics

# # -------------------------------------------------
# # BAYESIAN OPTIMISER (uses same back-test for objective)
# # -------------------------------------------------
# def _default_params(selected_inds: list) -> Dict[str, Dict[str, Any]]:
#     defaults = {}
#     for i in selected_inds:
#         if i == "RSI":
#             defaults[i] = {"period": 14}
#         elif i == "SMA":
#             defaults[i] = {"period": 50}
#         elif i == "Bollinger Bands (BB)":
#             defaults[i] = {"period": 20, "std_dev": 2.0}
#         elif i == "MACD":
#             defaults[i] = {"fast": 12, "slow": 26, "signal": 9}
#         elif i == "Support/Resistance":
#             defaults[i] = {"lookback": 20, "tolerance": 0.02}
#     return defaults

# def optimise_symbol(symbol: str,
#                     hist: pd.DataFrame,
#                     inds: list,
#                     default_params: dict) -> Tuple[dict, float, dict, float]:
#     # default performance (Sharpe)
#     _, default_metrics = backtest_equity(hist, inds, default_params)
#     default_sharpe = default_metrics["sharpe"]

#     # search space
#     pbounds = {}
#     param_names = []
#     for i in inds:
#         if i == "RSI":
#             pbounds["rsi_period"] = (5, 50)
#             param_names.append(("RSI", "period", "rsi_period"))
#         elif i == "SMA":
#             pbounds["sma_period"] = (10, 200)
#             param_names.append(("SMA", "period", "sma_period"))
#         elif i == "Bollinger Bands (BB)":
#             pbounds["bb_period"] = (10, 50)
#             pbounds["bb_sd"] = (1.0, 3.0)
#             param_names.extend([("Bollinger Bands (BB)", "period", "bb_period"),
#                                 ("Bollinger Bands (BB)", "std_dev", "bb_sd")])
#         elif i == "MACD":
#             pbounds["macd_fast"] = (5, 30)
#             pbounds["macd_slow"] = (20, 50)
#             pbounds["macd_sig"] = (5, 20)
#             param_names.extend([("MACD", "fast", "macd_fast"),
#                                 ("MACD", "slow", "macd_slow"),
#                                 ("MACD", "signal", "macd_sig")])
#         elif i == "Support/Resistance":
#             pbounds["sr_lookback"] = (10, 60)
#             pbounds["sr_tol"] = (0.0, 0.10)
#             param_names.extend([("Support/Resistance", "lookback", "sr_lookback"),
#                                 ("Support/Resistance", "tolerance", "sr_tol")])

#     if not pbounds:
#         return default_params, default_sharpe, default_params, default_sharpe

#     def _objective(**kwargs):
#         cur = {k: v.copy() for k, v in default_params.items()}
#         for ind, field, key in param_names:
#             cur[ind][field] = kwargs[key]
#         _, mets = backtest_equity(hist, inds, cur)
#         return mets["sharpe"]

#     optimizer = BayesianOptimization(f=_objective, pbounds=pbounds, random_state=42, verbose=0)
#     optimizer.maximize(init_points=BAYES_INIT_POINTS, n_iter=MAX_BAYES_TRIALS - BAYES_INIT_POINTS)

#     best = optimizer.max["params"]
#     best_params = {k: v.copy() for k, v in default_params.items()}
#     for ind, field, key in param_names:
#         best_params[ind][field] = best[key]

#     best_sharpe = optimizer.max["target"]
#     return best_params, best_sharpe, default_params, default_sharpe

# # -------------------------------------------------
# # INTERACTIVE CHART (price + indicators)
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

#     signal = "Neutral"
#     color = "gray"
#     if symbol in bull_df["symbol"].values:
#         signal, color = "Bullish", "red"
#     elif symbol in bear_df["symbol"].values:
#         signal, color = "Bearish", "green"

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
# # MAIN UI
# # -------------------------------------------------
# def main():
#     st.set_page_config(page_title="CBOE Screener + Equity Overlay", layout="wide")
#     st.title("CBOE Optionable Stock Screener – v10.9")
#     st.caption(
#         "**'Bullish' = Likely DOWN | 'Bearish' = Likely UP** | "
#         "**Bayesian tuning + Equity-Curve Overlay**"
#     )

#     # ---------- CONTROLS ----------
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
#                     st.number_input("Bullish RSI <", 0, 100, 30, key="input_rsi_bull")
#                 with col_b:
#                     st.number_input("Bearish RSI >", 0, 100, 70, key="input_rsi_bear")
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

#     rsi_bull = st.session_state.get("input_rsi_bull", 40)
#     rsi_bear = st.session_state.get("input_rsi_bear", 60)

#     # ---------- LOAD SYMBOLS ----------
#     with st.spinner("Loading CBOE symbols..."):
#         sym_df = update_symbols()
#     symbols = sym_df["symbol"].dropna().unique().tolist()
#     if dry_run:
#         symbols = symbols[:30]
#         st.info(f"**Dry Run**: {len(symbols)} symbols")
#     else:
#         st.info(f"Scanning **{len(symbols):,}** symbols")

#     # ---------- SCAN + BAYESIAN + EQUITY ----------
#     if st.button("Start Scan & Build Equity Curves", type="primary"):
#         tuner.__init__()
#         start_all = time.time()

#         # ---- 1. default-parameter scan (for signals) ----
#         with st.spinner("Running default scan..."):
#             df_default = compute_parallel(symbols, min_vol, selected, params)

#         if df_default.empty:
#             st.warning("No stocks passed the volume filter.")
#             return

#         # price & change columns
#         df_default["Close"] = df_default["symbol"].map(get_last_close)
#         df_default["Prev Close"] = df_default["symbol"].map(get_prev_close)
#         df_default["Change %"] = np.where(
#             df_default["Prev Close"].notna() & (df_default["Prev Close"] != 0),
#             ((df_default["Close"] - df_default["Prev Close"]) / df_default["Prev Close"] * 100).round(2),
#             np.nan
#         )
#         df_default["Avg Volume"] = df_default["Avg Volume"].apply(lambda x: f"{x:,.0f}")

#         bull_df, bear_df, neutral_df = classify_bull_bear(df_default, selected, rsi_bull, rsi_bear)

#         # ---- 2. Bayesian optimisation + equity curves ----
#         opt_results = []
#         equity_store = {}          # key = f"{sym}_{mode}" , value = (equity_series, metrics)

#         valid_symbols = df_default["symbol"].tolist()
#         prog_opt = st.progress(0)
#         status_opt = st.empty()

#         def _process_one(sym):
#             hist = fetch_historical_data(sym)
#             if hist is None or len(hist) < 100:
#                 return None

#             default_p = _default_params(selected)

#             # ---- default equity ----
#             eq_def, met_def = backtest_equity(hist, selected, default_p)
#             equity_store[f"{sym}_default"] = (eq_def, met_def)

#             # ---- optimisation ----
#             try:
#                 best_p, best_sharpe, _, def_sharpe = optimise_symbol(sym, hist, selected, default_p)
#             except:
#                 best_p, best_sharpe, def_sharpe = default_p, met_def["sharpe"], met_def["sharpe"]

#             # ---- optimised equity ----
#             eq_opt, met_opt = backtest_equity(hist, selected, best_p)
#             equity_store[f"{sym}_optimised"] = (eq_opt, met_opt)

#             return {
#                 "symbol": sym,
#                 "default_sharpe": round(def_sharpe, 3),
#                 "optimised_sharpe": round(best_sharpe, 3),
#                 "default_params": default_p,
#                 "optimised_params": best_p,
#                 "avg_volume": hist["Volume"].mean(),
#                 "default_total_ret": met_def["total_return"],
#                 "optimised_total_ret": met_opt["total_return"],
#                 "default_max_dd": met_def["max_dd"],
#                 "optimised_max_dd": met_opt["max_dd"]
#             }

#         with ThreadPoolExecutor(max_workers=min(4, MAX_WORKERS)) as pool_opt:
#             futures = {pool_opt.submit(_process_one, s): s for s in valid_symbols}
#             for i, f in enumerate(as_completed(futures), 1):
#                 res = f.result()
#                 if res:
#                     opt_results.append(res)
#                 prog_opt.progress(i / len(futures))
#                 status_opt.text(f"Processing… {i}/{len(futures)}")

#         opt_df = pd.DataFrame(opt_results)
#         if not opt_df.empty:
#             min_vol_sym = opt_df.loc[opt_df["avg_volume"].idxmin()]["symbol"]
#             st.info(f"**Lowest-average-volume symbol:** `{min_vol_sym}`")

#         elapsed_all = time.time() - start_all
#         st.success(
#             f"**Finished in {elapsed_all:.1f}s** – {len(df_default)} valid | {len(opt_df)} tuned"
#         )

#         # store everything
#         st.session_state.update({
#             "bull_df": bull_df,
#             "bear_df": bear_df,
#             "neutral_df": neutral_df,
#             "default_df": df_default,
#             "opt_df": opt_df,
#             "equity_store": equity_store,
#             "inds": selected,
#             "params": params
#         })

#     # ==============================================
#     # EQUITY-CURVE OVERLAY SECTION
#     # ==============================================
#     if "equity_store" in st.session_state:
#         st.markdown("---")
#         st.subheader("Equity-Curve Overlay")

#         # ---- selector ----
#         all_keys = list(st.session_state.equity_store.keys())
#         default_options = [k for k in all_keys if k.endswith("_default")]
#         opt_options = [k for k in all_keys if k.endswith("_optimised")]
#         options = default_options + opt_options
#         selected_curves = st.multiselect(
#             "Select curves to overlay (you can pick any combination)",
#             options,
#             default=options[:4] if len(options) >= 4 else options
#         )

#         if selected_curves:
#             fig = go.Figure()
#             perf_rows = []

#             for key in selected_curves:
#                 equity, mets = st.session_state.equity_store[key]
#                 sym = key.split("_")[0]
#                 mode = "Default" if key.endswith("_default") else "Optimised"
#                 color = "steelblue" if mode == "Default" else "orange"

#                 fig.add_trace(go.Scatter(
#                     x=equity.index,
#                     y=equity,
#                     name=f"{sym} ({mode})",
#                     line=dict(color=color, width=2),
#                     hovertemplate=
#                     "<b>%{fullData.name}</b><br>" +
#                     "Date: %{x|%Y-%m-%d}<br>" +
#                     "Equity: %{y:.3f}<extra></extra>"
#                 ))

#                 perf_rows.append({
#                     "Symbol": sym,
#                     "Mode": mode,
#                     "Total Return": mets["total_return"],
#                     "Sharpe": mets["sharpe"],
#                     "Max DD": mets["max_dd"]
#                 })

#             fig.update_layout(
#                 title="Equity-Curve Overlay (starting capital = 1.0)",
#                 xaxis_title="Date",
#                 yaxis_title="Equity",
#                 hovermode="x unified",
#                 template="plotly_white",
#                 height=600,
#                 legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
#             )
#             fig.update_yaxes(tickformat=".2f")
#             st.plotly_chart(fig, use_container_width=True)

#             # ---- performance table ----
#             perf_df = pd.DataFrame(perf_rows)
#             st.dataframe(perf_df.round(4), use_container_width=True)

#     # ==============================================
#     # CLASSIC RESULTS (signals)
#     # ==============================================
#     if 'bull_df' in st.session_state:
#         st.markdown("---")
#         st.subheader("Classic Scan Results (default parameters)")

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

#         with st.expander("Bullish Trade Signals", expanded=True):
#             if st.session_state.bull_df.empty:
#                 st.info("No Bullish Trade Signals.")
#             else:
#                 valid_cols = [c for c in display_cols if c in st.session_state.bull_df.columns]
#                 st.dataframe(
#                     st.session_state.bull_df[valid_cols].round(2)
#                     .sort_values("Change %", ascending=True, na_position='last'),
#                     use_container_width=True
#                 )

#         with st.expander("Bearish Trade Signals", expanded=True):
#             if st.session_state.bear_df.empty:
#                 st.info("No Bearish Trade Signals.")
#             else:
#                 valid_cols = [c for c in display_cols if c in st.session_state.bear_df.columns]
#                 st.dataframe(
#                     st.session_state.bear_df[valid_cols].round(2)
#                     .sort_values("Change %", ascending=False, na_position='last'),
#                     use_container_width=True
#                 )

#         # ---- chart viewer ----
#         st.markdown("---")
#         st.subheader("Interactive Price Chart")
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

#     # ---------- FOOTER ----------
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



###### default and optimize parameter values

# """
# CBOE Optionable Stock Screener – v10.15
# FULLY OPTIMIZED INDICATORS + BACKTEST (NO INF, NO CRASH)
# - Default: default params → default indicators → default backtest
# - Optimized: optimized params → optimized indicators → optimized backtest
# - RSI, BB, Support/Resistance fully recomputed per symbol
# - Bayesian optimization safe & stable
# """

# import os
# import io
# import time
# import warnings
# from datetime import datetime
# from concurrent.futures import ThreadPoolExecutor, as_completed
# from typing import Dict, Any

# import psutil
# import requests
# import pandas as pd
# import numpy as np
# import streamlit as st
# import yfinance as yf
# from bayes_opt import BayesianOptimization
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# # -------------------------------------------------
# # CONFIG
# # -------------------------------------------------
# PARQUET_FILE = "optionable_full.parquet"
# HISTORY_CACHE_DIR = "history_cache"
# CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"

# SCHEMA_VERSION = "10.15"
# HISTORY_TTL = 24 * 3600
# SYMBOLS_TTL = 7 * 24 * 3600

# CPU_COUNT = psutil.cpu_count(logical=False) or 4
# MAX_WORKERS = min(CPU_COUNT, 8)
# INITIAL_BATCH_SIZE = min(CPU_COUNT * 20, 200)

# MAX_BAYES_TRIALS = 20
# BAYES_INIT_POINTS = 5

# os.makedirs(HISTORY_CACHE_DIR, exist_ok=True)

# # -------------------------------------------------
# # YFINANCE HELPERS
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
# # RATE-LIMIT TUNER
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
# # YFINANCE FETCH
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
#         return None

# # -------------------------------------------------
# # INDICATOR COMPUTATION (VECTORIZED, SAFE)
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
#         p = int(params["RSI"]["period"])
#         delta = close.diff()
#         gain = delta.clip(lower=0).rolling(p).mean()
#         loss = -delta.clip(upper=0).rolling(p).mean()
#         rs = gain / loss.replace(0, np.nan)
#         rsi = 100 - (100 / (1 + rs))
#         out["RSI"] = rsi.fillna(50)

#     if "Bollinger Bands (BB)" in inds:
#         p = int(params["Bollinger Bands (BB)"]["period"])
#         sd = params["Bollinger Bands (BB)"]["std_dev"]
#         mid = close.rolling(p).mean()
#         std = close.rolling(p).std()
#         out["BB_Mid"] = mid
#         out["BB_Upper"] = mid + std * sd
#         out["BB_Lower"] = mid - std * sd

#     if "Support/Resistance" in inds:
#         lb = int(params["Support/Resistance"]["lookback"])
#         tol = params["Support/Resistance"]["tolerance"]
#         sup = low.rolling(lb).min() * (1 + tol)
#         res = high.rolling(lb).max() * (1 - tol)
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
#             status.text(f"Valid: {sum(len(r) for r in results)}")

#     return pd.concat(results, ignore_index=True) if results else pd.DataFrame()

# # -------------------------------------------------
# # BACK-TEST ENGINE (SAFE SHARPE)
# # -------------------------------------------------
# def backtest_equity(df: pd.DataFrame, inds: list, params: dict) -> dict:
#     close = df["Close"]
#     signals = pd.Series(0, index=df.index)

#     if "RSI" in inds:
#         p = int(params["RSI"]["period"])
#         delta = close.diff()
#         gain = delta.clip(lower=0).rolling(p).mean()
#         loss = -delta.clip(upper=0).rolling(p).mean()
#         rs = gain / loss.replace(0, np.nan)
#         rsi = 100 - (100 / (1 + rs))
#         signals += (rsi < 30).astype(int) * 1
#         signals += (rsi > 70).astype(int) * (-1)

#     if "Bollinger Bands (BB)" in inds:
#         p = int(params["Bollinger Bands (BB)"]["period"])
#         sd = params["Bollinger Bands (BB)"]["std_dev"]
#         mid = close.rolling(p).mean()
#         std = close.rolling(p).std()
#         signals += (close < mid - sd*std).astype(int) * 1
#         signals += (close > mid + sd*std).astype(int) * (-1)

#     if "Support/Resistance" in inds:
#         lb = int(params["Support/Resistance"]["lookback"])
#         tol = params["Support/Resistance"]["tolerance"]
#         sup = df["Low"].rolling(lb).min() * (1 + tol)
#         res = df["High"].rolling(lb).max() * (1 - tol)
#         signals += (close < sup).astype(int) * 1
#         signals += (close > res).astype(int) * (-1)

#     daily_ret = close.pct_change().shift(-1)
#     strat_ret = signals * daily_ret
#     strat_ret = strat_ret.dropna()

#     if len(strat_ret) < 20:
#         return {"total_return": 0.0, "sharpe": 0.0, "max_dd": 0.0}

#     equity = (1 + strat_ret).cumprod()
#     total_ret = equity.iloc[-1] - 1.0

#     if strat_ret.std() == 0 or np.isnan(strat_ret.std()):
#         sharpe = 0.0
#     else:
#         sharpe = strat_ret.mean() / strat_ret.std() * np.sqrt(252)
#         sharpe = np.clip(sharpe, -10.0, 10.0)  # Safe for Bayesian

#     rolling_max = equity.cummax()
#     drawdown = equity / rolling_max - 1.0
#     max_dd = drawdown.min()

#     return {
#         "total_return": round(total_ret, 4),
#         "sharpe": round(sharpe, 3),
#         "max_dd": round(max_dd, 4)
#     }

# # -------------------------------------------------
# # DEFAULT PARAMS
# # -------------------------------------------------
# def _default_params(selected_inds: list) -> Dict[str, Dict[str, Any]]:
#     defaults = {}
#     for i in selected_inds:
#         if i == "RSI": defaults[i] = {"period": 14}
#         elif i == "Bollinger Bands (BB)": defaults[i] = {"period": 20, "std_dev": 2.0}
#         elif i == "Support/Resistance": defaults[i] = {"lookback": 20, "tolerance": 0.02}
#     return defaults

# # -------------------------------------------------
# # BAYESIAN OPTIMISER (SAFE)
# # -------------------------------------------------
# def optimise_symbol(symbol: str, hist: pd.DataFrame, inds: list, default_params: dict):
#     def _objective(**kwargs):
#         cur = {k: v.copy() for k, v in default_params.items()}
#         for ind, field, key in param_names:
#             val = kwargs[key]
#             cur[ind][field] = int(val) if field in ["period", "lookback"] else val
#         try:
#             metrics = backtest_equity(hist, inds, cur)
#             return metrics["sharpe"]
#         except:
#             return -10.0

#     pbounds = {}
#     param_names = []
#     for i in inds:
#         if i == "RSI":
#             pbounds["rsi_period"] = (5, 50)
#             param_names.append(("RSI", "period", "rsi_period"))
#         elif i == "Bollinger Bands (BB)":
#             pbounds["bb_period"] = (10, 50)
#             pbounds["bb_sd"] = (1.0, 3.0)
#             param_names.extend([("Bollinger Bands (BB)", "period", "bb_period"),
#                                 ("Bollinger Bands (BB)", "std_dev", "bb_sd")])
#         elif i == "Support/Resistance":
#             pbounds["sr_lookback"] = (10, 60)
#             pbounds["sr_tol"] = (0.0, 0.10)
#             param_names.extend([("Support/Resistance", "lookback", "sr_lookback"),
#                                 ("Support/Resistance", "tolerance", "sr_tol")])

#     if not pbounds:
#         return default_params

#     optimizer = BayesianOptimization(f=_objective, pbounds=pbounds, random_state=42, verbose=0)
#     try:
#         optimizer.maximize(init_points=BAYES_INIT_POINTS, n_iter=MAX_BAYES_TRIALS - BAYES_INIT_POINTS)
#         best = optimizer.max["params"]
#         best_params = {k: v.copy() for k, v in default_params.items()}
#         for ind, field, key in param_names:
#             val = best[key]
#             best_params[ind][field] = int(val) if field in ["period", "lookback"] else val
#         return best_params
#     except:
#         return default_params

# # -------------------------------------------------
# # MAIN UI
# # -------------------------------------------------
# def main():
#     st.set_page_config(page_title="CBOE Screener – FINAL", layout="wide")
#     st.title("CBOE Optionable Stock Screener – v10.15")
#     st.success("**FULLY OPTIMIZED INDICATORS + BACKTEST (NO CRASH)**")

#     col1, col2 = st.columns(2)
#     with col1:
#         min_vol = st.number_input("Min Avg Daily Volume", 100_000, 5_000_000, 500_000, 50_000)
#     with col2:
#         dry_run = st.checkbox("Dry Run (first 30 symbols)", value=True)

#     st.subheader("Technical Indicators")
#     all_inds = ["RSI", "Bollinger Bands (BB)", "Support/Resistance"]
#     selected = st.multiselect("Select Indicators", all_inds, default=[])

#     params = {}
#     for i in selected:
#         with st.expander(i, expanded=True):
#             if i == "RSI":
#                 p = st.slider("Period", 5, 50, 14, key="rsi_p")
#                 col_a, col_b = st.columns(2)
#                 with col_a:
#                     st.number_input("Bullish RSI <", 0, 100, 30, key="input_rsi_bull")
#                 with col_b:
#                     st.number_input("Bearish RSI >", 0, 100, 70, key="input_rsi_bear")
#                 params[i] = {"period": p}
#             elif i == "Bollinger Bands (BB)":
#                 p1 = st.slider("Period", 10, 50, 20, key="bb_p")
#                 p2 = st.slider("Std Dev", 1.0, 3.0, 2.0, 0.1, key="bb_sd")
#                 params[i] = {"period": p1, "std_dev": p2}
#             elif i == "Support/Resistance":
#                 lb = st.slider("Lookback", 10, 60, 20, key="sr_lb")
#                 tol = st.slider("Tolerance (%)", 0.0, 10.0, 2.0, 0.1, key="sr_tol") / 100
#                 params[i] = {"lookback": lb, "tolerance": tol}

#     rsi_bull = st.session_state.get("input_rsi_bull", 40)
#     rsi_bear = st.session_state.get("input_rsi_bear", 60)

#     with st.spinner("Loading symbols..."):
#         sym_df = update_symbols()
#     symbols = sym_df["symbol"].dropna().unique().tolist()
#     if dry_run:
#         symbols = symbols[:30]
#         st.info(f"**Dry Run**: {len(symbols)} symbols")
#     else:
#         st.info(f"Scanning **{len(symbols):,}** symbols")

#     if st.button("Start Scan & Backtest", type="primary"):
#         tuner.__init__()
#         start_all = time.time()

#         # 1. Default scan
#         with st.spinner("Running default scan..."):
#             df_default = compute_parallel(symbols, min_vol, selected, params)

#         if df_default.empty:
#             st.warning("No stocks passed volume filter.")
#             return

#         df_default["Close"] = df_default["symbol"].map(get_last_close)
#         df_default["Prev Close"] = df_default["symbol"].map(get_prev_close)
#         df_default["Change %"] = np.where(
#             df_default["Prev Close"].notna() & (df_default["Prev Close"] != 0),
#             ((df_default["Close"] - df_default["Prev Close"]) / df_default["Prev Close"] * 100).round(2),
#             np.nan
#         )
#         df_default["Avg Volume"] = df_default["Avg Volume"].apply(lambda x: f"{x:,.0f}")

#         # 2. Per-symbol optimization + full recompute
#         results = []
#         valid_symbols = df_default["symbol"].tolist()
#         prog_opt = st.progress(0)
#         status_opt = st.empty()

#         default_p = _default_params(selected)

#         def _process_one(sym):
#             hist = fetch_historical_data(sym)
#             if hist is None or len(hist) < 100:
#                 return None

#             # DEFAULT
#             ind_def = compute_indicators_vectorized(hist, selected, default_p)
#             row_def = ind_def[ind_def["symbol"] == sym].iloc[0]
#             met_def = backtest_equity(hist, selected, default_p)

#             # OPTIMIZED
#             best_p = optimise_symbol(sym, hist, selected, default_p)
#             ind_opt = compute_indicators_vectorized(hist, selected, best_p)
#             row_opt = ind_opt[ind_opt["symbol"] == sym].iloc[0]
#             met_opt = backtest_equity(hist, selected, best_p)

#             return {
#                 "symbol": sym,
#                 "close": round(row_def["Close"], 2),
#                 "change_pct": df_default[df_default["symbol"] == sym]["Change %"].iloc[0],
#                 "avg_volume": row_def["Avg Volume"],
#                 "default": {
#                     "rsi": round(row_def.get("RSI", np.nan), 2) if "RSI" in row_def else np.nan,
#                     "bb_lower": round(row_def.get("BB_Lower", np.nan), 2) if "BB_Lower" in row_def else np.nan,
#                     "bb_mid": round(row_def.get("BB_Mid", np.nan), 2) if "BB_Mid" in row_def else np.nan,
#                     "bb_upper": round(row_def.get("BB_Upper", np.nan), 2) if "BB_Upper" in row_def else np.nan,
#                     "support": round(row_def.get("Support", np.nan), 2) if "Support" in row_def else np.nan,
#                     "resistance": round(row_def.get("Resistance", np.nan), 2) if "Resistance" in row_def else np.nan,
#                     "metrics": met_def
#                 },
#                 "optimized": {
#                     "rsi": round(row_opt.get("RSI", np.nan), 2) if "RSI" in row_opt else np.nan,
#                     "bb_lower": round(row_opt.get("BB_Lower", np.nan), 2) if "BB_Lower" in row_opt else np.nan,
#                     "bb_mid": round(row_opt.get("BB_Mid", np.nan), 2) if "BB_Mid" in row_opt else np.nan,
#                     "bb_upper": round(row_opt.get("BB_Upper", np.nan), 2) if "BB_Upper" in row_opt else np.nan,
#                     "support": round(row_opt.get("Support", np.nan), 2) if "Support" in row_opt else np.nan,
#                     "resistance": round(row_opt.get("Resistance", np.nan), 2) if "Resistance" in row_opt else np.nan,
#                     "metrics": met_opt
#                 }
#             }

#         with ThreadPoolExecutor(max_workers=min(4, MAX_WORKERS)) as pool_opt:
#             futures = {pool_opt.submit(_process_one, s): s for s in valid_symbols}
#             for i, f in enumerate(as_completed(futures), 1):
#                 res = f.result()
#                 if res:
#                     results.append(res)
#                 prog_opt.progress(i / len(futures))
#                 status_opt.text(f"Backtesting… {i}/{len(futures)}")

#         # Build final table
#         rows = []
#         for r in results:
#             d = r["default"]
#             o = r["optimized"]
#             rows.append({
#                 "Symbol": r["symbol"],
#                 "Mode": "Default",
#                 "Close": r["close"],
#                 "Change %": r["change_pct"],
#                 "Avg Volume": r["avg_volume"],
#                 "RSI": d["rsi"],
#                 "BB_Lower": d["bb_lower"],
#                 "BB_Mid": d["bb_mid"],
#                 "BB_Upper": d["bb_upper"],
#                 "Support": d["support"],
#                 "Resistance": d["resistance"],
#                 "Max DD": d["metrics"]["max_dd"],
#                 "Sharpe": d["metrics"]["sharpe"],
#                 "Total Return": d["metrics"]["total_return"]
#             })
#             rows.append({
#                 "Symbol": r["symbol"],
#                 "Mode": "Optimized",
#                 "Close": r["close"],
#                 "Change %": r["change_pct"],
#                 "Avg Volume": r["avg_volume"],
#                 "RSI": o["rsi"],
#                 "BB_Lower": o["bb_lower"],
#                 "BB_Mid": o["bb_mid"],
#                 "BB_Upper": o["bb_upper"],
#                 "Support": o["support"],
#                 "Resistance": o["resistance"],
#                 "Max DD": o["metrics"]["max_dd"],
#                 "Sharpe": o["metrics"]["sharpe"],
#                 "Total Return": o["metrics"]["total_return"]
#             })

#         results_df = pd.DataFrame(rows)
#         results_df = results_df.sort_values(["Symbol", "Mode"], ascending=[True, False])

#         elapsed_all = time.time() - start_all
#         st.success(f"**Done in {elapsed_all:.1f}s** – {len(df_default)} valid | {len(results)} tuned")

#         st.session_state["results_df"] = results_df

#     # FINAL TABLE
#     if "results_df" in st.session_state:
#         st.markdown("---")
#         st.subheader("Backtest Results: Default vs Optimized")
#         df = st.session_state.results_df
#         st.dataframe(
#             df[[
#                 "Symbol", "Mode", "Close", "Change %", "Avg Volume",
#                 "RSI", "BB_Lower", "BB_Mid", "BB_Upper",
#                 "Support", "Resistance",
#                 "Max DD", "Sharpe", "Total Return"
#             ]],
#             use_container_width=True,
#             hide_index=True
#         )
#         csv = df.to_csv(index=False).encode()
#         st.download_button("Download Results", csv, "backtest_results.csv", "text/csv")

#     st.caption(f"Updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

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


###### forward walking test

# """
# CBOE Optionable Stock Screener – v10.19
# WALK-FORWARD OPTIMIZATION + REAL DATA + FALLBACK
# - 60-day train + 60-day test (120 days total)
# - Fallback to full-period if not enough data
# - No "No results" | No KeyError | Production-ready
# """

# import os
# import io
# import time
# import warnings
# from datetime import datetime
# from concurrent.futures import ThreadPoolExecutor, as_completed
# from typing import Dict, Any

# import psutil
# import requests
# import pandas as pd
# import numpy as np
# import streamlit as st
# import yfinance as yf
# from bayes_opt import BayesianOptimization
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# # -------------------------------------------------
# # CONFIG
# # -------------------------------------------------
# PARQUET_FILE = "optionable_full.parquet"
# HISTORY_CACHE_DIR = "history_cache"
# CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"

# SCHEMA_VERSION = "10.19"
# HISTORY_TTL = 24 * 3600
# SYMBOLS_TTL = 7 * 24 * 3600

# CPU_COUNT = psutil.cpu_count(logical=False) or 4
# MAX_WORKERS = min(CPU_COUNT, 8)
# INITIAL_BATCH_SIZE = min(CPU_COUNT * 20, 200)

# MAX_BAYES_TRIALS = 20
# BAYES_INIT_POINTS = 5

# # WALK-FORWARD (REALISTIC FOR DAILY DATA)
# TRAIN_DAYS = 60   # ~3 months of trading days
# TEST_DAYS = 60    # ~3 months of trading days
# MIN_DATA_DAYS = 120  # ~5 months total

# os.makedirs(HISTORY_CACHE_DIR, exist_ok=True)

# # -------------------------------------------------
# # YFINANCE HELPERS
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
# # RATE-LIMIT TUNER
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
# # YFINANCE FETCH
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
#         return None

# # -------------------------------------------------
# # INDICATOR COMPUTATION (VECTORIZED, SAFE)
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
#         p = int(params["RSI"]["period"])
#         delta = close.diff()
#         gain = delta.clip(lower=0).rolling(p).mean()
#         loss = -delta.clip(upper=0).rolling(p).mean()
#         rs = gain / loss.replace(0, np.nan)
#         rsi = 100 - (100 / (1 + rs))
#         out["RSI"] = rsi.fillna(50)

#     if "Bollinger Bands (BB)" in inds:
#         p = int(params["Bollinger Bands (BB)"]["period"])
#         sd = params["Bollinger Bands (BB)"]["std_dev"]
#         mid = close.rolling(p).mean()
#         std = close.rolling(p).std()
#         out["BB_Mid"] = mid
#         out["BB_Upper"] = mid + std * sd
#         out["BB_Lower"] = mid - std * sd

#     if "Support/Resistance" in inds:
#         lb = int(params["Support/Resistance"]["lookback"])
#         tol = params["Support/Resistance"]["tolerance"]
#         sup = low.rolling(lb).min() * (1 + tol)
#         res = high.rolling(lb).max() * (1 - tol)
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
#             status.text(f"Valid: {sum(len(r) for r in results)}")

#     return pd.concat(results, ignore_index=True) if results else pd.DataFrame()

# # -------------------------------------------------
# # BACK-TEST ENGINE (SAFE SHARPE)
# # -------------------------------------------------
# def backtest_equity(df: pd.DataFrame, inds: list, params: dict) -> dict:
#     close = df["Close"]
#     signals = pd.Series(0, index=df.index)

#     if "RSI" in inds:
#         p = int(params["RSI"]["period"])
#         delta = close.diff()
#         gain = delta.clip(lower=0).rolling(p).mean()
#         loss = -delta.clip(upper=0).rolling(p).mean()
#         rs = gain / loss.replace(0, np.nan)
#         rsi = 100 - (100 / (1 + rs))
#         signals += (rsi < 30).astype(int) * 1
#         signals += (rsi > 70).astype(int) * (-1)

#     if "Bollinger Bands (BB)" in inds:
#         p = int(params["Bollinger Bands (BB)"]["period"])
#         sd = params["Bollinger Bands (BB)"]["std_dev"]
#         mid = close.rolling(p).mean()
#         std = close.rolling(p).std()
#         signals += (close < mid - sd*std).astype(int) * 1
#         signals += (close > mid + sd*std).astype(int) * (-1)

#     if "Support/Resistance" in inds:
#         lb = int(params["Support/Resistance"]["lookback"])
#         tol = params["Support/Resistance"]["tolerance"]
#         sup = df["Low"].rolling(lb).min() * (1 + tol)
#         res = df["High"].rolling(lb).max() * (1 - tol)
#         signals += (close < sup).astype(int) * 1
#         signals += (close > res).astype(int) * (-1)

#     daily_ret = close.pct_change().shift(-1)
#     strat_ret = signals * daily_ret
#     strat_ret = strat_ret.dropna()

#     if len(strat_ret) < 10:
#         return {"total_return": 0.0, "sharpe": 0.0, "max_dd": 0.0}

#     equity = (1 + strat_ret).cumprod()
#     total_ret = equity.iloc[-1] - 1.0

#     if strat_ret.std() == 0 or np.isnan(strat_ret.std()):
#         sharpe = 0.0
#     else:
#         sharpe = strat_ret.mean() / strat_ret.std() * np.sqrt(252)
#         sharpe = np.clip(sharpe, -10.0, 10.0)

#     rolling_max = equity.cummax()
#     drawdown = equity / rolling_max - 1.0
#     max_dd = drawdown.min()

#     return {
#         "total_return": round(total_ret, 4),
#         "sharpe": round(sharpe, 3),
#         "max_dd": round(max_dd, 4)
#     }

# # -------------------------------------------------
# # DEFAULT PARAMS
# # -------------------------------------------------
# def _default_params(selected_inds: list) -> Dict[str, Dict[str, Any]]:
#     defaults = {}
#     for i in selected_inds:
#         if i == "RSI": defaults[i] = {"period": 14}
#         elif i == "Bollinger Bands (BB)": defaults[i] = {"period": 20, "std_dev": 2.0}
#         elif i == "Support/Resistance": defaults[i] = {"lookback": 20, "tolerance": 0.02}
#     return defaults

# # -------------------------------------------------
# # BAYESIAN OPTIMISER (SAFE)
# # -------------------------------------------------
# def optimise_symbol(symbol: str, hist: pd.DataFrame, inds: list, default_params: dict):
#     def _objective(**kwargs):
#         cur = {k: v.copy() for k, v in default_params.items()}
#         for ind, field, key in param_names:
#             val = kwargs[key]
#             cur[ind][field] = int(val) if field in ["period", "lookback"] else val
#         try:
#             return backtest_equity(hist, inds, cur)["sharpe"]
#         except:
#             return -10.0

#     pbounds = {}
#     param_names = []
#     for i in inds:
#         if i == "RSI":
#             pbounds["rsi_period"] = (5, 50)
#             param_names.append(("RSI", "period", "rsi_period"))
#         elif i == "Bollinger Bands (BB)":
#             pbounds["bb_period"] = (10, 50)
#             pbounds["bb_sd"] = (1.0, 3.0)
#             param_names.extend([("Bollinger Bands (BB)", "period", "bb_period"),
#                                 ("Bollinger Bands (BB)", "std_dev", "bb_sd")])
#         elif i == "Support/Resistance":
#             pbounds["sr_lookback"] = (10, 60)
#             pbounds["sr_tol"] = (0.0, 0.10)
#             param_names.extend([("Support/Resistance", "lookback", "sr_lookback"),
#                                 ("Support/Resistance", "tolerance", "sr_tol")])

#     if not pbounds:
#         return default_params

#     optimizer = BayesianOptimization(f=_objective, pbounds=pbounds, random_state=42, verbose=0)
#     try:
#         optimizer.maximize(init_points=BAYES_INIT_POINTS, n_iter=MAX_BAYES_TRIALS - BAYES_INIT_POINTS)
#         best = optimizer.max["params"]
#         best_params = {k: v.copy() for k, v in default_params.items()}
#         for ind, field, key in param_names:
#             val = best[key]
#             best_params[ind][field] = int(val) if field in ["period", "lookback"] else val
#         return best_params
#     except:
#         return default_params

# # -------------------------------------------------
# # WALK-FORWARD OPTIMIZER
# # -------------------------------------------------
# def walk_forward_optimize(hist: pd.DataFrame, inds: list, default_params: dict):
#     if len(hist) < MIN_DATA_DAYS:
#         return default_params, {"sharpe": 0.0, "total_return": 0.0, "max_dd": 0.0}

#     train_df = hist.iloc[:TRAIN_DAYS].copy()
#     test_df = hist.iloc[TRAIN_DAYS:TRAIN_DAYS + TEST_DAYS].copy()

#     if len(train_df) < 40 or len(test_df) < 20:
#         return default_params, {"sharpe": 0.0, "total_return": 0.0, "max_dd": 0.0}

#     best_params = optimise_symbol("tmp", train_df, inds, default_params)
#     oos_metrics = backtest_equity(test_df, inds, best_params)

#     return best_params, oos_metrics

# # -------------------------------------------------
# # MAIN UI
# # -------------------------------------------------
# def main():
#     st.set_page_config(page_title="CBOE Screener – WFO", layout="wide")
#     st.title("CBOE Optionable Stock Screener – v10.19")
#     st.success("**WALK-FORWARD + REAL DATA + FALLBACK**")

#     col1, col2 = st.columns(2)
#     with col1:
#         min_vol = st.number_input("Min Avg Daily Volume", 100_000, 5_000_000, 500_000, 50_000)
#     with col2:
#         dry_run = st.checkbox("Dry Run (first 30 symbols)", value=True)

#     st.subheader("Technical Indicators")
#     all_inds = ["RSI", "Bollinger Bands (BB)", "Support/Resistance"]
#     selected = st.multiselect("Select Indicators", all_inds, default=[])

#     params = {}
#     for i in selected:
#         with st.expander(i, expanded=True):
#             if i == "RSI":
#                 p = st.slider("Period", 5, 50, 14, key="rsi_p")
#                 col_a, col_b = st.columns(2)
#                 with col_a:
#                     st.number_input("Bullish RSI <", 0, 100, 30, key="input_rsi_bull")
#                 with col_b:
#                     st.number_input("Bearish RSI >", 0, 100, 70, key="input_rsi_bear")
#                 params[i] = {"period": p}
#             elif i == "Bollinger Bands (BB)":
#                 p1 = st.slider("Period", 10, 50, 20, key="bb_p")
#                 p2 = st.slider("Std Dev", 1.0, 3.0, 2.0, 0.1, key="bb_sd")
#                 params[i] = {"period": p1, "std_dev": p2}
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

#     if st.button("Start Scan & Walk-Forward Backtest", type="primary"):
#         tuner.__init__()
#         start_all = time.time()

#         # 1. Default scan
#         with st.spinner("Running default scan..."):
#             df_default = compute_parallel(symbols, min_vol, selected, params)

#         if df_default.empty:
#             st.warning("No stocks passed volume filter.")
#             return

#         df_default["Close"] = df_default["symbol"].map(get_last_close)
#         df_default["Prev Close"] = df_default["symbol"].map(get_prev_close)
#         df_default["Change %"] = np.where(
#             df_default["Prev Close"].notna() & (df_default["Prev Close"] != 0),
#             ((df_default["Close"] - df_default["Prev Close"]) / df_default["Prev Close"] * 100).round(2),
#             np.nan
#         )
#         df_default["Avg Volume"] = df_default["Avg Volume"].apply(lambda x: f"{x:,.0f}")

#         # 2. Per-symbol WFO
#         results = []
#         valid_symbols = df_default["symbol"].tolist()
#         prog_opt = st.progress(0)
#         status_opt = st.empty()

#         default_p = _default_params(selected)

#         def _process_one(sym):
#             hist = fetch_historical_data(sym)
#             if hist is None or len(hist) < 100:
#                 return None

#             # DEFAULT (full period)
#             ind_def = compute_indicators_vectorized(hist, selected, default_p)
#             row_def = ind_def[ind_def["symbol"] == sym].iloc[0]
#             met_def = backtest_equity(hist, selected, default_p)

#             # OPTIMIZED + WFO with fallback
#             if len(hist) < MIN_DATA_DAYS:
#                 best_p = optimise_symbol(sym, hist, selected, default_p)
#                 ind_opt = compute_indicators_vectorized(hist, selected, best_p)
#                 row_opt = ind_opt[ind_opt["symbol"] == sym].iloc[0]
#                 met_opt = backtest_equity(hist, selected, best_p)
#                 oos_metrics = {"sharpe": np.nan, "total_return": np.nan, "max_dd": np.nan}
#             else:
#                 best_p, oos_metrics = walk_forward_optimize(hist, selected, default_p)
#                 ind_opt = compute_indicators_vectorized(hist, selected, best_p)
#                 row_opt = ind_opt[ind_opt["symbol"] == sym].iloc[0]
#                 met_opt = backtest_equity(hist, selected, best_p)

#             return {
#                 "symbol": sym,
#                 "close": round(row_def["Close"], 2),
#                 "change_pct": df_default[df_default["symbol"] == sym]["Change %"].iloc[0],
#                 "avg_volume": row_def["Avg Volume"],
#                 "default": {
#                     "rsi": round(row_def.get("RSI", np.nan), 2) if "RSI" in row_def else np.nan,
#                     "bb_lower": round(row_def.get("BB_Lower", np.nan), 2) if "BB_Lower" in row_def else np.nan,
#                     "bb_mid": round(row_def.get("BB_Mid", np.nan), 2) if "BB_Mid" in row_def else np.nan,
#                     "bb_upper": round(row_def.get("BB_Upper", np.nan), 2) if "BB_Upper" in row_def else np.nan,
#                     "support": round(row_def.get("Support", np.nan), 2) if "Support" in row_def else np.nan,
#                     "resistance": round(row_def.get("Resistance", np.nan), 2) if "Resistance" in row_def else np.nan,
#                     "metrics": met_def
#                 },
#                 "optimized": {
#                     "rsi": round(row_opt.get("RSI", np.nan), 2) if "RSI" in row_opt else np.nan,
#                     "bb_lower": round(row_opt.get("BB_Lower", np.nan), 2) if "BB_Lower" in row_opt else np.nan,
#                     "bb_mid": round(row_opt.get("BB_Mid", np.nan), 2) if "BB_Mid" in row_opt else np.nan,
#                     "bb_upper": round(row_opt.get("BB_Upper", np.nan), 2) if "BB_Upper" in row_opt else np.nan,
#                     "support": round(row_opt.get("Support", np.nan), 2) if "Support" in row_opt else np.nan,
#                     "resistance": round(row_opt.get("Resistance", np.nan), 2) if "Resistance" in row_opt else np.nan,
#                     "metrics": met_opt,
#                     "oos": oos_metrics
#                 }
#             }

#         with ThreadPoolExecutor(max_workers=min(4, MAX_WORKERS)) as pool_opt:
#             futures = {pool_opt.submit(_process_one, s): s for s in valid_symbols}
#             for i, f in enumerate(as_completed(futures), 1):
#                 res = f.result()
#                 if res:
#                     results.append(res)
#                 prog_opt.progress(i / len(futures))
#                 status_opt.text(f"Backtesting… {i}/{len(futures)}")

#         # Build final table
#         rows = []
#         for r in results:
#             d = r["default"]
#             o = r["optimized"]
#             # Default Row
#             rows.append({
#                 "Symbol": r["symbol"], "Mode": "Default",
#                 "Close": r["close"], "Change %": r["change_pct"], "Avg Volume": r["avg_volume"],
#                 "RSI": d["rsi"], "BB_Lower": d["bb_lower"], "BB_Mid": d["bb_mid"], "BB_Upper": d["bb_upper"],
#                 "Support": d["support"], "Resistance": d["resistance"],
#                 "Max DD": d["metrics"]["max_dd"], "Sharpe": d["metrics"]["sharpe"], "Total Return": d["metrics"]["total_return"],
#                 "Sharpe_OOS": np.nan, "Return_OOS": np.nan, "MaxDD_OOS": np.nan
#             })
#             # Optimized Row
#             rows.append({
#                 "Symbol": r["symbol"], "Mode": "Optimized",
#                 "Close": r["close"], "Change %": r["change_pct"], "Avg Volume": r["avg_volume"],
#                 "RSI": o["rsi"], "BB_Lower": o["bb_lower"], "BB_Mid": o["bb_mid"], "BB_Upper": o["bb_upper"],
#                 "Support": o["support"], "Resistance": o["resistance"],
#                 "Max DD": o["metrics"]["max_dd"], "Sharpe": o["metrics"]["sharpe"], "Total Return": o["metrics"]["total_return"],
#                 "Sharpe_OOS": o["oos"]["sharpe"], "Return_OOS": o["oos"]["total_return"], "MaxDD_OOS": o["oos"]["max_dd"]
#             })

#         results_df = pd.DataFrame(rows)

#         if not results_df.empty:
#             if "Symbol" in results_df.columns and "Mode" in results_df.columns:
#                 results_df = results_df.sort_values(["Symbol", "Mode"], ascending=[True, False])
#             else:
#                 st.warning("Missing 'Symbol' or 'Mode' column. Sorting skipped.")
#         else:
#             st.warning("No results to display.")
#             return

#         elapsed_all = time.time() - start_all
#         st.success(f"**Done in {elapsed_all:.1f}s** – {len(df_default)} valid | {len(results)} tuned")

#         st.session_state["results_df"] = results_df

#     # FINAL TABLE (SAFE DISPLAY)
#     if "results_df" in st.session_state:
#         st.markdown("---")
#         st.subheader("Walk-Forward Results: In-Sample vs Out-of-Sample")
#         df = st.session_state.results_df

#         if df.empty:
#             st.warning("No results to display.")
#         else:
#             # Base columns
#             base_cols = [
#                 "Symbol", "Mode", "Close", "Change %", "Avg Volume",
#                 "RSI", "BB_Lower", "BB_Mid", "BB_Upper", "Support", "Resistance",
#                 "Max DD", "Sharpe", "Total Return"
#             ]
#             oos_cols = ["Sharpe_OOS", "Return_OOS", "MaxDD_OOS"]
#             available_oos = [col for col in oos_cols if col in df.columns]
#             display_cols = [col for col in base_cols if col in df.columns] + available_oos

#             st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
#             csv = df.to_csv(index=False).encode()
#             st.download_button("Download WFO Results", csv, "wfo_results.csv", "text/csv")

#     st.caption(f"Updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

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

###### auto refresh data up to date and min stock price value
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
CBOE Optionable Stock Screener (Reversed Logic)
================================================
- Bullish = Likely DOWN
- Bearish = Likely UP
- Auto daily refresh (UTC day boundary)
- Min Avg Volume + Min Current Price filter
- Industry best practices: atomic writes, cache hygiene, rate-limit resilience
"""

import os
import io
import time
import warnings
import shutil
from datetime import datetime, timezone
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
# CONFIG – DAILY REFRESH & FILTERS
# -------------------------------------------------
PARQUET_FILE = "optionable_full.parquet"
HISTORY_CACHE_DIR = "history_cache"
CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"
SCHEMA_VERSION = "10.7"

SYMBOLS_TTL = 24 * 3600          # 1 day
HISTORY_TTL = 24 * 3600          # 1 day

CPU_COUNT = psutil.cpu_count(logical=False) or 4
MAX_WORKERS = min(CPU_COUNT, 8)
INITIAL_BATCH_SIZE = min(CPU_COUNT * 20, 200)

os.makedirs(HISTORY_CACHE_DIR, exist_ok=True)


# -------------------------------------------------
# DAILY REFRESH HELPERS
# -------------------------------------------------
def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()

def _last_refresh_date(parquet_path: str) -> str | None:
    if not os.path.exists(parquet_path):
        return None
    try:
        df = pd.read_parquet(parquet_path, columns=["updated_at"])
        return pd.to_datetime(df["updated_at"].iloc[0]).date().isoformat()
    except Exception:
        return None

def _purge_stale_history():
    now = time.time()
    for filename in os.listdir(HISTORY_CACHE_DIR):
        path = os.path.join(HISTORY_CACHE_DIR, filename)
        if os.path.getmtime(path) < now - HISTORY_TTL:
            os.remove(path)


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
        except Exception:
            return pd.DataFrame()


# -------------------------------------------------
# ADAPTIVE TUNER
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
# CACHE LAYER
# -------------------------------------------------
def get_cached_history(symbol: str) -> pd.DataFrame | None:
    path = os.path.join(HISTORY_CACHE_DIR, f"{symbol}.parquet")
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_parquet(path)
        required = ["Open", "High", "Low", "Close", "Volume"]
        if not all(c in df.columns for c in required) or df[required].isna().any().any():
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
    return cached["Close"].iloc[-1] if cached is not None and not cached.empty else np.nan

def get_prev_close(symbol: str) -> float:
    cached = get_cached_history(symbol)
    return cached["Close"].iloc[-2] if cached is not None and len(cached) >= 2 else np.nan


# -------------------------------------------------
# CBOE SYMBOLS – AUTO DAILY REFRESH
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
    df = df.drop_duplicates()
    return df

def update_symbols() -> pd.DataFrame:
    today = _utc_today()
    last_date = _last_refresh_date(PARQUET_FILE)

    if last_date != today:
        fresh = fetch_cboe_symbols()
        fresh = fresh.assign(
            updated_at=datetime.now(timezone.utc).isoformat(),
            schema_version=SCHEMA_VERSION
        )
        tmp_path = PARQUET_FILE + ".tmp"
        fresh.to_parquet(tmp_path, index=False)
        os.replace(tmp_path, PARQUET_FILE)
        return fresh

    return pd.read_parquet(PARQUET_FILE)


# -------------------------------------------------
# YFINANCE HISTORICAL DATA
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
# BATCH PROCESSOR – WITH MIN PRICE FILTER
# -------------------------------------------------
def process_batch(symbols: list, min_vol: int, min_price: float, inds: list, params: dict) -> pd.DataFrame:
    data_frames = []
    for sym in symbols:
        hist = fetch_historical_data(sym)
        if hist is not None and len(hist) >= 100:
            latest_close = hist["Close"].iloc[-1]
            if latest_close < min_price:
                continue
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
def compute_parallel(symbols: list, min_vol: int, min_price: float, inds: list, params: dict) -> pd.DataFrame:
    batch_size = tuner.batch_size
    batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
    results = []
    with ThreadPoolExecutor(max_workers=tuner.workers) as pool:
        futures = [pool.submit(process_batch, b, min_vol, min_price, inds, params) for b in batches]
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
    bull_count = pd.Series(0, index=df.index)
    bear_count = pd.Series(0, index=df.index)

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
# INTERACTIVE CHART
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

    signal = color = "Neutral", "gray"
    if symbol in bull_df["symbol"].values:
        signal, color = "Bullish", "red"
    elif symbol in bear_df["symbol"].values:
        signal, color = "Bearish", "green"

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
# MAIN UI
# -------------------------------------------------
def main():
    st.set_page_config(page_title="CBOE Screener (Reversed)", layout="wide")
    st.title("CBOE Optionable Stock Screener (Reversed Logic)")
    st.caption("**'Bullish' = Likely DOWN | 'Bearish' = Likely UP**")

    # === AUTO DAILY DATA REFRESH ===
    with st.spinner("Refreshing CBOE symbols (once per UTC day)..."):
        sym_df = update_symbols()
    last_sym_update = pd.read_parquet(PARQUET_FILE)["updated_at"].iloc[0][:10]
    st.success(f"Symbols updated: {last_sym_update} UTC")

    _purge_stale_history()

    # === UI CONTROLS ===
    col1, col2 = st.columns(2)
    with col1:
        min_vol = st.number_input(
            "Min Avg Daily Volume", 
            100_000, 5_000_000, 500_000, 50_000,
            help="Filter stocks with low liquidity"
        )
        min_price = st.number_input(
            "Min Current Price ($)", 
            0.0, 1000.0, 5.0, 0.5,
            help="Filter out penny stocks or low-priced securities"
        )
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
            df = compute_parallel(symbols, min_vol, min_price, selected, params)
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

        st.session_state.update({
            "bull_df": bull_df,
            "bear_df": bear_df,
            "neutral_df": neutral_df,
            "inds": selected,
            "params": params
        })

    # === RESULTS ===
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
                valid = [c for c in display_cols if c in st.session_state.bull_df.columns]
                st.dataframe(
                    st.session_state.bull_df[valid].round(2).sort_values("Change %", ascending=True),
                    use_container_width=True
                )

        with st.expander("Bearish Trade Signals", expanded=True):
            if st.session_state.bear_df.empty:
                st.info("No Bearish Trade Signals.")
            else:
                valid = [c for c in display_cols if c in st.session_state.bear_df.columns]
                st.dataframe(
                    st.session_state.bear_df[valid].round(2).sort_values("Change %", ascending=False),
                    use_container_width=True
                )

        with st.expander("Neutral", expanded=False):
            if st.session_state.neutral_df.empty:
                st.info("No neutral signals.")
            else:
                valid = [c for c in display_cols if c in st.session_state.neutral_df.columns]
                st.dataframe(st.session_state.neutral_df[valid].head(20).round(2), use_container_width=True)

        # === CHART ===
        st.markdown("---")
        st.subheader("Interactive Chart Viewer")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            bull_sym = st.selectbox("Bullish", options=[""] + st.session_state.bull_df["symbol"].tolist())
        with col_b:
            bear_sym = st.selectbox("Bearish", options=[""] + st.session_state.bear_df["symbol"].tolist())
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

    st.caption(
        f"Data as of: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | "
        f"CBOE list: {len(symbols):,} symbols | "
        f"Last refresh: {last_sym_update}"
    )

    if st.button("Clear Cache"):
        if os.path.exists(HISTORY_CACHE_DIR):
            shutil.rmtree(HISTORY_CACHE_DIR)
            os.makedirs(HISTORY_CACHE_DIR, exist_ok=True)
        if os.path.exists(PARQUET_FILE):
            os.remove(PARQUET_FILE)
        st.success("Cache cleared!")
        st.rerun()


if __name__ == "__main__":
    main()




###### backward testing added



# """
# CBOE Optionable Stock Screener – v11.8
# INSTANT LOAD | NO HANG | BEAUTIFUL PROGRESS | BULLETPROOF
# """

# import os
# import time
# import numpy as np
# import pandas as pd
# import streamlit as st
# import yfinance as yf
# import plotly.graph_objects as go
# from datetime import datetime
# from typing import Dict, List, Optional
# from sklearn.cluster import KMeans
# from bayes_opt import BayesianOptimization
# import requests
# from requests.adapters import HTTPAdapter
# from urllib3.util.retry import Retry

# # -------------------------------------------------
# # CONFIG
# # -------------------------------------------------
# st.set_page_config(page_title="CBOE Screener v11.8", layout="wide")
# CACHE_DIR = "cache"
# os.makedirs(CACHE_DIR, exist_ok=True)

# MIN_VOL = 500_000
# MIN_BETA = 0.7
# CLUSTERS = 10
# MC_PATHS = 1000
# BAYES_TRIALS = 20
# TRAIN_DAYS, TEST_DAYS = 60, 60
# RETRY_ATTEMPTS = 3
# TIMEOUT = 12

# # Known junk symbols (skip instantly)
# JUNK_SYMBOLS = {"ZVV", "ZBZX", "BTEST", "BRK.B", "BF.B", "CWEN.A", "ZTEST"}

# # -------------------------------------------------
# # 1. ROBUST SESSION
# # -------------------------------------------------
# def _get_session() -> requests.Session:
#     s = requests.Session()
#     retry = Retry(total=RETRY_ATTEMPTS,
#                   backoff_factor=1,
#                   status_forcelist=[429, 500, 502, 503, 504],
#                   allowed_methods={"GET"})
#     adapter = HTTPAdapter(max_retries=retry)
#     s.mount("https://", adapter)
#     s.headers.update({"User-Agent": "Mozilla/5.0 (compatible; CBOE-Screener/11.8)"})
#     return s

# SESSION = _get_session()

# # -------------------------------------------------
# # 2. CACHED CBOE LIST – INSTANT, NO HANG
# # -------------------------------------------------
# @st.cache_data(ttl=7*86400, show_spinner=False)
# def load_cboe_symbols() -> List[str]:
#     """Return CBOE symbols instantly – cached 7 days, fallback if down."""
#     url = "https://cdn.cboe.com/data/us/options/market_statistics/symbol_reference/exo-underlying.csv"
#     try:
#         response = requests.head(url, timeout=5)
#         if response.status_code != 200:
#             raise Exception("CBOE CSV not reachable")
#     except Exception:
#         fallback = ["AAPL","MSFT","GOOGL","TSLA","NVDA","AMD","META","NFLX","SPY","QQQ"]
#         return fallback

#     try:
#         df = pd.read_csv(url, usecols=[0], dtype=str)
#         col = df.columns[0]
#         symbols = df[col].str.upper().str.strip().dropna().unique().tolist()
#         return symbols
#     except Exception:
#         fallback = ["AAPL","MSFT","GOOGL","TSLA","NVDA","AMD","META","NFLX","SPY","QQQ"]
#         return fallback

# # -------------------------------------------------
# # 3. BULLETPROOF CACHED FETCH
# # -------------------------------------------------
# @st.cache_data(
#     ttl=86400,
#     show_spinner=False,
#     hash_funcs={pd.DataFrame: lambda df: f"{df.shape}{df.index[-1] if len(df)>0 else ''}"}
# )
# def cached_fetch(symbol: str) -> Optional[pd.DataFrame]:
#     if symbol in JUNK_SYMBOLS:
#         return None
#     for attempt in range(RETRY_ATTEMPTS):
#         try:
#             ticker = yf.Ticker(symbol, session=SESSION)
#             df = ticker.history(period="6mo", interval="1d", auto_adjust=True, timeout=TIMEOUT)
#             if df.empty or df["Close"].isna().all():
#                 return None
#             df = df.dropna(subset=["Close", "Volume"])
#             if len(df) < 50:
#                 return None
#             df.index = pd.to_datetime(df.index)
#             return df
#         except Exception as e:
#             if attempt == RETRY_ATTEMPTS - 1:
#                 msg = str(e).lower()
#                 if any(x in msg for x in ["delisted", "404", "not found", "no price data"]):
#                     return None
#                 st.warning(f"[{symbol}] {type(e).__name__}: {e}")
#             time.sleep(2 ** attempt)
#     return None

# # -------------------------------------------------
# # 4. PRE-SCREEN
# # -------------------------------------------------
# def pre_screen(symbols: List[str]) -> List[str]:
#     valid = []
#     for sym in symbols:
#         df = cached_fetch(sym)
#         if df is None or len(df) < 100:
#             continue
#         vol = df["Volume"].mean()
#         ret = df["Close"].pct_change().dropna()
#         if len(ret) < 30:
#             continue
#         beta = ret.std() * np.sqrt(252)
#         if vol >= MIN_VOL and beta >= MIN_BETA:
#             valid.append(sym)
#     return valid[:200] if len(valid) > 200 else valid

# # -------------------------------------------------
# # 5. CLUSTERING
# # -------------------------------------------------
# def cluster_symbols(symbols: List[str]) -> Dict[str, int]:
#     feats, syms = [], []
#     for sym in symbols:
#         df = cached_fetch(sym)
#         if df is None or len(df) < 100:
#             continue
#         close, vol = df["Close"], df["Volume"]
#         ret = close.pct_change().dropna()
#         if len(ret) < 30:
#             continue
#         beta = ret.std() * np.sqrt(252)
#         avg_vol = vol.mean()
#         if not (np.isfinite(beta) and np.isfinite(avg_vol)):
#             continue
#         feats.append([beta, np.log1p(avg_vol)])
#         syms.append(sym)

#     if len(feats) < 2:
#         return {s: 0 for s in syms}
#     try:
#         X = np.array(feats)
#         n = min(CLUSTERS, len(feats))
#         km = KMeans(n_clusters=n, random_state=42, n_init=10)
#         labels = km.fit_predict(X)
#         return dict(zip(syms, labels))
#     except Exception:
#         return {s: 0 for s in syms}

# # -------------------------------------------------
# # 6. INDICATORS
# # -------------------------------------------------
# def compute_indicators(df: pd.DataFrame, params: Dict) -> Dict:
#     close, high, low = df["Close"], df["High"], df["Low"]
#     out = {}
#     if "RSI" in params:
#         p = int(params["RSI"]["period"])
#         delta = close.diff()
#         gain = delta.clip(lower=0).rolling(p).mean()
#         loss = -delta.clip(upper=0).rolling(p).mean()
#         rs = gain / loss.replace(0, np.nan)
#         out["RSI"] = 100 - (100 / (1 + rs))
#     if "BB" in params:
#         p, sd = int(params["BB"]["period"]), params["BB"]["std"]
#         mid = close.rolling(p).mean()
#         std = close.rolling(p).std()
#         out["BB_L"], out["BB_U"] = mid - sd*std, mid + sd*std
#     if "SR" in params:
#         lb, tol = int(params["SR"]["lookback"]), params["SR"]["tol"]
#         out["Support"] = low.rolling(lb).min() * (1 + tol)
#         out["Resistance"] = high.rolling(lb).max() * (1 - tol)
#     return out

# # -------------------------------------------------
# # 7. BACKTEST
# # -------------------------------------------------
# def backtest_strategy(df: pd.DataFrame, params: Dict) -> Dict:
#     ind = compute_indicators(df, params)
#     close = df["Close"].values
#     dates = df.index.strftime('%Y-%m-%d').values
#     sig = np.zeros(len(df))

#     for i in range(len(df)):
#         if "RSI" in ind and not pd.isna(ind["RSI"].iloc[i]):
#             if ind["RSI"].iloc[i] < 30: sig[i] += 1
#             if ind["RSI"].iloc[i] > 70: sig[i] -= 1
#         if "BB" in ind and not pd.isna(ind["BB_L"].iloc[i]) and close[i] < ind["BB_L"].iloc[i]: sig[i] += 1
#         if "BB" in ind and not pd.isna(ind["BB_U"].iloc[i]) and close[i] > ind["BB_U"].iloc[i]: sig[i] -= 1
#         if "SR" in ind and not pd.isna(ind["Support"].iloc[i]) and close[i] < ind["Support"].iloc[i]: sig[i] += 1
#         if "SR" in ind and not pd.isna(ind["Resistance"].iloc[i]) and close[i] > ind["Resistance"].iloc[i]: sig[i] -= 1

#     pos, entry, equity, trades = 0, 0, [1.0], []
#     for i in range(1, len(df)):
#         if pos == 0 and sig[i] > 0:
#             pos, entry = 1, close[i]
#             trades.append({"Entry": dates[i], "EPrice": entry})
#         elif pos == 1 and sig[i] < 0:
#             pos = 0
#             pnl = (close[i] - entry) / entry
#             trades[-1].update({"Exit": dates[i], "XPrice": close[i], "P&L": round(pnl, 4)})
#             equity.append(equity[-1] * (1 + pnl))
#         else:
#             equity.append(equity[-1])

#     if pos == 1:
#         pnl = (close[-1] - entry) / entry
#         trades[-1].update({"Exit": dates[-1], "XPrice": close[-1], "P&L": round(pnl, 4)})
#         equity[-1] *= (1 + pnl)

#     rets = np.diff(equity) / equity[:-1] if len(equity) > 1 else np.array([])
#     sharpe = np.mean(rets) / np.std(rets) * np.sqrt(252) if len(rets) and np.std(rets) else 0
#     total_ret = equity[-1] - 1
#     max_dd = np.min((np.maximum.accumulate(equity) - equity) / np.maximum.accumulate(equity)) if equity else 0

#     return {
#         "sharpe": round(sharpe, 3),
#         "return": round(total_ret, 4),
#         "max_dd": round(max_dd, 4),
#         "equity": equity,
#         "dates": dates[-len(equity):].tolist(),
#         "trades": trades,
#         "returns": rets.tolist()
#     }

# # -------------------------------------------------
# # 8. BAYESIAN PER CLUSTER
# # -------------------------------------------------
# def optimize_cluster(rep: str, df: pd.DataFrame, inds: List[str]) -> Dict:
#     def obj(**kw):
#         p = {}
#         for i in inds:
#             if i == "RSI": p[i] = {"period": int(kw.get("rsi_p", 14))}
#             if i == "BB": p[i] = {"period": int(kw.get("bb_p", 20)), "std": kw.get("bb_s", 2.0)}
#             if i == "SR": p[i] = {"lookback": int(kw.get("sr_l", 20)), "tol": kw.get("sr_t", 0.02)}
#         try:
#             return backtest_strategy(df, p)["sharpe"]
#         except:
#             return -10

#     pb = {}
#     if "RSI" in inds: pb["rsi_p"] = (5, 50)
#     if "BB" in inds: pb.update({"bb_p": (10, 50), "bb_s": (1.0, 3.0)})
#     if "SR" in inds: pb.update({"sr_l": (10, 60), "sr_t": (0.0, 0.1)})

#     if not pb:
#         return {i: {"period": 14} for i in inds}

#     opt = BayesianOptimization(obj, pb, random_state=42)
#     opt.maximize(init_points=5, n_iter=BAYES_TRIALS-5)
#     best = opt.max["params"]
#     out = {}
#     for i in inds:
#         if i == "RSI": out[i] = {"period": int(best.get("rsi_p", 14))}
#         if i == "BB": out[i] = {"period": int(best.get("bb_p", 20)), "std": best.get("bb_s", 2.0)}
#         if i == "SR": out[i] = {"lookback": int(best.get("sr_l", 20)), "tol": best.get("sr_t", 0.02)}
#     return out

# # -------------------------------------------------
# # 9. MONTE-CARLO & WALK-FORWARD
# # -------------------------------------------------
# def monte_carlo(returns: List[float]) -> Dict:
#     if not returns: return {"paths": [], "p5": [], "p95": []}
#     sim = np.zeros((MC_PATHS, len(returns)+1))
#     sim[:,0] = 1.0
#     for i in range(1, len(returns)+1):
#         sim[:,i] = sim[:,i-1] * (1 + np.random.choice(returns, MC_PATHS))
#     return {"paths": sim.tolist(),
#             "p5": np.percentile(sim,5,axis=0).tolist(),
#             "p95": np.percentile(sim,95,axis=0).tolist()}

# def walk_forward_equity(df: pd.DataFrame, params: Dict) -> Dict:
#     eq, dt = [], []
#     i = 0
#     while i + TRAIN_DAYS + TEST_DAYS <= len(df):
#         test = df.iloc[i+TRAIN_DAYS:i+TRAIN_DAYS+TEST_DAYS]
#         if len(test) < 20: break
#         bt = backtest_strategy(test, params)
#         eq.append(bt["return"] + 1)
#         dt.append(test.index[-1].strftime('%Y-%m-%d'))
#         i += TEST_DAYS
#     return {"dates": dt, "equity": np.cumprod(eq).tolist() if eq else []}

# # -------------------------------------------------
# # 10. SIGNALS
# # -------------------------------------------------
# def generate_signals(df: pd.DataFrame, params: Dict) -> List[Dict]:
#     ind = compute_indicators(df, params)
#     close, vol = df["Close"], df["Volume"]
#     vol_ma = vol.rolling(20).mean()
#     low10 = df["Low"].rolling(10).min()
#     high10 = df["High"].rolling(10).max()
#     sigs = []
#     for i in range(len(df)):
#         score, reasons = 0, []
#         if "RSI" in ind and not pd.isna(ind["RSI"].iloc[i]):
#             if ind["RSI"].iloc[i] < 30: score+=1; reasons.append("RSI<30")
#             if ind["RSI"].iloc[i] > 70: score+=1; reasons.append("RSI>70")
#         if "BB" in ind and not pd.isna(ind["BB_L"].iloc[i]) and close.iloc[i] < ind["BB_L"].iloc[i]: score+=1; reasons.append("Below BB")
#         if "BB" in ind and not pd.isna(ind["BB_U"].iloc[i]) and close.iloc[i] > ind["BB_U"].iloc[i]: score+=1; reasons.append("Above BB")
#         if "SR" in ind and not pd.isna(ind["Support"].iloc[i]) and close.iloc[i] < ind["Support"].iloc[i]: score+=1; reasons.append("Below Support")
#         if "SR" in ind and not pd.isna(ind["Resistance"].iloc[i]) and close.iloc[i] > ind["Resistance"].iloc[i]: score+=1; reasons.append("Above Resistance")
#         if vol.iloc[i] > 1.5*vol_ma.iloc[i]: score+=1; reasons.append("High Vol")
#         if abs(close.iloc[i]-low10.iloc[i])/close.iloc[i] < 0.02: score+=1; reasons.append("Near Low")
#         if abs(close.iloc[i]-high10.iloc[i])/close.iloc[i] < 0.02: score+=1; reasons.append("Near High")
#         if score:
#             stars = "star" * score + "☆" * (5-score)
#             bull = any(x in reasons for x in ["RSI<30","Below BB","Below Support","Near Low"])
#             sigs.append({"Date":df.index[i].strftime('%Y-%m-%d'),"Price":round(close.iloc[i],2),
#                          "Strength":stars,"Reasons":", ".join(reasons),"Direction":"Bullish" if bull else "Bearish"})
#     return sigs[-5:]

# # -------------------------------------------------
# # 11. MAIN UI
# # -------------------------------------------------
# def main():
#     st.title("CBOE Optionable Screener v11.8")
#     st.success("**Instant Load | No Hang | Beautiful Progress**")

#     col1, col2 = st.columns(2)
#     with col1:
#         min_vol = st.number_input("Min Avg Volume", 100_000, 5_000_000, MIN_VOL, 100_000)
#     with col2:
#         dry = st.checkbox("Dry Run (30 symbols)", True)

#     st.subheader("Indicators")
#     ind_opts = ["RSI","Bollinger Bands (BB)","Support/Resistance"]
#     selected = st.multiselect("Select", ind_opts, default=ind_opts)

#     if st.button("Launch Scan", type="primary"):
#         t0 = time.time()

#         # === INSTANT SYMBOL LOAD (NO SPINNER) ===
#         all_syms = load_cboe_symbols()
#         symbols = all_syms[:30] if dry else pre_screen(all_syms)
#         if not symbols:
#             st.error("No symbols passed filters.")
#             return

#         st.info(f"**{len(symbols)} symbols loaded** → clustering → optimizing → backtesting")

#         # === SHOW PROGRESS BAR IMMEDIATELY ===
#         results, sigs = [], []
#         total = len(symbols)
#         progress_bar = st.progress(0)
#         status_text = st.empty()

#         # CLUSTER
#         with st.spinner("Clustering symbols..."):
#             clusters = cluster_symbols(symbols)
#             rep_map = {c: next((s for s,cl in clusters.items() if cl==c), None) for c in set(clusters.values())}

#         # OPTIMISE PER CLUSTER
#         cluster_params = {}
#         cluster_prog = st.progress(0)
#         for i, (cid, rep) in enumerate(rep_map.items()):
#             if rep is None: continue
#             df = cached_fetch(rep)
#             if df is not None and len(df) >= 100:
#                 cluster_params[cid] = optimize_cluster(rep, df, selected)
#             cluster_prog.progress((i+1)/len(rep_map))
#         cluster_prog.empty()

#         # === PROCESS EACH SYMBOL WITH PROGRESS ===
#         for idx, sym in enumerate(symbols):
#             completed = idx + 1
#             percent = completed / total
#             bar = "█" * int(percent * 20) + "░" * (20 - int(percent * 20))
#             status_text.markdown(
#                 f"**Processing `{sym}`...**  `({completed}/{total})`  `{int(percent*100)}%`  \n"
#                 f"`[{bar}]`"
#             )

#             df = cached_fetch(sym)
#             if df is None or len(df) < 100:
#                 progress_bar.progress(percent)
#                 continue

#             cid = clusters.get(sym, 0)
#             params = cluster_params.get(cid, {i: {"period":14} for i in selected})
#             bt = backtest_strategy(df, params)
#             mc = monte_carlo(bt["returns"])
#             wf = walk_forward_equity(df, params)
#             sig = generate_signals(df, params)

#             results.append({"symbol":sym, "params":params, "bt":bt, "mc":mc, "wf":wf})
#             sigs.extend([{"Symbol":sym, **s} for s in sig])

#             progress_bar.progress(percent)

#         progress_bar.empty()
#         status_text.empty()

#         st.session_state.results = results
#         st.session_state.signals = pd.DataFrame(sigs) if sigs else pd.DataFrame()
#         st.success(f"**Done in {time.time()-t0:.1f}s – {len(results)} symbols analyzed**")

#     # DISPLAY
#     if not st.session_state.get("results"):
#         st.info("Run the scan to see results.")
#         return

#     results = st.session_state.results
#     tab1,tab2,tab3,tab4,tab5 = st.tabs(["WFO","Backtest","Monte-Carlo","WF-Equity","Signals"])

#     def sel(key, label):
#         opts = [r["symbol"] for r in results]
#         return st.selectbox(label, opts, key=key) if opts else None

#     with tab1:
#         rows = [{"Symbol":r["symbol"],
#                  "Return":f"{r['bt']['return']:+.1%}",
#                  "Sharpe":r["bt"]["sharpe"],
#                  "MaxDD":f"{r['bt']['max_dd']:.1%}",
#                  "Trades":len(r["bt"]["trades"])} for r in results]
#         df = pd.DataFrame(rows)
#         st.dataframe(df, use_container_width=True, hide_index=True)
#         st.download_button("Download WFO", df.to_csv(index=False).encode(), "wfo.csv")

#     with tab2:
#         sym = sel("bt","Backtest Symbol")
#         if sym:
#             r = next(x for x in results if x["symbol"]==sym)
#             fig = go.Figure(go.Scatter(x=r["bt"]["dates"], y=r["bt"]["equity"], name="Equity"))
#             fig.update_layout(title=f"{sym} – Equity Curve")
#             st.plotly_chart(fig, use_container_width=True)
#             if r["bt"]["trades"]:
#                 st.write(pd.DataFrame(r["bt"]["trades"]))

#     with tab3:
#         sym = sel("mc","Monte-Carlo Symbol")
#         if sym:
#             r = next(x for x in results if x["symbol"]==sym)
#             mc = r["mc"]
#             if mc["paths"]:
#                 fig = go.Figure()
#                 for p in mc["paths"][::50]:
#                     fig.add_scatter(y=p, line=dict(width=0.5, color="lightgray"), showlegend=False)
#                 fig.add_scatter(y=mc["p5"], line=dict(dash="dash", color="red"), name="5th %")
#                 fig.add_scatter(y=mc["p95"], line=dict(dash="dash", color="green"), name="95th %")
#                 fig.update_layout(title=f"{sym} – Monte-Carlo (1k paths)")
#                 st.plotly_chart(fig, use_container_width=True)

#     with tab4:
#         sym = sel("wf","WF Symbol")
#         if sym:
#             r = next(x for x in results if x["symbol"]==sym)
#             wf = r["wf"]
#             if wf["equity"]:
#                 fig = go.Figure(go.Scatter(x=wf["dates"], y=wf["equity"], mode="lines+markers"))
#                 fig.update_layout(title=f"{sym} – Walk-Forward Equity")
#                 st.plotly_chart(fig, use_container_width=True)

#     with tab5:
#         if not st.session_state.signals.empty:
#             df = st.session_state.signals.sort_values(["Symbol","Strength"], ascending=[True,False])
#             st.dataframe(df[["Symbol","Date","Price","Strength","Direction","Reasons"]], use_container_width=True, hide_index=True)
#             st.download_button("Download Signals", df.to_csv(index=False).encode(), "signals.csv")

#     if st.button("Clear Cache"):
#         st.cache_data.clear()
#         st.success("Cache cleared")

# if __name__ == "__main__":
#     main()