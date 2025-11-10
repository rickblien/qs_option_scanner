
# import streamlit as st
# import graphviz
# import pandas as pd
# import sqlite3
# import os
# from streamlit_option_menu import option_menu
# import io
# import logging
# import uuid

# # Custom CSS for Jony Ive-inspired design
# st.markdown("""
# <style>
#     /* Main container */
#     .main {
#         background-color: #f5f5f7;
#         padding: 20px;
#         border-radius: 12px;
#         box-shadow: 0 4px 12px rgba(0,0,0,0.05);
#     }
    
#     /* Title */
#     h1 {
#         font-family: 'Helvetica Neue', sans-serif;
#         color: #1d1d1f;
#         font-weight: 600;
#         text-align: center;
#         margin-bottom: 30px;
#     }
    
#     /* Subheaders */
#     h2 {
#         font-family: 'Helvetica Neue', sans-serif;
#         color: #1d1d1f;
#         font-weight: 500;
#         margin-top: 20px;
#     }
    
#     /* Inputs and buttons */
#     .stTextInput > div > div > input,
#     .stNumberInput > div > div > input,
#     .stSelectbox > div > div > select {
#         border: 1px solid #d2d2d7;
#         border-radius: 8px;
#         padding: 10px;
#         font-family: 'Helvetica Neue', sans-serif;
#         background-color: #ffffff;
#         transition: border-color 0.2s;
#     }
    
#     .stTextInput > div > div > input:focus,
#     .stNumberInput > div > div > input:focus,
#     .stSelectbox > div > div > select:focus {
#         border-color: #007aff;
#         box-shadow: 0 0 0 2px rgba(0,122,255,0.2);
#     }
    
#     .stButton > button {
#         background-color: #007aff;
#         color: white;
#         border-radius: 8px;
#         padding: 10px 20px;
#         font-family: 'Helvetica Neue', sans-serif;
#         font-weight: 500;
#         border: none;
#         transition: background-color 0.2s;
#     }
    
#     .stButton > button:hover {
#         background-color: #005bb5;
#     }
    
#     /* Option menu */
#     .nav-item {
#         background-color: #ffffff;
#         border-radius: 8px;
#         margin: 0 5px;
#         padding: 8px 16px;
#         font-family: 'Helvetica Neue', sans-serif;
#         color: #1d1d1f;
#         transition: background-color 0.2s;
#     }
    
#     .nav-item:hover {
#         background-color: #e5e5ea;
#     }
    
#     /* Dataframe */
#     .stDataFrame {
#         border: 1px solid #d2d2d7;
#         border-radius: 8px;
#         background-color: #ffffff;
#     }
    
#     /* File uploader */
#     .stFileUploader > div > div {
#         border: 1px solid #d2d2d7;
#         border-radius: 8px;
#         background-color: #ffffff;
#         padding: 10px;
#     }
    
#     /* Graphviz chart */
#     .stGraphvizChart {
#         background-color: #ffffff;
#         border-radius: 8px;
#         padding: 15px;
#         border: 1px solid #d2d2d7;
#     }
    
#     /* General text */
#     body, p, div, span {
#         font-family: 'Helvetica Neue', sans-serif;
#         color: #1d1d1f;
#     }
# </style>
# """, unsafe_allow_html=True)

# def create_mindmap_graph(data):
#     dot = graphviz.Digraph(comment='Mind Map')
#     dot.attr(rankdir='LR', bgcolor='transparent')
#     for node in data['nodes']:
#         node_label = f"{node['id']}. {node['label']}\nLevel: {node.get('level', 0)}\nPriority: {node.get('priority', 0)}"
#         dot.node(str(node['id']), node_label, style='filled', fillcolor=node['color'], shape='rect', 
#                  fontname='Helvetica Neue', fontsize='12', color='#d2d2d7', penwidth='1')
#     for edge in data['edges']:
#         is_feedback = edge.get('feedback', False)
#         dot.edge(str(edge['from']), str(edge['to']), style='dashed' if is_feedback else 'solid', 
#                  color='#ff3b30' if is_feedback else '#1d1d1f', arrowhead='vee' if is_feedback else 'normal')
#     return dot

# def get_hierarchical_path(node_id, nodes, edges, node_dict, visited=None):
#     if visited is None:
#         visited = set()
    
#     if node_id in visited:
#         return []
#     visited.add(node_id)
    
#     parents = [edge['from'] for edge in edges if edge['to'] == node_id and not edge.get('feedback', False)]
    
#     if not parents:
#         return [node_dict[node_id]['label']]
    
#     parent_id = parents[0]
#     parent_path = get_hierarchical_path(parent_id, nodes, edges, node_dict, visited.copy())
#     parent_path.append(node_dict[node_id]['label'])
#     return parent_path

# def create_dataframe(data):
#     df = pd.DataFrame(data['nodes'])
#     if not df.empty:
#         nodes = data['nodes']
#         edges = data['edges']
#         node_dict = {node['id']: node for node in nodes}
        
#         df['path'] = [
#             ' → '.join(get_hierarchical_path(node['id'], nodes, edges, node_dict))
#             for node in nodes
#         ]
    
#     df_sorted = df.sort_values(by=['level', 'priority'], ascending=[False, True])
#     df_sorted = df_sorted[['id', 'label', 'level', 'priority', 'color', 'path']]
#     df_sorted.columns = ['ID', 'Label', 'Level', 'Priority', 'Color', 'Path']
#     return df_sorted


