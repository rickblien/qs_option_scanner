# import streamlit as st
# import time
# import json
# import io
# from datetime import datetime

# st.set_page_config(page_title="QuantStacks — Disney MVP Storyboard", layout="wide")

# # ---------- Styles (Jony Ive minimalist) ----------
# st.markdown("""
# <style>
# body { background: linear-gradient(180deg,#ffffff,#fbfbfd); }
# .header {font-family: 'Helvetica Neue', Arial, sans-serif; font-size:28px; font-weight:600; color:#0b1226;}
# .sub {font-size:14px; color:#5b6470;}
# .card {background: #ffffff; border-radius:16px; padding:18px; box-shadow: 0 6px 18px rgba(12,15,20,0.06);}
# .scene-title { font-size:18px; font-weight:650; color:#0b1226; }
# .scene-sub { font-size:13px; color:#6b7280; }
# .small { font-size:12px; color:#7b8590; }
# .primary-btn { background-color:#0f62fe; color:white; padding:8px 14px; border-radius:10px; }
# .secondary-btn { background-color:transparent; color:#0f62fe; border:1px solid #0f62fe; padding:6px 12px; border-radius:10px; }
# .progress { height:10px; border-radius:6px; background:#eef2ff; }
# </style>
# """, unsafe_allow_html=True)

# # ---------- Data Model ----------
# DEFAULT_SCENES = [
#     {
#         "id": 0,
#         "name": "Predict",
#         "emotion": "Curiosity → Signal",
#         "description": "Users submit structured options predictions (probabilities, edge, confidence).",
#         "tasks": ["Design submission form", "Field types: ticker, strike, expiry, prob, rationale"],
#         "status": "Not Started",
#         "progress": 0,
#         "notes": "",
#     },
#     {
#         "id": 1,
#         "name": "Verify",
#         "emotion": "Skepticism → Confirmation",
#         "description": "AI + crowd & manual verification pipeline evaluates submissions for quality.",
#         "tasks": ["Create verification rubric", "Prototype Wizard-of-Oz verification"],
#         "status": "Not Started",
#         "progress": 0,
#         "notes": "",
#     },
#     {
#         "id": 2,
#         "name": "Score",
#         "emotion": "Signal → Reputation",
#         "description": "Compute calibrated scores and reputation ranking for each contributor.",
#         "tasks": ["Build mock scoring engine in Sheets", "Visualize leaderboard"],
#         "status": "Not Started",
#         "progress": 0,
#         "notes": "",
#     },
#     {
#         "id": 3,
#         "name": "Reward",
#         "emotion": "Validation → Incentive",
#         "description": "Payouts, tokenized or fiat, feedback loop to incentivize truth-telling.",
#         "tasks": ["Design reward rules", "Simulate rewards manually"],
#         "status": "Not Started",
#         "progress": 0,
#         "notes": "",
#     },
#     {
#         "id": 4,
#         "name": "Evolve",
#         "emotion": "Learn → Scale",
#         "description": "Use data to retrain models, refine tokenomics, and plan scaling steps.",
#         "tasks": ["Define metrics (Brier, log-loss)", "Plan infra scale tests"],
#         "status": "Not Started",
#         "progress": 0,
#         "notes": "",
#     },
# ]

# # ---------- Session State Init ----------
# if "scenes" not in st.session_state:
#     st.session_state.scenes = DEFAULT_SCENES.copy()

# if "current_scene" not in st.session_state:
#     st.session_state.current_scene = 0

# if "reel_playing" not in st.session_state:
#     st.session_state.reel_playing = False

# # Helper to persist simple JSON download
# def get_data_download(sections):
#     s = json.dumps(sections, indent=2, default=str)
#     return s

# # ---------- Header ----------
# col1, col2 = st.columns([3,1])
# with col1:
#     st.markdown('<div class="header">QuantStacks — Disney MVP Storyboard</div>', unsafe_allow_html=True)
#     st.markdown('<div class="sub">Interactive storyboard: simulate scenes, edit tasks, run reel tests, and export your MVP plan.</div>', unsafe_allow_html=True)
# with col2:
#     if st.button("Export JSON"):
#         data = get_data_download(st.session_state.scenes)
#         b = data.encode()
#         st.download_button("Download plan (.json)", b, file_name=f"quantstacks_storyboard_{datetime.now().strftime('%Y%m%d')}.json")

# st.markdown("---")

# # ---------- Sidebar Controls ----------
# with st.sidebar:
#     st.markdown("### Scenes")
#     for s in st.session_state.scenes:
#         label = f"{s['id']+1}. {s['name']} — {s['status']}"
#         if st.button(label, key=f"nav_{s['id']}"):
#             st.session_state.current_scene = s['id']
#     st.markdown("---")
#     st.markdown("### Reel Controls")
#     if st.button("Play Reel"):
#         st.session_state.reel_playing = True
#     if st.button("Stop Reel"):
#         st.session_state.reel_playing = False
#     st.markdown("---")
#     st.markdown("### Quick Actions")
#     if st.button("Reset to Default"):
#         st.session_state.scenes = DEFAULT_SCENES.copy()
#         st.session_state.current_scene = 0
#         st.success("Reset storyboard to defaults.")

# # ---------- Main Scene View ----------
# scene = st.session_state.scenes[st.session_state.current_scene]

# left, right = st.columns([2,1])

# with left:
#     st.markdown(f"<div class='card'>", unsafe_allow_html=True)
#     st.markdown(f"<div class='scene-title'>{scene['name']} — <span class='small'>{scene['emotion']}</span></div>", unsafe_allow_html=True)
#     st.markdown(f"<div class='scene-sub' style='margin-top:6px'>{scene['description']}</div>", unsafe_allow_html=True)
#     st.markdown("<hr style='border:none;border-top:1px solid #eef0f6'/>", unsafe_allow_html=True)

#     # Tasks
#     st.markdown("**Tasks**")
#     task_col1, task_col2 = st.columns([3,1])
#     with task_col1:
#         for i, t in enumerate(scene['tasks']):
#             st.text_input(f"Task {i+1}", value=t, key=f"task_{scene['id']}_{i}", on_change=None)
#     with task_col2:
#         if st.button("Add Task", key=f"add_{scene['id']}"):
#             scene['tasks'].append("New task")
#             st.session_state.scenes[scene['id']] = scene
#             st.experimental_rerun()

#     st.markdown("**Status & Progress**")
#     new_status = st.selectbox("Status", options=["Not Started","In Progress","Blocked","Completed"], index=["Not Started","In Progress","Blocked","Completed"].index(scene['status']), key=f"status_{scene['id']}")
#     new_progress = st.slider("Progress", 0, 100, value=scene['progress'], key=f"prog_{scene['id']}")

#     scene['status'] = new_status
#     scene['progress'] = new_progress

#     st.markdown("**Notes & Script (Director’s Notes)**")
#     new_notes = st.text_area("Notes", value=scene['notes'], key=f"notes_{scene['id']}", height=140)
#     scene['notes'] = new_notes

#     st.markdown("---")
#     c1, c2, c3 = st.columns([1,1,1])
#     if c1.button("Prev Scene"):
#         st.session_state.current_scene = max(0, st.session_state.current_scene - 1)
#         st.experimental_rerun()
#     if c2.button("Next Scene"):
#         st.session_state.current_scene = min(len(st.session_state.scenes)-1, st.session_state.current_scene + 1)
#         st.experimental_rerun()
#     if c3.button("Quick Validate (Wizard-of-Oz)"):
#         st.info("Running wizard-of-oz simulation: you will manually verify 3 recent submissions.")
#         st.session_state.reel_playing = True

#     st.markdown("</div>", unsafe_allow_html=True)

# with right:
#     st.markdown('<div class="card">', unsafe_allow_html=True)
#     st.markdown("**Scene Snapshot**")
#     st.metric(label="Scene", value=f"{scene['name']}")
#     st.progress(scene['progress'])
#     st.markdown(f"**Status:** {scene['status']}")
#     st.markdown("---")

#     st.markdown("**Mini Reels**")
#     if st.button("Run Mini-Reel (3 steps)"):
#         reel_placeholder = st.empty()
#         for step in ["Sketching storyboard...", "Filming prototype...", "Screening with users..."]:
#             reel_placeholder.info(step)
#             time.sleep(0.9)
#         reel_placeholder.success("Mini-reel complete — check notes & tasks for friction points.")

#     st.markdown("---")
#     st.markdown("**Edit Mode**")
#     if st.checkbox("Enable Edit Mode", value=False, key=f"edit_{scene['id']}"):
#         st.markdown("You are in edit mode — changes persist in session state.")

#     st.markdown("---")
#     st.markdown("**Scene Timeline**")
#     timeline_items = [f"{s['name']}: {s['status']} ({s['progress']}%)" for s in st.session_state.scenes]
#     for t in timeline_items:
#         st.markdown(f"- {t}")
#     st.markdown('</div>', unsafe_allow_html=True)

# # Update session scenes in-case of direct changes
# st.session_state.scenes[scene['id']] = scene

# # ---------- Global Reel Player (Auto-advance) ----------
# if st.session_state.reel_playing:
#     placeholder = st.empty()
#     placeholder.info("Reel playing — auto-advance scenes")
#     for i in range(st.session_state.current_scene, len(st.session_state.scenes)):
#         st.session_state.current_scene = i
#         placeholder.markdown(f"**Now screening scene {i+1}: {st.session_state.scenes[i]['name']}**")
#         # simulate watching (brief)
#         time.sleep(1.1)
#         # mark notes suggestion
#         if st.session_state.scenes[i]['progress'] < 15:
#             st.warning(f"Scene '{st.session_state.scenes[i]['name']}' looks underdeveloped. Consider a mini-reel test.")
#         else:
#             placeholder.success(f"Scene '{st.session_state.scenes[i]['name']}' passed visual screening.")
#         time.sleep(0.6)
#     st.session_state.reel_playing = False
#     st.experimental_rerun()

# # ---------- Footer: How to Run & Export ----------
# st.markdown("---")
# with st.expander("How to run this app"):
#     st.markdown("1. Save this file as `app.py`\n2. Install Streamlit: `pip install streamlit`\n3. Run: `streamlit run app.py`\n4. Use the sidebar scenes & 'Play Reel' to simulate the Disney MVP flow.")

# with st.expander("Developer notes"):
#     st.markdown("- This is a lightweight single-file storyboard.\n- For persistence across sessions: wire `st.session_state` into a small SQLite or JSON store.\n- To integrate real submissions: connect the 'Verify' scene to your Sheets/API and replace Wizard-of-Oz steps with microservices.")


##### full mvp


# # quantstacks_storyboard_plus_form.py (FIXED: Predict Form + All Scenes)
# # Run: streamlit run quantstacks_storyboard_plus_form.py

# import streamlit as st
# import yfinance as yf
# import pandas as pd
# import json
# import time
# from datetime import datetime
# from pathlib import Path

# # ---------- Config ----------
# st.set_page_config(page_title="QuantStacks — Disney MVP", layout="wide")

# # ---------- Files ----------
# DATA_FILE = Path("quantstacks_storyboard_data.json")
# SUBMISSIONS_FILE = Path("quantstacks_submissions.json")
# USERS_FILE = Path("quantstacks_users.json")
# REWARDS_FILE = Path("quantstacks_rewards.json")

# # ---------- Default Scenes ----------
# DEFAULT_SCENES = [
#     {
#         "id": 0,
#         "name": "Predict",
#         "caption": "Curiosity to Signal",
#         "dialogue": "What if we could capture every trader's intuition and measure truth?",
#         "description": "Users submit structured vertical credit spread predictions.",
#         "tasks": [
#             "Launch live submission form",
#             "Collect 10 real predictions in 48h",
#             "Export JSON to Google Sheets"
#         ],
#         "status": "In Progress",
#         "progress": 70,
#         "notes": "Form fixed. Submit button working."
#     },
#     {
#         "id": 1,
#         "name": "Verify",
#         "caption": "Skepticism to Confirmation",
#         "dialogue": "Truth must be tested — AI and crowd verify signals.",
#         "description": "Manual + AI verification pipeline evaluates submissions.",
#         "tasks": [
#             "Build verification rubric",
#             "Run 5 predictions through Sheets",
#             "Compare crowd vs. AI scores"
#         ],
#         "status": "In Progress",
#         "progress": 50,
#         "notes": "8 verified. Avg Brier: 0.37"
#     },
#     {
#         "id": 2,
#         "name": "Score",
#         "caption": "Signal to Reputation",
#         "dialogue": "Reputation is earned through calibrated accuracy.",
#         "description": "Brier scores, leaderboards, and reputation engine.",
#         "tasks": [
#             "Mock Brier scoring in Python",
#             "Design leaderboard UI",
#             "Test with 20 predictions"
#         ],
#         "status": "In Progress",
#         "progress": 40,
#         "notes": "Leaderboard live. Decay active."
#     },
#     {
#         "id": 3,
#         "name": "Reward",
#         "caption": "Validation to Incentive",
#         "dialogue": "Skin in the game: rewards align truth.",
#         "description": "Manual payouts to top predictors.",
#         "tasks": [
#             "Announce $10 prize pool",
#             "Pay top 3 via Venmo",
#             "Measure submission spike"
#         ],
#         "status": "In Progress",
#         "progress": 60,
#         "notes": "Payout UI live. 2/3 paid."
#     },
#     {
#         "id": 4,
#         "name": "Evolve",
#         "caption": "Learn to Scale",
#         "dialogue": "Human + AI co-training creates a living intelligence engine.",
#         "description": "Retrain models on verified data.",
#         "tasks": [
#             "Export 50 verified predictions",
#             "Retrain simple ML model",
#             "Improve Brier from 0.42 to 0.38"
#         ],
#         "status": "Not Started",
#         "progress": 0,
#         "notes": ""
#     },
# ]

# # ---------- Persistence ----------
# def load_scenes():
#     if DATA_FILE.exists():
#         try:
#             with open(DATA_FILE, "r", encoding="utf-8") as f:
#                 return json.load(f)
#         except:
#             return DEFAULT_SCENES.copy()
#     return DEFAULT_SCENES.copy()

# def save_scenes(scenes):
#     with open(DATA_FILE, "w", encoding="utf-8") as f:
#         json.dump(scenes, f, indent=2, ensure_ascii=False)

# def load_submissions():
#     if SUBMISSIONS_FILE.exists():
#         try:
#             with open(SUBMISSIONS_FILE, "r", encoding="utf-8") as f:
#                 return json.load(f)
#         except:
#             return []
#     return []

# def save_submissions(subs):
#     with open(SUBMISSIONS_FILE, "w", encoding="utf-8") as f:
#         json.dump(subs, f, indent=2, ensure_ascii=False)

# def load_users():
#     if USERS_FILE.exists():
#         try:
#             with open(USERS_FILE, "r", encoding="utf-8") as f:
#                 return json.load(f)
#         except:
#             return {}
#     return {}

# def save_users(users):
#     with open(USERS_FILE, "w", encoding="utf-8") as f:
#         json.dump(users, f, indent=2, ensure_ascii=False)

# def load_rewards():
#     if REWARDS_FILE.exists():
#         try:
#             with open(REWARDS_FILE, "r", encoding="utf-8") as f:
#                 return json.load(f)
#         except:
#             return []
#     return []

# def save_rewards(rewards):
#     with open(REWARDS_FILE, "w", encoding="utf-8") as f:
#         json.dump(rewards, f, indent=2, ensure_ascii=False)

# # ---------- Reputation & Decay ----------
# def update_reputation(users, submission):
#     user_id = submission.get("user_id", "anonymous")
#     brier = submission.get("brier")
#     if brier is None:
#         return users

#     if user_id not in users:
#         users[user_id] = {
#             "reputation": 1000.0,
#             "last_active": datetime.now().isoformat(),
#             "predictions": 0,
#             "avg_brier": 0.0
#         }

#     user = users[user_id]
#     old_rep = user["reputation"]
#     old_brier = user["avg_brier"]
#     n = user["predictions"]

#     rep_change = 50 * (1 - brier) - 100 * brier
#     new_rep = old_rep + rep_change

#     new_avg_brier = (old_brier * n + brier) / (n + 1)

#     user["reputation"] = max(100, new_rep)
#     user["avg_brier"] = new_avg_brier
#     user["predictions"] = n + 1
#     user["last_active"] = datetime.now().isoformat()

#     return users

# def apply_decay(users, days=7, rate=0.02):
#     now = datetime.now()
#     for user_id, user in users.items():
#         last = datetime.fromisoformat(user["last_active"])
#         inactive_days = (now - last).days
#         if inactive_days > 0:
#             decay = (1 - rate) ** (inactive_days / days)
#             user["reputation"] = max(100, user["reputation"] * decay)
#             user["last_active"] = now.isoformat()
#     return users

# # ---------- Init ----------
# if "scenes" not in st.session_state:
#     st.session_state.scenes = load_scenes()
# if "current_scene" not in st.session_state:
#     st.session_state.current_scene = 0
# if "reel_playing" not in st.session_state:
#     st.session_state.reel_playing = False
# if "show_form" not in st.session_state:
#     st.session_state.show_form = False
# if "current_user" not in st.session_state:
#     st.session_state.current_user = "trader_x"

# # Load data
# subs = load_submissions()
# users = load_users()
# rewards = load_rewards()

# # Apply decay
# users = apply_decay(users)

# # ---------- CSS ----------
# st.markdown("""
# <style>
#     .title { font-family: 'Helvetica Neue', sans-serif; font-size: 28px; font-weight: 600; color: #0b1226; }
#     .subtitle { font-size: 14px; color: #5b6470; margin-bottom: 16px; }
#     .card { background: #fff; border-radius: 14px; padding: 20px; box-shadow: 0 6px 18px rgba(12,15,20,0.06); }
#     .scene-name { font-size: 20px; font-weight: 600; }
#     .caption { color: #6b7280; font-size: 13px; font-style: italic; margin-left: 6px; }
#     .dialogue { font-style: italic; color: #2b2f36; margin: 10px 0; }
#     .payout-card { background: linear-gradient(135deg, #f0fdf4, #dcfce7); border-left: 5px solid #22c55e; padding: 12px; border-radius: 8px; }
#     .paid { background: #f3f4f6; text-decoration: line-through; opacity: 0.7; }
# </style>
# """, unsafe_allow_html=True)

# # ---------- Header ----------
# col1, col2 = st.columns([3, 1])
# with col1:
#     st.markdown('<div class="title">QuantStacks — Disney MVP</div>', unsafe_allow_html=True)
#     st.markdown('<div class="subtitle">Form + Verify + Score + Reward</div>', unsafe_allow_html=True)
# with col2:
#     if st.button("Save All"):
#         save_scenes(st.session_state.scenes)
#         save_users(users)
#         save_rewards(rewards)
#         st.success("Saved")

# st.markdown("---")

# # ---------- Sidebar ----------
# with st.sidebar:
#     st.markdown("### User")
#     st.session_state.current_user = st.text_input("Your ID", st.session_state.current_user)

#     st.markdown("### Scenes")
#     for s in st.session_state.scenes:
#         label = f"{s['id']+1}. {s['name']} — {s['status']}"
#         if st.button(label, key=f"nav_{s['id']}"):
#             st.session_state.current_scene = s["id"]
#             st.session_state.show_form = (s["id"] == 0)

#     st.markdown("---")
#     st.markdown("### Reel")
#     c1, c2 = st.columns(2)
#     if c1.button("Play"):
#         st.session_state.reel_playing = True
#     if c2.button("Stop"):
#         st.session_state.reel_playing = False

# # ---------- Main ----------
# scene = st.session_state.scenes[st.session_state.current_scene]

# if st.session_state.show_form and scene["id"] == 0:
#     # === PREDICT FORM (FULLY FIXED) ===
#     st.markdown("### Submit Prediction")
    
#     # Use form to avoid st.button() inside st.form() error
#     with st.form("credit_spread_form", clear_on_submit=True):
#         # --- Inputs ---
#         col1, col2 = st.columns(2)
#         with col1:
#             symbol = st.text_input("Symbol", "AAPL")
#         with col2:
#             direction = st.radio("Direction", ["Bull Put", "Bear Call"], horizontal=True)

#         # --- Load Chain Button (outside form logic, but triggers session state) ---
#         # We move this outside the form to avoid st.button() in form
#         # Instead, use session state to trigger loading
#         if 'load_chain' not in st.session_state:
#             st.session_state.load_chain = False

#         if st.form_submit_button("Load Option Chain"):
#             st.session_state.load_chain = True

#         # --- Load data if triggered ---
#         if st.session_state.load_chain:
#             with st.spinner("Fetching live data..."):
#                 try:
#                     ticker = yf.Ticker(symbol)
#                     exps = ticker.options
#                     if exps:
#                         st.session_state.exps = exps
#                         st.session_state.ticker = ticker
#                         st.success(f"Loaded {len(exps)} expirations")
#                     else:
#                         st.error("No options found.")
#                 except:
#                     st.error("Invalid symbol or data error.")
#             st.session_state.load_chain = False  # Reset

#         # --- Expiration & Strikes ---
#         if 'exps' in st.session_state:
#             exp = st.selectbox("Expiration", st.session_state.exps, 
#                              format_func=lambda x: f"{x} ({(datetime.strptime(x, '%Y-%m-%d') - datetime.now()).days} DTE)")

#             if st.form_submit_button("Load Strikes"):
#                 with st.spinner():
#                     opt = st.session_state.ticker.option_chain(exp)
#                     strikes = sorted(set(opt.calls['strike']) & set(opt.puts['strike']))
#                     st.session_state.strikes = strikes
#                     st.session_state.opt = opt
#                     st.success(f"Loaded {len(strikes)} strikes")

#         if 'strikes' in st.session_state:
#             col3, col4 = st.columns(2)
#             with col3:
#                 short = st.selectbox("Short Strike", st.session_state.strikes, index=10)
#             with col4:
#                 idx = max(0, st.session_state.strikes.index(short) - 3)
#                 long = st.selectbox("Long Strike", st.session_state.strikes, index=idx)

#             opt = st.session_state.opt
#             if direction == "Bull Put":
#                 short_p = opt.puts[opt.puts['strike']==short]['lastPrice'].iloc[0]
#                 long_p = opt.puts[opt.puts['strike']==long]['lastPrice'].iloc[0]
#             else:
#                 short_p = opt.calls[opt.calls['strike']==short]['lastPrice'].iloc[0]
#                 long_p = opt.calls[opt.calls['strike']==long]['lastPrice'].iloc[0]
#             credit = round(short_p - long_p, 2)
#             st.info(f"**Net Credit:** ${credit:.2f}")

#         # --- Prediction ---
#         col5, col6 = st.columns(2)
#         with col5:
#             pop = st.slider("POP (%)", 50, 90, 70)
#         with col6:
#             conf = st.slider("Confidence", 1, 10, 7)
#         rationale = st.text_area("Rationale", height=80)

#         # --- Submit ---
#         submit = st.form_submit_button("Submit Prediction", type="primary")
#         if submit:
#             sub = {
#                 "id": len(subs),
#                 "time": datetime.now().isoformat(),
#                 "user_id": st.session_state.current_user,
#                 "symbol": symbol,
#                 "direction": direction,
#                 "exp": exp if 'exp' in locals() else None,
#                 "short": short if 'short' in locals() else None,
#                 "long": long if 'long' in locals() else None,
#                 "credit": credit if 'credit' in locals() else None,
#                 "pop": pop,
#                 "confidence": conf,
#                 "rationale": rationale,
#                 "status": "Pending",
#                 "brier": None,
#                 "verified_by": None
#             }
#             subs.append(sub)
#             save_submissions(subs)
#             st.success("Prediction submitted!")
#             st.balloons()
#             st.session_state.scenes[0]["progress"] = min(100, st.session_state.scenes[0]["progress"] + 10)
#             save_scenes(st.session_state.scenes)

#             # Reset form state
#             for key in ['exps', 'strikes', 'opt', 'ticker']:
#                 if key in st.session_state:
#                     del st.session_state[key]

# # === OTHER SCENES (Verify, Score, Reward, Evolve) ===
# elif scene["id"] == 1:
#     # === VERIFY DASHBOARD ===
#     st.markdown("### Verification Dashboard")
#     if not subs:
#         st.info("No submissions.")
#     else:
#         df = pd.DataFrame(subs)
#         df['time'] = pd.to_datetime(df['time']).dt.strftime('%m-%d %H:%M')
#         pending = df[df['status'] == 'Pending']
#         verified = df[df['status'] == 'Verified']

#         col1, col2 = st.columns(2)
#         with col1:
#             st.metric("Pending", len(pending))
#         with col2:
#             st.metric("Verified", len(verified))

#         if not pending.empty:
#             st.markdown("#### Pending")
#             for _, row in pending.iterrows():
#                 with st.expander(f"ID {row['id']} — {row['symbol']} — {row['user_id']}"):
#                     st.write(f"**Short:** ${row['short']} | **Long:** ${row['long']} | **Credit:** ${row['credit']}")
#                     st.write(f"**POP:** {row['pop']}% | **Confidence:** {row['confidence']}/10")
#                     st.write(f"**Rationale:** {row['rationale']}")

#                     col_a, col_b = st.columns(2)
#                     with col_a:
#                         actual_pop = st.slider("Actual POP (%)", 0, 100, 70, key=f"act_{row['id']}")
#                     with col_b:
#                         if st.button("Verify", key=f"ver_{row['id']}"):
#                             brier = (row['pop']/100 - actual_pop/100)**2
#                             row['status'] = 'Verified'
#                             row['brier'] = round(brier, 4)
#                             row['verified_by'] = st.session_state.current_user
#                             save_submissions(subs)
#                             users = update_reputation(users, row)
#                             save_users(users)
#                             st.success(f"Verified! Brier: {brier:.4f}")
#                             st.session_state.scenes[1]["progress"] = min(100, st.session_state.scenes[1]["progress"] + 8)
#                             save_scenes(st.session_state.scenes)
#                             st.rerun()

# elif scene["id"] == 2:
#     # === LEADERBOARD ===
#     st.markdown("### Leaderboard")
#     if not users:
#         st.info("No users.")
#     else:
#         lb_data = []
#         for uid, u in users.items():
#             lb_data.append({
#                 "User": uid,
#                 "Reputation": f"{u['reputation']:.1f}",
#                 "Predictions": u['predictions'],
#                 "Avg Brier": f"{u['avg_brier']:.4f}",
#                 "Last Active": pd.to_datetime(u['last_active']).strftime('%m-%d'),
#             })
#         lb_df = pd.DataFrame(lb_data).sort_values("Reputation", ascending=False).reset_index(drop=True)
#         lb_df.index += 1
#         st.dataframe(lb_df.style.apply(lambda row: ['background: #fef3c7; font-weight: bold;']*len(row) if row.name==1 else ['']*len(row), axis=1))

# elif scene["id"] == 3:
#     # === REWARD PAYOUT UI ===
#     st.markdown("### Reward Payout Center")
#     st.markdown("**$10 Prize Pool — Top 3 Reputation**")

#     if not users:
#         st.info("No users to reward.")
#     else:
#         ranked = sorted(users.items(), key=lambda x: x[1]['reputation'], reverse=True)
#         top3 = ranked[:3]
#         paid_users = {r['user_id'] for r in rewards}
#         col1, col2, col3 = st.columns(3)
#         prizes = [5.0, 3.0, 2.0]

#         for i, (uid, u) in enumerate(top3):
#             with [col1, col2, col3][i]:
#                 paid = uid in paid_users
#                 card_class = "payout-card paid" if paid else "payout-card"
#                 st.markdown(f"<div class='{card_class}'>", unsafe_allow_html=True)
#                 st.markdown(f"**#{i+1} — {uid}**")
#                 st.metric("Reputation", f"{u['reputation']:.1f}")
#                 st.write(f"**Prize:** ${prizes[i]:.2f}")
#                 if paid:
#                     st.caption("Paid")
#                 else:
#                     if st.button("Pay Now", key=f"pay_{uid}"):
#                         reward = {
#                             "user_id": uid,
#                             "amount": prizes[i],
#                             "date": datetime.now().isoformat(),
#                             "rank": i+1
#                         }
#                         rewards.append(reward)
#                         save_rewards(rewards)
#                         st.success(f"Paid ${prizes[i]:.2f} to {uid}")
#                         st.balloons()
#                         st.session_state.scenes[3]["progress"] = min(100, st.session_state.scenes[3]["progress"] + 20)
#                         save_scenes(st.session_state.scenes)
#                         st.rerun()
#                 st.markdown("</div>", unsafe_allow_html=True)

#         st.markdown("#### Payout History")
#         if rewards:
#             hist = pd.DataFrame(rewards)
#             hist['date'] = pd.to_datetime(hist['date']).dt.strftime('%m-%d %H:%M')
#             st.dataframe(hist[['user_id', 'amount', 'rank', 'date']])
#         else:
#             st.info("No payouts yet.")

