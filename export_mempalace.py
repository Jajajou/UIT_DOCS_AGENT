import sqlite3
import json
import os

db_path = os.path.expanduser("~/.mempalace/palace/chroma.sqlite3")
output_path = "mempalace_export.json"

def export_mempalace():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Lấy dữ liệu từ bảng content và metadata
    query = """
    SELECT c.rowid, c.c0, m.key, m.string_value 
    FROM embedding_fulltext_search_content c
    LEFT JOIN embedding_metadata m ON c.rowid = m.id
    ORDER BY c.rowid DESC
    LIMIT 1000;
    """
    
    try:
        cursor.execute(query)
        rows = cursor.fetchall()
        
        drawers = {}
        for rowid, content, key, value in rows:
            if rowid not in drawers:
                drawers[rowid] = {"id": rowid, "content": content, "metadata": {}}
            if key:
                drawers[rowid]["metadata"][key] = value
        
        # Chuyển thành list để lưu JSON
        export_data = list(drawers.values())
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
            
        print(f"Successfully exported {len(export_data)} drawers to {output_path}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    export_mempalace()