# def save_mindmap_to_sqlite(mindmap_data, db_name='mindmap.db'):
#     conn = None
#     try:
#         if mindmap_data is None or 'nodes' not in mindmap_data or 'edges' not in mindmap_data:
#             raise ValueError("Mind map data is missing 'nodes' or 'edges'.")
#         conn = sqlite3.connect(db_name)
#         cursor = conn.cursor()
#         cursor.execute('''CREATE TABLE IF NOT EXISTS nodes (
#                             id INTEGER PRIMARY KEY,
#                             label TEXT,
#                             color TEXT,
#                             level INTEGER,
#                             priority INTEGER)''')
#         cursor.execute('''CREATE TABLE IF NOT EXISTS edges (
#                             from_node INTEGER,
#                             to_node INTEGER,
#                             feedback BOOLEAN,
#                             FOREIGN KEY(from_node) REFERENCES nodes(id),
#                             FOREIGN KEY(to_node) REFERENCES nodes(id))''')
#         nodes = mindmap_data['nodes']  # Define nodes from mindmap_data
#         edges = mindmap_data['edges']  # Define edges from mindmap_data
#         cursor.executemany('''INSERT OR REPLACE INTO nodes (id, label, color, level, priority) 
#                              VALUES (?, ?, ?, ?, ?)''', 
#                           [(node['id'], node['label'], node['color'], node['level'], node['priority']) for node in nodes])
#         cursor.executemany('''INSERT INTO edges (from_node, to_node, feedback) 
#                              VALUES (?, ?, ?)''', 
#                           [(edge['from'], edge['to'], edge['feedback']) for edge in edges])
#         conn.commit()
#     except sqlite3.Error as e:
#         st.error(f"Database error: {e}")
#     except ValueError as e:
#         st.error(f"Data error: {e}")
#     finally:
#         if conn:
#             conn.close()

# def fetch_mindmap_from_sqlite(db_name='mindmap.db'):
#     try:
#         conn = sqlite3.connect(db_name)
#         cursor = conn.cursor()
#         cursor.execute('SELECT id, label, color, level, priority FROM nodes')
#         nodes = [{'id': row[0], 'label': row[1], 'color': row[2], 'level': row[3], 'priority': row[4]} for row in cursor.fetchall()]
#         cursor.execute('SELECT from_node, to_node, feedback FROM edges')
#         edges = [{'from': row[0], 'to': row[1], 'feedback': row[2]} for row in cursor.fetchall()]
#     except sqlite3.Error as e:
#         st.error(f"Database error: {e}")
#         return {'nodes': [], 'edges': []}
#     finally:
#         if conn:
#             conn.close()
#     return {'nodes': nodes, 'edges': edges}

# def excel_to_mindmap_data(excel_file):
#     try:
#         df = pd.read_excel(excel_file, header=None)
#     except Exception as e:
#         st.error(f"Error reading Excel file: {e}")
#         return {'nodes': [], 'edges': []}, 0
    
#     nodes = []
#     edges = []
#     node_counter = 0
#     level_nodes = {}
#     priority_counters = {}
    
#     for row_idx, row in df.iterrows():
#         parent_id = None
#         parent_level = -1
        
#         for level, cell in enumerate(row):
#             if pd.notna(cell):
#                 for prev_level in range(level - 1, -1, -1):
#                     if prev_level in level_nodes.get(row_idx, {}) and level_nodes[row_idx][prev_level] is not None:
#                         parent_id = level_nodes[row_idx][prev_level]
#                         parent_level = prev_level
#                         break
                
#                 if parent_id is None:
#                     for prev_row in range(row_idx - 1, -1, -1):
#                         if prev_row in level_nodes:
#                             for prev_level in range(level - 1, -1, -1):
#                                 if prev_level in level_nodes[prev_row] and level_nodes[prev_row][prev_level] is not None:
#                                     parent_id = level_nodes[prev_row][prev_level]
#                                     parent_level = prev_level
#                                     break
#                             if parent_id is not None:
#                                 break
                
#                 priority_counters.setdefault(level, 0)
#                 priority_counters[level] += 1
                
#                 node = {
#                     'id': node_counter,
#                     'label': str(cell),
#                     'color': '#ffcccb' if level == 0 else '#ccffcc',
#                     'level': level,
#                     'priority': priority_counters[level]
#                 }
#                 nodes.append(node)
                
#                 if row_idx not in level_nodes:
#                     level_nodes[row_idx] = {}
#                 level_nodes[row_idx][level] = node_counter
                
#                 if parent_id is not None:
#                     edges.append({'from': parent_id, 'to': node_counter, 'feedback': False})
                
#                 node_counter += 1
    
#     return {'nodes': nodes, 'edges': edges}, node_counter

# def mindmap_to_excel_data(mindmap_data):
#     try:
#         if mindmap_data is None or 'nodes' not in mindmap_data or 'edges' not in mindmap_data:
#             raise ValueError("Mind map data is missing 'nodes' or 'edges'.")
        
#         nodes = mindmap_data['nodes']
#         edges = mindmap_data['edges']
        
#         required_node_keys = {'id', 'level', 'label', 'priority'}
#         for node in nodes:
#             if not all(key in node for key in required_node_keys):
#                 raise ValueError(f"Node {node.get('id', 'unknown')} missing required keys: {required_node_keys}")
        
#         if not nodes:
#             return pd.DataFrame()
        
#         max_level = max(node['level'] for node in nodes)
        
#         node_dict = {node['id']: node for node in nodes}
#         children = {node['id']: [] for node in nodes}
#         for edge in edges:
#             if edge['from'] not in node_dict or edge['to'] not in node_dict:
#                 logging.warning(f"Skipping invalid edge: from {edge.get('from')} to {edge.get('to')}")
#                 continue
#             children[edge['from']].append(edge['to'])
        
#         for parent_id in children:
#             children[parent_id].sort(
#                 key=lambda child_id: node_dict[child_id].get('priority', float('inf'))
#             )
        
#         levels = sorted(set(node['level'] for node in nodes))
#         second_highest_level = levels[-2] if len(levels) >= 2 else levels[-1] if levels else 0
#         highest_level = levels[-1] if levels else 0

#         def get_sort_key(node):
#             def get_descendants(node_id):
#                 descendants = []
#                 for child_id in children.get(node_id, []):
#                     descendants.append(node_dict[child_id])
#                     descendants.extend(get_descendants(child_id))
#                 return descendants
#             descendants = get_descendants(node['id'])
#             second_highest_priority = min(
#                 (n['priority'] for n in descendants if n['level'] == second_highest_level),
#                 default=float('inf')
#             )
#             highest_priority = min(
#                 (n['priority'] for n in descendants if n['level'] == highest_level),
#                 default=float('inf')
#             )
#             return (second_highest_priority, highest_priority, node['level'])

#         sorted_nodes = sorted(nodes, key=get_sort_key)
        
#         df = pd.DataFrame(index=range(len(nodes)), columns=range(max_level + 1))
        