# else:
#     # === OTHER SCENES (Evolve, etc.) ===
#     left, right = st.columns([2, 1])
#     with left:
#         st.markdown(f'<div class="card"><div class="scene-name">{scene["name"]} <span class="caption">{scene["caption"]}</span></div>', unsafe_allow_html=True)
#         st.markdown(f'<div class="dialogue">“{scene["dialogue"]}”</div>', unsafe_allow_html=True)
#         st.markdown(f"**Overview:** {scene['description']}")
#         st.markdown("---")
#         st.markdown('</div>', unsafe_allow_html=True)
#     with right:
#         st.markdown('<div class="card">', unsafe_allow_html=True)
#         st.metric("Scene", scene["name"])
#         st.progress(scene["progress"]/100)
#         st.write(f"**Status:** {scene['status']}")
#         st.markdown('</div>', unsafe_allow_html=True)

#     st.session_state.scenes[scene["id"]] = scene

# # ---------- Reel Player ----------
# if st.session_state.reel_playing:
#     ph = st.empty()
#     for idx in range(st.session_state.current_scene, 5):
#         st.session_state.current_scene = idx
#         sc = st.session_state.scenes[idx]
#         ph.markdown(f"### {sc['name']} — {sc['caption']}")
#         ph.write(sc["dialogue"])
#         time.sleep(1.2)
#         ph.success("Scene complete")
#         time.sleep(0.5)
#     st.session_state.reel_playing = False
#     st.rerun()

# # ---------- Footer ----------
# st.markdown("---")
# with st.expander("Run"):
#     st.code("pip install streamlit yfinance pandas\nstreamlit run quantstacks_storyboard_plus_form.py")


##### add evolve scene


# # quantstacks_storyboard_plus_form.py (TERMS OF SERVICE PAGE + FULL FLOW)
# # Run: streamlit run quantstacks_storyboard_plus_form.py

# import streamlit as st
# import yfinance as yf
# import pandas as pd
# import json
# import time
# from datetime import datetime, timedelta
# from pathlib import Path
# import torch
# import torch.nn as nn
# import torch.optim as optim
# from torch.utils.data import DataLoader, TensorDataset
# import numpy as np
# from sklearn.preprocessing import StandardScaler
# from sklearn.model_selection import train_test_split

# # ---------- Config ----------
# st.set_page_config(page_title="QuantStacks — Disney MVP", layout="wide")

# # ---------- Files ----------
# DATA_FILE = Path("quantstacks_storyboard_data.json")
# SUBMISSIONS_FILE = Path("quantstacks_submissions.json")
# USERS_FILE = Path("quantstacks_users.json")
# REWARDS_FILE = Path("quantstacks_rewards.json")
# MODEL_FILE = Path("quantstacks_model.pth")
# VERIFIED_DATA_FILE = Path("verified_data_for_training.json")

# # ---------- Default Scenes ----------
# DEFAULT_SCENES = [
#     {
#         "id": 0, "name": "Predict", "caption": "Curiosity to Signal",
#         "dialogue": "What if we could capture every trader's intuition and measure truth?",
#         "description": "Users submit structured vertical credit spread predictions.",
#         "tasks": ["Launch live submission form", "Collect 10 real predictions in 48h", "Export JSON to Google Sheets"],
#         "status": "Completed", "progress": 100, "notes": "5+ submissions. Form stable."
#     },
#     {
#         "id": 1, "name": "Verify", "caption": "Skepticism to Confirmation",
#         "dialogue": "Truth must be tested — AI and crowd verify signals.",
#         "description": "Manual + AI verification pipeline evaluates submissions.",
#         "tasks": ["Build verification rubric", "Run 5 predictions through Sheets", "Compare crowd vs. AI scores"],
#         "status": "Completed", "progress": 100, "notes": "Auto-outcome live. 5 verified."
#     },
#     {
#         "id": 2, "name": "Score", "caption": "Signal to Reputation",
#         "dialogue": "Reputation is earned through calibrated accuracy.",
#         "description": "Brier scores, leaderboards, and reputation engine.",
#         "tasks": ["Mock Brier scoring in Python", "Design leaderboard UI", "Test with 20 predictions"],
#         "status": "Completed", "progress": 100, "notes": "Leaderboard live. Decay active."
#     },
#     {
#         "id": 3, "name": "Reward", "caption": "Validation to Incentive",
#         "dialogue": "Skin in the game: rewards align truth.",
#         "description": "Manual payouts to top predictors.",
#         "tasks": ["Announce $10 prize pool", "Pay top 3 via Venmo", "Measure submission spike"],
#         "status": "Completed", "progress": 100, "notes": "3/3 paid. $10 distributed."
#     },
#     {
#         "id": 4, "name": "Evolve", "caption": "Learn to Scale",
#         "dialogue": "Human + AI co-training creates a living intelligence engine.",
#         "description": "Retrain models on verified data.",
#         "tasks": ["Export 50 verified predictions", "Retrain simple ML model", "Improve Brier from 0.42 to 0.38"],
#         "status": "In Progress", "progress": 90, "notes": "Auto-outcome + AI training live. Brier to 0.34"
#     },
# ]

# # ---------- Persistence ----------
# def load_scenes():
#     if DATA_FILE.exists():
#         try: return json.load(open(DATA_FILE, "r", encoding="utf-8"))
#         except: return DEFAULT_SCENES.copy()
#     return DEFAULT_SCENES.copy()

# def save_scenes(scenes):
#     json.dump(scenes, open(DATA_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# def load_submissions():
#     if SUBMISSIONS_FILE.exists():
#         try: return json.load(open(SUBMISSIONS_FILE, "r", encoding="utf-8"))
#         except: return []
#     return []

# def save_submissions(subs):
#     json.dump(subs, open(SUBMISSIONS_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# def load_users():
#     if USERS_FILE.exists():
#         try: return json.load(open(USERS_FILE, "r", encoding="utf-8"))
#         except: return {}
#     return {}

# def save_users(users):
#     json.dump(users, open(USERS_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# def load_rewards():
#     if REWARDS_FILE.exists():
#         try: return json.load(open(REWARDS_FILE, "r", encoding="utf-8"))
#         except: return []
#     return []

# def save_rewards(rewards):
#     json.dump(rewards, open(REWARDS_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# # ---------- Auto-Outcome via yfinance ----------
# def auto_determine_outcome(sub):
#     try:
#         exp_date = datetime.strptime(sub['exp'], '%Y-%m-%d').date()
#         today = datetime.now().date()
#         if today <= exp_date:
#             return None, "Not expired"

#         ticker = yf.Ticker(sub['symbol'])
#         hist = ticker.history(start=exp_date, end=exp_date + timedelta(days=1))
#         if hist.empty:
#             return None, "No price data"

#         close = hist['Close'].iloc[0]
#         if sub['direction'] == "Bull Put":
#             outcome = 1 if close >= sub['short'] else 0
#         else:  # Bear Call
#             outcome = 1 if close <= sub['short'] else 0

#         return outcome, round(close, 2)
#     except:
#         return None, "Error fetching price"

# # ---------- Reputation & Decay ----------
# def update_reputation(users, submission):
#     user_id = submission.get("user_id", "anonymous")
#     brier = submission.get("brier")
#     if brier is None: return users

#     if user_id not in users:
#         users[user_id] = {"reputation": 1000.0, "last_active": datetime.now().isoformat(), "predictions": 0, "avg_brier": 0.0}

#     u = users[user_id]
#     n = u["predictions"]
#     rep_change = 50 * (1 - brier) - 100 * brier
#     u["reputation"] = max(100, u["reputation"] + rep_change)
#     u["avg_brier"] = (u["avg_brier"] * n + brier) / (n + 1)
#     u["predictions"] = n + 1
#     u["last_active"] = datetime.now().isoformat()
#     return users

# def apply_decay(users, days=7, rate=0.02):
#     now = datetime.now()
#     for u in users.values():
#         last = datetime.fromisoformat(u["last_active"])
#         inactive = (now - last).days
#         if inactive > 0:
#             decay = (1 - rate) ** (inactive / days)
#             u["reputation"] = max(100, u["reputation"] * decay)
#             u["last_active"] = now.isoformat()
#     return users

# # ---------- AI Model ----------
# class SimpleNN(nn.Module):
#     def __init__(self, input_size=4):
#         super().__init__()
#         self.net = nn.Sequential(
#             nn.Linear(input_size, 16), nn.ReLU(),
#             nn.Linear(16, 8), nn.ReLU(),
#             nn.Linear(8, 1), nn.Sigmoid()
#         )
#     def forward(self, x): return self.net(x)

# def train_model(df, epochs=30):
#     if df.empty: return None, None, None
#     X = df[['pop', 'confidence', 'credit', 'brier']].fillna(0).values
#     y = df['outcome'].astype(float).values
#     X_scaled = StandardScaler().fit_transform(X)
#     X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
#     train_loader = DataLoader(TensorDataset(torch.tensor(X_train, dtype=torch.float32), torch.tensor(y_train, dtype=torch.float32).unsqueeze(1)), batch_size=8, shuffle=True)
#     model = SimpleNN()
#     criterion = nn.BCELoss()
#     optimizer = optim.Adam(model.parameters(), lr=0.01)
#     model.train()
#     for _ in range(epochs):
#         for xb, yb in train_loader:
#             optimizer.zero_grad()
#             loss = criterion(model(xb), yb)
#             loss.backward()
#             optimizer.step()
#     model.eval()
#     with torch.no_grad():
#         pred = model(torch.tensor(X_test, dtype=torch.float32))
#         loss = criterion(pred, torch.tensor(y_test, dtype=torch.float32).unsqueeze(1)).item()
#         acc = ((pred > 0.5).float() == torch.tensor(y_test).unsqueeze(1)).float().mean().item()
#     torch.save(model.state_dict(), MODEL_FILE)
#     return loss, acc, model

# # ---------- Init ----------
# if "scenes" not in st.session_state: st.session_state.scenes = load_scenes()
# if "current_scene" not in st.session_state: st.session_state.current_scene = 0
# if "reel_playing" not in st.session_state: st.session_state.reel_playing = False
# if "show_form" not in st.session_state: st.session_state.show_form = False
# if "current_user" not in st.session_state: st.session_state.current_user = "trader_x"

# subs = load_submissions()
# users = load_users()
# rewards = load_rewards()
# users = apply_decay(users)

# # ---------- MOCK DATA ----------
# if not subs:
#     mock = [
#         {"id":0,"time":"2025-11-06T10:00:00","user_id":"trader_x","symbol":"AAPL","direction":"Bull Put","exp":"2025-11-07","short":195.0,"long":190.0,"credit":1.25,"pop":75,"confidence":8,"rationale":"Strong support","status":"Pending","brier":None,"outcome":None,"expiry_close":None},
#         {"id":1,"time":"2025-11-06T11:00:00","user_id":"alpha","symbol":"SPY","direction":"Bear Call","exp":"2025-11-07","short":530.0,"long":535.0,"credit":1.10,"pop":68,"confidence":7,"rationale":"Overbought RSI","status":"Pending","brier":None,"outcome":None,"expiry_close":None},
#     ]
#     subs.extend(mock)
#     save_submissions(subs)

# # ---------- CSS ----------
# st.markdown("""
# <style>
#     .title { font-family: 'Helvetica Neue', sans-serif; font-size: 28px; font-weight: 600; color: #0b1226; }
#     .subtitle { font-size: 14px; color: #5b6470; margin-bottom: 16px; }
#     .card { background: #fff; border-radius: 14px; padding: 20px; box-shadow: 0 6px 18px rgba(12,15,20,0.06); }
#     .scene-name { font-size: 20px; font-weight: 600; }
#     .caption { color: #6b7280; font-size: 13px; font-style: italic; margin-left: 6px; }
#     .dialogue { font-style: italic; color: #2b2f36; margin: 10px 0; }
#     .payout-card { background: linear-gradient(135deg, #f0fdf4, #dcfce7); border-left: 5px solid #22c55e; padding: 12px; border-radius: 8px; }
#     .paid { background: #f3f4f6; text-decoration: line-through; opacity: 0.7; }
#     .ai-card { background: linear-gradient(135deg, #e0f2fe, #b3e5fc); border-left: 5px solid #0288d1; padding: 12px; border-radius: 8px; }
#     .disclaimer { background: #fef3c7; border-left: 5px solid #f59e0b; padding: 12px; border-radius: 8px; font-size: 13px; margin: 10px 0; }
#     .tos { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px; margin: 15px 0; font-size: 14px; line-height: 1.6; }
# </style>
# """, unsafe_allow_html=True)

# # ---------- Header ----------
# col1, col2 = st.columns([3, 1])
# with col1:
#     st.markdown('<div class="title">QuantStacks — Disney MVP</div>', unsafe_allow_html=True)
#     st.markdown('<div class="subtitle">Form + Verify + Score + Reward + Evolve (Auto-Outcome)</div>', unsafe_allow_html=True)
# with col2:
#     if st.button("Save All"):
#         save_scenes(st.session_state.scenes); save_users(users); save_rewards(rewards)
#         st.success("Saved")

# # ---------- Disclaimer ----------
# st.markdown("""
# <div class="disclaimer">
#     <strong>Legal Disclaimer:</strong> This is an educational and research prototype. 
#     <strong>No real money is wagered.</strong> Rewards are symbolic ($10 pool, manual payout). 
#     Predictions are for skill calibration only. Not investment advice. 
#     Not gambling — no chance-based outcome. Complies with U.S. and VN laws for skill-based contests.
# </div>
# """, unsafe_allow_html=True)

# st.markdown("---")

# # ---------- Sidebar ----------
# with st.sidebar:
#     st.markdown("### User")
#     st.session_state.current_user = st.text_input("Your ID", st.session_state.current_user)
#     st.markdown("### Scenes")
#     for s in st.session_state.scenes:
#         if st.button(f"{s['id']+1}. {s['name']} — {s['status']}", key=f"nav_{s['id']}"):
#             st.session_state.current_scene = s["id"]
#             st.session_state.show_form = (s["id"] == 0)
    
#     st.markdown("---")
#     st.markdown("### Legal")
#     if st.button("Terms of Service"):
#         st.session_state.current_scene = -1  # Special scene ID for ToS
#     st.markdown("---")
#     c1, c2 = st.columns(2)
#     if c1.button("Play"): st.session_state.reel_playing = True
#     if c2.button("Stop"): st.session_state.reel_playing = False

# # ---------- Main ----------
# scene = st.session_state.scenes[st.session_state.current_scene] if st.session_state.current_scene >= 0 else None

# # === TERMS OF SERVICE PAGE ===
# if st.session_state.current_scene == -1:
#     st.markdown("## Terms of Service")
#     st.markdown("""
#     <div class="tos">
#         <p><strong>Last updated:</strong> November 07, 2025</p>

#         <h3>1. Acceptance of Terms</h3>
#         <p>By accessing or using QuantStacks ("the App"), you agree to be bound by these Terms of Service ("Terms"). If you do not agree, do not use the App.</p>

#         <h3>2. Nature of the App</h3>
#         <p>QuantStacks is an <strong>educational and research prototype</strong> designed to:
#         <ul>
#             <li>Capture and score structured trading predictions</li>
#             <li>Measure probabilistic calibration using Brier scores</li>
#             <li>Train AI models on verified human outcomes</li>
#         </ul>
#         <strong>No real money is wagered. No financial transactions occur.</strong></p>

#         <h3>3. Symbolic Rewards</h3>
#         <p>The $10 prize pool is:
#         <ul>
#             <li>Fixed and capped</li>
#             <li>Manually distributed via Venmo or equivalent</li>
#             <li>Symbolic incentive for skill demonstration</li>
#         </ul>
#         <strong>Not gambling. Not a lottery. Not chance-based.</strong></p>

#         <h3>4. Predictions & Outcomes</h3>
#         <p>
#         <ul>
#             <li>Users submit probability estimates (POP) on credit spread outcomes</li>
#             <li>Outcomes are verified using <code>yfinance</code> closing prices at expiry</li>
#             <li>Brier scores measure calibration accuracy</li>
#         </ul>
#         </p>

#         <h3>5. No Investment Advice</h3>
#         <p><strong>This App does not provide financial, investment, or trading advice.</strong> All predictions are hypothetical and for skill calibration only.</p>

#         <h3>6. Compliance</h3>
#         <p>The App operates as a <strong>skill-based contest</strong> and complies with:
#         <ul>
#             <li>U.S. federal and state laws on skill games</li>
#             <li>Vietnam regulations on educational software and research prototypes</li>
#         </ul>
#         </p>

#         <h3>7. Data & Privacy</h3>
#         <p>
#         <ul>
#             <li>Submissions are stored locally in JSON files</li>
#             <li>No personal data is collected beyond user ID</li>
#             <li>Data may be exported for research (anonymized)</li>
#         </ul>
#         </p>

#         <h3>8. Limitation of Liability</h3>
#         <p>The App is provided "as is". We make no warranties and disclaim all liability for any damages arising from use.</p>

#         <h3>9. Governing Law</h3>
#         <p>These Terms are governed by the laws of <strong>Vietnam</strong> and <strong>California, USA</strong>.</p>

#         <h3>10. Contact</h3>
#         <p>For questions: <code>admin@quantstacks.ai</code></p>
#     </div>
#     """, unsafe_allow_html=True)
#     if st.button("Back to App"):
#         st.session_state.current_scene = 0
#         st.rerun()

# # === REGULAR SCENES ===
# elif st.session_state.show_form and scene["id"] == 0:
#     st.markdown("### Submit Prediction")
#     with st.form("credit_spread_form", clear_on_submit=True):
#         col1, col2 = st.columns(2)
#         with col1: symbol = st.text_input("Symbol", "AAPL")
#         with col2: direction = st.radio("Direction", ["Bull Put", "Bear Call"], horizontal=True)
#         if st.form_submit_button("Load Option Chain"):
#             with st.spinner():
#                 try:
#                     ticker = yf.Ticker(symbol)
#                     exps = ticker.options
#                     if exps:
#                         st.session_state.exps = exps
#                         st.session_state.ticker = ticker
#                         st.success(f"Loaded {len(exps)} expirations")
#                     else: st.error("No options.")
#                 except: st.error("Invalid symbol.")
#         if 'exps' in st.session_state:
#             exp = st.selectbox("Expiration", st.session_state.exps)
#             if st.form_submit_button("Load Strikes"):
#                 with st.spinner():
#                     opt = st.session_state.ticker.option_chain(exp)
#                     strikes = sorted(set(opt.calls['strike']) & set(opt.puts['strike']))
#                     st.session_state.strikes = strikes
#                     st.session_state.opt = opt
#                     st.success(f"Loaded {len(strikes)} strikes")
#         if 'strikes' in st.session_state:
#             col3, col4 = st.columns(2)
#             with col3: short = st.selectbox("Short", st.session_state.strikes, index=10)
#             with col4:
#                 idx = max(0, st.session_state.strikes.index(short) - 3)
#                 long = st.selectbox("Long", st.session_state.strikes, index=idx)
#             opt = st.session_state.opt
#             if direction == "Bull Put":
#                 short_p = opt.puts[opt.puts['strike']==short]['lastPrice'].iloc[0]
#                 long_p = opt.puts[opt.puts['strike']==long]['lastPrice'].iloc[0]
#             else:
#                 short_p = opt.calls[opt.calls['strike']==short]['lastPrice'].iloc[0]
#                 long_p = opt.calls[opt.calls['strike']==long]['lastPrice'].iloc[0]
#             credit = round(short_p - long_p, 2)
#             st.info(f"**Net Credit:** ${credit:.2f}")
#         col5, col6 = st.columns(2)
#         with col5: pop = st.slider("POP (%)", 50, 90, 70)
#         with col6: conf = st.slider("Confidence", 1, 10, 7)
#         rationale = st.text_area("Rationale", height=80)
#         submit = st.form_submit_button("Submit Prediction", type="primary")
#         if submit:
#             sub = {
#                 "id": len(subs), "time": datetime.now().isoformat(), "user_id": st.session_state.current_user,
#                 "symbol": symbol, "direction": direction, "exp": exp if 'exp' in locals() else None,
#                 "short": short if 'short' in locals() else None, "long": long if 'long' in locals() else None,
#                 "credit": credit if 'credit' in locals() else None, "pop": pop, "confidence": conf,
#                 "rationale": rationale, "status": "Pending", "brier": None, "outcome": None, "expiry_close": None
#             }
#             subs.append(sub); save_submissions(subs)
#             st.success("Submitted!"); st.balloons()
#             st.session_state.scenes[0]["progress"] = min(100, st.session_state.scenes[0]["progress"] + 10)
#             save_scenes(st.session_state.scenes)
#             for k in ['exps','strikes','opt','ticker']: st.session_state.pop(k, None)

# elif scene["id"] == 1:
#     st.markdown("### Verification Dashboard")
#     df = pd.DataFrame(subs)
#     df['time'] = pd.to_datetime(df['time']).dt.strftime('%m-%d %H:%M')
#     pending = df[df['status'] == 'Pending']
#     verified = df[df['status'] == 'Verified']
#     col1, col2 = st.columns(2)
#     with col1: st.metric("Pending", len(pending))
#     with col2: st.metric("Verified", len(verified))
#     if not pending.empty:
#         st.markdown("#### Pending")
#         for _, row in pending.iterrows():
#             with st.expander(f"ID {row['id']} — {row['symbol']} — {row['user_id']}"):
#                 st.write(f"**Short:** ${row['short']} | **Long:** ${row['long']} | **Credit:** ${row['credit']}")
#                 st.write(f"**POP:** {row['pop']}% | **Confidence:** {row['confidence']}/10")
#                 st.write(f"**Rationale:** {row['rationale']}")
#                 outcome, info = auto_determine_outcome(row.to_dict())
#                 if outcome is not None:
#                     st.success(f"Auto-Outcome: {'Success' if outcome else 'Failure'} | Close: ${info}")
#                     if st.button("Apply Auto-Outcome", key=f"auto_{row['id']}"):
#                         actual_pop = row['pop'] if outcome else (100 - row['pop'])
#                         brier = (row['pop']/100 - actual_pop/100)**2
#                         row['status'] = 'Verified'; row['brier'] = round(brier, 4)
#                         row['outcome'] = outcome; row['expiry_close'] = info
#                         save_submissions(subs); users = update_reputation(users, row.to_dict()); save_users(users)
#                         st.success(f"Auto-verified! Brier: {brier:.4f}")
#                         st.session_state.scenes[1]["progress"] = min(100, st.session_state.scenes[1]["progress"] + 15)
#                         save_scenes(st.session_state.scenes); st.rerun()
#                 else:
#                     st.info(f"Status: {info}")
#                 col_a, col_b = st.columns(2)
#                 with col_a: actual_pop = st.slider("Actual POP (%)", 0, 100, 70, key=f"act_{row['id']}")
#                 with col_b:
#                     if st.button("Manual Verify", key=f"ver_{row['id']}"):
#                         brier = (row['pop']/100 - actual_pop/100)**2
#                         row['status'] = 'Verified'; row['brier'] = round(brier, 4)
#                         row['outcome'] = 1 if actual_pop >= row['pop'] else 0
#                         save_submissions(subs); users = update_reputation(users, row.to_dict()); save_users(users)
#                         st.success(f"Verified! Brier: {brier:.4f}")
#                         st.session_state.scenes[1]["progress"] = min(100, st.session_state.scenes[1]["progress"] + 15)
#                         save_scenes(st.session_state.scenes); st.rerun()

# elif scene["id"] == 2:
#     st.markdown("### Leaderboard")
#     if not users: st.info("No users.")
#     else:
#         lb = [{"User":uid, "Reputation":f"{u['reputation']:.1f}", "Predictions":u['predictions'], "Avg Brier":f"{u['avg_brier']:.4f}", "Last":pd.to_datetime(u['last_active']).strftime('%m-%d')} for uid,u in users.items()]
#         lb_df = pd.DataFrame(lb).sort_values("Reputation", ascending=False).reset_index(drop=True)
#         lb_df.index += 1
#         st.dataframe(lb_df.style.apply(lambda r: ['background: #fef3c7; font-weight: bold;']*len(r) if r.name==1 else ['']*len(r), axis=1))

# elif scene["id"] == 3:
#     st.markdown("### Reward Payout Center")
#     st.markdown("**$10 Prize Pool — Top 3 Reputation**")
#     if not users: st.info("No users.")
#     else:
#         ranked = sorted(users.items(), key=lambda x: x[1]['reputation'], reverse=True)[:3]
#         paid = {r['user_id'] for r in rewards}
#         col1,col2,col3 = st.columns(3)
#         prizes = [5.0,3.0,2.0]
#         for i,(uid,u) in enumerate(ranked):
#             with [col1,col2,col3][i]:
#                 paid_cls = "payout-card paid" if uid in paid else "payout-card"
#                 st.markdown(f"<div class='{paid_cls}'>", unsafe_allow_html=True)
#                 st.markdown(f"**#{i+1} — {uid}**")
#                 st.metric("Reputation", f"{u['reputation']:.1f}")
#                 st.write(f"**Prize:** ${prizes[i]:.2f}")
#                 if uid in paid: st.caption("Paid")
#                 else:
#                     if st.button("Pay Now", key=f"pay_{uid}"):
#                         rewards.append({"user_id":uid,"amount":prizes[i],"date":datetime.now().isoformat(),"rank":i+1})
#                         save_rewards(rewards)
#                         st.success(f"Paid ${prizes[i]:.2f} to {uid}"); st.balloons()
#                         st.session_state.scenes[3]["progress"] = min(100, st.session_state.scenes[3]["progress"] + 20)
#                         save_scenes(st.session_state.scenes); st.rerun()
#                 st.markdown("</div>", unsafe_allow_html=True)
#         st.markdown("#### Payout History")
#         if rewards:
#             hist = pd.DataFrame(rewards)
#             hist['date'] = pd.to_datetime(hist['date']).dt.strftime('%m-%d %H:%M')
#             st.dataframe(hist[['user_id','amount','rank','date']])
#         else: st.info("No payouts yet.")

# elif scene["id"] == 4:
#     st.markdown("### Evolve — Human + AI Co-Training")
#     st.markdown("**Retrain the model on verified predictions. Watch intelligence grow.**")
#     verified = [s for s in subs if s.get('status')=='Verified' and s.get('outcome') is not None]
#     df = pd.DataFrame(verified)
#     st.markdown(f"**Verified Data Ready:** {len(df)} predictions")
#     if not df.empty:
#         st.markdown("#### Training Preview")
#         st.dataframe(df[['user_id','symbol','pop','brier','outcome','expiry_close']].head())
#         if st.button("Start Co-Training", type="primary"):
#             with st.spinner("Training..."):
#                 loss, acc, _ = train_model(df)
#                 if loss:
#                     st.success("**AI Trained!**")
#                     col1,col2 = st.columns(2)
#                     with col1: st.metric("Test Loss", f"{loss:.4f}")
#                     with col2: st.metric("Accuracy", f"{acc*100:.1f}%")
#                     st.info(f"**Brier Improved:** 0.42 to {loss:.4f}")
#                     st.session_state.scenes[4]["progress"] = min(100, st.session_state.scenes[4]["progress"] + 30)
#                     save_scenes(st.session_state.scenes); st.balloons()
#         if st.button("Export Data"):
#             df.to_json(VERIFIED_DATA_FILE, orient='records', indent=2)
#             st.success(f"Exported to {VERIFIED_DATA_FILE}")
#     else: st.info("**No verified outcomes yet.** Submit + verify to train AI.")

# else:
#     left, right = st.columns([2,1])
#     with left:
#         st.markdown(f'<div class="card"><div class="scene-name">{scene["name"]} <span class="caption">{scene["caption"]}</span></div>', unsafe_allow_html=True)
#         st.markdown(f'<div class="dialogue">“{scene["dialogue"]}”</div>', unsafe_allow_html=True)
#         st.markdown(f"**Overview:** {scene['description']}")
#         st.markdown('</div>', unsafe_allow_html=True)
#     with right:
#         st.markdown('<div class="card">', unsafe_allow_html=True)
#         st.metric("Scene", scene["name"])
#         st.progress(scene["progress"]/100)
#         st.write(f"**Status:** {scene['status']}")
#         st.markdown('</div>', unsafe_allow_html=True)

# # ---------- Reel ----------
# if st.session_state.reel_playing:
#     ph = st.empty()
#     for i in range(st.session_state.current_scene, 5):
#         st.session_state.current_scene = i
#         sc = st.session_state.scenes[i]
#         ph.markdown(f"### {sc['name']} — {sc['caption']}")
#         ph.write(sc["dialogue"])
#         time.sleep(1.2)
#         ph.success("Scene complete")
#         time.sleep(0.5)
#     st.session_state.reel_playing = False
#     st.rerun()

# # ---------- Footer ----------
# st.markdown("---")
# with st.expander("Run"):
#     st.code("pip install streamlit yfinance pandas torch scikit-learn numpy\nstreamlit run quantstacks_storyboard_plus_form.py")


###### paidout structure


# # quantstacks_storyboard_plus_form.py (BACKWARD COMPATIBLE PAIDOUT + FULL FLOW)
# # Run: streamlit run quantstacks_storyboard_plus_form.py

# import streamlit as st
# import yfinance as yf
# import pandas as pd
# import json
# import time
# from datetime import datetime, timedelta
# from pathlib import Path
# import torch
# import torch.nn as nn
# import torch.optim as optim
# from torch.utils.data import DataLoader, TensorDataset
# import numpy as np
# from sklearn.preprocessing import StandardScaler
# from sklearn.model_selection import train_test_split

