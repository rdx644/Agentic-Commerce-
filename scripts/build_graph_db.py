import os
import ast
import sqlite3
import json
from pathlib import Path

def init_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            type TEXT,
            name TEXT,
            file_path TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS edges (
            source TEXT,
            target TEXT,
            relationship TEXT,
            PRIMARY KEY (source, target, relationship),
            FOREIGN KEY(source) REFERENCES nodes(id),
            FOREIGN KEY(target) REFERENCES nodes(id)
        )
    ''')
    conn.commit()
    return conn

def extract_info(file_path, project_root):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        tree = ast.parse(content)
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None

    # Module name based on path
    rel_path = file_path.relative_to(project_root)
    module_name = str(rel_path.with_suffix('')).replace(os.sep, '.')
    
    info = {
        'module_name': module_name,
        'file_path': str(rel_path),
        'imports': [],
        'classes': [],
        'functions': []
    }
    
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                info['imports'].append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module if node.module else ''
            info['imports'].append(module)
        elif isinstance(node, ast.ClassDef):
            info['classes'].append(node.name)
        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            info['functions'].append(node.name)
            
    return info

def build_graph(project_root, db_path):
    conn = init_db(db_path)
    cursor = conn.cursor()
    
    src_dir = project_root / 'src'
    
    all_info = []
    
    # 1. Parse all files and create Module nodes
    for py_file in src_dir.rglob('*.py'):
        if py_file.name == '__init__.py' and py_file.stat().st_size == 0:
            continue
        info = extract_info(py_file, project_root)
        if info:
            all_info.append(info)
            cursor.execute(
                "INSERT OR REPLACE INTO nodes (id, type, name, file_path) VALUES (?, ?, ?, ?)",
                (info['module_name'], 'module', info['module_name'], info['file_path'])
            )
            
            # Create nodes for classes and functions
            for cls in info['classes']:
                cls_id = f"{info['module_name']}.{cls}"
                cursor.execute(
                    "INSERT OR REPLACE INTO nodes (id, type, name, file_path) VALUES (?, ?, ?, ?)",
                    (cls_id, 'class', cls, info['file_path'])
                )
                cursor.execute(
                    "INSERT OR IGNORE INTO edges (source, target, relationship) VALUES (?, ?, ?)",
                    (info['module_name'], cls_id, 'CONTAINS')
                )
                
            for func in info['functions']:
                func_id = f"{info['module_name']}.{func}"
                cursor.execute(
                    "INSERT OR REPLACE INTO nodes (id, type, name, file_path) VALUES (?, ?, ?, ?)",
                    (func_id, 'function', func, info['file_path'])
                )
                cursor.execute(
                    "INSERT OR IGNORE INTO edges (source, target, relationship) VALUES (?, ?, ?)",
                    (info['module_name'], func_id, 'CONTAINS')
                )

    # 2. Add edges for imports
    for info in all_info:
        for imp in info['imports']:
            # Try to resolve to local project module if it starts with 'src.' or matches a known module
            if imp.startswith('src.'):
                # Ensure the target module exists in our nodes
                cursor.execute("SELECT id FROM nodes WHERE id = ?", (imp,))
                if cursor.fetchone():
                    cursor.execute(
                        "INSERT OR IGNORE INTO edges (source, target, relationship) VALUES (?, ?, ?)",
                        (info['module_name'], imp, 'IMPORTS')
                    )
            
    conn.commit()
    
    # Generate a summary
    cursor.execute("SELECT COUNT(*) FROM nodes")
    node_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM edges")
    edge_count = cursor.fetchone()[0]
    
    print(f"Graph Database built at {db_path}")
    print(f"Total Nodes: {node_count}")
    print(f"Total Edges: {edge_count}")
    
    cursor.execute("SELECT type, COUNT(*) FROM nodes GROUP BY type")
    print("\nNodes by type:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}")
        
    cursor.execute("SELECT relationship, COUNT(*) FROM edges GROUP BY relationship")
    print("\nEdges by relationship:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}")

    conn.close()

if __name__ == "__main__":
    project_root = Path(r"C:\Users\putit\agentic-commerce")
    db_path = project_root / "architecture_graph.db"
    build_graph(project_root, db_path)