#         row_idx = 0
#         def place_node(node_id, current_row):
#             nonlocal row_idx
#             if current_row >= len(df):
#                 logging.warning("Row index exceeded DataFrame size")
#                 return current_row
#             node = node_dict[node_id]
#             df.iloc[current_row, node['level']] = node['label']
#             row_idx = current_row
#             for child_id in children.get(node_id, []):
#                 row_idx += 1
#                 row_idx = place_node(child_id, row_idx)
#             return row_idx
        
#         for node in [n for n in sorted_nodes if n['level'] == 0]:
#             row_idx = place_node(node['id'], row_idx)
#             row_idx += 1
        
#         df = df.dropna(how='all').fillna('')
        
#         return df
    
#     except ValueError as e:
#         logging.error(f"Value error: {e}")
#         return pd.DataFrame()
#     except Exception as e:
#         logging.error(f"Unexpected error: {e}")
#         return pd.DataFrame()

# def mind_map_page():
#     st.title("Mind Map Creator")
    
#     if 'mindmap_data' not in st.session_state:
#         st.session_state.mindmap_data = {'nodes': [{'id': 0, 'label': 'Start', 'color': '#ffcccb', 'level': 0, 'priority': 1}], 'edges': []}
#     if 'node_counter' not in st.session_state:
#         st.session_state.node_counter = 1
#     if 'current_db' not in st.session_state:
#         st.session_state.current_db = None

#     with st.container():
#         uploaded_file = st.file_uploader("Import Mind Map", type=['xlsx'], help="Upload an Excel file to import a mind map")
#         if uploaded_file:
#             mindmap_data, node_count = excel_to_mindmap_data(uploaded_file)
#             st.session_state.mindmap_data = mindmap_data
#             st.session_state.node_counter = node_count
#             st.session_state.current_db = None  # Reset current_db when importing new data
#             st.success("Mind map imported successfully")

#     selected = option_menu(
#         menu_title=None,
#         options=["Add", "Connect", "Edit/Del", "Feedback", "Clear", "View Table", "Save DB", "Load DB", "Delete DB"],
#         icons=['plus-square', 'link', 'pencil-square', 'arrow-return-right', 'trash', 'table', 'save', 'folder', 'trash2'],
#         orientation='horizontal',
#         styles={
#             "container": {"padding": "10px", "background-color": "#ffffff", "border-radius": "8px", "##box-shadow": "0 2px 4px rgba(0,0,0,0.05)"},
#             "icon": {"color": "#1d1d1f", "font-size": "16px"},
#             "nav-link": {"font-size": "14px", "text-align": "center", "margin": "0px", "--hover-color": "#e5e5ea"},
#             "nav-link-selected": {"background-color": "#007aff", "color": "white", "border-radius": "6px"},
#         }
#     )

#     with st.container():
#         if selected == "Add":
#             st.subheader("Add Node")
#             label = st.text_input("Node Text", placeholder="Enter node label")
#             priority = st.number_input("Priority", min_value=1, value=1, step=1)
#             level = st.number_input("Level", min_value=0, value=0, step=1)
#             color = st.color_picker("Color", "#ffcccb")
#             if st.button("Add Node") and label:
#                 st.session_state.mindmap_data['nodes'].append({
#                     'id': st.session_state.node_counter,
#                     'label': label,
#                     'priority': priority,
#                     'level': level,
#                     'color': color,
#                 })
#                 st.session_state.node_counter += 1
#                 st.success("Node added successfully")
                
#                 # Auto-save to current database or prompt for new database name
#                 if st.session_state.current_db:
#                     save_mindmap_to_sqlite(st.session_state.mindmap_data, st.session_state.current_db)
#                     st.success(f"Automatically saved to {st.session_state.current_db}")
#                 else:
#                     new_db_name = st.text_input("Enter new database name to save", "mindmap.db", placeholder="Enter database name (e.g., mindmap.db)")
#                     if st.button("Save to New Database"):
#                         if new_db_name:
#                             st.session_state.current_db = new_db_name
#                             save_mindmap_to_sqlite(st.session_state.mindmap_data, new_db_name)
#                             st.success(f"Saved to new database {new_db_name}")
#                         else:
#                             st.error("Please enter a valid database name")
            
#             if st.session_state.mindmap_data['nodes']:
#                 df = create_dataframe(st.session_state.mindmap_data)
#                 st.subheader("Current Nodes")
#                 st.dataframe(df, use_container_width=True)

#         elif selected == "Connect":
#             st.subheader("Manage Connections")
#             action = st.radio("Choose Action", ["Connect", "Disconnect"], horizontal=True)

#             nodes = st.session_state.mindmap_data['nodes']
#             edges = st.session_state.mindmap_data['edges']
#             node_options = [f"{n['id']}. {n['label']}" for n in nodes]

#             if len(node_options) >= 2:
#                 from_node = st.selectbox("From Node", node_options, key="connect_from")
#                 to_node = st.selectbox("To Node", node_options, key="connect_to")
#                 from_id, to_id = int(from_node.split('.')[0]), int(to_node.split('.')[0])

#                 if from_id == to_id:
#                     st.warning("Cannot connect a node to itself")
#                 else:
#                     if action == "Connect":
#                         if st.button("Connect Nodes"):
#                             new_edge = {'from': from_id, 'to': to_id, 'feedback': False}
#                             if new_edge not in edges:
#                                 st.session_state.mindmap_data['edges'].append(new_edge)
#                                 st.success("Nodes connected")
#                             else:
#                                 st.info("These nodes are already connected")
#                     else:
#                         edge_to_remove = {'from': from_id, 'to': to_id, 'feedback': False}
#                         edge_to_remove_feedback = {'from': from_id, 'to': to_id, 'feedback': True}
#                         if st.button("Disconnect Nodes"):
#                             if edge_to_remove in edges:
#                                 st.session_state.mindmap_data['edges'].remove(edge_to_remove)
#                                 st.success(f"Disconnected {from_id} → {to_id}")
#                             elif edge_to_remove_feedback in edges:
#                                 st.session_state.mindmap_data['edges'].remove(edge_to_remove_feedback)
#                                 st.success(f"Disconnected feedback edge {from_id} → {to_id}")
#                             else:
#                                 st.error("No connection exists between these nodes")