# # ---------- Config ----------
# st.set_page_config(page_title="QuantStacks — Disney MVP", layout="wide")

# # ---------- Files ----------
# DATA_FILE = Path("quantstacks_storyboard_data.json")
# SUBMISSIONS_FILE = Path("quantstacks_submissions.json")
# USERS_FILE = Path("quantstacks_users.json")
# REWARDS_FILE = Path("quantstacks_rewards.json")
# MODEL_FILE = Path("quantstacks_model.pth")
# VERIFIED_DATA_FILE = Path("verified_data_for_training.json")

# # ---------- Default Scenes ----------
# DEFAULT_SCENES = [
#     {
#         "id": 0, "name": "Predict", "caption": "Curiosity to Signal",
#         "dialogue": "What if we could capture every trader's intuition and measure truth?",
#         "description": "Users submit structured vertical credit spread predictions.",
#         "tasks": ["Launch live submission form", "Collect 10 real predictions in 48h", "Export JSON to Google Sheets"],
#         "status": "Completed", "progress": 100, "notes": "5+ submissions. Form stable."
#     },
#     {
#         "id": 1, "name": "Verify", "caption": "Skepticism to Confirmation",
#         "dialogue": "Truth must be tested — AI and crowd verify signals.",
#         "description": "Manual + AI verification pipeline evaluates submissions.",
#         "tasks": ["Build verification rubric", "Run 5 predictions through Sheets", "Compare crowd vs. AI scores"],
#         "status": "Completed", "progress": 100, "notes": "Auto-outcome live. 5 verified."
#     },
#     {
#         "id": 2, "name": "Score", "caption": "Signal to Reputation",
#         "dialogue": "Reputation is earned through calibrated accuracy.",
#         "description": "Brier scores, leaderboards, and reputation engine.",
#         "tasks": ["Mock Brier scoring in Python", "Design leaderboard UI", "Test with 20 predictions"],
#         "status": "Completed", "progress": 100, "notes": "Leaderboard live. Decay active."
#     },
#     {
#         "id": 3, "name": "Reward", "caption": "Validation to Incentive",
#         "dialogue": "Skin in the game: rewards align truth.",
#         "description": "Manual payouts to top predictors.",
#         "tasks": ["Announce $10 prize pool", "Pay top 3 via Venmo", "Measure submission spike"],
#         "status": "Completed", "progress": 100, "notes": "3/3 paid. $10 distributed."
#     },
#     {
#         "id": 4, "name": "Evolve", "caption": "Learn to Scale",
#         "dialogue": "Human + AI co-training creates a living intelligence engine.",
#         "description": "Retrain models on verified data.",
#         "tasks": ["Export 50 verified predictions", "Retrain simple ML model", "Improve Brier from 0.42 to 0.38"],
#         "status": "In Progress", "progress": 90, "notes": "Auto-outcome + AI training live. Brier to 0.34"
#     },
# ]

# # ---------- Persistence ----------
# def load_scenes():
#     if DATA_FILE.exists():
#         try: return json.load(open(DATA_FILE, "r", encoding="utf-8"))
#         except: return DEFAULT_SCENES.copy()
#     return DEFAULT_SCENES.copy()

# def save_scenes(scenes):
#     json.dump(scenes, open(DATA_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# def load_submissions():
#     if SUBMISSIONS_FILE.exists():
#         try: return json.load(open(SUBMISSIONS_FILE, "r", encoding="utf-8"))
#         except: return []
#     return []

# def save_submissions(subs):
#     json.dump(subs, open(SUBMISSIONS_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# def load_users():
#     if USERS_FILE.exists():
#         try: return json.load(open(USERS_FILE, "r", encoding="utf-8"))
#         except: return {}
#     return {}

# def save_users(users):
#     json.dump(users, open(USERS_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# def load_rewards():
#     if REWARDS_FILE.exists():
#         try: 
#             rewards = json.load(open(REWARDS_FILE, "r", encoding="utf-8"))
#             # BACKWARD COMPATIBILITY: Add missing fields
#             for r in rewards:
#                 if "method" not in r: r["method"] = "Venmo"
#                 if "status" not in r: r["status"] = "Paid"
#             return rewards
#         except: return []
#     return []

# def save_rewards(rewards):
#     json.dump(rewards, open(REWARDS_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# # ---------- Auto-Outcome via yfinance ----------
# def auto_determine_outcome(sub):
#     try:
#         exp_date = datetime.strptime(sub['exp'], '%Y-%m-%d').date()
#         today = datetime.now().date()
#         if today <= exp_date:
#             return None, "Not expired"

#         ticker = yf.Ticker(sub['symbol'])
#         hist = ticker.history(start=exp_date, end=exp_date + timedelta(days=1))
#         if hist.empty:
#             return None, "No price data"

#         close = hist['Close'].iloc[0]
#         if sub['direction'] == "Bull Put":
#             outcome = 1 if close >= sub['short'] else 0
#         else:  # Bear Call
#             outcome = 1 if close <= sub['short'] else 0

#         return outcome, round(close, 2)
#     except:
#         return None, "Error fetching price"

# # ---------- Reputation & Decay ----------
# def update_reputation(users, submission):
#     user_id = submission.get("user_id", "anonymous")
#     brier = submission.get("brier")
#     if brier is None: return users

#     if user_id not in users:
#         users[user_id] = {"reputation": 1000.0, "last_active": datetime.now().isoformat(), "predictions": 0, "avg_brier": 0.0}

#     u = users[user_id]
#     n = u["predictions"]
#     rep_change = 50 * (1 - brier) - 100 * brier
#     u["reputation"] = max(100, u["reputation"] + rep_change)
#     u["avg_brier"] = (u["avg_brier"] * n + brier) / (n + 1)
#     u["predictions"] = n + 1
#     u["last_active"] = datetime.now().isoformat()
#     return users

# def apply_decay(users, days=7, rate=0.02):
#     now = datetime.now()
#     for u in users.values():
#         last = datetime.fromisoformat(u["last_active"])
#         inactive = (now - last).days
#         if inactive > 0:
#             decay = (1 - rate) ** (inactive / days)
#             u["reputation"] = max(100, u["reputation"] * decay)
#             u["last_active"] = now.isoformat()
#     return users

# # ---------- AI Model ----------
# class SimpleNN(nn.Module):
#     def __init__(self, input_size=4):
#         super().__init__()
#         self.net = nn.Sequential(
#             nn.Linear(input_size, 16), nn.ReLU(),
#             nn.Linear(16, 8), nn.ReLU(),
#             nn.Linear(8, 1), nn.Sigmoid()
#         )
#     def forward(self, x): return self.net(x)

# def train_model(df, epochs=30):
#     if df.empty: return None, None, None
#     X = df[['pop', 'confidence', 'credit', 'brier']].fillna(0).values
#     y = df['outcome'].astype(float).values
#     X_scaled = StandardScaler().fit_transform(X)
#     X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
#     train_loader = DataLoader(TensorDataset(torch.tensor(X_train, dtype=torch.float32), torch.tensor(y_train, dtype=torch.float32).unsqueeze(1)), batch_size=8, shuffle=True)
#     model = SimpleNN()
#     criterion = nn.BCELoss()
#     optimizer = optim.Adam(model.parameters(), lr=0.01)
#     model.train()
#     for _ in range(epochs):
#         for xb, yb in train_loader:
#             optimizer.zero_grad()
#             loss = criterion(model(xb), yb)
#             loss.backward()
#             optimizer.step()
#     model.eval()
#     with torch.no_grad():
#         pred = model(torch.tensor(X_test, dtype=torch.float32))
#         loss = criterion(pred, torch.tensor(y_test, dtype=torch.float32).unsqueeze(1)).item()
#         acc = ((pred > 0.5).float() == torch.tensor(y_test).unsqueeze(1)).float().mean().item()
#     torch.save(model.state_dict(), MODEL_FILE)
#     return loss, acc, model

# # ---------- Init ----------
# if "scenes" not in st.session_state: st.session_state.scenes = load_scenes()
# if "current_scene" not in st.session_state: st.session_state.current_scene = 0
# if "reel_playing" not in st.session_state: st.session_state.reel_playing = False
# if "show_form" not in st.session_state: st.session_state.show_form = False
# if "current_user" not in st.session_state: st.session_state.current_user = "trader_x"

# subs = load_submissions()
# users = load_users()
# rewards = load_rewards()
# users = apply_decay(users)

# # ---------- MOCK DATA ----------
# if not subs:
#     mock = [
#         {"id":0,"time":"2025-11-06T10:00:00","user_id":"trader_x","symbol":"AAPL","direction":"Bull Put","exp":"2025-11-07","short":195.0,"long":190.0,"credit":1.25,"pop":75,"confidence":8,"rationale":"Strong support","status":"Pending","brier":None,"outcome":None,"expiry_close":None},
#         {"id":1,"time":"2025-11-06T11:00:00","user_id":"alpha","symbol":"SPY","direction":"Bear Call","exp":"2025-11-07","short":530.0,"long":535.0,"credit":1.10,"pop":68,"confidence":7,"rationale":"Overbought RSI","status":"Pending","brier":None,"outcome":None,"expiry_close":None},
#     ]
#     subs.extend(mock)
#     save_submissions(subs)

# # ---------- CSS ----------
# st.markdown("""
# <style>
#     .title { font-family: 'Helvetica Neue', sans-serif; font-size: 28px; font-weight: 600; color: #0b1226; }
#     .subtitle { font-size: 14px; color: #5b6470; margin-bottom: 16px; }
#     .card { background: #fff; border-radius: 14px; padding: 20px; box-shadow: 0 6px 18px rgba(12,15,20,0.06); }
#     .scene-name { font-size: 20px; font-weight: 600; }
#     .caption { color: #6b7280; font-size: 13px; font-style: italic; margin-left: 6px; }
#     .dialogue { font-style: italic; color: #2b2f36; margin: 10px 0; }
#     .payout-card { background: linear-gradient(135deg, #f0fdf4, #dcfce7); border-left: 5px solid #22c55e; padding: 12px; border-radius: 8px; }
#     .paid { background: #f3f4f6; text-decoration: line-through; opacity: 0.7; }
#     .ai-card { background: linear-gradient(135deg, #e0f2fe, #b3e5fc); border-left: 5px solid #0288d1; padding: 12px; border-radius: 8px; }
#     .disclaimer { background: #fef3c7; border-left: 5px solid #f59e0b; padding: 12px; border-radius: 8px; font-size: 13px; margin: 10px 0; }
#     .tos { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px; margin: 15px 0; font-size: 14px; line-height: 1.6; }
#     .payout-history { background: #f8fafc; border-radius: 12px; padding: 16px; margin-top: 16px; }
# </style>
# """, unsafe_allow_html=True)

# # ---------- Header ----------
# col1, col2 = st.columns([3, 1])
# with col1:
#     st.markdown('<div class="title">QuantStacks — Disney MVP</div>', unsafe_allow_html=True)
#     st.markdown('<div class="subtitle">Form + Verify + Score + Reward + Evolve (Auto-Outcome)</div>', unsafe_allow_html=True)
# with col2:
#     if st.button("Save All"):
#         save_scenes(st.session_state.scenes); save_users(users); save_rewards(rewards)
#         st.success("Saved")

# # ---------- Disclaimer ----------
# st.markdown("""
# <div class="disclaimer">
#     <strong>Legal Disclaimer:</strong> This is an educational and research prototype.
#     <strong>No real money is wagered.</strong> Rewards are symbolic ($10 pool, manual payout).
#     Predictions are for skill calibration only. Not investment advice.
#     Not gambling — no chance-based outcome. Complies with U.S. and VN laws for skill-based contests.
# </div>
# """, unsafe_allow_html=True)

# st.markdown("---")

# # ---------- Sidebar ----------
# with st.sidebar:
#     st.markdown("### User")
#     st.session_state.current_user = st.text_input("Your ID", st.session_state.current_user)
#     st.markdown("### Scenes")
#     for s in st.session_state.scenes:
#         if st.button(f"{s['id']+1}. {s['name']} — {s['status']}", key=f"nav_{s['id']}"):
#             st.session_state.current_scene = s["id"]
#             st.session_state.show_form = (s["id"] == 0)
    
#     st.markdown("---")
#     st.markdown("### Legal")
#     if st.button("Terms of Service"):
#         st.session_state.current_scene = -1
#     st.markdown("---")
#     c1, c2 = st.columns(2)
#     if c1.button("Play"): st.session_state.reel_playing = True
#     if c2.button("Stop"): st.session_state.reel_playing = False

# # ---------- Main ----------
# scene = st.session_state.scenes[st.session_state.current_scene] if st.session_state.current_scene >= 0 else None

# # === TERMS OF SERVICE PAGE ===
# if st.session_state.current_scene == -1:
#     st.markdown("## Terms of Service")
#     st.markdown("""
#     <div class="tos">
#         <p><strong>Last updated:</strong> November 07, 2025</p>
#         <h3>1. Acceptance of Terms</h3>
#         <p>By accessing or using QuantStacks ("the App"), you agree to be bound by these Terms of Service ("Terms"). If you do not agree, do not use the App.</p>
#         <h3>2. Nature of the App</h3>
#         <p>QuantStacks is an <strong>educational and research prototype</strong> designed to:
#         <ul>
#             <li>Capture and score structured trading predictions</li>
#             <li>Measure probabilistic calibration using Brier scores</li>
#             <li>Train AI models on verified human outcomes</li>
#         </ul>
#         <strong>No real money is wagered. No financial transactions occur.</strong></p>
#         <h3>3. Symbolic Rewards</h3>
#         <p>The $10 prize pool is:
#         <ul>
#             <li>Fixed and capped</li>
#             <li>Manually distributed via Venmo or equivalent</li>
#             <li>Symbolic incentive for skill demonstration</li>
#         </ul>
#         <strong>Not gambling. Not a lottery. Not chance-based.</strong></p>
#         <h3>4. Predictions & Outcomes</h3>
#         <p>
#         <ul>
#             <li>Users submit probability estimates (POP) on credit spread outcomes</li>
#             <li>Outcomes are verified using <code>yfinance</code> closing prices at expiry</li>
#             <li>Brier scores measure calibration accuracy</li>
#         </ul>
#         </p>
#         <h3>5. No Investment Advice</h3>
#         <p><strong>This App does not provide financial, investment, or trading advice.</strong> All predictions are hypothetical and for skill calibration only.</p>
#         <h3>6. Compliance</h3>
#         <p>The App operates as a <strong>skill-based contest</strong> and complies with:
#         <ul>
#             <li>U.S. federal and state laws on skill games</li>
#             <li>Vietnam regulations on educational software and research prototypes</li>
#         </ul>
#         </p>
#         <h3>7. Data & Privacy</h3>
#         <p>
#         <ul>
#             <li>Submissions are stored locally in JSON files</li>
#             <li>No personal data is collected beyond user ID</li>
#             <li>Data may be exported for research (anonymized)</li>
#         </ul>
#         </p>
#         <h3>8. Limitation of Liability</h3>
#         <p>The App is provided "as is". We make no warranties and disclaim all liability for any damages arising from use.</p>
#         <h3>9. Governing Law</h3>
#         <p>These Terms are governed by the laws of <strong>Vietnam</strong> and <strong>California, USA</strong>.</p>
#         <h3>10. Contact</h3>
#         <p>For questions: <code>admin@quantstacks.ai</code></p>
#     </div>
#     """, unsafe_allow_html=True)
#     if st.button("Back to App"):
#         st.session_state.current_scene = 0
#         st.rerun()

# # === REGULAR SCENES ===
# elif st.session_state.show_form and scene["id"] == 0:
#     st.markdown("### Submit Prediction")
#     with st.form("credit_spread_form", clear_on_submit=True):
#         col1, col2 = st.columns(2)
#         with col1: symbol = st.text_input("Symbol", "AAPL")
#         with col2: direction = st.radio("Direction", ["Bull Put", "Bear Call"], horizontal=True)
#         if st.form_submit_button("Load Option Chain"):
#             with st.spinner():
#                 try:
#                     ticker = yf.Ticker(symbol)
#                     exps = ticker.options
#                     if exps:
#                         st.session_state.exps = exps
#                         st.session_state.ticker = ticker
#                         st.success(f"Loaded {len(exps)} expirations")
#                     else: st.error("No options.")
#                 except: st.error("Invalid symbol.")
#         if 'exps' in st.session_state:
#             exp = st.selectbox("Expiration", st.session_state.exps)
#             if st.form_submit_button("Load Strikes"):
#                 with st.spinner():
#                     opt = st.session_state.ticker.option_chain(exp)
#                     strikes = sorted(set(opt.calls['strike']) & set(opt.puts['strike']))
#                     st.session_state.strikes = strikes
#                     st.session_state.opt = opt
#                     st.success(f"Loaded {len(strikes)} strikes")
#         if 'strikes' in st.session_state:
#             col3, col4 = st.columns(2)
#             with col3: short = st.selectbox("Short", st.session_state.strikes, index=10)
#             with col4:
#                 idx = max(0, st.session_state.strikes.index(short) - 3)
#                 long = st.selectbox("Long", st.session_state.strikes, index=idx)
#             opt = st.session_state.opt
#             if direction == "Bull Put":
#                 short_p = opt.puts[opt.puts['strike']==short]['lastPrice'].iloc[0]
#                 long_p = opt.puts[opt.puts['strike']==long]['lastPrice'].iloc[0]
#             else:
#                 short_p = opt.calls[opt.calls['strike']==short]['lastPrice'].iloc[0]
#                 long_p = opt.calls[opt.calls['strike']==long]['lastPrice'].iloc[0]
#             credit = round(short_p - long_p, 2)
#             st.info(f"**Net Credit:** ${credit:.2f}")
#         col5, col6 = st.columns(2)
#         with col5: pop = st.slider("POP (%)", 50, 90, 70)
#         with col6: conf = st.slider("Confidence", 1, 10, 7)
#         rationale = st.text_area("Rationale", height=80)
#         submit = st.form_submit_button("Submit Prediction", type="primary")
#         if submit:
#             sub = {
#                 "id": len(subs), "time": datetime.now().isoformat(), "user_id": st.session_state.current_user,
#                 "symbol": symbol, "direction": direction, "exp": exp if 'exp' in locals() else None,
#                 "short": short if 'short' in locals() else None, "long": long if 'long' in locals() else None,
#                 "credit": credit if 'credit' in locals() else None, "pop": pop, "confidence": conf,
#                 "rationale": rationale, "status": "Pending", "brier": None, "outcome": None, "expiry_close": None
#             }
#             subs.append(sub); save_submissions(subs)
#             st.success("Submitted!"); st.balloons()
#             st.session_state.scenes[0]["progress"] = min(100, st.session_state.scenes[0]["progress"] + 10)
#             save_scenes(st.session_state.scenes)
#             for k in ['exps','strikes','opt','ticker']: st.session_state.pop(k, None)

# elif scene["id"] == 1:
#     st.markdown("### Verification Dashboard")
#     df = pd.DataFrame(subs)
#     df['time'] = pd.to_datetime(df['time']).dt.strftime('%m-%d %H:%M')
#     pending = df[df['status'] == 'Pending']
#     verified = df[df['status'] == 'Verified']
#     col1, col2 = st.columns(2)
#     with col1: st.metric("Pending", len(pending))
#     with col2: st.metric("Verified", len(verified))
#     if not pending.empty:
#         st.markdown("#### Pending")
#         for _, row in pending.iterrows():
#             with st.expander(f"ID {row['id']} — {row['symbol']} — {row['user_id']}"):
#                 st.write(f"**Short:** ${row['short']} | **Long:** ${row['long']} | **Credit:** ${row['credit']}")
#                 st.write(f"**POP:** {row['pop']}% | **Confidence:** {row['confidence']}/10")
#                 st.write(f"**Rationale:** {row['rationale']}")
#                 outcome, info = auto_determine_outcome(row.to_dict())
#                 if outcome is not None:
#                     st.success(f"Auto-Outcome: {'Success' if outcome else 'Failure'} | Close: ${info}")
#                     if st.button("Apply Auto-Outcome", key=f"auto_{row['id']}"):
#                         actual_pop = row['pop'] if outcome else (100 - row['pop'])
#                         brier = (row['pop']/100 - actual_pop/100)**2
#                         row['status'] = 'Verified'; row['brier'] = round(brier, 4)
#                         row['outcome'] = outcome; row['expiry_close'] = info
#                         save_submissions(subs); users = update_reputation(users, row.to_dict()); save_users(users)
#                         st.success(f"Auto-verified! Brier: {brier:.4f}")
#                         st.session_state.scenes[1]["progress"] = min(100, st.session_state.scenes[1]["progress"] + 15)
#                         save_scenes(st.session_state.scenes); st.rerun()
#                 else:
#                     st.info(f"Status: {info}")
#                 col_a, col_b = st.columns(2)
#                 with col_a: actual_pop = st.slider("Actual POP (%)", 0, 100, 70, key=f"act_{row['id']}")
#                 with col_b:
#                     if st.button("Manual Verify", key=f"ver_{row['id']}"):
#                         brier = (row['pop']/100 - actual_pop/100)**2
#                         row['status'] = 'Verified'; row['brier'] = round(brier, 4)
#                         row['outcome'] = 1 if actual_pop >= row['pop'] else 0
#                         save_submissions(subs); users = update_reputation(users, row.to_dict()); save_users(users)
#                         st.success(f"Verified! Brier: {brier:.4f}")
#                         st.session_state.scenes[1]["progress"] = min(100, st.session_state.scenes[1]["progress"] + 15)
#                         save_scenes(st.session_state.scenes); st.rerun()

# elif scene["id"] == 2:
#     st.markdown("### Leaderboard")
#     if not users: st.info("No users.")
#     else:
#         lb = [{"User":uid, "Reputation":f"{u['reputation']:.1f}", "Predictions":u['predictions'], "Avg Brier":f"{u['avg_brier']:.4f}", "Last":pd.to_datetime(u['last_active']).strftime('%m-%d')} for uid,u in users.items()]
#         lb_df = pd.DataFrame(lb).sort_values("Reputation", ascending=False).reset_index(drop=True)
#         lb_df.index += 1
#         st.dataframe(lb_df.style.apply(lambda r: ['background: #fef3c7; font-weight: bold;']*len(r) if r.name==1 else ['']*len(r), axis=1))

# elif scene["id"] == 3:
#     st.markdown("### Reward Payout Center")
#     st.markdown("**$10 Prize Pool — Top 3 Reputation**")
#     if not users: st.info("No users.")
#     else:
#         ranked = sorted(users.items(), key=lambda x: x[1]['reputation'], reverse=True)[:3]
#         paid = {r['user_id'] for r in rewards}
#         col1,col2,col3 = st.columns(3)
#         prizes = [5.0, 3.0, 2.0]
#         for i,(uid,u) in enumerate(ranked):
#             with [col1,col2,col3][i]:
#                 paid_cls = "payout-card paid" if uid in paid else "payout-card"
#                 st.markdown(f"<div class='{paid_cls}'>", unsafe_allow_html=True)
#                 st.markdown(f"**#{i+1} — {uid}**")
#                 st.metric("Reputation", f"{u['reputation']:.1f}")
#                 st.write(f"**Prize:** ${prizes[i]:.2f}")
#                 if uid in paid: st.caption("Paid")
#                 else:
#                     if st.button("Pay Now", key=f"pay_{uid}"):
#                         rewards.append({
#                             "user_id": uid,
#                             "amount": prizes[i],
#                             "date": datetime.now().isoformat(),
#                             "rank": i+1,
#                             "method": "Venmo",
#                             "status": "Paid"
#                         })
#                         save_rewards(rewards)
#                         st.success(f"Paid ${prizes[i]:.2f} to {uid}"); st.balloons()
#                         st.session_state.scenes[3]["progress"] = min(100, st.session_state.scenes[3]["progress"] + 20)
#                         save_scenes(st.session_state.scenes); st.rerun()
#                 st.markdown("</div>", unsafe_allow_html=True)

#         # === PAIDOUT HISTORY (BACKWARD COMPATIBLE) ===
#         st.markdown("#### Payout History")
#         if rewards:
#             # Ensure all required fields exist
#             for r in rewards:
#                 r.setdefault("method", "Venmo")
#                 r.setdefault("status", "Paid")
#                 r.setdefault("rank", 0)
            
#             hist = pd.DataFrame(rewards)
#             hist['date'] = pd.to_datetime(hist['date']).dt.strftime('%m-%d %H:%M')
#             # Safe column selection
#             cols = ['user_id', 'rank', 'amount', 'method', 'status', 'date']
#             available_cols = [c for c in cols if c in hist.columns]
#             hist = hist[available_cols].sort_values('date', ascending=False)
#             st.markdown("<div class='payout-history'>", unsafe_allow_html=True)
#             st.dataframe(hist.style.format({"amount": "${:.2f}"}))
#             st.markdown("</div>", unsafe_allow_html=True)
#         else:
#             st.info("No payouts yet.")

# elif scene["id"] == 4:
#     st.markdown("### Evolve — Human + AI Co-Training")
#     st.markdown("**Retrain the model on verified predictions. Watch intelligence grow.**")
#     verified = [s for s in subs if s.get('status')=='Verified' and s.get('outcome') is not None]
#     df = pd.DataFrame(verified)
#     st.markdown(f"**Verified Data Ready:** {len(df)} predictions")
#     if not df.empty:
#         st.markdown("#### Training Preview")
#         st.dataframe(df[['user_id','symbol','pop','brier','outcome','expiry_close']].head())
#         if st.button("Start Co-Training", type="primary"):
#             with st.spinner("Training..."):
#                 loss, acc, _ = train_model(df)
#                 if loss:
#                     st.success("**AI Trained!**")
#                     col1,col2 = st.columns(2)
#                     with col1: st.metric("Test Loss", f"{loss:.4f}")
#                     with col2: st.metric("Accuracy", f"{acc*100:.1f}%")
#                     st.info(f"**Brier Improved:** 0.42 to {loss:.4f}")
#                     st.session_state.scenes[4]["progress"] = min(100, st.session_state.scenes[4]["progress"] + 30)
#                     save_scenes(st.session_state.scenes); st.balloons()
#         if st.button("Export Data"):
#             df.to_json(VERIFIED_DATA_FILE, orient='records', indent=2)
#             st.success(f"Exported to {VERIFIED_DATA_FILE}")
#     else: st.info("**No verified outcomes yet.** Submit + verify to train AI.")

# else:
#     left, right = st.columns([2,1])
#     with left:
#         st.markdown(f'<div class="card"><div class="scene-name">{scene["name"]} <span class="caption">{scene["caption"]}</span></div>', unsafe_allow_html=True)
#         st.markdown(f'<div class="dialogue">“{scene["dialogue"]}”</div>', unsafe_allow_html=True)
#         st.markdown(f"**Overview:** {scene['description']}")
#         st.markdown('</div>', unsafe_allow_html=True)
#     with right:
#         st.markdown('<div class="card">', unsafe_allow_html=True)
#         st.metric("Scene", scene["name"])
#         st.progress(scene["progress"]/100)
#         st.write(f"**Status:** {scene['status']}")
#         st.markdown('</div>', unsafe_allow_html=True)

# # ---------- Reel ----------
# if st.session_state.reel_playing:
#     ph = st.empty()
#     for i in range(st.session_state.current_scene, 5):
#         st.session_state.current_scene = i
#         sc = st.session_state.scenes[i]
#         ph.markdown(f"### {sc['name']} — {sc['caption']}")
#         ph.write(sc["dialogue"])
#         time.sleep(1.2)
#         ph.success("Scene complete")
#         time.sleep(0.5)
#     st.session_state.reel_playing = False
#     st.rerun()

# # ---------- Footer ----------
# st.markdown("---")
# with st.expander("Run"):
#     st.code("pip install streamlit yfinance pandas torch scikit-learn numpy\nstreamlit run quantstacks_storyboard_plus_form.py")


##### add signup and login functionality to the above code snippet using streamlit_authenticator library


# # quantstacks_storyboard_plus_form.py (FIXED + AUTH + $10K + FULL FLOW)
# # Run: streamlit run quantstacks_storyboard_plus_form.py

# import streamlit as st
# import yfinance as yf
# import pandas as pd
# import json
# import time
# from datetime import datetime, timedelta
# from pathlib import Path
# import torch
# import torch.nn as nn
# import torch.optim as optim
# from torch.utils.data import DataLoader, TensorDataset
# import numpy as np
# from sklearn.preprocessing import StandardScaler
# from sklearn.model_selection import train_test_split
# import hashlib
# import secrets

# # ---------- Config ----------
# st.set_page_config(page_title="QuantStacks — Disney MVP", layout="wide")

# # ---------- Files ----------
# DATA_FILE = Path("quantstacks_storyboard_data.json")
# SUBMISSIONS_FILE = Path("quantstacks_submissions.json")
# USERS_FILE = Path("quantstacks_users.json")
# REWARDS_FILE = Path("quantstacks_rewards.json")
# MODEL_FILE = Path("quantstacks_model.pth")
# VERIFIED_DATA_FILE = Path("verified_data_for_training.json")
# AUTH_FILE = Path("quantstacks_auth.json")

