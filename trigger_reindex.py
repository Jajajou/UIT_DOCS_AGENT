import asyncio
import sys
import os
from pathlib import Path

# Add LangGraph/src to sys.path
sys.path.insert(0, str(Path("LangGraph/src").absolute()))

from agent.graphs.indexing_graph import graph as indexing_graph
from langchain_core.messages import HumanMessage

async def main():
    base_path = "/Users/jajajou1778/UIT_DOCS_AGENT/firecrawl/data/daa/"
    subdirs = ["chuongtrinh_daotao", "gioithieu", "kehoachnam", "khac", "quydinh_huongdan", "thongbao"]
    
    for subdir in subdirs:
        path = os.path.join(base_path, subdir)
        # Use rglob style to find all PDFs in subfolders manually if needed, 
        # but indexing_graph.py _get_files_from_path handles dir (non-recursively).
        # To be safe, we will walk and find all leaf directories with PDFs.
        
        print(f"\n--- Scanning Subdir: {subdir} ---")
        for root, dirs, files in os.walk(path):
            if any(f.lower().endswith('.pdf') for f in files):
                print(f"Triggering upload for folder: {root}")
                inputs = {
                    "messages": [HumanMessage(content=f"upload {root}")]
                }
                
                async for event in indexing_graph.astream(inputs, stream_mode="updates"):
                    for node, data in event.items():
                        if "upload_results" in data:
                            res = data["upload_results"][-1]
                            status = "✓" if res.get("status") == "success" else "✗"
                            print(f"  {status} {res.get('file_name')} | Track: {res.get('track_id')}")
                        elif "error" in data and data["error"]:
                            print(f"  Error in {node}: {data['error']}")

if __name__ == "__main__":
    asyncio.run(main())