#         elif selected == "Edit/Del":
#             st.subheader("Edit or Delete Node")
#             nodes = st.session_state.mindmap_data['nodes']
#             node_ids = [n['id'] for n in nodes]
#             if node_ids:
#                 edit_id = st.selectbox("Select Node ID", node_ids)
#                 node = next(n for n in nodes if n['id'] == edit_id)
#                 label = st.text_input("Label", node['label'])
#                 color = st.color_picker("Color", node['color'])
#                 level = st.number_input("Level", min_value=0, value=node['level'], step=1)
#                 priority = st.number_input("Priority", min_value=1, value=node['priority'], step=1)
#                 col1, col2 = st.columns(2)
#                 with col1:
#                     if st.button("Update Node"):
#                         node.update({'label': label, 'color': color, 'level': level, 'priority': priority})
#                         st.success("Node updated")
#                 with col2:
#                     if st.button("Delete Node"):
#                         st.session_state.mindmap_data['nodes'] = [n for n in nodes if n['id'] != edit_id]
#                         st.session_state.mindmap_data['edges'] = [e for e in st.session_state.mindmap_data['edges'] if e['from'] != edit_id and e['to'] != edit_id]
#                         st.success("Node deleted")

#         elif selected == "Feedback":
#             st.subheader("Add Feedback Edge")
#             nodes = st.session_state.mindmap_data['nodes']
#             node_options = [f"{n['id']}. {n['label']}" for n in nodes]
#             from_node = st.selectbox("From Node", node_options)
#             to_node = st.selectbox("To Node", node_options)
#             from_id, to_id = int(from_node.split('.')[0]), int(to_node.split('.')[0])
#             if st.button("Add Feedback Edge"):
#                 if from_id != to_id:
#                     new_edge = {'from': from_id, 'to': to_id, 'feedback': True}
#                     if new_edge not in st.session_state.mindmap_data['edges']:
#                         st.session_state.mindmap_data['edges'].append(new_edge)
#                         st.success("Feedback edge added")
#                 else:
#                     st.warning("Cannot add feedback edge to the same node")

#         elif selected == "Clear":
#             if st.button("Clear Mind Map"):
#                 st.session_state.mindmap_data = {'nodes': [{'id': 0, 'label': 'Start', 'color': '#ffcccb', 'level': 0, 'priority': 1}], 'edges': []}
#                 st.session_state.node_counter = 1
#                 st.session_state.current_db = None
#                 st.success("Mind map cleared")

#         elif selected == "View Table":
#             st.subheader("Mind Map Data")
#             df = create_dataframe(st.session_state.mindmap_data)
#             st.dataframe(df, use_container_width=True)

#         elif selected == "Save DB":
#             st.subheader("Save to Database")
#             df = create_dataframe(st.session_state.mindmap_data)
#             if len(st.session_state.mindmap_data['nodes']) == 0:
#                 st.error("No mind map data to save")
#             else:
#                 db_name = st.text_input("Database Name", "mindmap.db", placeholder="Enter database name")
#                 if db_name and st.button("Save to Database"):
#                     save_mindmap_to_sqlite(st.session_state.mindmap_data, db_name)
#                     st.session_state.current_db = db_name
#                     st.success(f"Saved to {db_name}")

#         elif selected == "Load DB":
#             st.subheader("Load from Database")
#             db_files = [f for f in os.listdir('.') if f.endswith('.db')]
#             if db_files:
#                 selected_db = st.selectbox("Select Database", db_files)
#                 if st.button("Load Database"):
#                     mindmap_data = fetch_mindmap_from_sqlite(selected_db)
#                     df = create_dataframe(mindmap_data)
#                     st.dataframe(df, use_container_width=True)
#                     st.session_state.mindmap_data = mindmap_data
#                     st.session_state.current_db = selected_db
#                     if mindmap_data['nodes']:
#                         st.session_state.node_counter = max(node['id'] for node in mindmap_data['nodes']) + 1
#                     else:
#                         st.session_state.node_counter = 1
#                     st.success(f"Loaded mind map from {selected_db}")
#             else:
#                 st.info("No database files found")

#         elif selected == "Delete DB":
#             st.subheader("Delete Database")
#             db_files = [f for f in os.listdir('.') if f.endswith('.db')]
#             if db_files:
#                 del_db = st.selectbox("Select Database to Delete", db_files)
#                 if st.button("Delete Database"):
#                     os.remove(del_db)
#                     if st.session_state.current_db == del_db:
#                         st.session_state.current_db = None
#                     st.success(f"Deleted {del_db}")

#     if selected not in ["View Table", "Save DB", "Delete DB"] and st.session_state.mindmap_data['nodes']:
#         st.subheader("Mind Map Visualization")
#         dot = create_mindmap_graph(st.session_state.mindmap_data)
#         st.graphviz_chart(dot, use_container_width=True)

#     with st.container():
#         if st.button("Export to Excel"):
#             excel_df = mindmap_to_excel_data(st.session_state.mindmap_data)
#             buffer = io.BytesIO()
#             excel_df.to_excel(buffer, index=False, header=False)
#             buffer.seek(0)
#             st.download_button(
#                 label="Download Mind Map as Excel",
#                 data=buffer,
#                 file_name="mindmap.xlsx",
#                 mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
#             )

# if __name__ == "__main__":
#     mind_map_page()


###### arrow pointing down

# import streamlit as st
# import graphviz
# import sqlite3
# import pandas as pd
# import os

# # ---------- DATABASE SETUP ----------
# DB_PATH = "mindmap.db"

# def init_db():
#     """Create tables if they don’t exist."""
#     conn = sqlite3.connect(DB_PATH)
#     c = conn.cursor()
#     c.execute("""
#         CREATE TABLE IF NOT EXISTS nodes (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             label TEXT,
#             priority TEXT
#         )
#     """)
#     c.execute("""
#         CREATE TABLE IF NOT EXISTS edges (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             source INTEGER,
#             target INTEGER
#         )
#     """)
#     conn.commit()
#     conn.close()

# def get_nodes():
#     conn = sqlite3.connect(DB_PATH)
#     df = pd.read_sql("SELECT * FROM nodes", conn)
#     conn.close()
#     return df.to_dict(orient="records")

# def get_edges():
#     conn = sqlite3.connect(DB_PATH)
#     df = pd.read_sql("SELECT * FROM edges", conn)
#     conn.close()
#     return df.to_dict(orient="records")

# def add_node(label, priority):
#     conn = sqlite3.connect(DB_PATH)
#     c = conn.cursor()
#     c.execute("INSERT INTO nodes (label, priority) VALUES (?, ?)", (label, priority))
#     conn.commit()
#     conn.close()