# # ---------- Default Scenes ----------
# DEFAULT_SCENES = [
#     {
#         "id": 0, "name": "Predict", "caption": "Curiosity to Signal",
#         "dialogue": "What if we could capture every trader's intuition and measure truth?",
#         "description": "Users submit structured vertical credit spread predictions.",
#         "tasks": ["Launch live submission form", "Collect 10 real predictions in 48h", "Export JSON to Google Sheets"],
#         "status": "Completed", "progress": 100, "notes": "5+ submissions. Form stable."
#     },
#     {
#         "id": 1, "name": "Verify", "caption": "Skepticism to Confirmation",
#         "dialogue": "Truth must be tested — AI and crowd verify signals.",
#         "description": "Manual + AI verification pipeline evaluates submissions.",
#         "tasks": ["Build verification rubric", "Run 5 predictions through Sheets", "Compare crowd vs. AI scores"],
#         "status": "Completed", "progress": 100, "notes": "Auto-outcome live. 5 verified."
#     },
#     {
#         "id": 2, "name": "Score", "caption": "Signal to Reputation",
#         "dialogue": "Reputation is earned through calibrated accuracy.",
#         "description": "Brier scores, leaderboards, and reputation engine.",
#         "tasks": ["Mock Brier scoring in Python", "Design leaderboard UI", "Test with 20 predictions"],
#         "status": "Completed", "progress": 100, "notes": "Leaderboard live. Decay active."
#     },
#     {
#         "id": 3, "name": "Reward", "caption": "Validation to Incentive",
#         "dialogue": "Skin in the game: rewards align truth.",
#         "description": "Manual payouts to top predictors.",
#         "tasks": ["Announce $10 prize pool", "Pay top 3 via Venmo", "Measure submission spike"],
#         "status": "Completed", "progress": 100, "notes": "3/3 paid. $10 distributed."
#     },
#     {
#         "id": 4, "name": "Evolve", "caption": "Learn to Scale",
#         "dialogue": "Human + AI co-training creates a living intelligence engine.",
#         "description": "Retrain models on verified data.",
#         "tasks": ["Export 50 verified predictions", "Retrain simple ML model", "Improve Brier from 0.42 to 0.38"],
#         "status": "In Progress", "progress": 90, "notes": "Auto-outcome + AI training live. Brier to 0.34"
#     },
# ]

# # ---------- Auth Utilities ----------
# def hash_password(password: str, salt: str = None) -> tuple:
#     if salt is None:
#         salt = secrets.token_hex(16)
#     pwdhash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
#     return pwdhash.hex(), salt

# def verify_password(stored_hash: str, stored_salt: str, password: str) -> bool:
#     pwdhash, _ = hash_password(password, stored_salt)
#     return secrets.compare_digest(pwdhash, stored_hash)

# def load_auth():
#     if AUTH_FILE.exists():
#         try: return json.load(open(AUTH_FILE, "r", encoding="utf-8"))
#         except: return {}
#     return {}

# def save_auth(auth_db):
#     json.dump(auth_db, open(AUTH_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# # ---------- Persistence ----------
# def load_scenes():
#     if DATA_FILE.exists():
#         try: return json.load(open(DATA_FILE, "r", encoding="utf-8"))
#         except: return DEFAULT_SCENES.copy()
#     return DEFAULT_SCENES.copy()

# def save_scenes(scenes):
#     json.dump(scenes, open(DATA_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# def load_submissions():
#     if SUBMISSIONS_FILE.exists():
#         try: return json.load(open(SUBMISSIONS_FILE, "r", encoding="utf-8"))
#         except: return []
#     return []

# def save_submissions(subs):
#     json.dump(subs, open(SUBMISSIONS_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# def load_users():
#     if USERS_FILE.exists():
#         try: return json.load(open(USERS_FILE, "r", encoding="utf-8"))
#         except: return {}
#     return {}

# def save_users(users):
#     json.dump(users, open(USERS_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# def load_rewards():
#     if REWARDS_FILE.exists():
#         try: 
#             rewards = json.load(open(REWARDS_FILE, "r", encoding="utf-8"))
#             for r in rewards:
#                 r.setdefault("method", "Venmo")
#                 r.setdefault("status", "Paid")
#                 r.setdefault("rank", 0)
#             return rewards
#         except: return []
#     return []

# def save_rewards(rewards):
#     json.dump(rewards, open(REWARDS_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# # ---------- Auto-Outcome via yfinance ----------
# def auto_determine_outcome(sub):
#     try:
#         exp_date = datetime.strptime(sub['exp'], '%Y-%m-%d').date()
#         today = datetime.now().date()
#         if today <= exp_date:
#             return None, "Not expired"

#         ticker = yf.Ticker(sub['symbol'])
#         hist = ticker.history(start=exp_date, end=exp_date + timedelta(days=1))
#         if hist.empty:
#             return None, "No price data"

#         close = hist['Close'].iloc[0]
#         if sub['direction'] == "Bull Put":
#             outcome = 1 if close >= sub['short'] else 0
#         else:
#             outcome = 1 if close <= sub['short'] else 0

#         return outcome, round(close, 2)
#     except:
#         return None, "Error fetching price"

# # ---------- Reputation & Decay ----------
# def update_reputation(users, submission):
#     user_id = submission.get("user_id", "anonymous")
#     brier = submission.get("brier")
#     if brier is None: return users

#     if user_id not in users:
#         users[user_id] = {
#             "reputation": 1000.0,
#             "last_active": datetime.now().isoformat(),
#             "predictions": 0,
#             "avg_brier": 0.0,
#             "fake_balance": 10000.0,
#             "signup_date": datetime.now().isoformat()
#         }

#     u = users[user_id]
#     n = u["predictions"]
#     rep_change = 50 * (1 - brier) - 100 * brier
#     u["reputation"] = max(100, u["reputation"] + rep_change)
#     u["avg_brier"] = (u["avg_brier"] * n + brier) / (n + 1)
#     u["predictions"] = n + 1
#     u["last_active"] = datetime.now().isoformat()
#     return users

# def apply_decay(users, days=7, rate=0.02):
#     now = datetime.now()
#     for u in users.values():
#         last = datetime.fromisoformat(u["last_active"])
#         inactive = (now - last).days
#         if inactive > 0:
#             decay = (1 - rate) ** (inactive / days)
#             u["reputation"] = max(100, u["reputation"] * decay)
#             u["last_active"] = now.isoformat()
#     return users

# # ---------- AI Model ----------
# class SimpleNN(nn.Module):
#     def __init__(self, input_size=4):
#         super().__init__()
#         self.net = nn.Sequential(
#             nn.Linear(input_size, 16), nn.ReLU(),
#             nn.Linear(16, 8), nn.ReLU(),
#             nn.Linear(8, 1), nn.Sigmoid()
#         )
#     def forward(self, x): return self.net(x)

# def train_model(df, epochs=30):
#     if df.empty: return None, None, None
#     X = df[['pop', 'confidence', 'credit', 'brier']].fillna(0).values
#     y = df['outcome'].astype(float).values
#     X_scaled = StandardScaler().fit_transform(X)
#     X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
#     train_loader = DataLoader(TensorDataset(torch.tensor(X_train, dtype=torch.float32), torch.tensor(y_train, dtype=torch.float32).unsqueeze(1)), batch_size=8, shuffle=True)
#     model = SimpleNN()
#     criterion = nn.BCELoss()
#     optimizer = optim.Adam(model.parameters(), lr=0.01)
#     model.train()
#     for _ in range(epochs):
#         for xb, yb in train_loader:
#             optimizer.zero_grad()
#             loss = criterion(model(xb), yb)
#             loss.backward()
#             optimizer.step()
#     model.eval()
#     with torch.no_grad():
#         pred = model(torch.tensor(X_test, dtype=torch.float32))
#         loss = criterion(pred, torch.tensor(y_test, dtype=torch.float32).unsqueeze(1)).item()
#         acc = ((pred > 0.5).float() == torch.tensor(y_test).unsqueeze(1)).float().mean().item()
#     torch.save(model.state_dict(), MODEL_FILE)
#     return loss, acc, model

# # ---------- Init ----------
# auth_db = load_auth()
# if "authenticated" not in st.session_state:
#     st.session_state.authenticated = False
# if "current_user" not in st.session_state:
#     st.session_state.current_user = None

# if st.session_state.authenticated:
#     subs = load_submissions()
#     users = load_users()
#     rewards = load_rewards()
#     users = apply_decay(users)
# else:
#     subs = users = rewards = None

# # ---------- MOCK DATA ----------
# if st.session_state.authenticated and subs is not None and len(subs) == 0:
#     mock = [
#         {"id":0,"time":"2025-11-06T10:00:00","user_id":st.session_state.current_user,"symbol":"AAPL","direction":"Bull Put","exp":"2025-11-07","short":195.0,"long":190.0,"credit":1.25,"pop":75,"confidence":8,"rationale":"Strong support","status":"Pending","brier":None,"outcome":None,"expiry_close":None},
#         {"id":1,"time":"2025-11-06T11:00:00","user_id":"alpha","symbol":"SPY","direction":"Bear Call","exp":"2025-11-07","short":530.0,"long":535.0,"credit":1.10,"pop":68,"confidence":7,"rationale":"Overbought RSI","status":"Pending","brier":None,"outcome":None,"expiry_close":None},
#     ]
#     subs.extend(mock)
#     save_submissions(subs)

# # ---------- CSS ----------
# st.markdown("""
# <style>
#     .title { font-family: 'Helvetica Neue', sans-serif; font-size: 28px; font-weight: 600; color: #0b1226; }
#     .subtitle { font-size: 14px; color: #5b6470; margin-bottom: 16px; }
#     .card { background: #fff; border-radius: 14px; padding: 20px; box-shadow: 0 6px 18px rgba(12,15,20,0.06); }
#     .scene-name { font-size: 20px; font-weight: 600; }
#     .caption { color: #6b7280; font-size: 13px; font-style: italic; margin-left: 6px; }
#     .dialogue { font-style: italic; color: #2b2f36; margin: 10px 0; }
#     .payout-card { background: linear-gradient(135deg, #f0fdf4, #dcfce7); border-left: 5px solid #22c55e; padding: 12px; border-radius: 8px; }
#     .paid { background: #f3f4f6; text-decoration: line-through; opacity: 0.7; }
#     .ai-card { background: linear-gradient(135deg, #e0f2fe, #b3e5fc); border-left: 5px solid #0288d1; padding: 12px; border-radius: 8px; }
#     .disclaimer { background: #fef3c7; border-left: 5px solid #f59e0b; padding: 12px; border-radius: 8px; font-size: 13px; margin: 10px 0; }
#     .tos { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px; margin: 15px 0; font-size: 14px; line-height: 1.6; }
#     .payout-history { background: #f8fafc; border-radius: 12px; padding: 16px; margin-top: 16px; }
#     .auth-box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; max-width: 400px; margin: 20px auto; }
#     .balance { font-size: 18px; font-weight: 600; color: #059669; }
# </style>
# """, unsafe_allow_html=True)

# # ---------- AUTH FLOW ----------
# if not st.session_state.authenticated:
#     col1, col2, col3 = st.columns([1, 2, 1])
#     with col2:
#         st.markdown("<div class='auth-box'>", unsafe_allow_html=True)
#         auth_mode = st.radio(" ", ["Login", "Sign Up"], horizontal=True)
        
#         with st.form("auth_form"):
#             username = st.text_input("Username", placeholder="trader_x")
#             password = st.text_input("Password", type="password")
#             submit_auth = st.form_submit_button("Submit")

#             if submit_auth:
#                 if auth_mode == "Sign Up":
#                     if username in auth_db:
#                         st.error("Username taken.")
#                     elif len(password) < 6:
#                         st.error("Password must be 6+ chars.")
#                     else:
#                         pwdhash, salt = hash_password(password)
#                         auth_db[username] = {"pwdhash": pwdhash, "salt": salt}
#                         save_auth(auth_db)
#                         users = load_users()
#                         users[username] = {
#                             "reputation": 1000.0,
#                             "last_active": datetime.now().isoformat(),
#                             "predictions": 0,
#                             "avg_brier": 0.0,
#                             "fake_balance": 10000.0,
#                             "signup_date": datetime.now().isoformat()
#                         }
#                         save_users(users)
#                         st.success("Account created! $10,000 fake balance added.")
#                         st.session_state.authenticated = True
#                         st.session_state.current_user = username
#                         st.rerun()
#                 else:  # Login
#                     if username not in auth_db:
#                         st.error("Invalid username.")
#                     elif not verify_password(auth_db[username]["pwdhash"], auth_db[username]["salt"], password):
#                         st.error("Wrong password.")
#                     else:
#                         st.session_state.authenticated = True
#                         st.session_state.current_user = username
#                         st.success(f"Welcome back, {username}!")
#                         st.rerun()
#         st.markdown("</div>", unsafe_allow_html=True)
# else:
#     # ---------- Header ----------
#     col1, col2 = st.columns([3, 1])
#     with col1:
#         st.markdown('<div class="title">QuantStacks — Disney MVP</div>', unsafe_allow_html=True)
#         st.markdown('<div class="subtitle">Form + Verify + Score + Reward + Evolve (Auto-Outcome)</div>', unsafe_allow_html=True)
#     with col2:
#         user_balance = users[st.session_state.current_user].get("fake_balance", 10000.0)
#         st.markdown(f"<div class='balance'>${user_balance:,.2f}</div>", unsafe_allow_html=True)
#         if st.button("Logout"):
#             st.session_state.authenticated = False
#             st.session_state.current_user = None
#             st.rerun()

#     # ---------- Disclaimer ----------
#     st.markdown("""
#     <div class="disclaimer">
#         <strong>Legal Disclaimer:</strong> This is an educational and research prototype.
#         <strong>No real money is wagered.</strong> $10,000 is fake balance for simulation.
#         Predictions are for skill calibration only. Not investment advice.
#         Not gambling — no chance-based outcome. Complies with U.S. and VN laws for skill-based contests.
#     </div>
#     """, unsafe_allow_html=True)
#     st.markdown("---")

#     # ---------- Sidebar ----------
#     with st.sidebar:
#         st.markdown(f"### Trader")
#         st.write(f"**{st.session_state.current_user}**")
#         st.markdown(f"<div class='balance'>${user_balance:,.2f}</div>", unsafe_allow_html=True)
#         st.markdown("### Scenes")
#         if "scenes" not in st.session_state:
#             st.session_state.scenes = load_scenes()
#         for s in st.session_state.scenes:
#             if st.button(f"{s['id']+1}. {s['name']} — {s['status']}", key=f"nav_{s['id']}"):
#                 st.session_state.current_scene = s["id"]
#                 st.session_state.show_form = (s["id"] == 0)
        
#         st.markdown("---")
#         st.markdown("### Legal")
#         if st.button("Terms of Service"):
#             st.session_state.current_scene = -1
#         st.markdown("---")
#         c1, c2 = st.columns(2)
#         if c1.button("Play"): st.session_state.reel_playing = True
#         if c2.button("Stop"): st.session_state.reel_playing = False

#     # ---------- Main ----------
#     if "current_scene" not in st.session_state:
#         st.session_state.current_scene = 0
#     if "show_form" not in st.session_state:
#         st.session_state.show_form = False
#     if "scenes" not in st.session_state:
#         st.session_state.scenes = load_scenes()

#     scene = st.session_state.scenes[st.session_state.current_scene] if st.session_state.current_scene >= 0 else None

#     # === TERMS OF SERVICE PAGE ===
#     if st.session_state.current_scene == -1:
#         st.markdown("## Terms of Service")
#         st.markdown("""
#         <div class="tos">
#             <p><strong>Last updated:</strong> November 07, 2025</p>
#             <h3>1. Acceptance of Terms</h3>
#             <p>By accessing or using QuantStacks, you agree to be bound by these Terms.</p>
#             <h3>2. Fake Balance</h3>
#             <p>Each user starts with <strong>$10,000 fake balance</strong> for simulation. No real money.</p>
#             <h3>3. Authentication</h3>
#             <p>Passwords are hashed using PBKDF2-HMAC-SHA256 with unique salts. Industry standard.</p>
#             <h3>4. No Investment Advice</h3>
#             <p>All predictions are hypothetical. For skill calibration only.</p>
#             <h3>5. Compliance</h3>
#             <p>Skill-based contest. Complies with U.S. and Vietnam laws.</p>
#         </div>
#         """, unsafe_allow_html=True)
#         if st.button("Back to App"):
#             st.session_state.current_scene = 0
#             st.rerun()

#     # === PREDICT SCENE (FULLY RESTORED + $100 COST) ===
#     elif st.session_state.show_form and scene["id"] == 0:
#         st.markdown("### Submit Prediction")
#         st.info("**Simulated Cost:** $100 fake balance per prediction")
#         with st.form("credit_spread_form", clear_on_submit=True):
#             col1, col2 = st.columns(2)
#             with col1: symbol = st.text_input("Symbol", "AAPL")
#             with col2: direction = st.radio("Direction", ["Bull Put", "Bear Call"], horizontal=True)
#             load_chain = st.form_submit_button("Load Option Chain")
#             if load_chain:
#                 with st.spinner():
#                     try:
#                         ticker = yf.Ticker(symbol)
#                         exps = ticker.options
#                         if exps:
#                             st.session_state.exps = exps
#                             st.session_state.ticker = ticker
#                             st.success(f"Loaded {len(exps)} expirations")
#                         else: st.error("No options.")
#                     except: st.error("Invalid symbol.")
#             if 'exps' in st.session_state:
#                 exp = st.selectbox("Expiration", st.session_state.exps)
#                 load_strikes = st.form_submit_button("Load Strikes")
#                 if load_strikes:
#                     with st.spinner():
#                         opt = st.session_state.ticker.option_chain(exp)
#                         strikes = sorted(set(opt.calls['strike']) & set(opt.puts['strike']))
#                         st.session_state.strikes = strikes
#                         st.session_state.opt = opt
#                         st.success(f"Loaded {len(strikes)} strikes")
#             if 'strikes' in st.session_state:
#                 col3, col4 = st.columns(2)
#                 with col3: short = st.selectbox("Short", st.session_state.strikes, index=10)
#                 with col4:
#                     idx = max(0, st.session_state.strikes.index(short) - 3)
#                     long = st.selectbox("Long", st.session_state.strikes, index=idx)
#                 opt = st.session_state.opt
#                 if direction == "Bull Put":
#                     short_p = opt.puts[opt.puts['strike']==short]['lastPrice'].iloc[0]
#                     long_p = opt.puts[opt.puts['strike']==long]['lastPrice'].iloc[0]
#                 else:
#                     short_p = opt.calls[opt.calls['strike']==short]['lastPrice'].iloc[0]
#                     long_p = opt.calls[opt.calls['strike']==long]['lastPrice'].iloc[0]
#                 credit = round(short_p - long_p, 2)
#                 st.info(f"**Net Credit:** ${credit:.2f}")
#             col5, col6 = st.columns(2)
#             with col5: pop = st.slider("POP (%)", 50, 90, 70)
#             with col6: conf = st.slider("Confidence", 1, 10, 7)
#             rationale = st.text_area("Rationale", height=80)
#             submit = st.form_submit_button("Submit Prediction", type="primary")  # FIXED: renamed from submit_auth

#             if submit:
#                 if users[st.session_state.current_user]["fake_balance"] < 100:
#                     st.error("Insufficient fake balance!")
#                 else:
#                     users[st.session_state.current_user]["fake_balance"] -= 100
#                     save_users(users)
#                     sub = {
#                         "id": len(subs), "time": datetime.now().isoformat(), "user_id": st.session_state.current_user,
#                         "symbol": symbol, "direction": direction, "exp": exp if 'exp' in locals() else None,
#                         "short": short if 'short' in locals() else None, "long": long if 'long' in locals() else None,
#                         "credit": credit if 'credit' in locals() else None, "pop": pop, "confidence": conf,
#                         "rationale": rationale, "status": "Pending", "brier": None, "outcome": None, "expiry_close": None
#                     }
#                     subs.append(sub)
#                     save_submissions(subs)
#                     st.success("Submitted! -$100 fake balance")
#                     st.balloons()
#                     st.session_state.scenes[0]["progress"] = min(100, st.session_state.scenes[0]["progress"] + 10)
#                     save_scenes(st.session_state.scenes)
#                     for k in ['exps','strikes','opt','ticker']: st.session_state.pop(k, None)
#                     st.rerun()

#     # === OTHER SCENES (Verify, Score, Reward, Evolve) ===
#     elif scene["id"] == 1:
#         st.markdown("### Verification Dashboard")
#         df = pd.DataFrame(subs)
#         df['time'] = pd.to_datetime(df['time']).dt.strftime('%m-%d %H:%M')
#         pending = df[df['status'] == 'Pending']
#         verified = df[df['status'] == 'Verified']
#         col1, col2 = st.columns(2)
#         with col1: st.metric("Pending", len(pending))
#         with col2: st.metric("Verified", len(verified))
#         if not pending.empty:
#             st.markdown("#### Pending")
#             for _, row in pending.iterrows():
#                 with st.expander(f"ID {row['id']} — {row['symbol']} — {row['user_id']}"):
#                     st.write(f"**Short:** ${row['short']} | **Long:** ${row['long']} | **Credit:** ${row['credit']}")
#                     st.write(f"**POP:** {row['pop']}% | **Confidence:** {row['confidence']}/10")
#                     st.write(f"**Rationale:** {row['rationale']}")
#                     outcome, info = auto_determine_outcome(row.to_dict())
#                     if outcome is not None:
#                         st.success(f"Auto-Outcome: {'Success' if outcome else 'Failure'} | Close: ${info}")
#                         if st.button("Apply Auto-Outcome", key=f"auto_{row['id']}"):
#                             actual_pop = row['pop'] if outcome else (100 - row['pop'])
#                             brier = (row['pop']/100 - actual_pop/100)**2
#                             row['status'] = 'Verified'; row['brier'] = round(brier, 4)
#                             row['outcome'] = outcome; row['expiry_close'] = info
#                             save_submissions(subs); users = update_reputation(users, row.to_dict()); save_users(users)
#                             st.success(f"Auto-verified! Brier: {brier:.4f}")
#                             st.session_state.scenes[1]["progress"] = min(100, st.session_state.scenes[1]["progress"] + 15)
#                             save_scenes(st.session_state.scenes); st.rerun()
#                     else:
#                         st.info(f"Status: {info}")
#                     col_a, col_b = st.columns(2)
#                     with col_a: actual_pop = st.slider("Actual POP (%)", 0, 100, 70, key=f"act_{row['id']}")
#                     with col_b:
#                         if st.button("Manual Verify", key=f"ver_{row['id']}"):
#                             brier = (row['pop']/100 - actual_pop/100)**2
#                             row['status'] = 'Verified'; row['brier'] = round(brier, 4)
#                             row['outcome'] = 1 if actual_pop >= row['pop'] else 0
#                             save_submissions(subs); users = update_reputation(users, row.to_dict()); save_users(users)
#                             st.success(f"Verified! Brier: {brier:.4f}")
#                             st.session_state.scenes[1]["progress"] = min(100, st.session_state.scenes[1]["progress"] + 15)
#                             save_scenes(st.session_state.scenes); st.rerun()

#     elif scene["id"] == 2:
#         st.markdown("### Leaderboard")
#         if not users: st.info("No users.")
#         else:
#             lb = [{"User":uid, "Reputation":f"{u['reputation']:.1f}", "Predictions":u['predictions'], "Avg Brier":f"{u['avg_brier']:.4f}", "Last":pd.to_datetime(u['last_active']).strftime('%m-%d')} for uid,u in users.items()]
#             lb_df = pd.DataFrame(lb).sort_values("Reputation", ascending=False).reset_index(drop=True)
#             lb_df.index += 1
#             st.dataframe(lb_df.style.apply(lambda r: ['background: #fef3c7; font-weight: bold;']*len(r) if r.name==1 else ['']*len(r), axis=1))

#     elif scene["id"] == 3:
#         st.markdown("### Reward Payout Center")
#         st.markdown("**$10 Prize Pool — Top 3 Reputation**")
#         if not users: st.info("No users.")
#         else:
#             ranked = sorted(users.items(), key=lambda x: x[1]['reputation'], reverse=True)[:3]
#             paid = {r['user_id'] for r in rewards}
#             col1,col2,col3 = st.columns(3)
#             prizes = [5.0, 3.0, 2.0]
#             for i,(uid,u) in enumerate(ranked):
#                 with [col1,col2,col3][i]:
#                     paid_cls = "payout-card paid" if uid in paid else "payout-card"
#                     st.markdown(f"<div class='{paid_cls}'>", unsafe_allow_html=True)
#                     st.markdown(f"**#{i+1} — {uid}**")
#                     st.metric("Reputation", f"{u['reputation']:.1f}")
#                     st.write(f"**Prize:** ${prizes[i]:.2f}")
#                     if uid in paid: st.caption("Paid")
#                     else:
#                         if st.button("Pay Now", key=f"pay_{uid}"):
#                             rewards.append({
#                                 "user_id": uid,
#                                 "amount": prizes[i],
#                                 "date": datetime.now().isoformat(),
#                                 "rank": i+1,
#                                 "method": "Venmo",
#                                 "status": "Paid"
#                             })
#                             save_rewards(rewards)
#                             st.success(f"Paid ${prizes[i]:.2f} to {uid}"); st.balloons()
#                             st.session_state.scenes[3]["progress"] = min(100, st.session_state.scenes[3]["progress"] + 20)
#                             save_scenes(st.session_state.scenes); st.rerun()
#                     st.markdown("</div>", unsafe_allow_html=True)

#             st.markdown("#### Payout History")
#             if rewards:
#                 for r in rewards:
#                     r.setdefault("method", "Venmo")
#                     r.setdefault("status", "Paid")
#                     r.setdefault("rank", 0)
#                 hist = pd.DataFrame(rewards)
#                 hist['date'] = pd.to_datetime(hist['date']).dt.strftime('%m-%d %H:%M')
#                 cols = ['user_id', 'rank', 'amount', 'method', 'status', 'date']
#                 available_cols = [c for c in cols if c in hist.columns]
#                 hist = hist[available_cols].sort_values('date', ascending=False)
#                 st.markdown("<div class='payout-history'>", unsafe_allow_html=True)
#                 st.dataframe(hist.style.format({"amount": "${:.2f}"}))
#                 st.markdown("</div>", unsafe_allow_html=True)
#             else:
#                 st.info("No payouts yet.")

#     elif scene["id"] == 4:
#         st.markdown("### Evolve — Human + AI Co-Training")
#         verified = [s for s in subs if s.get('status')=='Verified' and s.get('outcome') is not None]
#         df = pd.DataFrame(verified)
#         st.markdown(f"**Verified Data Ready:** {len(df)} predictions")
#         if not df.empty:
#             st.markdown("#### Training Preview")
#             st.dataframe(df[['user_id','symbol','pop','brier','outcome','expiry_close']].head())
#             if st.button("Start Co-Training", type="primary"):
#                 with st.spinner("Training..."):
#                     loss, acc, _ = train_model(df)
#                     if loss:
#                         st.success("**AI Trained!**")
#                         col1,col2 = st.columns(2)
#                         with col1: st.metric("Test Loss", f"{loss:.4f}")
#                         with col2: st.metric("Accuracy", f"{acc*100:.1f}%")
#                         st.info(f"**Brier Improved:** 0.42 to {loss:.4f}")
#                         st.session_state.scenes[4]["progress"] = min(100, st.session_state.scenes[4]["progress"] + 30)
#                         save_scenes(st.session_state.scenes); st.balloons()
#             if st.button("Export Data"):
#                 df.to_json(VERIFIED_DATA_FILE, orient='records', indent=2)
#                 st.success(f"Exported to {VERIFIED_DATA_FILE}")
#         else: st.info("**No verified outcomes yet.** Submit + verify to train AI.")

#     else:
#         left, right = st.columns([2,1])
#         with left:
#             st.markdown(f'<div class="card"><div class="scene-name">{scene["name"]} <span class="caption">{scene["caption"]}</span></div>', unsafe_allow_html=True)
#             st.markdown(f'<div class="dialogue">“{scene["dialogue"]}”</div>', unsafe_allow_html=True)
#             st.markdown(f"**Overview:** {scene['description']}")
#             st.markdown('</div>', unsafe_allow_html=True)
#         with right:
#             st.markdown('<div class="card">', unsafe_allow_html=True)
#             st.metric("Scene", scene["name"])
#             st.progress(scene["progress"]/100)
#             st.write(f"**Status:** {scene['status']}")
#             st.markdown('</div>', unsafe_allow_html=True)

#     # ---------- Reel ----------
#     if st.session_state.get("reel_playing", False):
#         ph = st.empty()
#         for i in range(st.session_state.current_scene, 5):
#             st.session_state.current_scene = i
#             sc = st.session_state.scenes[i]
#             ph.markdown(f"### {sc['name']} — {sc['caption']}")
#             ph.write(sc["dialogue"])
#             time.sleep(1.2)
#             ph.success("Scene complete")
#             time.sleep(0.5)
#         st.session_state.reel_playing = False
#         st.rerun()

