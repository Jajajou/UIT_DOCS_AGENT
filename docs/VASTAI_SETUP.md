# Hướng dẫn Thuê máy Vast.ai và Triển khai vLLM

Tài liệu này hướng dẫn cách thuê một máy chủ GPU (NVIDIA A100) trên Vast.ai thông qua Command Line (CLI) và triển khai toàn bộ hệ thống AI (Embeddings, Reranker, LLM) phục vụ cho dự án.

## Bước 1: Cài đặt công cụ và Đăng nhập

Sử dụng `uv` (trình quản lý package Python siêu tốc) để chạy CLI của Vast.ai mà không cần cài đặt rườm rà vào hệ thống:

1. Lấy API Key tại trang [Vast.ai Console > Account](https://console.vast.ai/account/). (Nhớ tạo key với quyền Read/Write cho Instances và tắt 2FA qua CLI).
2. Đăng nhập qua CLI:
   ```bash
   uvx vastai set api-key YOUR_API_KEY_HERE
   ```

## Bước 2: Tìm và Thuê máy A100

Vì các model vLLM (Qwen3-8B, Embeddings, Reranker) cần tải về hàng chục GB dữ liệu, bạn **BẮT BUỘC PHẢI** thuê máy có ổ cứng lớn (>150GB) để tránh lỗi `No space left on device`.

**1. Tìm máy rẻ và ổn định:**
```bash
uvx vastai search offers "gpu_name=A100_SXM4 reliability > 0.95 inet_up > 200 disk_space > 150" -o "dph"
```
*Lưu ý cột ID (ví dụ: `1234567`) của máy có giá tốt nhất.*

**2. Thuê máy (Tạo Instance):**
```bash
uvx vastai create instance DIEN_ID_MAY_VAO_DAY --image pytorch/pytorch:2.2.0-cuda12.1-cudnn8-devel --disk 150 --ssh --direct
```

## Bước 3: Kết nối SSH vào máy

**1. Kiểm tra trạng thái máy:**
```bash
uvx vastai show instances
```
Chờ đến khi cột `Status` chuyển thành `running`. Ghi lại thông tin `SSH Addr` (ví dụ: `ssh4.vast.ai`) và `SSH Port` (ví dụ: `29166`).

**2. Đẩy khóa SSH của bạn lên máy (Bắt buộc nếu bị Permission Denied):**
Nếu lệnh ssh yêu cầu mật khẩu hoặc báo lỗi publickey, hãy gắn khóa SSH của bạn vào máy:
```bash
uvx vastai attach ssh DIEN_ID_INSTANCE_VAO_DAY ~/.ssh/id_ed25519.pub
```

**3. Kết nối vào máy:**
```bash
ssh -p 29166 root@ssh4.vast.ai
```

## Bước 4: Triển khai Hệ thống vLLM (Bare-metal)

Lưu ý: Các máy ảo mặc định của Vast.ai bản chất đã là một Docker Container. Việc chạy `docker-compose` (Docker-in-Docker) bên trong nó thường gây ra lỗi thiếu quyền (Missing `docker.sock`). 
**Giải pháp tốt nhất và cho hiệu năng GPU cao nhất là chạy trực tiếp (Bare-metal) trên môi trường PyTorch đã có sẵn.**

Sau khi SSH vào máy Vast.ai, chạy lần lượt các lệnh sau:

**1. Tải source code:**
```bash
apt-get update && apt-get install -y git nano curl tmux
git clone -b feat/a100-stack https://github.com/fuisl/vllm-test.git
cd vllm-test
```

**2. Cài đặt thư viện AI:**
```bash
pip install vllm fastapi uvicorn requests
```

**3. Đặt Token HuggingFace:**
```bash
export HF_TOKEN="hf_DienTokenCuaBanVaoDay"
```

**4. Kích hoạt các Model (Chạy nền):**

Chạy Embeddings (Cổng 8000):
```bash
nohup vllm serve AITeamVN/Vietnamese_Embedding_V2 --task embed --host 0.0.0.0 --port 8000 --gpu-memory-utilization 0.08 > embed.log 2>&1 &
```

Chạy Reranker (Cổng 8001):
```bash
nohup vllm serve AITeamVN/Vietnamese_Reranker --task score --host 0.0.0.0 --port 8001 --gpu-memory-utilization 0.08 > rerank.log 2>&1 &
```

Chạy LLM Qwen3-8B (Cổng 8002) - Đã bật Chunked Prefill và FP8 KV Cache:
```bash
nohup vllm serve Qwen/Qwen3-8B --host 0.0.0.0 --port 8002 --gpu-memory-utilization 0.50 --max-model-len 32768 --enable-chunked-prefill --kv-cache-dtype fp8 --enable-reasoning --reasoning-parser deepseek_r1 > llm.log 2>&1 &
```

Chạy Rerank Adapter (Cổng 8003):
```bash
export VLLM_RERANK_URL=http://localhost:8001/v1/score
nohup python rerank_adapter.py > adapter.log 2>&1 &
```

**5. Kiểm tra log khởi động:**
```bash
tail -f llm.log
```
*(Bấm `Ctrl+C` để thoát xem log. Chờ đến khi thấy chữ `Uvicorn running on http://0.0.0.0:8002` là model đã sẵn sàng).*

## Bước 5: Cấu hình cho UIT_DOCS_AGENT

Sau khi mọi thứ trên Vast.ai đã chạy, hãy copy địa chỉ IP của máy Vast.ai (ví dụ: `18.208.190.192`) và mở file `.env.lightrag` trên máy tính của bạn, sửa lại các cổng kết nối:

```env
# Thay IP dưới đây bằng IP của Vast.ai
LLM_BASE_URL=http://18.208.190.192:8002/v1
EMBEDDING_BASE_URL=http://18.208.190.192:8000/v1
RERANK_BINDING_HOST=http://18.208.190.192:8003/v2/rerank
```

## Bước 6: Dọn dẹp
Để tránh bị trừ tiền oan uổng khi đã làm xong việc:
```bash
uvx vastai destroy instance DIEN_ID_INSTANCE_VAO_DAY
```