# def add_edge(source, target):
#     conn = sqlite3.connect(DB_PATH)
#     c = conn.cursor()
#     c.execute("INSERT INTO edges (source, target) VALUES (?, ?)", (source, target))
#     conn.commit()
#     conn.close()

# def delete_all():
#     conn = sqlite3.connect(DB_PATH)
#     c = conn.cursor()
#     c.execute("DELETE FROM nodes")
#     c.execute("DELETE FROM edges")
#     conn.commit()
#     conn.close()


# # ---------- GRAPH CREATION ----------
# def create_mindmap_graph(nodes, edges):
#     """Render Graphviz mind map with top-to-bottom arrows."""
#     dot = graphviz.Digraph(format="svg")
#     dot.attr(rankdir='TB', bgcolor='transparent')  # Top-to-Bottom flow

#     dot.attr('node', shape='box', style='filled,rounded',
#              color='#555555', fillcolor='#f8f9fa',
#              fontname='Helvetica', fontsize='12')

#     for node in nodes:
#         label = node.get("label", "")
#         priority = node.get("priority", "")
#         node_label = f"{label}\n({priority})" if priority else label
#         dot.node(str(node["id"]), node_label)

#     for edge in edges:
#         dot.edge(str(edge["source"]), str(edge["target"]),
#                  arrowhead='normal', color='#999999')

#     return dot


# # ---------- STREAMLIT APP ----------
# st.set_page_config(page_title="Mind Map (SQLite)", layout="wide")

# st.title("🧠 Downward Flow Mind Map (with Database)")
# st.markdown("Create and visualize a mind map with arrows flowing **top → bottom**, saved in **SQLite**.")

# # Initialize database
# init_db()

# # Sidebar controls
# st.sidebar.header("🧩 Add or Edit Mind Map Elements")

# # ---------- Add Node ----------
# st.sidebar.subheader("Add Node")
# new_label = st.sidebar.text_input("Label")
# new_priority = st.sidebar.selectbox("Priority", ["", "High", "Medium", "Low"])
# if st.sidebar.button("Add Node"):
#     if new_label:
#         add_node(new_label, new_priority)
#         st.success(f"✅ Added node: {new_label}")
#     else:
#         st.warning("Please enter a label before adding a node.")

# # ---------- Add Edge ----------
# nodes_list = get_nodes()
# if nodes_list:
#     st.sidebar.subheader("Add Edge")
#     node_options = {n["label"]: n["id"] for n in nodes_list}
#     source_label = st.sidebar.selectbox("Source", list(node_options.keys()))
#     target_label = st.sidebar.selectbox("Target", list(node_options.keys()))
#     if st.sidebar.button("Add Edge"):
#         source_id = node_options[source_label]
#         target_id = node_options[target_label]
#         if source_id != target_id:
#             add_edge(source_id, target_id)
#             st.success(f"✅ Added edge: {source_label} → {target_label}")
#         else:
#             st.warning("Cannot connect a node to itself.")

# # ---------- Delete All ----------
# if st.sidebar.button("🗑️ Clear All Data"):
#     delete_all()
#     st.warning("All nodes and edges deleted.")

# # ---------- Load Data ----------
# nodes = get_nodes()
# edges = get_edges()

# # ---------- Display Mind Map ----------
# st.subheader("📊 Mind Map Visualization")
# if nodes:
#     graph = create_mindmap_graph(nodes, edges)
#     st.graphviz_chart(graph.source, use_container_width=True)
# else:
#     st.info("No nodes found. Add one from the sidebar to begin!")

# # ---------- View Tables ----------
# with st.expander("🧾 View Data Tables"):
#     st.write("### Nodes")
#     st.dataframe(pd.DataFrame(nodes))
#     st.write("### Edges")
#     st.dataframe(pd.DataFrame(edges))

#### add del edge


# import streamlit as st
# import graphviz
# import sqlite3
# import pandas as pd
# import os

# # ---------- DATABASE SETUP ----------
# DB_PATH = "mindmap.db"

# def init_db():
#     """Create tables if they don’t exist."""
#     conn = sqlite3.connect(DB_PATH)
#     c = conn.cursor()
#     c.execute("""
#         CREATE TABLE IF NOT EXISTS nodes (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             label TEXT,
#             priority TEXT
#         )
#     """)
#     c.execute("""
#         CREATE TABLE IF NOT EXISTS edges (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             source INTEGER,
#             target INTEGER
#         )
#     """)
#     conn.commit()
#     conn.close()

# def get_nodes():
#     conn = sqlite3.connect(DB_PATH)
#     df = pd.read_sql("SELECT * FROM nodes", conn)
#     conn.close()
#     return df.to_dict(orient="records")

# def get_edges():
#     conn = sqlite3.connect(DB_PATH)
#     df = pd.read_sql("SELECT * FROM edges", conn)
#     conn.close()
#     return df.to_dict(orient="records")

# def add_node(label, priority):
#     conn = sqlite3.connect(DB_PATH)
#     c = conn.cursor()
#     c.execute("INSERT INTO nodes (label, priority) VALUES (?, ?)", (label, priority))
#     conn.commit()
#     conn.close()

# def add_edge(source, target):
#     conn = sqlite3.connect(DB_PATH)
#     c = conn.cursor()
#     c.execute("INSERT INTO edges (source, target) VALUES (?, ?)", (source, target))
#     conn.commit()
#     conn.close()

# def delete_edge(source, target):
#     """Delete a specific edge from source → target."""
#     conn = sqlite3.connect(DB_PATH)
#     c = conn.cursor()
#     c.execute("DELETE FROM edges WHERE source=? AND target=?", (source, target))
#     conn.commit()
#     conn.close()

# def update_node_label(node_id, new_label):
#     """Update node label by ID."""
#     conn = sqlite3.connect(DB_PATH)
#     c = conn.cursor()
#     c.execute("UPDATE nodes SET label=? WHERE id=?", (new_label, node_id))
#     conn.commit()
#     conn.close()

# def delete_all():
#     conn = sqlite3.connect(DB_PATH)
#     c = conn.cursor()
#     c.execute("DELETE FROM nodes")
#     c.execute("DELETE FROM edges")
#     conn.commit()
#     conn.close()