# # ---------- Footer ----------
# st.markdown("---")
# with st.expander("Run"):
#     st.code("pip install streamlit yfinance pandas torch scikit-learn numpy\nstreamlit run quantstacks_storyboard_plus_form.py")


##### fix some errors


# # quantstacks_storyboard_plus_form.py
# # Run: streamlit run quantstacks_storyboard_plus_form.py

# import streamlit as st
# import yfinance as yf
# import pandas as pd
# import json
# import time
# from datetime import datetime, timedelta
# from pathlib import Path
# import torch
# import torch.nn as nn
# import torch.optim as optim
# from torch.utils.data import DataLoader, TensorDataset
# import numpy as np
# from sklearn.preprocessing import StandardScaler
# from sklearn.model_selection import train_test_split
# import hashlib
# import secrets

# # ---------- Config ----------
# st.set_page_config(page_title="QuantStacks — Disney MVP", layout="wide")

# # ---------- Files ----------
# DATA_FILE = Path("quantstacks_storyboard_data.json")
# SUBMISSIONS_FILE = Path("quantstacks_submissions.json")
# USERS_FILE = Path("quantstacks_users.json")
# REWARDS_FILE = Path("quantstacks_rewards.json")
# MODEL_FILE = Path("quantstacks_model.pth")
# VERIFIED_DATA_FILE = Path("verified_data_for_training.json")
# SCALER_FILE = Path("quantstacks_scaler.json")
# AUTH_FILE = Path("quantstacks_auth.json")

# # ---------- Default Scenes ----------
# DEFAULT_SCENES = [
#     {
#         "id": 0, "name": "Predict", "caption": "Curiosity to Signal",
#         "dialogue": "What if we could capture every trader's intuition and measure truth?",
#         "description": "Users submit structured vertical credit spread predictions.",
#         "tasks": ["Launch live submission form", "Collect 10 real predictions in 48h", "Export JSON to Google Sheets"],
#         "status": "Completed", "progress": 100, "notes": "5+ submissions. Form stable."
#     },
#     {
#         "id": 1, "name": "Verify", "caption": "Skepticism to Confirmation",
#         "dialogue": "Truth must be tested — AI and crowd verify signals.",
#         "description": "Manual + AI verification pipeline evaluates submissions.",
#         "tasks": ["Build verification rubric", "Run 5 predictions through Sheets", "Compare crowd vs. AI scores"],
#         "status": "Completed", "progress": 100, "notes": "Auto-outcome live. 5 verified."
#     },
#     {
#         "id": 2, "name": "Score", "caption": "Signal to Reputation",
#         "dialogue": "Reputation is earned through calibrated accuracy.",
#         "description": "Brier scores, leaderboards, and reputation engine.",
#         "tasks": ["Mock Brier scoring in Python", "Design leaderboard UI", "Test with 20 predictions"],
#         "status": "Completed", "progress": 100, "notes": "Leaderboard live. Decay active."
#     },
#     {
#         "id": 3, "name": "Reward", "caption": "Validation to Incentive",
#         "dialogue": "Skin in the game: rewards align truth.",
#         "description": "Manual payouts to top predictors.",
#         "tasks": ["Announce $10 prize pool", "Pay top 3 via Venmo", "Measure submission spike"],
#         "status": "Completed", "progress": 100, "notes": "3/3 paid. $10 distributed."
#     },
#     {
#         "id": 4, "name": "Evolve", "caption": "Learn to Scale",
#         "dialogue": "Human + AI co-training creates a living intelligence engine.",
#         "description": "Retrain models on verified data.",
#         "tasks": ["Export 50 verified predictions", "Retrain simple ML model", "Improve Brier from 0.42 to 0.38"],
#         "status": "In Progress", "progress": 90, "notes": "Auto-outcome + AI training live. Brier to 0.34"
#     },
# ]

# # ---------- Auth Utilities ----------
# def hash_password(password: str, salt: str = None) -> tuple:
#     if salt is None:
#         salt = secrets.token_hex(16)
#     pwdhash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
#     return pwdhash.hex(), salt

# def verify_password(stored_hash: str, stored_salt: str, password: str) -> bool:
#     pwdhash, _ = hash_password(password, stored_salt)
#     return secrets.compare_digest(pwdhash, stored_hash)

# def load_auth():
#     if AUTH_FILE.exists():
#         try: return json.load(open(AUTH_FILE, "r", encoding="utf-8"))
#         except: return {}
#     return {}

# def save_auth(auth_db):
#     json.dump(auth_db, open(AUTH_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# # ---------- Persistence ----------
# def load_scenes():
#     if DATA_FILE.exists():
#         try: return json.load(open(DATA_FILE, "r", encoding="utf-8"))
#         except: return DEFAULT_SCENES.copy()
#     return DEFAULT_SCENES.copy()

# def save_scenes(scenes):
#     json.dump(scenes, open(DATA_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# def load_submissions():
#     if SUBMISSIONS_FILE.exists():
#         try: return json.load(open(SUBMISSIONS_FILE, "r", encoding="utf-8"))
#         except: return []
#     return []

# def save_submissions(subs):
#     json.dump(subs, open(SUBMISSIONS_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# def load_users():
#     if USERS_FILE.exists():
#         try: return json.load(open(USERS_FILE, "r", encoding="utf-8"))
#         except: return {}
#     return {}

# def save_users(users):
#     json.dump(users, open(USERS_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# def load_rewards():
#     if REWARDS_FILE.exists():
#         try: 
#             rewards = json.load(open(REWARDS_FILE, "r", encoding="utf-8"))
#             for r in rewards:
#                 r.setdefault("method", "Venmo")
#                 r.setdefault("status", "Paid")
#                 r.setdefault("rank", 0)
#             return rewards
#         except: return []
#     return []

# def save_rewards(rewards):
#     json.dump(rewards, open(REWARDS_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# # ---------- Auto-Outcome via yfinance ----------
# def auto_determine_outcome(sub):
#     try:
#         exp_date = datetime.strptime(sub['exp'], '%Y-%m-%d').date()
#         today = datetime.now().date()
#         if today <= exp_date:
#             return None, "Not expired"

#         ticker = yf.Ticker(sub['symbol'])
#         hist = ticker.history(start=exp_date, end=exp_date + timedelta(days=2))
#         if hist.empty:
#             return None, "No price data"

#         close = hist['Close'].iloc[-1]  # Use last available (post-expiry)
#         if sub['direction'] == "Bull Put":
#             outcome = 1 if close >= sub['short'] else 0
#         else:
#             outcome = 1 if close <= sub['short'] else 0

#         return outcome, round(close, 2)
#     except Exception as e:
#         return None, f"Error: {str(e)}"

# # ---------- Reputation & Decay ----------
# def update_reputation(users, submission):
#     user_id = submission.get("user_id", "anonymous")
#     brier = submission.get("brier")
#     if brier is None: return users

#     if user_id not in users:
#         users[user_id] = {
#             "reputation": 1000.0,
#             "last_active": datetime.now().isoformat(),
#             "predictions": 0,
#             "avg_brier": 0.0,
#             "fake_balance": 10000.0,
#             "signup_date": datetime.now().isoformat()
#         }

#     u = users[user_id]
#     n = u["predictions"]
#     rep_change = 50 * (1 - brier) - 100 * brier
#     u["reputation"] = max(100, u["reputation"] + rep_change)
#     u["avg_brier"] = (u["avg_brier"] * n + brier) / (n + 1)
#     u["predictions"] = n + 1
#     u["last_active"] = datetime.now().isoformat()
#     return users

# def apply_decay(users, days=7, rate=0.02):
#     now = datetime.now()
#     for u in users.values():
#         last = datetime.fromisoformat(u["last_active"])
#         inactive = (now - last).days
#         if inactive > 0:
#             decay = (1 - rate) ** (inactive / days)
#             u["reputation"] = max(100, u["reputation"] * decay)
#             u["last_active"] = now.isoformat()
#     return users

# # ---------- AI Model ----------
# class SimpleNN(nn.Module):
#     def __init__(self, input_size=3):  # pop, confidence, credit
#         super().__init__()
#         self.net = nn.Sequential(
#             nn.Linear(input_size, 16), nn.ReLU(),
#             nn.Linear(16, 8), nn.ReLU(),
#             nn.Linear(8, 1), nn.Sigmoid()
#         )
#     def forward(self, x): return self.net(x)

# def train_model(df, epochs=30):
#     if df.empty or len(df) < 5: return None, None, None, None
#     feature_cols = ['pop', 'confidence', 'credit']
#     X = df[feature_cols].fillna(0).values
#     y = df['outcome'].astype(float).values

#     scaler = StandardScaler()
#     X_scaled = scaler.fit_transform(X)

#     X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
#     train_loader = DataLoader(TensorDataset(torch.tensor(X_train, dtype=torch.float32), torch.tensor(y_train, dtype=torch.float32).unsqueeze(1)), batch_size=8, shuffle=True)

#     model = SimpleNN()
#     criterion = nn.BCELoss()
#     optimizer = optim.Adam(model.parameters(), lr=0.01)
#     model.train()
#     for _ in range(epochs):
#         for xb, yb in train_loader:
#             optimizer.zero_grad()
#             loss = criterion(model(xb), yb)
#             loss.backward()
#             optimizer.step()

#     model.eval()
#     with torch.no_grad():
#         pred = model(torch.tensor(X_test, dtype=torch.float32))
#         loss = criterion(pred, torch.tensor(y_test, dtype=torch.float32).unsqueeze(1)).item()
#         acc = ((pred > 0.5).float() == torch.tensor(y_test).unsqueeze(1)).float().mean().item()

#     torch.save(model.state_dict(), MODEL_FILE)
#     # Save scaler
#     scaler_dict = {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist()}
#     json.dump(scaler_dict, open(SCALER_FILE, "w"))
#     return loss, acc, model, scaler

# def load_model_and_scaler():
#     if not MODEL_FILE.exists() or not SCALER_FILE.exists():
#         return None, None
#     model = SimpleNN()
#     model.load_state_dict(torch.load(MODEL_FILE))
#     model.eval()
#     scaler_data = json.load(open(SCALER_FILE))
#     scaler = StandardScaler()
#     scaler.mean_ = np.array(scaler_data["mean"])
#     scaler.scale_ = np.array(scaler_data["scale"])
#     return model, scaler

# # ---------- Init ----------
# auth_db = load_auth()
# if "authenticated" not in st.session_state:
#     st.session_state.authenticated = False
# if "current_user" not in st.session_state:
#     st.session_state.current_user = None

# if st.session_state.authenticated:
#     subs = load_submissions()
#     users = load_users()
#     rewards = load_rewards()
#     users = apply_decay(users)
# else:
#     subs = users = rewards = None

# # ---------- MOCK DATA ----------
# if st.session_state.authenticated and subs is not None and len(subs) == 0:
#     mock = [
#         {"id":0,"time":"2025-11-06T10:00:00","user_id":st.session_state.current_user,"symbol":"AAPL","direction":"Bull Put","exp":"2025-11-07","short":195.0,"long":190.0,"credit":1.25,"pop":75,"confidence":8,"rationale":"Strong support","status":"Pending","brier":None,"outcome":None,"expiry_close":None,"days_to_exp":1},
#         {"id":1,"time":"2025-11-06T11:00:00","user_id":"alpha","symbol":"SPY","direction":"Bear Call","exp":"2025-11-07","short":530.0,"long":535.0,"credit":1.10,"pop":68,"confidence":7,"rationale":"Overbought RSI","status":"Pending","brier":None,"outcome":None,"expiry_close":None,"days_to_exp":1},
#     ]
#     subs.extend(mock)
#     save_submissions(subs)

# # ---------- CSS ----------
# st.markdown("""
# <style>
#     .title { font-family: 'Helvetica Neue', sans-serif; font-size: 28px; font-weight: 600; color: #0b1226; }
#     .subtitle { font-size: 14px; color: #5b6470; margin-bottom: 16px; }
#     .card { background: #fff; border-radius: 14px; padding: 20px; box-shadow: 0 6px 18px rgba(12,15,20,0.06); }
#     .scene-name { font-size: 20px; font-weight: 600; }
#     .caption { color: #6b7280; font-size: 13px; font-style: italic; margin-left: 6px; }
#     .dialogue { font-style: italic; color: #2b2f36; margin: 10px 0; }
#     .payout-card { background: linear-gradient(135deg, #f0fdf4, #dcfce7); border-left: 5px solid #22c55e; padding: 12px; border-radius: 8px; }
#     .paid { background: #f3f4f6; text-decoration: line-through; opacity: 0.7; }
#     .ai-card { background: linear-gradient(135deg, #e0f2fe, #b3e5fc); border-left: 5px solid #0288d1; padding: 12px; border-radius: 8px; }
#     .disclaimer { background: #fef3c7; border-left: 5px solid #f59e0b; padding: 12px; border-radius: 8px; font-size: 13px; margin: 10px 0; }
#     .tos { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px; margin: 15px 0; font-size: 14px; line-height: 1.6; }
#     .payout-history { background: #f8fafc; border-radius: 12px; padding: 16px; margin-top: 16px; }
#     .auth-box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; max-width: 400px; margin: 20px auto; }
#     .balance { font-size: 18px; font-weight: 600; color: #059669; }
# </style>
# """, unsafe_allow_html=True)

# # ---------- AUTH FLOW ----------
# if not st.session_state.authenticated:
#     col1, col2, col3 = st.columns([1, 2, 1])
#     with col2:
#         st.markdown("<div class='auth-box'>", unsafe_allow_html=True)
#         auth_mode = st.radio(" ", ["Login", "Sign Up"], horizontal=True)
        
#         with st.form("auth_form"):
#             username = st.text_input("Username", placeholder="trader_x")
#             password = st.text_input("Password", type="password")
#             submit_auth = st.form_submit_button("Submit")

#             if submit_auth:
#                 if auth_mode == "Sign Up":
#                     if username in auth_db:
#                         st.error("Username taken.")
#                     elif len(password) < 6:
#                         st.error("Password must be 6+ chars.")
#                     else:
#                         pwdhash, salt = hash_password(password)
#                         auth_db[username] = {"pwdhash": pwdhash, "salt": salt}
#                         save_auth(auth_db)
#                         users = load_users()
#                         users[username] = {
#                             "reputation": 1000.0,
#                             "last_active": datetime.now().isoformat(),
#                             "predictions": 0,
#                             "avg_brier": 0.0,
#                             "fake_balance": 10000.0,
#                             "signup_date": datetime.now().isoformat()
#                         }
#                         save_users(users)
#                         st.success("Account created! $10,000 fake balance added.")
#                         st.session_state.authenticated = True
#                         st.session_state.current_user = username
#                         st.rerun()
#                 else:
#                     if username not in auth_db:
#                         st.error("Invalid username.")
#                     elif not verify_password(auth_db[username]["pwdhash"], auth_db[username]["salt"], password):
#                         st.error("Wrong password.")
#                     else:
#                         st.session_state.authenticated = True
#                         st.session_state.current_user = username
#                         st.success(f"Welcome back, {username}!")
#                         st.rerun()
#         st.markdown("</div>", unsafe_allow_html=True)
# else:
#     # ---------- Header ----------
#     col1, col2 = st.columns([3, 1])
#     with col1:
#         st.markdown('<div class="title">QuantStacks — Disney MVP</div>', unsafe_allow_html=True)
#         st.markdown('<div class="subtitle">Form + Verify + Score + Reward + Evolve (Auto-Outcome)</div>', unsafe_allow_html=True)
#     with col2:
#         user_balance = users[st.session_state.current_user].get("fake_balance", 10000.0)
#         st.markdown(f"<div class='balance'>${user_balance:,.2f}</div>", unsafe_allow_html=True)
#         if st.button("Logout"):
#             st.session_state.authenticated = False
#             st.session_state.current_user = None
#             st.rerun()

#     # ---------- Disclaimer ----------
#     st.markdown("""
#     <div class="disclaimer">
#         <strong>Legal Disclaimer:</strong> This is an educational and research prototype.
#         <strong>No real money is wagered.</strong> $10,000 is fake balance for simulation.
#         Predictions are for skill calibration only. Not investment advice.
#         Not gambling — no chance-based outcome. Complies with U.S. and VN laws for skill-based contests.
#     </div>
#     """, unsafe_allow_html=True)
#     st.markdown("---")

#     # ---------- Sidebar ----------
#     with st.sidebar:
#         st.markdown(f"### Trader")
#         st.write(f"**{st.session_state.current_user}**")
#         st.markdown(f"<div class='balance'>${user_balance:,.2f}</div>", unsafe_allow_html=True)
#         st.markdown("### Scenes")
#         if "scenes" not in st.session_state:
#             st.session_state.scenes = load_scenes()
#         for s in st.session_state.scenes:
#             if st.button(f"{s['id']+1}. {s['name']} — {s['status']}", key=f"nav_{s['id']}"):
#                 st.session_state.current_scene = s["id"]
#                 st.session_state.show_form = (s["id"] == 0)
        
#         st.markdown("---")
#         st.markdown("### Legal")
#         if st.button("Terms of Service"):
#             st.session_state.current_scene = -1
#         st.markdown("---")
#         c1, c2 = st.columns(2)
#         if c1.button("Play"): st.session_state.reel_playing = True
#         if c2.button("Stop"): st.session_state.reel_playing = False

#     # ---------- Main ----------
#     if "current_scene" not in st.session_state:
#         st.session_state.current_scene = 0
#     if "show_form" not in st.session_state:
#         st.session_state.show_form = False
#     if "scenes" not in st.session_state:
#         st.session_state.scenes = load_scenes()

#     scene = st.session_state.scenes[st.session_state.current_scene] if st.session_state.current_scene >= 0 else None

#     # === TERMS OF SERVICE PAGE ===
#     if st.session_state.current_scene == -1:
#         st.markdown("## Terms of Service")
#         st.markdown("""
#         <div class="tos">
#             <p><strong>Last updated:</strong> November 07, 2025</p>
#             <h3>1. Acceptance of Terms</h3>
#             <p>By accessing or using QuantStacks, you agree to be bound by these Terms.</p>
#             <h3>2. Fake Balance</h3>
#             <p>Each user starts with <strong>$10,000 fake balance</strong> for simulation. No real money.</p>
#             <h3>3. Authentication</h3>
#             <p>Passwords are hashed using PBKDF2-HMAC-SHA256 with unique salts. Industry standard.</p>
#             <h3>4. No Investment Advice</h3>
#             <p>All predictions are hypothetical. For skill calibration only.</p>
#             <h3>5. Compliance</h3>
#             <p>Skill-based contest. Complies with U.S. and Vietnam laws.</p>
#         </div>
#         """, unsafe_allow_html=True)
#         if st.button("Back to App"):
#             st.session_state.current_scene = 0
#             st.rerun()

#     # === PREDICT SCENE (FULLY RESTORED + $100 COST + AI CONFIDENCE) ===
#     elif st.session_state.show_form and scene["id"] == 0:
#         st.markdown("### Submit Prediction")
#         st.info("**Simulated Cost:** $100 fake balance per prediction")

#         # Load AI model
#         model, scaler = load_model_and_scaler() if MODEL_FILE.exists() else (None, None)

#         with st.form("credit_spread_form", clear_on_submit=True):
#             col1, col2 = st.columns(2)
#             with col1: symbol = st.text_input("Symbol", "AAPL", key="symbol_input")
#             with col2: direction = st.radio("Direction", ["Bull Put", "Bear Call"], horizontal=True, key="direction_input")

#             load_chain = st.form_submit_button("Load Option Chain")
#             if load_chain:
#                 with st.spinner("Fetching option chain..."):
#                     try:
#                         ticker = yf.Ticker(symbol.upper())
#                         exps = ticker.options
#                         if exps:
#                             st.session_state.exps = exps
#                             st.session_state.ticker = ticker
#                             st.success(f"Loaded {len(exps)} expirations")
#                         else:
#                             st.error("No options available for this symbol.")
#                     except Exception as e:
#                         st.error(f"Invalid symbol or error: {e}")

#             if 'exps' in st.session_state:
#                 exp = st.selectbox("Expiration", st.session_state.exps, key="exp_select")
#                 load_strikes = st.form_submit_button("Load Strikes")
#                 if load_strikes:
#                     with st.spinner("Loading strikes..."):
#                         try:
#                             opt = st.session_state.ticker.option_chain(exp)
#                             calls = opt.calls[['strike', 'lastPrice']].dropna()
#                             puts = opt.puts[['strike', 'lastPrice']].dropna()
#                             common_strikes = sorted(set(calls['strike']) & set(puts['strike']))
#                             if len(common_strikes) < 2:
#                                 st.error("Not enough common strikes.")
#                             else:
#                                 st.session_state.strikes = common_strikes
#                                 st.session_state.opt = opt
#                                 st.success(f"Loaded {len(common_strikes)} common strikes")
#                         except Exception as e:
#                             st.error(f"Error loading strikes: {e}")

#             if 'strikes' in st.session_state and len(st.session_state.strikes) > 1:
#                 col3, col4 = st.columns(2)
#                 with col3:
#                     short_idx = st.selectbox("Short Strike", range(len(st.session_state.strikes)), format_func=lambda i: f"${st.session_state.strikes[i]:.2f}", key="short_select")
#                     short = st.session_state.strikes[short_idx]
#                 with col4:
#                     long_idx = st.selectbox("Long Strike", range(len(st.session_state.strikes)), format_func=lambda i: f"${st.session_state.strikes[i]:.2f}", index=max(0, short_idx-3), key="long_select")
#                     long = st.session_state.strikes[long_idx]

#                 opt = st.session_state.opt
#                 try:
#                     if direction == "Bull Put":
#                         short_p = opt.puts[opt.puts['strike']==short]['lastPrice'].iloc[0]
#                         long_p = opt.puts[opt.puts['strike']==long]['lastPrice'].iloc[0]
#                     else:
#                         short_p = opt.calls[opt.calls['strike']==short]['lastPrice'].iloc[0]
#                         long_p = opt.calls[opt.calls['strike']==long]['lastPrice'].iloc[0]
#                     credit = round(short_p - long_p, 2)
#                     st.info(f"**Net Credit:** ${credit:.2f}")
#                 except:
#                     credit = 0.0
#                     st.warning("Could not calculate credit.")

#                 col5, col6 = st.columns(2)
#                 with col5: pop = st.slider("POP (%)", 50, 90, 70, key="pop_slider")
#                 with col6: conf = st.slider("Confidence", 1, 10, 7, key="conf_slider")
#                 rationale = st.text_area("Rationale", height=80, key="rationale_input")

#                 # AI Confidence
#                 if model and scaler:
#                     try:
#                         X = np.array([[pop/100, conf/10, credit]])
#                         X_scaled = (X - scaler.mean_) / scaler.scale_
#                         with torch.no_grad():
#                             ai_prob = model(torch.tensor(X_scaled, dtype=torch.float32)).item()
#                         st.markdown(f"<div class='ai-card'>**AI Confidence:** {ai_prob*100:.1f}%</div>", unsafe_allow_html=True)
#                     except:
#                         pass

#                 submit = st.form_submit_button("Submit Prediction", type="primary")

#                 if submit:
#                     if users[st.session_state.current_user]["fake_balance"] < 100:
#                         st.error("Insufficient fake balance!")
#                     elif 'strikes' not in st.session_state:
#                         st.error("Load option chain and select strikes first.")
#                     else:
#                         users[st.session_state.current_user]["fake_balance"] -= 100
#                         save_users(users)
#                         days_to_exp = (datetime.strptime(exp, '%Y-%m-%d') - datetime.now()).days
#                         sub = {
#                             "id": len(subs), "time": datetime.now().isoformat(), "user_id": st.session_state.current_user,
#                             "symbol": symbol.upper(), "direction": direction, "exp": exp,
#                             "short": float(short), "long": float(long), "credit": credit,
#                             "pop": pop, "confidence": conf, "rationale": rationale,
#                             "status": "Pending", "brier": None, "outcome": None, "expiry_close": None,
#                             "days_to_exp": days_to_exp
#                         }
#                         subs.append(sub)
#                         save_submissions(subs)
#                         st.success("Submitted! -$100 fake balance")
#                         st.balloons()
#                         st.session_state.scenes[0]["progress"] = min(100, st.session_state.scenes[0]["progress"] + 10)
#                         save_scenes(st.session_state.scenes)
#                         for k in ['exps','strikes','opt','ticker']: st.session_state.pop(k, None)
#                         st.rerun()

#     # === VERIFY, SCORE, REWARD, EVOLVE (unchanged logic, only Brier fix) ===
#     elif scene["id"] == 1:
#         st.markdown("### Verification Dashboard")
#         df = pd.DataFrame(subs)
#         df['time'] = pd.to_datetime(df['time']).dt.strftime('%m-%d %H:%M')
#         pending = df[df['status'] == 'Pending']
#         verified = df[df['status'] == 'Verified']
#         col1, col2 = st.columns(2)
#         with col1: st.metric("Pending", len(pending))
#         with col2: st.metric("Verified", len(verified))
#         if not pending.empty:
#             st.markdown("#### Pending")
#             for _, row in pending.iterrows():
#                 with st.expander(f"ID {row['id']} — {row['symbol']} — {row['user_id']}"):
#                     st.write(f"**Short:** ${row['short']} | **Long:** ${row['long']} | **Credit:** ${row['credit']}")
#                     st.write(f"**POP:** {row['pop']}% | **Confidence:** {row['confidence']}/10")
#                     st.write(f"**Rationale:** {row['rationale']}")
#                     outcome, info = auto_determine_outcome(row.to_dict())
#                     if outcome is not None:
#                         st.success(f"Auto-Outcome: {'Success' if outcome else 'Failure'} | Close: ${info}")
#                         if st.button("Apply Auto-Outcome", key=f"auto_{row['id']}"):
#                             p = row['pop'] / 100
#                             o = outcome
#                             brier = (p - o) ** 2
#                             row['status'] = 'Verified'; row['brier'] = round(brier, 4)
#                             row['outcome'] = outcome; row['expiry_close'] = info
#                             save_submissions(subs); users = update_reputation(users, row.to_dict()); save_users(users)
#                             st.success(f"Auto-verified! Brier: {brier:.4f}")
#                             st.session_state.scenes[1]["progress"] = min(100, st.session_state.scenes[1]["progress"] + 15)
#                             save_scenes(st.session_state.scenes); st.rerun()
#                     else:
#                         st.info(f"Status: {info}")
#                     col_a, col_b = st.columns(2)
#                     with col_a: actual_pop = st.slider("Actual POP (%)", 0, 100, row['pop'], key=f"act_{row['id']}")
#                     with col_b:
#                         if st.button("Manual Verify", key=f"ver_{row['id']}"):
#                             p = row['pop'] / 100
#                             o = 1 if actual_pop >= row['pop'] else 0
#                             brier = (p - o) ** 2
#                             row['status'] = 'Verified'; row['brier'] = round(brier, 4)
#                             row['outcome'] = o
#                             save_submissions(subs); users = update_reputation(users, row.to_dict()); save_users(users)
#                             st.success(f"Verified! Brier: {brier:.4f}")
#                             st.session_state.scenes[1]["progress"] = min(100, st.session_state.scenes[1]["progress"] + 15)
#                             save_scenes(st.session_state.scenes); st.rerun()

#     elif scene["id"] == 2:
#         st.markdown("### Leaderboard")
#         if not users: st.info("No users.")
#         else:
#             lb = [{"User":uid, "Reputation":f"{u['reputation']:.1f}", "Predictions":u['predictions'], "Avg Brier":f"{u['avg_brier']:.4f}", "Last":pd.to_datetime(u['last_active']).strftime('%m-%d')} for uid,u in users.items()]
#             lb_df = pd.DataFrame(lb).sort_values("Reputation", ascending=False).reset_index(drop=True)
#             lb_df.index += 1
#             st.dataframe(lb_df.style.apply(lambda r: ['background: #fef3c7; font-weight: bold;']*len(r) if r.name==1 else ['']*len(r), axis=1))

#     elif scene["id"] == 3:
#         st.markdown("### Reward Payout Center")
#         st.markdown("**$10 Prize Pool — Top 3 Reputation**")
#         if not users: st.info("No users.")
#         else:
#             ranked = sorted(users.items(), key=lambda x: x[1]['reputation'], reverse=True)[:3]
#             paid = {r['user_id'] for r in rewards}
#             col1,col2,col3 = st.columns(3)
#             prizes = [5.0, 3.0, 2.0]
#             for i,(uid,u) in enumerate(ranked):
#                 with [col1,col2,col3][i]:
#                     paid_cls = "payout-card paid" if uid in paid else "payout-card"
#                     st.markdown(f"<div class='{paid_cls}'>", unsafe_allow_html=True)
#                     st.markdown(f"**#{i+1} — {uid}**")
#                     st.metric("Reputation", f"{u['reputation']:.1f}")
#                     st.write(f"**Prize:** ${prizes[i]:.2f}")
#                     if uid in paid: st.caption("Paid")
#                     else:
#                         if st.button("Pay Now", key=f"pay_{uid}"):
#                             rewards.append({
#                                 "user_id": uid,
#                                 "amount": prizes[i],
#                                 "date": datetime.now().isoformat(),
#                                 "rank": i+1,
#                                 "method": "Venmo",
#                                 "status": "Paid"
#                             })
#                             save_rewards(rewards)
#                             st.success(f"Paid ${prizes[i]:.2f} to {uid}"); st.balloons()
#                             st.session_state.scenes[3]["progress"] = min(100, st.session_state.scenes[3]["progress"] + 20)
#                             save_scenes(st.session_state.scenes); st.rerun()
#                     st.markdown("</div>", unsafe_allow_html=True)

