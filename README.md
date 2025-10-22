# UIT_DOCS_AGENT
# Steps:
Clone this repo 
config .env.firecrawl .env.lightrag and LangGraph/.env
```bash
git clone https://github.com/Jajajou/UIT_DOCS_AGENT.git
```
Run LightRAG and Firecrawl service:
```bash
cd UIT_DOCS_AGENT
docker compose up -d
```
Run MinerU service:
```bash
mineru-api --host 0.0.0.0 --port 6969
```
Run LangGraph
```bash
uvx --from "langgraph-cli[inmem]" --with-editable LangGraph langgraph dev --config LangGraph/langgraph.json
```