# # ---------- GRAPH CREATION ----------
# def create_mindmap_graph(nodes, edges):
#     """Render Graphviz mind map with top-to-bottom arrows."""
#     dot = graphviz.Digraph(format="svg")
#     dot.attr(rankdir='TB', bgcolor='transparent')  # Top-to-Bottom flow

#     dot.attr('node', shape='box', style='filled,rounded',
#              color='#555555', fillcolor='#f8f9fa',
#              fontname='Helvetica', fontsize='12')

#     for node in nodes:
#         label = node.get("label", "")
#         priority = node.get("priority", "")
#         node_label = f"{label}\n({priority})" if priority else label
#         dot.node(str(node["id"]), node_label)

#     for edge in edges:
#         dot.edge(str(edge["source"]), str(edge["target"]),
#                  arrowhead='normal', color='#999999')

#     return dot


# # ---------- STREAMLIT APP ----------
# st.set_page_config(page_title="Mind Map (SQLite)", layout="wide")

# st.title("🧠 Downward Flow Mind Map (with Database)")
# st.markdown("Create and visualize a mind map with arrows flowing **top → bottom**, saved in **SQLite**.")

# # Initialize database
# init_db()

# # Sidebar controls
# st.sidebar.header("🧩 Add or Edit Mind Map Elements")

# # ---------- Add Node ----------
# st.sidebar.subheader("Add Node")
# new_label = st.sidebar.text_input("Label")
# new_priority = st.sidebar.selectbox("Priority", ["", "High", "Medium", "Low"])
# if st.sidebar.button("Add Node"):
#     if new_label:
#         add_node(new_label, new_priority)
#         st.success(f"✅ Added node: {new_label}")
#     else:
#         st.warning("Please enter a label before adding a node.")

# # ---------- Edit Node ----------
# nodes_list = get_nodes()
# if nodes_list:
#     st.sidebar.subheader("Edit Node Label")
#     node_options = {n["label"]: n["id"] for n in nodes_list}
#     selected_label = st.sidebar.selectbox("Select Node", list(node_options.keys()), key="edit_node")
#     new_label_text = st.sidebar.text_input("New Label", value=selected_label, key="edit_label_input")

#     if st.sidebar.button("✏️ Update Label"):
#         node_id = node_options[selected_label]
#         if new_label_text.strip():
#             update_node_label(node_id, new_label_text.strip())
#             st.success(f"✅ Updated node label: '{selected_label}' → '{new_label_text.strip()}'")
#         else:
#             st.warning("Label cannot be empty.")

# # ---------- Add Edge ----------
# if nodes_list:
#     st.sidebar.subheader("Add Edge")
#     node_options = {n["label"]: n["id"] for n in nodes_list}
#     source_label = st.sidebar.selectbox("Source", list(node_options.keys()), key="add_source")
#     target_label = st.sidebar.selectbox("Target", list(node_options.keys()), key="add_target")
#     if st.sidebar.button("Add Edge"):
#         source_id = node_options[source_label]
#         target_id = node_options[target_label]
#         if source_id != target_id:
#             add_edge(source_id, target_id)
#             st.success(f"✅ Added edge: {source_label} → {target_label}")
#         else:
#             st.warning("Cannot connect a node to itself.")

# # ---------- Delete Edge ----------
# edges_list = get_edges()
# if edges_list:
#     st.sidebar.subheader("Delete Edge")
#     id_to_label = {n["id"]: n["label"] for n in nodes_list}
#     edge_labels = {
#         f"{id_to_label.get(e['source'], '?')} → {id_to_label.get(e['target'], '?')}": (e['source'], e['target'])
#         for e in edges_list
#     }

#     selected_edge_label = st.sidebar.selectbox("Select Edge to Delete", list(edge_labels.keys()))
#     if st.sidebar.button("❌ Delete Edge"):
#         source, target = edge_labels[selected_edge_label]
#         delete_edge(source, target)
#         st.warning(f"🗑️ Deleted edge: {selected_edge_label}")

# # ---------- Delete All ----------
# if st.sidebar.button("🗑️ Clear All Data"):
#     delete_all()
#     st.warning("All nodes and edges deleted.")

# # ---------- Load Data ----------
# nodes = get_nodes()
# edges = get_edges()

# # ---------- Display Mind Map ----------
# st.subheader("📊 Mind Map Visualization")
# if nodes:
#     graph = create_mindmap_graph(nodes, edges)
#     st.graphviz_chart(graph.source, use_container_width=True)
# else:
#     st.info("No nodes found. Add one from the sidebar to begin!")

# # ---------- View Tables ----------
# with st.expander("🧾 View Data Tables"):
#     st.write("### Nodes")
#     st.dataframe(pd.DataFrame(nodes))
#     st.write("### Edges")
#     st.dataframe(pd.DataFrame(edges))


###### add database to create
#### flowchart https://grok.com/share/bGVnYWN5LWNvcHk%3D_2d8c9e1d-6c13-4532-85e3-c0379469878c 

import streamlit as st
import graphviz
import sqlite3
import pandas as pd
import os

# ---------- STREAMLIT APP ----------
st.set_page_config(page_title="Mind Map (SQLite)", layout="wide")
st.title("🧠 Downward Flow Mind Map (with Database)")
st.markdown("Create and visualize a mind map with arrows flowing **top → bottom**, saved in **SQLite**.")

# ---------- DATABASE FILE SELECTION ----------
st.sidebar.header("🗄️ Database Management")

# Initialize DB_PATH in session_state
if "DB_PATH" not in st.session_state:
    st.session_state.DB_PATH = "mindmap.db"  # default

# List existing .db files
db_files = [f for f in os.listdir() if f.endswith(".db")]
db_files.append("Create New Database")

selected_db = st.sidebar.selectbox("Select Database", db_files, index=0)

if selected_db == "Create New Database":
    new_db_name = st.sidebar.text_input("New Database Name", value="my_mindmap.db")
    if st.sidebar.button("✅ Create Database"):
        st.session_state.DB_PATH = new_db_name
        if not os.path.exists(st.session_state.DB_PATH):
            open(st.session_state.DB_PATH, "w").close()
        st.success(f"Database '{st.session_state.DB_PATH}' created and selected.")
else:
    st.session_state.DB_PATH = selected_db
    st.info(f"Using database: {st.session_state.DB_PATH}")