#             st.markdown("#### Payout History")
#             if rewards:
#                 hist = pd.DataFrame(rewards)
#                 hist['date'] = pd.to_datetime(hist['date']).dt.strftime('%m-%d %H:%M')
#                 cols = ['user_id', 'rank', 'amount', 'method', 'status', 'date']
#                 available_cols = [c for c in cols if c in hist.columns]
#                 hist = hist[available_cols].sort_values('date', ascending=False)
#                 st.markdown("<div class='payout-history'>", unsafe_allow_html=True)
#                 st.dataframe(hist.style.format({"amount": "${:.2f}"}))
#                 st.markdown("</div>", unsafe_allow_html=True)
#             else:
#                 st.info("No payouts yet.")

#     elif scene["id"] == 4:
#         st.markdown("### Evolve — Human + AI Co-Training")
#         verified = [s for s in subs if s.get('status')=='Verified' and s.get('outcome') is not None]
#         df = pd.DataFrame(verified)
#         st.markdown(f"**Verified Data Ready:** {len(df)} predictions")
#         if not df.empty:
#             st.markdown("#### Training Preview")
#             st.dataframe(df[['user_id','symbol','pop','brier','outcome','expiry_close']].head())
#             if st.button("Start Co-Training", type="primary"):
#                 with st.spinner("Training AI model..."):
#                     loss, acc, _, _ = train_model(df)
#                     if loss:
#                         st.success("**AI Trained!**")
#                         col1,col2 = st.columns(2)
#                         with col1: st.metric("Test Loss", f"{loss:.4f}")
#                         with col2: st.metric("Accuracy", f"{acc*100:.1f}%")
#                         st.info(f"**Model updated and saved.**")
#                         st.session_state.scenes[4]["progress"] = min(100, st.session_state.scenes[4]["progress"] + 30)
#                         save_scenes(st.session_state.scenes); st.balloons()
#             if st.button("Export Verified Data"):
#                 df.to_json(VERIFIED_DATA_FILE, orient='records', indent=2)
#                 st.success(f"Exported {len(df)} records to `{VERIFIED_DATA_FILE}`")
#                 st.code(f"Copy to Google Sheets via script or CSV.")
#         else: st.info("**No verified outcomes yet.** Submit + verify to train AI.")

#     else:
#         left, right = st.columns([2,1])
#         with left:
#             st.markdown(f'<div class="card"><div class="scene-name">{scene["name"]} <span class="caption">{scene["caption"]}</span></div>', unsafe_allow_html=True)
#             st.markdown(f'<div class="dialogue">“{scene["dialogue"]}”</div>', unsafe_allow_html=True)
#             st.markdown(f"**Overview:** {scene['description']}")
#             st.markdown('</div>', unsafe_allow_html=True)
#         with right:
#             st.markdown('<div class="card">', unsafe_allow_html=True)
#             st.metric("Scene", scene["name"])
#             st.progress(scene["progress"]/100)
#             st.write(f"**Status:** {scene['status']}")
#             st.markdown('</div>', unsafe_allow_html=True)

#     # ---------- Reel ----------
#     if st.session_state.get("reel_playing", False):
#         ph = st.empty()
#         for i in range(st.session_state.current_scene, 5):
#             st.session_state.current_scene = i
#             sc = st.session_state.scenes[i]
#             ph.markdown(f"### {sc['name']} — {sc['caption']}")
#             ph.write(sc["dialogue"])
#             time.sleep(1.2)
#             ph.success("Scene complete")
#             time.sleep(0.5)
#         st.session_state.reel_playing = False
#         st.rerun()

# # ---------- Footer ----------
# st.markdown("---")
# with st.expander("Run"):
#     st.code("pip install streamlit yfinance pandas torch scikit-learn numpy\nstreamlit run quantstacks_storyboard_plus_form.py")

##### add voting

# # quantstacks_storyboard_plus_form.py
# # Run: streamlit run quantstacks_storyboard_plus_form.py

# import streamlit as st
# import yfinance as yf
# import pandas as pd
# import json
# import time
# from datetime import datetime, timedelta
# from pathlib import Path
# import torch
# import torch.nn as nn
# import torch.optim as optim  # ← FIXED: Required for Adam optimizer
# from torch.utils.data import DataLoader, TensorDataset
# import numpy as np
# from sklearn.preprocessing import StandardScaler
# from sklearn.model_selection import train_test_split
# import hashlib
# import secrets

# # ---------- Config ----------
# st.set_page_config(page_title="QuantStacks — Disney MVP", layout="wide")

# # ---------- Files ----------
# DATA_FILE = Path("quantstacks_storyboard_data.json")
# SUBMISSIONS_FILE = Path("quantstacks_submissions.json")
# USERS_FILE = Path("quantstacks_users.json")
# REWARDS_FILE = Path("quantstacks_rewards.json")
# MODEL_FILE = Path("quantstacks_model.pth")
# VERIFIED_DATA_FILE = Path("verified_data_for_training.json")
# SCALER_FILE = Path("quantstacks_scaler.json")
# AUTH_FILE = Path("quantstacks_auth.json")

# # ---------- Default Scenes ----------
# DEFAULT_SCENES = [
#     {
#         "id": 0, "name": "Predict", "caption": "Curiosity to Signal",
#         "dialogue": "What if we could capture every trader's intuition and measure truth?",
#         "description": "Users submit structured vertical credit spread predictions.",
#         "tasks": ["Launch live submission form", "Collect 10 real predictions in 48h", "Export JSON to Google Sheets"],
#         "status": "Completed", "progress": 100, "notes": "5+ submissions. Form stable."
#     },
#     {
#         "id": 1, "name": "Verify", "caption": "Skepticism to Confirmation",
#         "dialogue": "Truth must be tested — AI and crowd verify signals.",
#         "description": "Manual + AI verification pipeline evaluates submissions.",
#         "tasks": ["Build verification rubric", "Run 5 predictions through Sheets", "Compare crowd vs. AI scores"],
#         "status": "Completed", "progress": 100, "notes": "Auto-outcome live. 5 verified."
#     },
#     {
#         "id": 2, "name": "Score", "caption": "Signal to Reputation",
#         "dialogue": "Reputation is earned through calibrated accuracy.",
#         "description": "Brier scores, leaderboards, and reputation engine.",
#         "tasks": ["Mock Brier scoring in Python", "Design leaderboard UI", "Test with 20 predictions"],
#         "status": "Completed", "progress": 100, "notes": "Leaderboard live. Decay active."
#     },
#     {
#         "id": 3, "name": "Reward", "caption": "Validation to Incentive",
#         "dialogue": "Skin in the game: rewards align truth.",
#         "description": "Manual payouts to top predictors.",
#         "tasks": ["Announce $10 prize pool", "Pay top 3 via Venmo", "Measure submission spike"],
#         "status": "Completed", "progress": 100, "notes": "3/3 paid. $10 distributed."
#     },
#     {
#         "id": 4, "name": "Evolve", "caption": "Learn to Scale",
#         "dialogue": "Human + AI co-training creates a living intelligence engine.",
#         "description": "Retrain models on verified data.",
#         "tasks": ["Export 50 verified predictions", "Retrain simple ML model", "Improve Brier from 0.42 to 0.38"],
#         "status": "In Progress", "progress": 90, "notes": "Auto-outcome + AI training live. Brier to 0.34"
#     },
# ]

# # ---------- Auth Utilities ----------
# def hash_password(password: str, salt: str = None) -> tuple:
#     if salt is None:
#         salt = secrets.token_hex(16)
#     pwdhash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
#     return pwdhash.hex(), salt

# def verify_password(stored_hash: str, stored_salt: str, password: str) -> bool:
#     pwdhash, _ = hash_password(password, stored_salt)
#     return secrets.compare_digest(pwdhash, stored_hash)

# def load_auth():
#     if AUTH_FILE.exists():
#         try: return json.load(open(AUTH_FILE, "r", encoding="utf-8"))
#         except: return {}
#     return {}

# def save_auth(auth_db):
#     json.dump(auth_db, open(AUTH_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# # ---------- Persistence ----------
# def load_scenes():
#     if DATA_FILE.exists():
#         try: return json.load(open(DATA_FILE, "r", encoding="utf-8"))
#         except: return DEFAULT_SCENES.copy()
#     return DEFAULT_SCENES.copy()

# def save_scenes(scenes):
#     json.dump(scenes, open(DATA_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# def load_submissions():
#     if SUBMISSIONS_FILE.exists():
#         try:
#             subs = json.load(open(SUBMISSIONS_FILE, "r", encoding="utf-8"))
#             for s in subs:
#                 s.setdefault("votes_up", 0)
#                 s.setdefault("votes_down", 0)
#                 s.setdefault("voters", [])
#             return subs
#         except: return []
#     return []

# def save_submissions(subs):
#     json.dump(subs, open(SUBMISSIONS_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# def load_users():
#     if USERS_FILE.exists():
#         try:
#             users = json.load(open(USERS_FILE, "r", encoding="utf-8"))
#             for u in users.values():
#                 u.setdefault("login_streak", 0)
#                 u.setdefault("last_login", None)
#                 u.setdefault("pred_streak", 0)
#                 u.setdefault("last_pred_win", False)
#                 u.setdefault("badges", [])
#             return users
#         except: return {}
#     return {}

# def save_users(users):
#     json.dump(users, open(USERS_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# def load_rewards():
#     if REWARDS_FILE.exists():
#         try: 
#             rewards = json.load(open(REWARDS_FILE, "r", encoding="utf-8"))
#             for r in rewards:
#                 r.setdefault("method", "Venmo")
#                 r.setdefault("status", "Paid")
#                 r.setdefault("rank", 0)
#             return rewards
#         except: return []
#     return []

# def save_rewards(rewards):
#     json.dump(rewards, open(REWARDS_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# # ---------- Auto-Outcome ----------
# def auto_determine_outcome(sub):
#     try:
#         exp_date = datetime.strptime(sub['exp'], '%Y-%m-%d').date()
#         today = datetime.now().date()
#         if today <= exp_date:
#             return None, "Not expired"

#         ticker = yf.Ticker(sub['symbol'])
#         hist = ticker.history(start=exp_date, end=exp_date + timedelta(days=2))
#         if hist.empty:
#             return None, "No price data"

#         close = hist['Close'].iloc[-1]
#         if sub['direction'] == "Bull Put":
#             outcome = 1 if close >= sub['short'] else 0
#         else:
#             outcome = 1 if close <= sub['short'] else 0

#         return outcome, round(close, 2)
#     except Exception as e:
#         return None, f"Error: {str(e)}"

# # ---------- Reputation, Decay, Streaks & Badges ----------
# def update_streaks_and_badges(users, user_id, is_win=None):
#     u = users[user_id]
#     today = datetime.now().date().isoformat()

#     # Login Streak
#     last_login = u.get("last_login")
#     if last_login:
#         last_date = datetime.strptime(last_login, "%Y-%m-%d").date()
#         days_diff = (datetime.now().date() - last_date).days
#         if days_diff == 1:
#             u["login_streak"] += 1
#         elif days_diff > 1:
#             u["login_streak"] = 1
#     else:
#         u["login_streak"] = 1
#     u["last_login"] = today

#     # Prediction Streak
#     if is_win is not None:
#         if is_win and u.get("last_pred_win", False):
#             u["pred_streak"] += 1
#         elif is_win:
#             u["pred_streak"] = 1
#         else:
#             u["pred_streak"] = 0
#         u["last_pred_win"] = is_win

#     # Badges
#     badges = u["badges"]
#     if u["login_streak"] == 3 and "3-Day Login" not in badges:
#         badges.append("3-Day Login")
#     if u["login_streak"] == 7 and "7-Day Login" not in badges:
#         badges.append("7-Day Login")
#     if u["pred_streak"] == 3 and "...." in badges:
#         badges.append("3 Wins in a Row")
#     if u["pred_streak"] == 5 and "5 Wins in a Row" not in badges:
#         badges.append("5 Wins in a Row")
#     if u.get("predictions", 0) >= 10 and "10 Predictions" not in badges:
#         badges.append("10 Predictions")

#     return users

# def update_reputation(users, submission):
#     user_id = submission.get("user_id", "anonymous")
#     brier = submission.get("brier")
#     if brier is None: return users

#     if user_id not in users:
#         users[user_id] = {
#             "reputation": 1000.0,
#             "last_active": datetime.now().isoformat(),
#             "predictions": 0,
#             "avg_brier": 0.0,
#             "fake_balance": 10000.0,
#             "signup_date": datetime.now().isoformat(),
#             "login_streak": 0,
#             "pred_streak": 0,
#             "last_pred_win": False,
#             "badges": []
#         }

#     u = users[user_id]
#     n = u["predictions"]
#     rep_change = 50 * (1 - brier) - 100 * brier

#     # Vote bonus
#     net_votes = submission.get("votes_up", 0) - submission.get("votes_down", 0)
#     rep_change += net_votes * 5

#     u["reputation"] = max(100, u["reputation"] + rep_change)
#     u["avg_brier"] = (u["avg_brier"] * n + brier) / (n + 1)
#     u["predictions"] = n + 1
#     u["last_active"] = datetime.now().isoformat()

#     outcome = submission.get("outcome")
#     if outcome is not None:
#         users = update_streaks_and_badges(users, user_id, bool(outcome))

#     return users

# def apply_decay(users, days=7, rate=0.02):
#     now = datetime.now()
#     for u in users.values():
#         last = datetime.fromisoformat(u["last_active"])
#         inactive = (now - last).days
#         if inactive > 0:
#             decay = (1 - rate) ** (inactive / days)
#             u["reputation"] = max(100, u["reputation"] * decay)
#             u["last_active"] = now.isoformat()
#     return users

# # ---------- AI Model ----------
# class SimpleNN(nn.Module):
#     def __init__(self, input_size=3):
#         super().__init__()
#         self.net = nn.Sequential(
#             nn.Linear(input_size, 16), nn.ReLU(),
#             nn.Linear(16, 8), nn.ReLU(),
#             nn.Linear(8, 1), nn.Sigmoid()
#         )
#     def forward(self, x): return self.net(x)

# def train_model(df, epochs=30):
#     if df.empty or len(df) < 5: return None, None, None, None
#     feature_cols = ['pop', 'confidence', 'credit']
#     X = df[feature_cols].fillna(0).values
#     y = df['outcome'].astype(float).values

#     scaler = StandardScaler()
#     X_scaled = scaler.fit_transform(X)

#     X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
#     train_loader = DataLoader(TensorDataset(torch.tensor(X_train, dtype=torch.float32), torch.tensor(y_train, dtype=torch.float32).unsqueeze(1)), batch_size=8, shuffle=True)

#     model = SimpleNN()
#     criterion = nn.BCELoss()
#     optimizer = optim.Adam(model.parameters(), lr=0.01)
#     model.train()
#     for _ in range(epochs):
#         for xb, yb in train_loader:
#             optimizer.zero_grad()
#             loss = criterion(model(xb), yb)
#             loss.backward()
#             optimizer.step()

#     model.eval()
#     with torch.no_grad():
#         pred = model(torch.tensor(X_test, dtype=torch.float32))
#         loss = criterion(pred, torch.tensor(y_test, dtype=torch.float32).unsqueeze(1)).item()
#         acc = ((pred > 0.5).float() == torch.tensor(y_test).unsqueeze(1)).float().mean().item()

#     torch.save(model.state_dict(), MODEL_FILE)
#     scaler_dict = {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist()}
#     json.dump(scaler_dict, open(SCALER_FILE, "w"))
#     return loss, acc, model, scaler

# def load_model_and_scaler():
#     if not MODEL_FILE.exists() or not SCALER_FILE.exists():
#         return None, None
#     model = SimpleNN()
#     model.load_state_dict(torch.load(MODEL_FILE))
#     model.eval()
#     scaler_data = json.load(open(SCALER_FILE))
#     scaler = StandardScaler()
#     scaler.mean_ = np.array(scaler_data["mean"])
#     scaler.scale_ = np.array(scaler_data["scale"])
#     return model, scaler

# # ---------- Init ----------
# auth_db = load_auth()
# if "authenticated" not in st.session_state:
#     st.session_state.authenticated = False
# if "current_user" not in st.session_state:
#     st.session_state.current_user = None

# if st.session_state.authenticated:
#     subs = load_submissions()
#     users = load_users()
#     rewards = load_rewards()
#     users = apply_decay(users)
#     users = update_streaks_and_badges(users, st.session_state.current_user)
#     save_users(users)
# else:
#     subs = users = rewards = None

# # ---------- MOCK DATA ----------
# if st.session_state.authenticated and subs and len(subs) == 0:
#     mock = [
#         {"id":0,"time":"2025-11-06T10:00:00","user_id":st.session_state.current_user,"symbol":"AAPL","direction":"Bull Put","exp":"2025-11-07","short":195.0,"long":190.0,"credit":1.25,"pop":75,"confidence":8,"rationale":"Strong support","status":"Pending","brier":None,"outcome":None,"expiry_close":None,"days_to_exp":1,"votes_up":0,"votes_down":0,"voters":[]},
#     ]
#     subs.extend(mock)
#     save_submissions(subs)

# # ---------- CSS ----------
# st.markdown("""
# <style>
#     .title { font-family: 'Helvetica Neue', sans-serif; font-size: 28px; font-weight: 600; color: #0b1226; }
#     .subtitle { font-size: 14px; color: #5b6470; margin-bottom: 16px; }
#     .card { background: #fff; border-radius: 14px; padding: 20px; box-shadow: 0 6px 18px rgba(12,15,20,0.06); }
#     .scene-name { font-size: 20px; font-weight: 600; }
#     .caption { color: #6b7280; font-size: 13px; font-style: italic; margin-left: 6px; }
#     .dialogue { font-style: italic; color: #2b2f36; margin: 10px 0; }
#     .payout-card { background: linear-gradient(135deg, #f0fdf4, #dcfce7); border-left: 5px solid #22c55e; padding: 12px; border-radius: 8px; }
#     .paid { background: #f3f4f6; text-decoration: line-through; opacity: 0.7; }
#     .ai-card { background: linear-gradient(135deg, #e0f2fe, #b3e5fc); border-left: 5px solid #0288d1; padding: 12px; border-radius: 8px; }
#     .disclaimer { background: #fef3c7; border-left: 5px solid #f59e0b; padding: 12px; border-radius: 8px; font-size: 13px; margin: 10px 0; }
#     .tos { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px; margin: 15px 0; font-size: 14px; line-height: 1.6; }
#     .payout-history { background: #f8fafc; border-radius: 12px; padding: 16px; margin-top: 16px; }
#     .auth-box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; max-width: 400px; margin: 20px auto; }
#     .balance { font-size: 18px; font-weight: 600; color: #059669; }
#     .badge { background: #fef3c7; color: #92400e; padding: 4px 8px; border-radius: 12px; font-size: 12px; margin: 2px; display: inline-block; }
# </style>
# """, unsafe_allow_html=True)

# # ---------- AUTH FLOW ----------
# if not st.session_state.authenticated:
#     col1, col2, col3 = st.columns([1, 2, 1])
#     with col2:
#         st.markdown("<div class='auth-box'>", unsafe_allow_html=True)
#         auth_mode = st.radio(" ", ["Login", "Sign Up"], horizontal=True)
        
#         with st.form("auth_form"):
#             username = st.text_input("Username", placeholder="trader_x")
#             password = st.text_input("Password", type="password")
#             submit_auth = st.form_submit_button("Submit")

#             if submit_auth:
#                 if auth_mode == "Sign Up":
#                     if username in auth_db:
#                         st.error("Username taken.")
#                     elif len(password) < 6:
#                         st.error("Password must be 6+ chars.")
#                     else:
#                         pwdhash, salt = hash_password(password)
#                         auth_db[username] = {"pwdhash": pwdhash, "salt": salt}
#                         save_auth(auth_db)
#                         users = load_users()
#                         users[username] = {
#                             "reputation": 1000.0,
#                             "last_active": datetime.now().isoformat(),
#                             "predictions": 0,
#                             "avg_brier": 0.0,
#                             "fake_balance": 10000.0,
#                             "signup_date": datetime.now().isoformat(),
#                             "login_streak": 1,
#                             "last_login": datetime.now().date().isoformat(),
#                             "pred_streak": 0,
#                             "last_pred_win": False,
#                             "badges": []
#                         }
#                         save_users(users)
#                         st.success("Account created! $10,000 fake balance added.")
#                         st.session_state.authenticated = True
#                         st.session_state.current_user = username
#                         st.rerun()
#                 else:
#                     if username not in auth_db:
#                         st.error("Invalid username.")
#                     elif not verify_password(auth_db[username]["pwdhash"], auth_db[username]["salt"], password):
#                         st.error("Wrong password.")
#                     else:
#                         st.session_state.authenticated = True
#                         st.session_state.current_user = username
#                         users = load_users()
#                         users = update_streaks_and_badges(users, username)
#                         save_users(users)
#                         st.success(f"Welcome back, {username}!")
#                         st.rerun()
#         st.markdown("</div>", unsafe_allow_html=True)
# else:
#     # ---------- Header ----------
#     col1, col2 = st.columns([3, 1])
#     with col1:
#         st.markdown('<div class="title">QuantStacks — Disney MVP</div>', unsafe_allow_html=True)
#         st.markdown('<div class="subtitle">Form + Verify + Score + Reward + Evolve (Auto-Outcome)</div>', unsafe_allow_html=True)
#     with col2:
#         user_balance = users[st.session_state.current_user].get("fake_balance", 10000.0)
#         st.markdown(f"<div class='balance'>${user_balance:,.2f}</div>", unsafe_allow_html=True)
#         if st.button("Logout"):
#             st.session_state.authenticated = False
#             st.session_state.current_user = None
#             st.rerun()

#     # ---------- Disclaimer ----------
#     st.markdown("""
#     <div class="disclaimer">
#         <strong>Legal Disclaimer:</strong> This is an educational and research prototype.
#         <strong>No real money is wagered.</strong> $10,000 is fake balance for simulation.
#         Predictions are for skill calibration only. Not investment advice.
#         Not gambling — no chance-based outcome. Complies with U.S. and VN laws for skill-based contests.
#     </div>
#     """, unsafe_allow_html=True)
#     st.markdown("---")

#     # ---------- Sidebar ----------
#     with st.sidebar:
#         st.markdown(f"### Trader")
#         st.write(f"**{st.session_state.current_user}**")
#         st.markdown(f"<div class='balance'>${user_balance:,.2f}</div>", unsafe_allow_html=True)
        
#         st.markdown("### Streaks & Badges")
#         u = users[st.session_state.current_user]
#         st.write(f"**Login Streak:** {u['login_streak']} day{'s' if u['login_streak'] != 1 else ''}")
#         st.write(f"**Win Streak:** {u['pred_streak']} win{'s' if u['pred_streak'] != 1 else ''}")
#         if u['badges']:
#             st.markdown(" ".join([f"<span class='badge'>{b}</span>" for b in u['badges']]), unsafe_allow_html=True)
#         else:
#             st.caption("No badges yet")

#         st.markdown("### Scenes")
#         if "scenes" not in st.session_state:
#             st.session_state.scenes = load_scenes()
#         for s in st.session_state.scenes:
#             if st.button(f"{s['id']+1}. {s['name']} — {s['status']}", key=f"nav_{s['id']}"):
#                 st.session_state.current_scene = s["id"]
#                 st.session_state.show_form = (s["id"] == 0)
        
#         st.markdown("---")
#         st.markdown("### Legal")
#         if st.button("Terms of Service"):
#             st.session_state.current_scene = -1
#         st.markdown("---")
#         c1, c2 = st.columns(2)
#         if c1.button("Play"): st.session_state.reel_playing = True
#         if c2.button("Stop"): st.session_state.reel_playing = False

#     # ---------- Main ----------
#     if "current_scene" not in st.session_state:
#         st.session_state.current_scene = 0
#     if "show_form" not in st.session_state:
#         st.session_state.show_form = False
#     if "scenes" not in st.session_state:
#         st.session_state.scenes = load_scenes()

#     scene = st.session_state.scenes[st.session_state.current_scene] if st.session_state.current_scene >= 0 else None

#     # === TERMS OF SERVICE PAGE ===
#     if st.session_state.current_scene == -1:
#         st.markdown("## Terms of Service")
#         st.markdown("""
#         <div class="tos">
#             <p><strong>Last updated:</strong> November 07, 2025</p>
#             <h3>1. Acceptance of Terms</h3>
#             <p>By accessing or using QuantStacks, you agree to be bound by these Terms.</p>
#             <h3>2. Fake Balance</h3>
#             <p>Each user starts with <strong>$10,000 fake balance</strong> for simulation. No real money.</p>
#             <h3>3. Authentication</h3>
#             <p>Passwords are hashed using PBKDF2-HMAC-SHA256 with unique salts. Industry standard.</p>
#             <h3>4. No Investment Advice</h3>
#             <p>All predictions are hypothetical. For skill calibration only.</p>
#             <h3>5. Compliance</h3>
#             <p>Skill-based contest. Complies with U.S. and Vietnam laws.</p>
#         </div>
#         """, unsafe_allow_html=True)
#         if st.button("Back to App"):
#             st.session_state.current_scene = 0
#             st.rerun()

#     # === PREDICT SCENE ===
#     elif st.session_state.show_form and scene["id"] == 0:
#         st.markdown("### Submit Prediction")
#         st.info("**Simulated Cost:** $100 fake balance per prediction")

#         model, scaler = load_model_and_scaler() if MODEL_FILE.exists() else (None, None)

#         with st.form("credit_spread_form", clear_on_submit=True):
#             col1, col2 = st.columns(2)
#             with col1: symbol = st.text_input("Symbol", "AAPL", key="symbol_input")
#             with col2: direction = st.radio("Direction", ["Bull Put", "Bear Call"], horizontal=True, key="direction_input")

#             load_chain = st.form_submit_button("Load Option Chain")
#             if load_chain:
#                 with st.spinner("Fetching..."):
#                     try:
#                         ticker = yf.Ticker(symbol.upper())
#                         exps = ticker.options
#                         if exps:
#                             st.session_state.exps = exps
#                             st.session_state.ticker = ticker
#                             st.success(f"Loaded {len(exps)} expirations")
#                         else:
#                             st.error("No options.")
#                     except: st.error("Invalid symbol.")

#             if 'exps' in st.session_state:
#                 exp = st.selectbox("Expiration", st.session_state.exps, key="exp_select")
#                 load_strikes = st.form_submit_button("Load Strikes")
#                 if load_strikes:
#                     with st.spinner():
#                         opt = st.session_state.ticker.option_chain(exp)
#                         common = sorted(set(opt.calls['strike']) & set(opt.puts['strike']))
#                         if len(common) >= 2:
#                             st.session_state.strikes = common
#                             st.session_state.opt = opt
#                             st.success(f"Loaded {len(common)} strikes")
#                         else:
#                             st.error("Not enough strikes.")

#             if 'strikes' in st.session_state and len(st.session_state.strikes) > 1:
#                 col3, col4 = st.columns(2)
#                 with col3:
#                     short_idx = st.selectbox("Short", range(len(st.session_state.strikes)), format_func=lambda i: f"${st.session_state.strikes[i]:.2f}", key="short_select")
#                     short = st.session_state.strikes[short_idx]
#                 with col4:
#                     long_idx = st.selectbox("Long", range(len(st.session_state.strikes)), format_func=lambda i: f"${st.session_state.strikes[i]:.2f}", index=max(0, short_idx-3), key="long_select")
#                     long = st.session_state.strikes[long_idx]

#                 opt = st.session_state.opt
#                 try:
#                     if direction == "Bull Put":
#                         short_p = opt.puts[opt.puts['strike']==short]['lastPrice'].iloc[0]
#                         long_p = opt.puts[opt.puts['strike']==long]['lastPrice'].iloc[0]
#                     else:
#                         short_p = opt.calls[opt.calls['strike']==short]['lastPrice'].iloc[0]
#                         long_p = opt.calls[opt.calls['strike']==long]['lastPrice'].iloc[0]
#                     credit = round(short_p - long_p, 2)
#                     st.info(f"**Net Credit:** ${credit:.2f}")
#                 except:
#                     credit = 0.0

#                 col5, col6 = st.columns(2)
#                 with col5: pop = st.slider("POP (%)", 50, 90, 70, key="pop_slider")
#                 with col6: conf = st.slider("Confidence", 1, 10, 7, key="conf_slider")
#                 rationale = st.text_area("Rationale", height=80, key="rationale_input")

