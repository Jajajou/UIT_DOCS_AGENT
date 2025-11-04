import glob
import os
from langgraph_sdk import get_sync_client
from tqdm import tqdm
import time


root_dir = "firecrawl/data/daa"

pdf_paths = sorted(
    os.path.abspath(p) for p in glob.glob(os.path.join(root_dir, '**', '*.pdf'), recursive=True)
)

client = get_sync_client(url="http://localhost:2024")

for path in tqdm(pdf_paths, desc=f"Uploading"):
    for chunk in client.runs.stream(
        None,
        "index",
        input={
            "messages":[
                {"role": "human",
                "content": f"upload {path}"}
            ]
        },
        stream_mode="updates"
    ):
        # print(f"Receiving new event of type: {chunk.event}")
        # print(chunk.data)
        # print("\n\n")
        pass