# ---------- DATABASE FUNCTIONS ----------
def init_db():
    """Create tables if they don’t exist."""
    conn = sqlite3.connect(st.session_state.DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT,
            priority TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source INTEGER,
            target INTEGER
        )
    """)
    conn.commit()
    conn.close()

def get_nodes():
    conn = sqlite3.connect(st.session_state.DB_PATH)
    df = pd.read_sql("SELECT * FROM nodes", conn)
    conn.close()
    return df.to_dict(orient="records")

def get_edges():
    conn = sqlite3.connect(st.session_state.DB_PATH)
    df = pd.read_sql("SELECT * FROM edges", conn)
    conn.close()
    return df.to_dict(orient="records")

def add_node(label, priority):
    conn = sqlite3.connect(st.session_state.DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO nodes (label, priority) VALUES (?, ?)", (label, priority))
    conn.commit()
    conn.close()

def add_edge(source, target):
    conn = sqlite3.connect(st.session_state.DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO edges (source, target) VALUES (?, ?)", (source, target))
    conn.commit()
    conn.close()

def delete_edge(source, target):
    conn = sqlite3.connect(st.session_state.DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM edges WHERE source=? AND target=?", (source, target))
    conn.commit()
    conn.close()

def update_node_label(node_id, new_label):
    conn = sqlite3.connect(st.session_state.DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE nodes SET label=? WHERE id=?", (new_label, node_id))
    conn.commit()
    conn.close()

def delete_all():
    conn = sqlite3.connect(st.session_state.DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM nodes")
    c.execute("DELETE FROM edges")
    conn.commit()
    conn.close()

# Initialize database after selection
init_db()

# ---------- GRAPH CREATION ----------
def create_mindmap_graph(nodes, edges):
    dot = graphviz.Digraph(format="svg")
    dot.attr(rankdir='TB', bgcolor='transparent')
    dot.attr('node', shape='box', style='filled,rounded',
             color='#555555', fillcolor='#f8f9fa',
             fontname='Helvetica', fontsize='12')

    for node in nodes:
        label = node.get("label", "")
        priority = node.get("priority", "")
        node_label = f"{label}\n({priority})" if priority else label
        dot.node(str(node["id"]), node_label)

    for edge in edges:
        dot.edge(str(edge["source"]), str(edge["target"]),
                 arrowhead='normal', color='#999999')

    return dot

# ---------- SIDEBAR: Mind Map Controls ----------
st.sidebar.header("🧩 Add or Edit Mind Map Elements")

# Add Node
st.sidebar.subheader("Add Node")
new_label = st.sidebar.text_input("Label")
new_priority = st.sidebar.selectbox("Priority", ["", "High", "Medium", "Low"])
if st.sidebar.button("Add Node"):
    if new_label:
        add_node(new_label, new_priority)
        st.success(f"✅ Added node: {new_label}")
    else:
        st.warning("Please enter a label before adding a node.")

# Edit Node
nodes_list = get_nodes()
if nodes_list:
    st.sidebar.subheader("Edit Node Label")
    node_options = {n["label"]: n["id"] for n in nodes_list}
    selected_label = st.sidebar.selectbox("Select Node", list(node_options.keys()), key="edit_node")
    new_label_text = st.sidebar.text_input("New Label", value=selected_label, key="edit_label_input")
    if st.sidebar.button("✏️ Update Label"):
        node_id = node_options[selected_label]
        if new_label_text.strip():
            update_node_label(node_id, new_label_text.strip())
            st.success(f"✅ Updated node label: '{selected_label}' → '{new_label_text.strip()}'")
        else:
            st.warning("Label cannot be empty.")

# Add Edge
if nodes_list:
    st.sidebar.subheader("Add Edge")
    node_options = {n["label"]: n["id"] for n in nodes_list}
    source_label = st.sidebar.selectbox("Source", list(node_options.keys()), key="add_source")
    target_label = st.sidebar.selectbox("Target", list(node_options.keys()), key="add_target")
    if st.sidebar.button("Add Edge"):
        source_id = node_options[source_label]
        target_id = node_options[target_label]
        if source_id != target_id:
            add_edge(source_id, target_id)
            st.success(f"✅ Added edge: {source_label} → {target_label}")
        else:
            st.warning("Cannot connect a node to itself.")

# Delete Edge
edges_list = get_edges()
if edges_list:
    st.sidebar.subheader("Delete Edge")
    id_to_label = {n["id"]: n["label"] for n in nodes_list}
    edge_labels = {
        f"{id_to_label.get(e['source'], '?')} → {id_to_label.get(e['target'], '?')}": (e['source'], e['target'])
        for e in edges_list
    }
    selected_edge_label = st.sidebar.selectbox("Select Edge to Delete", list(edge_labels.keys()))
    if st.sidebar.button("❌ Delete Edge"):
        source, target = edge_labels[selected_edge_label]
        delete_edge(source, target)
        st.warning(f"🗑️ Deleted edge: {selected_edge_label}")

# Delete All
if st.sidebar.button("🗑️ Clear All Data"):
    delete_all()
    st.warning("All nodes and edges deleted.")

# ---------- Load Data ----------
nodes = get_nodes()
edges = get_edges()

# ---------- Display Mind Map ----------
st.subheader("📊 Mind Map Visualization")
if nodes:
    graph = create_mindmap_graph(nodes, edges)
    st.graphviz_chart(graph.source, use_container_width=True)
else:
    st.info("No nodes found. Add one from the sidebar to begin!")

# View Tables
with st.expander("🧾 View Data Tables"):
    st.write("### Nodes")
    st.dataframe(pd.DataFrame(nodes))
    st.write("### Edges")
    st.dataframe(pd.DataFrame(edges))


##### interactive arrow pointing down

# import streamlit as st
# import json
# import random

# st.set_page_config(page_title="Adaptive Mind Map", layout="wide")
# st.title("🧠 Interactive Mind Map (Rectangles + Rename + Recolor)")

# # --- Initialize session state ---
# if "nodes" not in st.session_state:
#     st.session_state.nodes = [{"id": "Central Idea", "x": 400, "y": 300, "color": "#007aff"}]
# if "links" not in st.session_state:
#     st.session_state.links = []

# # --- Sidebar Controls ---
# st.sidebar.header("⚙️ Mind Map Controls")

# # Add node
# new_node = st.sidebar.text_input("Add new node:")
# if st.sidebar.button("➕ Add Node"):
#     if new_node and new_node not in [n["id"] for n in st.session_state.nodes]:
#         st.session_state.nodes.append({
#             "id": new_node,
#             "x": random.randint(100, 700),
#             "y": random.randint(100, 500),
#             "color": "#007aff"
#         })
#         st.sidebar.success(f"Node '{new_node}' added.")
#     else:
#         st.sidebar.warning("Enter a unique node name.")

# # Connect nodes
# st.sidebar.subheader("🔗 Connect Nodes")
# subjects = st.sidebar.multiselect("Select subject node(s):", [n["id"] for n in st.session_state.nodes])
# targets = st.sidebar.multiselect("Select target node(s):", [n["id"] for n in st.session_state.nodes])
# if st.sidebar.button("🔄 Connect"):
#     for s in subjects:
#         for t in targets:
#             if s != t and not any(l["source"] == s and l["target"] == t for l in st.session_state.links):
#                 st.session_state.links.append({"source": s, "target": t})
#     st.sidebar.success("Connection(s) added.")

# # Remove node
# remove_node = st.sidebar.selectbox("🗑️ Remove node:", ["(none)"] + [n["id"] for n in st.session_state.nodes if n["id"] != "Central Idea"])
# if st.sidebar.button("🗑️ Remove Selected"):
#     if remove_node != "(none)":
#         st.session_state.nodes = [n for n in st.session_state.nodes if n["id"] != remove_node]
#         st.session_state.links = [
#             l for l in st.session_state.links
#             if l["source"] != remove_node and l["target"] != remove_node
#         ]
#         st.sidebar.success(f"Node '{remove_node}' removed.")

# # --- D3 Data ---
# data = {"nodes": st.session_state.nodes, "links": st.session_state.links}
# data_json = json.dumps(data)

# # --- D3 Visualization ---
# d3_code = rf"""
# <div id="mindmap"></div>
# <script src="https://d3js.org/d3.v7.min.js"></script>
# <script>
# const data = {data_json};
# const width = 950, height = 650;