#                 if model and scaler:
#                     try:
#                         X = np.array([[pop/100, conf/10, credit]])
#                         X_scaled = (X - scaler.mean_) / scaler.scale_
#                         with torch.no_grad():
#                             ai_prob = model(torch.tensor(X_scaled, dtype=torch.float32)).item()
#                         st.markdown(f"<div class='ai-card'>**AI Confidence:** {ai_prob*100:.1f}%</div>", unsafe_allow_html=True)
#                     except: pass

#                 submit = st.form_submit_button("Submit Prediction", type="primary")

#                 if submit:
#                     if users[st.session_state.current_user]["fake_balance"] < 100:
#                         st.error("Insufficient fake balance!")
#                     elif 'strikes' not in st.session_state:
#                         st.error("Load chain and select strikes.")
#                     else:
#                         users[st.session_state.current_user]["fake_balance"] -= 100
#                         save_users(users)
#                         days_to_exp = (datetime.strptime(exp, '%Y-%m-%d') - datetime.now()).days
#                         sub = {
#                             "id": len(subs), "time": datetime.now().isoformat(), "user_id": st.session_state.current_user,
#                             "symbol": symbol.upper(), "direction": direction, "exp": exp,
#                             "short": float(short), "long": float(long), "credit": credit,
#                             "pop": pop, "confidence": conf, "rationale": rationale,
#                             "status": "Pending", "brier": None, "outcome": None, "expiry_close": None,
#                             "days_to_exp": days_to_exp, "votes_up": 0, "votes_down": 0, "voters": []
#                         }
#                         subs.append(sub)
#                         save_submissions(subs)
#                         st.success("Submitted! -$100")
#                         st.balloons()
#                         st.session_state.scenes[0]["progress"] = min(100, st.session_state.scenes[0]["progress"] + 10)
#                         save_scenes(st.session_state.scenes)
#                         for k in ['exps','strikes','opt','ticker']: st.session_state.pop(k, None)
#                         st.rerun()

#     # === VERIFY SCENE WITH PEER VOTING ===
#     elif scene["id"] == 1:
#         st.markdown("### Verification Dashboard")
#         df = pd.DataFrame(subs)
#         df['time'] = pd.to_datetime(df['time']).dt.strftime('%m-%d %H:%M')
#         pending = df[df['status'] == 'Pending']
#         verified = df[df['status'] == 'Verified']
#         col1, col2 = st.columns(2)
#         with col1: st.metric("Pending", len(pending))
#         with col2: st.metric("Verified", len(verified))

#         if not pending.empty:
#             st.markdown("#### Pending Predictions")
#             for _, row in pending.iterrows():
#                 with st.expander(f"ID {row['id']} — {row['symbol']} — {row['user_id']}"):
#                     st.write(f"**Short:** ${row['short']} | **Long:** ${row['long']} | **Credit:** ${row['credit']}")
#                     st.write(f"**POP:** {row['pop']}% | **Confidence:** {row['confidence']}/10")
#                     st.write(f"**Rationale:** {row['rationale']}")
                    
#                     # Peer Voting
#                     colv1, colv2, colv3 = st.columns([1,1,3])
#                     with colv1:
#                         if st.session_state.current_user in row['voters']:
#                             st.write("Voted")
#                         else:
#                             if st.button("Upvote", key=f"up_{row['id']}"):
#                                 idx = int(row['id'])
#                                 subs[idx]['votes_up'] += 1
#                                 subs[idx]['voters'].append(st.session_state.current_user)
#                                 save_submissions(subs)
#                                 st.rerun()
#                     with colv2:
#                         if st.session_state.current_user in row['voters']:
#                             pass
#                         else:
#                             if st.button("Downvote", key=f"down_{row['id']}"):
#                                 idx = int(row['id'])
#                                 subs[idx]['votes_down'] += 1
#                                 subs[idx]['voters'].append(st.session_state.current_user)
#                                 save_submissions(subs)
#                                 st.rerun()
#                     with colv3:
#                         net = row['votes_up'] - row['votes_down']
#                         st.write(f"**Net Votes:** {net}")

#                     outcome, info = auto_determine_outcome(row.to_dict())
#                     if outcome is not None:
#                         st.success(f"Auto-Outcome: {'Success' if outcome else 'Failure'} | Close: ${info}")
#                         if st.button("Apply Auto-Outcome", key=f"auto_{row['id']}"):
#                             p = row['pop'] / 100
#                             o = outcome
#                             brier = (p - o) ** 2
#                             idx = int(row['id'])
#                             subs[idx].update({"status": "Verified", "brier": round(brier, 4), "outcome": outcome, "expiry_close": info})
#                             save_submissions(subs)
#                             users = update_reputation(users, subs[idx])
#                             save_users(users)
#                             st.success(f"Verified! Brier: {brier:.4f}")
#                             st.session_state.scenes[1]["progress"] = min(100, st.session_state.scenes[1]["progress"] + 15)
#                             save_scenes(st.session_state.scenes)
#                             st.rerun()
#                     else:
#                         st.info(f"Status: {info}")

#                     col_a, col_b = st.columns(2)
#                     with col_a: actual_pop = st.slider("Actual POP (%)", 0, 100, row['pop'], key=f"act_{row['id']}")
#                     with col_b:
#                         if st.button("Manual Verify", key=f"ver_{row['id']}"):
#                             p = row['pop'] / 100
#                             o = 1 if actual_pop >= row['pop'] else 0
#                             brier = (p - o) ** 2
#                             idx = int(row['id'])
#                             subs[idx].update({"status": "Verified", "brier": round(brier, 4), "outcome": o})
#                             save_submissions(subs)
#                             users = update_reputation(users, subs[idx])
#                             save_users(users)
#                             st.success(f"Verified! Brier: {brier:.4f}")
#                             st.session_state.scenes[1]["progress"] = min(100, st.session_state.scenes[1]["progress"] + 15)
#                             save_scenes(st.session_state.scenes)
#                             st.rerun()

#     # === LEADERBOARD SCENE ===
#     elif scene["id"] == 2:
#         st.markdown("### Leaderboard")
#         if not users: st.info("No users.")
#         else:
#             lb = [{"User":uid, "Reputation":f"{u['reputation']:.1f}", "Predictions":u['predictions'], "Avg Brier":f"{u['avg_brier']:.4f}", "Last":pd.to_datetime(u['last_active']).strftime('%m-%d')} for uid,u in users.items()]
#             lb_df = pd.DataFrame(lb).sort_values("Reputation", ascending=False).reset_index(drop=True)
#             lb_df.index += 1
#             st.dataframe(lb_df.style.apply(lambda r: ['background: #fef3c7; font-weight: bold;']*len(r) if r.name==1 else ['']*len(r), axis=1))

#     # === REWARD SCENE ===
#     elif scene["id"] == 3:
#         st.markdown("### Reward Payout Center")
#         st.markdown("**$10 Prize Pool — Top 3 Reputation**")
#         if not users: st.info("No users.")
#         else:
#             ranked = sorted(users.items(), key=lambda x: x[1]['reputation'], reverse=True)[:3]
#             paid = {r['user_id'] for r in rewards}
#             col1,col2,col3 = st.columns(3)
#             prizes = [5.0, 3.0, 2.0]
#             for i,(uid,u) in enumerate(ranked):
#                 with [col1,col2,col3][i]:
#                     paid_cls = "payout-card paid" if uid in paid else "payout-card"
#                     st.markdown(f"<div class='{paid_cls}'>", unsafe_allow_html=True)
#                     st.markdown(f"**#{i+1} — {uid}**")
#                     st.metric("Reputation", f"{u['reputation']:.1f}")
#                     st.write(f"**Prize:** ${prizes[i]:.2f}")
#                     if uid in paid: st.caption("Paid")
#                     else:
#                         if st.button("Pay Now", key=f"pay_{uid}"):
#                             rewards.append({
#                                 "user_id": uid, "amount": prizes[i], "date": datetime.now().isoformat(),
#                                 "rank": i+1, "method": "Venmo", "status": "Paid"
#                             })
#                             save_rewards(rewards)
#                             st.success(f"Paid ${prizes[i]:.2f} to {uid}")
#                             st.balloons()
#                             st.session_state.scenes[3]["progress"] = min(100, st.session_state.scenes[3]["progress"] + 20)
#                             save_scenes(st.session_state.scenes)
#                             st.rerun()
#                     st.markdown("</div>", unsafe_allow_html=True)

#             st.markdown("#### Payout History")
#             if rewards:
#                 hist = pd.DataFrame(rewards)
#                 hist['date'] = pd.to_datetime(hist['date']).dt.strftime('%m-%d %H:%M')
#                 st.markdown("<div class='payout-history'>", unsafe_allow_html=True)
#                 st.dataframe(hist[['user_id','rank','amount','method','status','date']].style.format({"amount": "${:.2f}"}))
#                 st.markdown("</div>", unsafe_allow_html=True)
#             else:
#                 st.info("No payouts yet.")

#     # === EVOLVE SCENE — FULLY FIXED ===
#     elif scene["id"] == 4:
#         st.markdown("### Evolve — Human + AI Co-Training")

#         # ---- FILTER VERIFIED + OUTCOME ----
#         verified = [
#             s for s in subs
#             if s.get("status") == "Verified" and s.get("outcome") is not None
#         ]
#         df = pd.DataFrame(verified)

#         st.markdown(f"**Verified Data Ready:** {len(df)} prediction{'s' if len(df) != 1 else ''}")

#         if not df.empty:
#             st.markdown("#### Training Preview")
#             preview_cols = ["user_id", "symbol", "direction", "exp", "short", "long",
#                             "credit", "pop", "confidence", "brier", "outcome", "expiry_close"]
#             safe_cols = [c for c in preview_cols if c in df.columns]
#             st.dataframe(df[safe_cols].head(10))

#             if len(df) >= 5:
#                 if st.button("Start Co-Training", type="primary"):
#                     with st.spinner("Training neural net…"):
#                         loss, acc, _, _ = train_model(df)
#                         if loss is not None:
#                             st.success("**AI Trained!**")
#                             col1, col2 = st.columns(2)
#                             with col1: st.metric("Test Loss", f"{loss:.4f}")
#                             with col2: st.metric("Accuracy", f"{acc*100:.1f}%")
#                             st.session_state.scenes[4]["progress"] = min(100, st.session_state.scenes[4]["progress"] + 30)
#                             save_scenes(st.session_state.scenes)
#                             st.balloons()
#                         else:
#                             st.error("Training failed – check data.")
#             else:
#                 st.info("**Need at least 5 verified outcomes** to train the model.")

#             if st.button("Export Verified Data"):
#                 export_path = VERIFIED_DATA_FILE
#                 df.to_json(export_path, orient="records", indent=2)
#                 st.success(f"Exported {len(df)} rows → `{export_path.name}`")
#         else:
#             st.info("**No verified outcomes yet.** Submit & verify predictions first.")

#     # === DEFAULT SCENE DISPLAY ===
#     else:
#         left, right = st.columns([2,1])
#         with left:
#             st.markdown(f'<div class="card"><div class="scene-name">{scene["name"]} <span class="caption">{scene["caption"]}</span></div>', unsafe_allow_html=True)
#             st.markdown(f'<div class="dialogue">"{scene["dialogue"]}"</div>', unsafe_allow_html=True)
#             st.markdown(f"**Overview:** {scene['description']}")
#             st.markdown('</div>', unsafe_allow_html=True)
#         with right:
#             st.markdown('<div class="card">', unsafe_allow_html=True)
#             st.metric("Scene", scene["name"])
#             st.progress(scene["progress"]/100)
#             st.write(f"**Status:** {scene['status']}")
#             st.markdown('</div>', unsafe_allow_html=True)

#     # ---------- Reel ----------
#     if st.session_state.get("reel_playing", False):
#         ph = st.empty()
#         for i in range(st.session_state.current_scene, 5):
#             st.session_state.current_scene = i
#             sc = st.session_state.scenes[i]
#             ph.markdown(f"### {sc['name']} — {sc['caption']}")
#             ph.write(sc["dialogue"])
#             time.sleep(1.2)
#             ph.success("Scene complete")
#             time.sleep(0.5)
#         st.session_state.reel_playing = False
#         st.rerun()

##### good layout

# # quantstacks_storyboard_plus_form.py
# # JONY IVE DESIGN + st.tabs() + FULL FEATURES + X SHARE
# # Run: streamlit run quantstacks_storyboard_plus_form.py

# import streamlit as st
# import yfinance as yf
# import pandas as pd
# import json
# import time
# from datetime import datetime, timedelta
# from pathlib import Path
# import torch
# import torch.nn as nn
# import torch.optim as optim
# from torch.utils.data import DataLoader, TensorDataset
# import numpy as np
# from sklearn.preprocessing import StandardScaler
# from sklearn.model_selection import train_test_split
# import hashlib
# import secrets
# import random
# import uuid
# import re

# # ==============================
# # JONY IVE DESIGN SYSTEM
# # ==============================
# st.set_page_config(page_title="QuantStacks", layout="centered", initial_sidebar_state="collapsed")

# st.markdown("""
# <style>
#     .stApp {
#         background: linear-gradient(to bottom, #fafafa, #f5f5f5);
#         font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif;
#     }
#     .css-1d391kg { padding: 2rem 1rem; }
    
#     .title {
#         font-size: 36px;
#         font-weight: 600;
#         letter-spacing: -0.5px;
#         color: #1d1d1f;
#         margin: 0 0 8px 0;
#         text-align: center;
#     }
#     .subtitle {
#         font-size: 17px;
#         color: #6e6e73;
#         text-align: center;
#         margin-bottom: 32px;
#         font-weight: 400;
#     }
    
#     .card {
#         background: white;
#         border-radius: 18px;
#         padding: 24px;
#         box-shadow: 0 4px 12px rgba(0,0,0,0.05);
#         margin-bottom: 20px;
#         transition: all 0.2s ease;
#     }
#     .card:hover {
#         box-shadow: 0 8px 24px rgba(0,0,0,0.08);
#     }
    
#     .stButton > button {
#         background: #0071e3;
#         color: white;
#         border: none;
#         border-radius: 12px;
#         padding: 10px 20px;
#         font-weight: 500;
#         font-size: 16px;
#         height: 44px;
#         width: 100%;
#         transition: all 0.2s ease;
#     }
#     .stButton > button:hover {
#         background: #0061c3;
#         transform: translateY(-1px);
#     }
#     .stButton > button:active {
#         transform: translateY(0);
#     }
    
#     .stTextInput > div > div > input,
#     .stSelectbox > div > div > select,
#     .stSlider > div > div > div > div {
#         border-radius: 12px;
#         border: 1px solid #d2d2d7;
#         padding: 12px;
#         font-size: 17px;
#     }
    
#     .metric-card {
#         background: white;
#         border-radius: 16px;
#         padding: 16px;
#         text-align: center;
#         box-shadow: 0 2px 8px rgba(0,0,0,0.05);
#     }
#     .metric-label {
#         font-size: 13px;
#         color: #6e6e73;
#         margin-bottom: 4px;
#     }
#     .metric-value {
#         font-size: 24px;
#         font-weight: 600;
#         color: #1d1d1f;
#     }
    
#     .challenge-card {
#         background: linear-gradient(135deg, #fffbe6, #fff4c2);
#         border: 1px solid #ffd60a;
#         border-radius: 18px;
#         padding: 20px;
#         text-align: center;
#         margin-bottom: 24px;
#     }
    
#     .bot-card {
#         background: linear-gradient(135deg, #f0f9ff, #e0f2fe);
#         border: 1px solid #0ea5e9;
#         border-radius: 16px;
#         padding: 16px;
#         text-align: center;
#         font-size: 15px;
#     }
    
#     .share-btn {
#         background: #30d158;
#         color: white;
#         text-align: center;
#         padding: 12px;
#         border-radius: 12px;
#         font-weight: 500;
#         cursor: pointer;
#         margin-top: 16px;
#     }
    
#     .warning-card {
#         background: #fff4c2;
#         border: 1px solid #f59e0b;
#         border-radius: 16px;
#         padding: 16px;
#         font-size: 14px;
#     }
#     .ban-card {
#         background: #fee2e2;
#         border: 1px solid #ef4444;
#         border-radius: 16px;
#         padding: 16px;
#         font-size: 15px;
#         text-align: center;
#     }
    
#     .footer {
#         text-align: center;
#         color: #8e8e93;
#         font-size: 13px;
#         margin-top: 48px;
#         padding: 20px 0;
#     }

#     /* Tabs */
#     .stTabs [data-baseweb="tab-list"] {
#         gap: 24px;
#         justify-content: center;
#         padding: 0 16px;
#         border-bottom: 1px solid #d2d2d7;
#     }
#     .stTabs [data-baseweb="tab"] {
#         height: 50px;
#         padding: 0 24px;
#         font-size: 17px;
#         font-weight: 500;
#         color: #6e6e73;
#         border-bottom: 2px solid transparent;
#     }
#     .stTabs [data-baseweb="tab"][aria-selected="true"] {
#         color: #0071e3;
#         border-bottom: 2.0px solid #0071e3;
#     }
# </style>
# """, unsafe_allow_html=True)

# # ==============================
# # CONFIG & PATHS
# # ==============================
# DATA_FILE = Path("quantstacks_storyboard_data.json")
# SUBMISSIONS_FILE = Path("quantstacks_submissions.json")
# USERS_FILE = Path("quantstacks_users.json")
# REWARDS_FILE = Path("quantstacks_rewards.json")
# MODEL_FILE = Path("quantstacks_model.pth")
# AUTH_FILE = Path("quantstacks_auth.json")
# DAILY_FILE = Path("daily_challenge.json")
# STRIKES_FILE = Path("strikes.json")

# CHALLENGE_SYMBOL = "SPY"
# PRIZES = [5.0, 3.0, 2.0]
# MAX_PREDICTIONS_PER_DAY = 1
# STRIKE_THRESHOLD = 3
# BAN_DURATION_DAYS = 7

# # ==============================
# # PERSISTENCE
# # ==============================
# def load_auth(): return json.load(open(AUTH_FILE, "r")) if AUTH_FILE.exists() else {}
# def save_auth(db): json.dump(db, open(AUTH_FILE, "w"), indent=2)
# def load_users(): return json.load(open(USERS_FILE, "r")) if USERS_FILE.exists() else {}
# def save_users(u): json.dump(u, open(USERS_FILE, "w"), indent=2)
# def load_submissions(): return json.load(open(SUBMISSIONS_FILE, "r")) if SUBMISSIONS_FILE.exists() else []
# def save_submissions(s): json.dump(s, open(SUBMISSIONS_FILE, "w"), indent=2)
# def load_rewards(): 
#     r = json.load(open(REWARDS_FILE, "r")) if REWARDS_FILE.exists() else []
#     for x in r: x.setdefault("method", "Venmo"); x.setdefault("status", "Paid")
#     return r
# def save_rewards(r): json.dump(r, open(REWARDS_FILE, "w"), indent=2)
# def load_strikes(): return json.load(open(STRIKES_FILE, "r")) if STRIKES_FILE.exists() else {}
# def save_strikes(s): json.dump(s, open(STRIKES_FILE, "w"), indent=2)

# # ==============================
# # AUTO OUTCOME
# # ==============================
# def auto_determine_outcome(sub):
#     try:
#         exp_date = datetime.strptime(sub['exp'], '%Y-%m-%d').date()
#         today = datetime.now().date()
#         if today <= exp_date:
#             return None, "Not expired"
#         ticker = yf.Ticker(sub['symbol'])
#         hist = ticker.history(start=exp_date, end=exp_date + timedelta(days=1))
#         if hist.empty:
#             return None, "No price data"
#         close = hist['Close'].iloc[0]
#         success = (close >= sub['short']) if sub['direction'] == "Bull Put" else (close <= sub['short'])
#         return int(success), round(close, 2)
#     except Exception as e:
#         return None, f"Error: {str(e)}"

# # ==============================
# # REPUTATION
# # ==============================
# def update_reputation(users, sub):
#     uid = sub["user_id"]
#     brier = sub.get("brier")
#     if brier is None or uid not in users:
#         return users
#     u = users[uid]
#     rep_change = 50 * (1 - brier) - 100 * brier
#     u["reputation"] = max(100, u["reputation"] + rep_change)
#     n = u["predictions"]
#     u["avg_brier"] = (u["avg_brier"] * n + brier) / (n + 1)
#     u["predictions"] = n + 1
#     u["last_active"] = datetime.now().isoformat()
#     u["streak"] = u.get("streak", 0) + 1
#     return users

# # ==============================
# # AI BOT
# # ==============================
# class QuantBot(nn.Module):
#     def __init__(self):
#         super().__init__()
#         self.net = nn.Sequential(
#             nn.Linear(4, 16), nn.ReLU(),
#             nn.Linear(16, 8), nn.ReLU(),
#             nn.Linear(8, 1), nn.Sigmoid()
#         )
#     def forward(self, x): return self.net(x)

# def train_bot(df):
#     if df.empty or len(df) < 10:
#         return None, None
#     X = df[['pop', 'confidence', 'credit', 'brier']].fillna(0).values
#     y = df['outcome'].astype(float).values
#     scaler = StandardScaler()
#     X_scaled = scaler.fit_transform(X)
#     X_train, _, y_train, _ = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
#     loader = DataLoader(TensorDataset(torch.tensor(X_train, dtype=torch.float32), torch.tensor(y_train, dtype=torch.float32).unsqueeze(1)), batch_size=8, shuffle=True)
#     model = QuantBot()
#     crit = nn.BCELoss()
#     opt = optim.Adam(model.parameters(), lr=0.01)
#     model.train()
#     for _ in range(20):
#         for xb, yb in loader:
#             opt.zero_grad()
#             loss = crit(model(xb), yb)
#             loss.backward()
#             opt.step()
#     torch.save(model.state_dict(), MODEL_FILE)
#     return model, scaler

# # ==============================
# # AUTH
# # ==============================
# def hash_password(pw, salt=None):
#     salt = salt or secrets.token_hex(16)
#     h = hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), 100000).hex()
#     return h, salt

# def verify_password(h, s, pw):
#     nh, _ = hash_password(pw, s)
#     return secrets.compare_digest(nh, h)

# # ==============================
# # INIT
# # ==============================
# auth_db = load_auth()
# if "auth" not in st.session_state: st.session_state.auth = False
# if "user" not in st.session_state: st.session_state.user = None
# if "email_verified" not in st.session_state: st.session_state.email_verified = False

# if st.session_state.auth:
#     subs = load_submissions()
#     users = load_users()
#     rewards = load_rewards()
#     daily = json.load(open(DAILY_FILE, "r")) if DAILY_FILE.exists() and json.load(open(DAILY_FILE, "r"))["date"] == datetime.now().strftime("%Y-%m-%d") else {
#         "date": datetime.now().strftime("%Y-%m-%d"), "symbol": CHALLENGE_SYMBOL, "exp": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"), "entries": [], "payouts_done": False
#     }
#     json.dump(daily, open(DAILY_FILE, "w"), indent=2)
    
#     # Carregar AI
#     verified = [s for s in subs if s.get("status") == "Verified" and s.get("outcome") is not None]
#     bot_model, bot_scaler = None, None
#     if verified:
#         df = pd.DataFrame(verified)
#         bot_model, bot_scaler = train_bot(df)
# else:
#     subs = users = rewards = daily = bot_model = bot_scaler = None

# # ==============================
# # MOCK DATA
# # ==============================
# if st.session_state.auth and len(subs) == 0:
#     mock = [{
#         "id": 0, "time": "2025-11-06T10:00:00", "user_id": st.session_state.user,
#         "symbol": "AAPL", "direction": "Bull Put", "exp": "2025-11-07",
#         "short": 195.0, "long": 190.0, "credit": 1.25, "pop": 75,
#         "confidence": 8, "rationale": "Strong support", "status": "Pending"
#     }]
#     subs.extend(mock)
#     save_submissions(subs)

# # ==============================
# # JONY IVE UI: AUTH CON TABS
# # ==============================
# if not st.session_state.auth:
#     st.markdown('<div class="title">QuantStacks</div>', unsafe_allow_html=True)
#     st.markdown('<div class="subtitle">Predict. Verify. Win. $10 daily.</div>', unsafe_allow_html=True)
    
#     tab1, tab2 = st.tabs(["Sign Up", "Login"])
    
#     with tab1:
#         st.markdown("<div class='card'>", unsafe_allow_html=True)
#         with st.form("signup_form", clear_on_submit=True):
#             username = st.text_input("Username", placeholder="trader_x")
#             password = st.text_input("Password", type="password")
#             email = st.text_input("Email", placeholder="you@example.com")
#             submit = st.form_submit_button("Create $10K Account")
#             if submit:
#                 if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
#                     st.error("Valid email required.")
#                 elif username in auth_db:
#                     st.error("Taken")
#                 else:
#                     h, s = hash_password(password)
#                     auth_db[username] = {"pwdhash": h, "salt": s, "email": email}
#                     save_auth(auth_db)
#                     users = load_users()
#                     users[username] = {
#                         "reputation": 1000.0, "last_active": datetime.now().isoformat(),
#                         "predictions": 0, "avg_brier": 0.0, "fake_balance": 10000.0,
#                         "streak": 0, "email_verified": False
#                     }
#                     save_users(users)
#                     code = random.randint(100000, 999999)
#                     st.session_state.verification_code = code
#                     st.session_state.pending_user = username
#                     st.success(f"Código: {code}")
#                     st.rerun()
#         st.markdown("</div>", unsafe_allow_html=True)
    
#     with tab2:
#         st.markdown("<div class='card'>", unsafe_allow_html=True)
#         with st.form("login_form", clear_on_submit=True):
#             username = st.text_input("Username", key="login_un")
#             password = st.text_input("Password", type="password", key="login_pw")
#             submit = st.form_submit_button("Login")
#             if submit:
#                 if username not in auth_db or not verify_password(auth_db[username]["pwdhash"], auth_db[username]["salt"], password):
#                     st.error("Invalid")
#                 else:
#                     st.session_state.auth = True
#                     st.session_state.user = username
#                     st.rerun()
#         st.markdown("</div>", unsafe_allow_html=True)
    
#     if "pending_user" in st.session_state:
#         st.markdown("<div class='card'>", unsafe_allow_html=True)
#         with st.form("verify_form"):
#             code = st.text_input("6-digit code")
#             if st.form_submit_button("Verify"):
#                 if str(st.session_state.verification_code) == code:
#                     users = load_users()
#                     users[st.session_state.pending_user]["email_verified"] = True
#                     save_users(users)
#                     st.session_state.auth = True
#                     st.session_state.user = st.session_state.pending_user
#                     del st.session_state.pending_user
#                     del st.session_state.verification_code
#                     st.rerun()
#                 else:
#                     st.error("Wrong")
#         st.markdown("</div>", unsafe_allow_html=True)

# else:
#     # ==============================
#     # JONY IVE UI: MAIN APP CON SCENE TABS
#     # ==============================
#     st.markdown('<div class="title">QuantStacks</div>', unsafe_allow_html=True)
#     st.markdown('<div class="subtitle">Truth wins. Skill scales.</div>', unsafe_allow_html=True)
    
#     # Balance
#     bal = users[st.session_state.user]["fake_balance"]
#     col1, col2, col3 = st.columns(3)
#     with col2:
#         st.markdown(f"""
#         <div class="metric-card">
#             <div class="metric-label">Fake Balance</div>
#             <div class="metric-value">${bal:,.0f}</div>
#         </div>
#         """, unsafe_allow_html=True)
    
#     # Ban Check
#     if users[st.session_state.user].get("banned_until"):
#         ban_until = users[st.session_state.user]["banned_until"].split("T")[0]
#         st.markdown(f'<div class="ban-card">Banned until {ban_until}</div>', unsafe_allow_html=True)
#         st.stop()
    
#     # Scene Tabs
#     tab_predict, tab_verify, tab_score, tab_reward, tab_evolve = st.tabs([
#         "Predict", "Verify", "Score", "Reward", "Evolve"
#     ])
    
#     # === PREDICT ===
#     with tab_predict:
#         st.markdown("<div class='challenge-card'>", unsafe_allow_html=True)
#         st.markdown(f"### Daily Challenge — {CHALLENGE_SYMBOL}")
#         st.markdown("Expires tomorrow. Top 3 win $10.")
#         st.markdown("</div>", unsafe_allow_html=True)
        
#         today = datetime.now().strftime("%Y-%m-%d")
#         user_preds = [s for s in subs if s["user_id"] == st.session_state.user and s["time"].startswith(today)]
#         if len(user_preds) >= MAX_PREDICTIONS_PER_DAY:
#             st.markdown('<div class="warning-card">Predicted today.</div>', unsafe_allow_html=True)
#         else:
#             if bot_model and bot_scaler:
#                 bot_pop = random.randint(60, 80)
#                 st.markdown(f'<div class="bot-card">QuantBot predicts {bot_pop}% POP</div>', unsafe_allow_html=True)
            
#             with st.form("predict_form"):
#                 direction = st.radio("Direction", ["Bull Put", "Bear Call"], horizontal=True)
#                 pop = st.slider("POP (%)", 50, 90, 70)
#                 conf = st.slider("Confidence", 1, 10, 7)
#                 rationale = st.text_area("Rationale", height=80)
#                 submit = st.form_submit_button("Predict (-$100)")
#                 if submit:
#                     if bal < 100:
#                         st.error("Need $100")
#                     else:
#                         users[st.session_state.user]["fake_balance"] -= 100
#                         save_users(users)
#                         entry = {
#                             "entry_id": str(uuid.uuid4()),
#                             "user_id": st.session_state.user,
#                             "direction": direction,
#                             "pop": pop,
#                             "confidence": conf,
#                             "rationale": rationale,
#                             "time": datetime.now().isoformat(),
#                             "symbol": CHALLENGE_SYMBOL,
#                             "exp": daily["exp"],
#                             "status": "Pending"
#                         }
#                         daily["entries"].append(entry)
#                         json.dump(daily, open(DAILY_FILE, "w"), indent=2)
#                         st.success("Predicted!")
#                         st.balloons()
        
#         if st.button("Share My Edge"):
#             st.markdown('<div class="share-btn">I predicted SPY @ QuantStacks — beat me!</div>', unsafe_allow_html=True)
    
#     # === VERIFY ===
#     with tab_verify:
#         st.markdown("### Verify Outcomes")
#         pending = [s for s in subs if s["status"] == "Pending"]
#         if not pending:
#             st.info("No pending predictions.")
#         for s in pending:
#             with st.expander(f"{s['symbol']} — {s['user_id']}"):
#                 o, c = auto_determine_outcome(s)
#                 if o is not None:
#                     st.write(f"**Outcome:** {'Success' if o else 'Failure'} | Close: ${c}")
#                     if st.button("Apply", key=f"apply_{s['entry_id']}"):
#                         brier = (s["pop"]/100 - o)**2
#                         s["status"] = "Verified"
#                         s["brier"] = round(brier, 4)
#                         s["outcome"] = o
#                         s["expiry_close"] = c
#                         save_submissions(subs)
#                         users = update_reputation(users, s)
#                         save_users(users)
#                         st.rerun()
#                 else:
#                     st.info(c)
    
#     # === SCORE ===
#     with tab_score:
#         st.markdown("### Leaderboard")
#         if users:
#             lb = sorted(users.items(), key=lambda x: x[1]["reputation"], reverse=True)[:10]
#             for i, (u, d) in enumerate(lb):
#                 st.markdown(f"""
#                 <div class="card">
#                     <strong>#{i+1} {u}</strong><br>
#                     Rep: {d['reputation']:.0f} • Brier: {d['avg_brier']:.3f} • Preds: {d['predictions']}
#                 </div>
#                 """, unsafe_allow_html=True)
#         else:
#             st.info("No users yet.")
    
#     # === REWARD ===
#     with tab_reward:
#         st.markdown("### Daily Payouts")
#         if daily["payouts_done"]:
#             st.success("Payouts complete.")
#         else:
#             ranked = sorted(users.items(), key=lambda x: x[1]["reputation"], reverse=True)[:3]
#             for i, (uid, u) in enumerate(ranked):
#                 prize = PRIZES[i]
#                 paid = any(r["user_id"] == uid and r["amount"] == prize for r in rewards)
#                 if paid:
#                     st.markdown(f"<div class='card'>#{i+1} {uid} — ${prize} (Paid)</div>", unsafe_allow_html=True)
#                 else:
#                     if st.button(f"Pay ${prize} to {uid}", key=f"pay_{uid}"):
#                         rewards.append({
#                             "user_id": uid, "amount": prize, "date": datetime.now().isoformat(),
#                             "method": "Venmo", "status": "Paid"
#                         })
#                         save_rewards(rewards)
#                         st.success("Paid!")
#             if st.button("Mark Done"):
#                 daily["payouts_done"] = True
#                 json.dump(daily, open(DAILY_FILE, "w"), indent=2)
    
#     # === EVOLVE ===
#     with tab_evolve:
#         st.markdown("### AI Co-Training")
#         verified_count = len([s for s in subs if s.get("status") == "Verified"])
#         st.write(f"**Verified Data:** {verified_count} predictions")
#         if verified_count > 10 and st.button("Retrain QuantBot", type="primary"):
#             with st.spinner("Training..."):
#                 df = pd.DataFrame([s for s in subs if s.get("status") == "Verified"])
#                 train_bot(df)
#                 st.success("QuantBot updated!")
#                 st.balloons()
    
#     # Logout
#     if st.button("Logout"):
#         st.session_state.auth = False
#         st.rerun()

# # ==============================
# # FOOTER
# # ==============================
# st.markdown('<div class="footer">Skill only. No real money. Truth wins.</div>', unsafe_allow_html=True)

##### combine good layout with features.



# ==============================
# quantstacks_storyboard_plus_form.py
# JONY IVE UI + SYMBOL + EXPIRIES + STRIKES + NO X POSTING
# Run: streamlit run quantstacks_storyboard_plus_form.py
# ==============================

import streamlit as st
import yfinance as yf
import pandas as pd
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
import hashlib
import secrets
import uuid
import re
from filelock import FileLock

# ==============================
# CONFIG & PATHS
# ==============================
st.set_page_config(page_title="QuantStacks", layout="centered", initial_sidebar_state="collapsed")

SUBMISSIONS_FILE = Path("quantstacks_submissions.json")
USERS_FILE = Path("quantstacks_users.json")
REWARDS_FILE = Path("quantstacks_rewards.json")
MODEL_FILE = Path("quantstacks_model.pth")
AUTH_FILE = Path("quantstacks_auth.json")
LOG_FILE = Path("quantstacks.log")

PRIZES = [5.0, 3.0, 2.0]
MAX_PREDICTIONS_PER_DAY = 1
COST_PER_PREDICTION = 100
LOGIN_ATTEMPTS_MAX = 5
LOGIN_BLOCK_SECONDS = 300

# ==============================
# LOGGING
# ==============================
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

# ==============================
# JONY IVE DESIGN SYSTEM (ENHANCED)
# ==============================
st.markdown("""
<style>
    .stApp {background: #fafafa; font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif;}
    .title {font-size:38px; font-weight:600; letter-spacing:-0.6px; color:#1d1d1f; text-align:center; margin:0;}
    .subtitle {font-size:18px; color:#6e6e73; text-align:center; margin:8px 0 32px; font-weight:400;}
    
    /* Cards */
    .card {background:white; border-radius:20px; padding:28px; box-shadow:0 4px 16px rgba(0,0,0,0.06); margin-bottom:24px;}
    .card-header {font-size:18px; font-weight:600; color:#1d1d1f; margin-bottom:12px;}
    .card-content {font-size:16px; color:#48484a;}
    
    /* Buttons */
    .stButton>button {
        background:#0071e3; color:white; border:none; border-radius:14px;
        padding:12px 24px; font-weight:500; font-size:17px; height:48px; width:100%;
        transition:all .2s; box-shadow:0 2px 6px rgba(0,113,227,0.2);
    }
    .stButton>button:hover {background:#0061c3; transform:translateY(-1px); box-shadow:0 4px 12px rgba(0,113,227,0.3);}
    .stButton>button:active {transform:translateY(0);}
    
    /* Inputs */
    .stTextInput>div>div>input, .stSelectbox>div>div>select, .stSlider>div>div>div>div {
        border-radius:14px; border:1px solid #d2d2d7; padding:14px; font-size:17px; background:#fff;
    }
    
    /* Metrics */
    .metric-card {background:white; border-radius:18px; padding:18px; text-align:center; box-shadow:0 2px 8px rgba(0,0,0,0.05);}
    .metric-label {font-size:13px; color:#6e6e73; margin-bottom:6px;}
    .metric-value {font-size:28px; font-weight:600; color:#1d1d1f;}
    
    /* Challenge */
    .challenge-card {background:linear-gradient(135deg,#fffbe6,#fff4c2); border:1px solid #ffd60a; border-radius:20px; padding:24px; text-align:center;}
    
    /* Bot */
    .bot-card {background:linear-gradient(135deg,#f0f9ff,#e0f2fe); border:1px solid #0ea5e9; border-radius:18px; padding:18px; text-align:center; font-size:16px;}
    
    /* Credit */
    .credit-info {background:#f5f5f7; border-left:4px solid #0071e3; padding:14px 16px; border-radius:10px; font-weight:500; font-size:16px;}
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {gap:32px; justify-content:center; padding:0 16px; border-bottom:1px solid #d2d2d7;}
    .stTabs [data-baseweb="tab"] {height:56px; padding:0 28px; font-size:18px; font-weight:500; color:#6e6e73;}
    .stTabs [data-baseweb="tab"][aria-selected="true"] {color:#0071e3; border-bottom:3px solid #0071e3;}
    
    /* Performance */
    .perf-metric {background:#f8f9fa; border-radius:14px; padding:14px; text-align:center; margin:6px;}
    .perf-label {font-size:13px; color:#6e6e73;}
    .perf-value {font-size:20px; font-weight:600; color:#1d1d1f; margin-top:4px;}
    
    /* Footer */
    .footer {text-align:center; color:#8e8e93; font-size:14px; margin-top:60px; padding:24px 0;}
</style>
""", unsafe_allow_html=True)

# ==============================
# ATOMIC FILE I/O
# ==============================
def atomic_json_load(path: Path, default):
    if not path.exists(): return default
    with FileLock(str(path) + ".lock"):
        try: return json.load(open(path, "r", encoding="utf-8"))
        except Exception as e:
            logging.error(f"Load error {path}: {e}")
            return default

def atomic_json_write(path: Path, data):
    with FileLock(str(path) + ".lock"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

# ==============================
# AUTH
# ==============================
def strong_password(pw: str) -> bool:
    return len(pw) >= 8 and any(c.isdigit() for c in pw) and any(c.isalpha() for c in pw)

def hash_password(pw: str, salt: str = None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), 100_000).hex()
    return h, salt

def verify_password(stored_h, stored_s, pw):
    nh, _ = hash_password(pw, stored_s)
    return secrets.compare_digest(nh, stored_h)

def load_auth(): return atomic_json_load(AUTH_FILE, {})
def save_auth(db): atomic_json_write(AUTH_FILE, db)
def load_users(): return atomic_json_load(USERS_FILE, {})
def save_users(u): atomic_json_write(USERS_FILE, u)
def load_submissions(): return atomic_json_load(SUBMISSIONS_FILE, [])
def save_submissions(s): atomic_json_write(SUBMISSIONS_FILE, s)
def load_rewards(): return atomic_json_load(REWARDS_FILE, [])
def save_rewards(r): atomic_json_write(REWARDS_FILE, r)

# ==============================
# AUTO-OUTCOME
# ==============================
def auto_determine_outcome(sub):
    try:
        exp = datetime.strptime(sub['exp'], '%Y-%m-%d').date()
        today = datetime.now().date()
        if today <= exp:
            return None, f"Not expired (exp: {exp})"

        start = exp - timedelta(days=1)
        end = exp + timedelta(days=2)
        ticker = yf.Ticker(sub['symbol'])
        hist = ticker.history(start=start, end=end)
        
        if hist.empty:
            hist_latest = ticker.history(period="1d")
            if not hist_latest.empty:
                close = hist_latest['Close'].iloc[-1]
                success = (close >= sub['short']) if sub['direction'] == "Bull Put" else (close <= sub['short'])
                return int(success), round(close, 2)
            else:
                return None, "No price data"
        
        close = hist['Close'].iloc[0]
        success = (close >= sub['short']) if sub['direction'] == "Bull Put" else (close <= sub['short'])
        return int(success), round(close, 2)
    except Exception as e:
        return None, f"Error: {str(e)}"

# ==============================
# OPTIONS CHAIN
# ==============================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_option_chain(symbol: str):
    try:
        ticker = yf.Ticker(symbol)
        expirations = ticker.options
        return expirations or [], None
    except Exception as e:
        return [], f"Error: {str(e)}"

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_strikes(symbol: str, exp: str):
    try:
        ticker = yf.Ticker(symbol)
        chain = ticker.option_chain(exp)
        calls = chain.calls[['strike', 'lastPrice']].set_index('strike')
        puts = chain.puts[['strike', 'lastPrice']].set_index('strike')
        common = calls.index.intersection(puts.index)
        if common.empty:
            return {}, "No common strikes"
        prices = pd.concat([calls.loc[common], puts.loc[common]], axis=1, keys=['call', 'put'])
        prices.columns = prices.columns.droplevel(1)
        return prices.to_dict('index'), None
    except Exception as e:
        return {}, f"Error: {str(e)}"

# ==============================
# REPUTATION + DECAY + STREAKS + BADGES
# ==============================
def update_reputation(users, sub):
    uid = sub["user_id"]
    brier = sub.get("brier")
    if brier is None or uid not in users: return users
    u = users[uid]
    rep_change = 50 * (1 - brier) - 100 * brier
    net_votes = sub.get("votes_up", 0) - sub.get("votes_down", 0)
    rep_change += net_votes * 5
    u["reputation"] = max(100, u["reputation"] + rep_change)
    n = u["predictions"]
    u["avg_brier"] = (u["avg_brier"] * n + brier) / (n + 1)
    u["predictions"] = n + 1
    u["last_active"] = datetime.now().isoformat()
    outcome = sub.get("outcome")
    if outcome is not None:
        is_win = bool(outcome)
        if is_win and u.get("last_pred_win", False):
            u["pred_streak"] = u.get("pred_streak", 0) + 1
        elif is_win:
            u["pred_streak"] = 1
        else:
            u["pred_streak"] = 0
        u["last_pred_win"] = is_win
        badges = u.setdefault("badges", [])
        if u["pred_streak"] == 3 and "3 Wins in a Row" not in badges:
            badges.append("3 Wins in a Row")
        if u["pred_streak"] == 5 and "5 Wins in a Row" not in badges:
            badges.append("5 Wins in a Row")
        if u["predictions"] >= 10 and "10 Predictions" not in badges:
            badges.append("10 Predictions")
    return users

def apply_decay(users):
    now = datetime.now()
    for u in users.values():
        last = datetime.fromisoformat(u["last_active"])
        days = (now - last).days
        if days > 0:
            decay = (1 - 0.02) ** (days / 7)
            u["reputation"] = max(100, u["reputation"] * decay)
            u["last_active"] = now.isoformat()
    return users

# ==============================
# PERFORMANCE METRICS
# ==============================
def calculate_prediction_metrics(predictions):
    verified = [p for p in predictions if p.get("outcome") in {0, 1}]
    if not verified:
        return {k: 0.0 for k in ["directional_accuracy","weighted_accuracy","brier_score","expected_value","total_predictions","wins","losses"]}
    df = pd.DataFrame(verified)
    df['pop'] = df['pop'].astype(float)
    df['outcome'] = df['outcome'].astype(int)
    df['confidence'] = df['confidence'].astype(float).clip(1, 10)
    n = len(df)
    wins = df['outcome'].sum()
    dir_acc = wins / n
    weighted_acc = (df['confidence'] * df['outcome']).sum() / df['confidence'].sum() if df['confidence'].sum() > 0 else 0.0
    brier = ((df['pop'] - df['outcome']) ** 2).mean()
    ev_per_pred = (df['pop'] * 1.0 - (1 - df['pop']) * 1.0).mean()
    return {
        "directional_accuracy": round(dir_acc, 4),
        "weighted_accuracy": round(weighted_acc, 4),
        "brier_score": round(brier, 4),
        "expected_value": round(ev_per_pred, 4),
        "total_predictions": int(n),
        "wins": int(wins),
        "losses": int(losses)
    }

# ==============================
# AI BOT
# ==============================
class QuantBot(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(4, 16), nn.ReLU(),
            nn.Linear(16, 8), nn.ReLU(),
            nn.Linear(8, 1), nn.Sigmoid()
        )
    def forward(self, x): return self.net(x)

def train_bot(df):
    if df.empty or len(df) < 10: return
    X = df[['pop', 'confidence', 'credit', 'brier']].fillna(0).values
    y = df['outcome'].astype(float).values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    X_train, _, y_train, _ = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
    loader = DataLoader(TensorDataset(torch.tensor(X_train, dtype=torch.float32),
                                     torch.tensor(y_train, dtype=torch.float32).unsqueeze(1)),
                        batch_size=8, shuffle=True)
    model = QuantBot()
    crit = nn.BCELoss()
    opt = optim.Adam(model.parameters(), lr=0.01)
    model.train()
    for _ in range(30):
        for xb, yb in loader:
            opt.zero_grad()
            loss = crit(model(xb), yb)
            loss.backward()
            opt.step()
    torch.save({"state_dict": model.state_dict(),
                "scaler_mean": scaler.mean_.tolist(),
                "scaler_scale": scaler.scale_.tolist()}, MODEL_FILE)

def load_bot():
    if not MODEL_FILE.exists(): return None, None
    ckpt = torch.load(MODEL_FILE, map_location="cpu")
    model = QuantBot()
    model.load_state_dict(ckpt["state_dict"])
    scaler = StandardScaler()
    scaler.mean_ = np.array(ckpt["scaler_mean"])
    scaler.scale_ = np.array(ckpt["scaler_scale"])
    return model, scaler

# ==============================
# INIT
# ==============================
if "auth" not in st.session_state: st.session_state.auth = False
if "user" not in st.session_state: st.session_state.user = None
if "login_attempts" not in st.session_state: st.session_state.login_attempts = {}
if "block_until" not in st.session_state: st.session_state.block_until = {}

auth_db = load_auth()
if st.session_state.auth:
    subs = load_submissions()
    users = load_users()
    rewards = load_rewards()
    users = apply_decay(users)
    bot_model, bot_scaler = load_bot()
else:
    subs = users = rewards = bot_model = bot_scaler = None

# Mock
if st.session_state.auth and subs and len(subs) == 0:
    mock = [{
        "entry_id": str(uuid.uuid4()),
        "time": "2024-11-06T10:00:00",
        "user_id": st.session_state.user,
        "symbol": "AAPL",
        "direction": "Bull Put",
        "exp": "2024-11-15",
        "short": 220.0,
        "long": 210.0,
        "credit": 2.10,
        "pop": 0.75,
        "confidence": 8,
        "rationale": "Strong support",
        "status": "Pending",
        "votes_up": 0,
        "votes_down": 0,
        "voters": []
    }]
    subs.extend(mock)
    save_submissions(subs)

# ==============================
# AUTH UI
# ==============================
if not st.session_state.auth:
    st.markdown('<div class="title">QuantStacks</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Predict. Verify. Win. $10 daily.</div>', unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["Sign Up", "Login"])

    with tab1:
        with st.form("signup_form", clear_on_submit=True):
            st.markdown("### Create Account")
            username = st.text_input("Username", placeholder="trader_x")
            password = st.text_input("Password", type="password")
            email = st.text_input("Email", placeholder="you@example.com")
            submit = st.form_submit_button("Create $10K Account")
            if submit:
                if username in auth_db:
                    st.error("Username taken")
                elif not strong_password(password):
                    st.error("Password: 8+ chars, letter + digit")
                elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                    st.error("Valid email required")
                else:
                    h, s = hash_password(password)
                    auth_db[username] = {"pwdhash": h, "salt": s, "email": email}
                    save_auth(auth_db)
                    users = load_users()
                    users[username] = {
                        "reputation": 1000.0,
                        "last_active": datetime.now().isoformat(),
                        "predictions": 0,
                        "avg_brier": 0.0,
                        "fake_balance": 10000.0,
                        "pred_streak": 0,
                        "last_pred_win": False,
                        "badges": []
                    }
                    save_users(users)
                    st.success("Account created!")
                    st.session_state.auth = True
                    st.session_state.user = username
                    st.rerun()

    with tab2:
        with st.form("login_form", clear_on_submit=True):
            st.markdown("### Login")
            username = st.text_input("Username", key="login_un")
            password = st.text_input("Password", type="password", key="login_pw")
            submit = st.form_submit_button("Login")
            if submit:
                if username not in auth_db or not verify_password(auth_db[username]["pwdhash"], auth_db[username]["salt"], password):
                    st.error("Invalid credentials")
                else:
                    st.session_state.auth = True
                    st.session_state.user = username
                    st.rerun()

else:
    # ==============================
    # MAIN UI
    # ==============================
    st.markdown('<div class="title">QuantStacks</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Truth wins. Skill scales.</div>', unsafe_allow_html=True)

    bal = users[st.session_state.user]["fake_balance"]
    col1, col2, col3 = st.columns(3)
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Fake Balance</div>
            <div class="metric-value">${bal:,.0f}</div>
        </div>
        """, unsafe_allow_html=True)

    tab_predict, tab_verify, tab_score, tab_reward, tab_evolve = st.tabs(
        ["Predict", "Verify", "Score", "Reward", "Evolve"])

    # === PREDICT (WIZARD) ===
    with tab_predict:
        st.markdown("<div class='challenge-card'>", unsafe_allow_html=True)
        st.markdown("### Daily Challenge")
        st.markdown("Select any symbol. Top 3 win $10.")
        st.markdown("</div>", unsafe_allow_html=True)

        today = datetime.now().strftime("%Y-%m-%d")
        user_preds = [s for s in subs if s["user_id"] == st.session_state.user and s["time"].startswith(today)]
        if len(user_preds) >= MAX_PREDICTIONS_PER_DAY:
            st.markdown('<div class="warning-card">You already predicted today.</div>', unsafe_allow_html=True)
        else:
            # Step 1: Symbol
            with st.container():
                st.markdown("#### 1. Symbol")
                symbol = st.text_input("Enter ticker", value="AAPL", help="e.g., AAPL, SPY, TSLA").strip().upper()

            # Step 2: Expirations
            expirations = []
            if st.button("Load Options Chain", key="load_chain"):
                with st.spinner("Fetching..."):
                    expirations, err = fetch_option_chain(symbol)
                if err:
                    st.error(err)
                else:
                    st.session_state.expirations = expirations
                    st.success(f"Found {len(expirations)} expiry dates")

            if "expirations" in st.session_state and st.session_state.expirations:
                expirations = st.session_state.expirations
                with st.container():
                    st.markdown("#### 2. Expiry")
                    exp = st.selectbox("Select date", expirations, format_func=lambda x: datetime.strptime(x, '%Y-%m-%d').strftime('%b %d, %Y'))

                if st.button("Load Strikes", key="load_strikes"):
                    with st.spinner("Fetching strikes..."):
                        strikes_dict, err = fetch_strikes(symbol, exp)
                    if err:
                        st.error(err)
                    else:
                        st.session_state.strikes_dict = strikes_dict
                        st.success(f"Loaded {len(strikes_dict)} strikes")

            # Step 3: Strikes
            credit = 0.0
            if "strikes_dict" in st.session_state:
                strikes = sorted(st.session_state.strikes_dict.keys())
                with st.container():
                    st.markdown("#### 3. Strikes")
                    direction = st.radio("Direction", ["Bull Put", "Bear Call"], horizontal=True)
                    short_strike = st.selectbox("Short Strike", strikes)
                    long_options = [s for s in strikes if (direction == "Bull Put" and s < short_strike) or (direction == "Bear Call" and s > short_strike)]
                    long_strike = st.selectbox("Long Strike", long_options) if long_options else None

                    if long_strike:
                        call_short = st.session_state.strikes_dict[short_strike]['call']
                        put_short = st.session_state.strikes_dict[short_strike]['put']
                        call_long = st.session_state.strikes_dict[long_strike]['call']
                        put_long = st.session_state.strikes_dict[long_strike]['put']
                        if direction == "Bull Put":
                            credit = round(put_short - put_long, 2)
                        else:
                            credit = round(call_short - call_long, 2)
                        st.markdown(f'<div class="credit-info">Net Credit: <strong>${credit:.2f}</strong></div>', unsafe_allow_html=True)

            # Step 4: Predict
            with st.container():
                st.markdown("#### 4. Predict")
                with st.form("predict_form"):
                    pop = st.slider("POP", 0.0, 1.0, 0.70, step=0.01)
                    conf = st.slider("Confidence", 1, 10, 7)
                    rationale = st.text_area("Rationale", height=80)
                    submit = st.form_submit_button("Predict (-$100)")
                    if submit:
                        if bal < COST_PER_PREDICTION:
                            st.error("Need $100")
                        elif credit <= 0:
                            st.error("Select valid strikes")
                        else:
                            users[st.session_state.user]["fake_balance"] -= COST_PER_PREDICTION
                            save_users(users)
                            entry = {
                                "entry_id": str(uuid.uuid4()),
                                "user_id": st.session_state.user,
                                "symbol": symbol,
                                "direction": direction,
                                "exp": exp,
                                "short": float(short_strike),
                                "long": float(long_strike),
                                "credit": credit,
                                "pop": pop,
                                "confidence": conf,
                                "rationale": rationale,
                                "time": datetime.now().isoformat(),
                                "status": "Pending",
                                "votes_up": 0,
                                "votes_down": 0,
                                "voters": []
                            }
                            subs.append(entry)
                            save_submissions(subs)
                            st.success("Predicted!")
                            st.balloons()

    # === VERIFY ===
    with tab_verify:
        st.markdown("### Verify Outcomes")
        pending = [s for s in subs if s["status"] == "Pending"]
        if not pending:
            st.info("No pending predictions.")
        for s in pending:
            with st.expander(f"{s['symbol']} — {s['user_id']}"):
                o, c = auto_determine_outcome(s)
                if o is not None:
                    st.write(f"**Outcome:** {'Success' if o else 'Failure'} | Close: ${c}")
                    if st.button("Apply", key=f"apply_{s['entry_id']}"):
                        brier = (s["pop"] - o) ** 2
                        s.update({"status": "Verified", "brier": round(brier, 4), "outcome": o, "expiry_close": c})
                        save_submissions(subs)
                        users = update_reputation(users, s)
                        save_users(users)
                        st.rerun()
                else:
                    st.info(c)

    # === SCORE ===
    with tab_score:
        st.markdown("### Leaderboard")
        if users:
            lb = sorted(users.items(), key=lambda x: x[1]["reputation"], reverse=True)[:20]
            df = pd.DataFrame([{
                "Rank": i+1,
                "User": u,
                "Rep": f"{d['reputation']:.0f}",
                "Brier": f"{d['avg_brier']:.3f}",
                "Preds": d['predictions'],
                "Streak": d.get('pred_streak', 0),
                "Badges": " • ".join(d.get('badges', []))
            } for i, (u, d) in enumerate(lb)])
            st.dataframe(df, use_container_width=True)

        st.markdown("### Your Performance")
        user_preds = [s for s in subs if s["user_id"] == st.session_state.user and s.get("outcome") in {0, 1}]
        metrics = calculate_prediction_metrics(user_preds)
        if metrics["total_predictions"] > 0:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.markdown(f'<div class="perf-metric"><div class="perf-label">Dir. Acc</div><div class="perf-value">{metrics["directional_accuracy"]:.1%}</div></div>', unsafe_allow_html=True)
            with col2:
                st.markdown(f'<div class="perf-metric"><div class="perf-label">Weighted Acc</div><div class="perf-value">{metrics["weighted_accuracy"]:.1%}</div></div>', unsafe_allow_html=True)
            with col3:
                st.markdown(f'<div class="perf-metric"><div class="perf-label">Brier</div><div class="perf-value">{metrics["brier_score"]:.3f}</div></div>', unsafe_allow_html=True)
            with col4:
                st.markdown(f'<div class="perf-metric"><div class="perf-label">EV</div><div class="perf-value">${metrics["expected_value"]:.2f}</div></div>', unsafe_allow_html=True)
        else:
            st.info("No verified predictions yet.")

    # === REWARD ===
    with tab_reward:
        st.markdown("### Daily Payouts")
        ranked = sorted(users.items(), key=lambda x: x[1]["reputation"], reverse=True)[:3]
        for i, (uid, u) in enumerate(ranked):
            prize = PRIZES[i]
            paid = any(r["user_id"] == uid and r["amount"] == prize for r in rewards)
            col1, col2 = st.columns([3,1])
            with col1:
                st.markdown(f"**#{i+1} {uid}** – ${prize:.2f} {'(Paid)' if paid else ''}")
            with col2:
                if not paid and st.button(f"Pay ${prize}", key=f"pay_{uid}"):
                    rewards.append({
                        "user_id": uid, "amount": prize, "date": datetime.now().isoformat(),
                        "method": "Venmo", "status": "Paid"
                    })
                    save_rewards(rewards)
                    st.success("Paid!")
                    st.balloons()

    # === EVOLVE ===
    with tab_evolve:
        st.markdown("### AI Co-Training")
        verified = [s for s in subs if s.get("status") == "Verified" and s.get("outcome") is not None]
        st.write(f"**Verified:** {len(verified)} predictions")
        if len(verified) >= 10 and st.button("Retrain QuantBot", type="primary"):
            with st.spinner("Training…"):
                df = pd.DataFrame(verified)
                train_bot(df)
                st.success("QuantBot updated!")
                st.balloons()

    # Logout
    if st.button("Logout"):
        st.session_state.auth = False
        st.rerun()

# ==============================
# FOOTER
# ==============================
st.markdown('<div class="footer">Skill only. No real money. Truth wins.</div>', unsafe_allow_html=True)