# const svg = d3.select("#mindmap")
#   .append("svg")
#   .attr("width", width)
#   .attr("height", height)
#   .style("border", "1px solid #aaa");

# // Arrow marker
# svg.append("defs").selectAll("marker")
#   .data(["arrow"])
#   .enter().append("marker")
#   .attr("id", d => d)
#   .attr("viewBox", "0 -5 10 10")
#   .attr("refX", 28)
#   .attr("refY", 0)
#   .attr("markerWidth", 6)
#   .attr("markerHeight", 6)
#   .attr("orient", "auto")
#   .append("path")
#   .attr("d", "M0,-5L10,0L0,5")
#   .attr("fill", "#888");

# // Links
# const link = svg.selectAll(".link")
#   .data(data.links)
#   .enter().append("line")
#   .attr("class", "link")
#   .attr("stroke", "#999")
#   .attr("stroke-width", 2)
#   .attr("marker-end", "url(#arrow)");

# // Groups
# const node = svg.selectAll(".node")
#   .data(data.nodes)
#   .enter().append("g")
#   .attr("class", "node")
#   .call(d3.drag()
#     .on("start", dragstarted)
#     .on("drag", dragged)
#     .on("end", dragended)
#   )
#   .on("click", nodeClick);

# // Text first to measure width
# const label = node.append("text")
#   .text(d => d.id)
#   .attr("text-anchor", "middle")
#   .attr("alignment-baseline", "middle")
#   .attr("fill", "white")
#   .attr("font-size", "13px")
#   .style("font-family", "sans-serif");

# // Compute dynamic rect size
# node.each(function(d) {{
#   const textWidth = this.querySelector("text").getBBox().width;
#   const padding = 16;
#   d.rectWidth = textWidth + padding * 2;
#   d.rectHeight = 40;
# }});

# // Add rectangles behind labels
# const rect = node.insert("rect", "text")
#   .attr("rx", 10)
#   .attr("ry", 10)
#   .attr("x", d => -d.rectWidth / 2)
#   .attr("y", d => -d.rectHeight / 2)
#   .attr("width", d => d.rectWidth)
#   .attr("height", d => d.rectHeight)
#   .attr("fill", d => d.color)
#   .attr("stroke", "#004a99")
#   .attr("stroke-width", 2);

# const simulation = d3.forceSimulation(data.nodes)
#   .force("link", d3.forceLink(data.links).id(d => d.id).distance(160))
#   .force("charge", d3.forceManyBody().strength(-400))
#   .force("center", d3.forceCenter(width / 2, height / 2))
#   .on("tick", ticked);

# function ticked() {{
#   link
#     .attr("x1", d => d.source.x)
#     .attr("y1", d => d.source.y)
#     .attr("x2", d => d.target.x)
#     .attr("y2", d => d.target.y);

#   node.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
# }}

# function dragstarted(event, d) {{
#   if (!event.active) simulation.alphaTarget(0.3).restart();
#   d.fx = d.x; d.fy = d.y;
# }}

# function dragged(event, d) {{
#   d.fx = event.x; d.fy = event.y;
# }}

# function dragended(event, d) {{
#   if (!event.active) simulation.alphaTarget(0);
#   d.fx = null; d.fy = null;
# }}

# function nodeClick(event, d) {{
#   if (event.shiftKey) {{
#     // ⇧ Shift + Click → random new color
#     const randomColor = `hsl(${{Math.random() * 360}}, 70%, 50%)`;
#     d3.select(this).select("rect").attr("fill", randomColor);
#     d.color = randomColor;
#   }} else {{
#     // Click → rename
#     const newName = prompt("Rename node:", d.id);
#     if (newName && newName.trim() !== "") {{
#       d.id = newName.trim();
#       d3.select(this).select("text").text(d.id);
#       const textWidth = this.querySelector("text").getBBox().width;
#       const padding = 16;
#       d.rectWidth = textWidth + padding * 2;
#       d3.select(this).select("rect")
#         .attr("x", -d.rectWidth / 2)
#         .attr("width", d.rectWidth);
#       simulation.alpha(0.5).restart();
#     }}
#   }}
# }}
# </script>
# """

# st.components.v1.html(d3_code, height=700)

# # --- Show JSON data ---
# with st.expander("🧩 Mind Map Data"):
#     st.json({"nodes": st.session_state.nodes, "links": st.session_state.links})
