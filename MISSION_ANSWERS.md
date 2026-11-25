# Day 14 Lab — Mission Answers

## Part 1 — Localhost vs Production

### Exercise 1.1 — Anti-patterns

1. API key ghi thẳng vào source. Nếu dùng key thật, người đọc repo có thể sử dụng nó ngay cả khi file đã được sửa ở commit sau.
2. Chuỗi kết nối database chứa thông tin đăng nhập ngay trong source và dùng địa chỉ localhost, nên khó chuyển sang môi trường khác.
3. App in API key ra log của mỗi request. Người có quyền xem log cũng có thể thấy key.
4. Port 8000 ghi cố định trong lệnh chạy Uvicorn, gây xung đột nếu port đã có tiến trình và không dùng được port do nền tảng cấp.
5. `reload=True` luôn bật. Đây là tiện ích khi sửa code local và có thể khởi động lại tiến trình khi file thay đổi.
6. Thiếu `/health` để công cụ giám sát kiểm tra tình trạng tiến trình.
7. App thiếu bước shutdown riêng để đóng các kết nối hoặc dọn tài nguyên do app quản lý.

### Exercise 1.2 — Chạy bản develop

Cổng 8000 đã được sử dụng trên máy, nên chạy Uvicorn ở cổng 8014. Kết quả từ lần gọi trên terminal:

```console
$ curl -i -X POST 'http://127.0.0.1:8014/ask?question=Hello'
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:51:54 GMT
server: uvicorn
content-length: 126
content-type: application/json

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

### Exercise 1.3 — So sánh hai bản

| Mục | Develop | Production | Vì sao quan trọng |
| --- | --- | --- | --- |
| Cấu hình | `port=8000` trong `develop/app.py:52` | `production/config.py:18` đọc `PORT`; `production/app.py:197` dùng giá trị đó | Có thể dùng cùng code ở local lẫn cloud và thay cổng khi cần. |
| Tình trạng dịch vụ | Thiếu endpoint kiểm tra | `GET /health` báo tiến trình đang hoạt động. `GET /ready` báo khả năng nhận request, trả 503 nếu chưa sẵn sàng. | Nền tảng có thể kiểm tra tiến trình và quyết định lúc chuyển lưu lượng vào. |
| Logging | `print()`, có dòng in cả API key | Khai báo định dạng log có cấu trúc cho startup và request. Trong lần chạy với mock, cảnh báo lúc nạp cấu hình có thể thiết lập logging trước, khiến cấu hình log INFO của app không được áp dụng. | Dễ tìm và lọc sự kiện, đồng thời tránh để API key xuất hiện trong log. |
| Shutdown | Uvicorn quản lý việc dừng tiến trình, app thiếu bước dọn dẹp riêng | FastAPI lifespan cập nhật cờ readiness và có bước shutdown | Có chỗ đóng kết nối, giải phóng tài nguyên khi app dừng. |

Kiểm tra bản production ở cổng 8014 với JSON body `{"question":"Hello"}` cho `POST /ask`:

| Lệnh | HTTP | Bằng chứng từ response |
| --- | --- | --- |
| `GET /health` | 200 | `"status":"ok"`, version `1.0.0` |
| `GET /ready` | 200 | `{"ready":true}` |
| `POST /ask` | 200 | `{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","model":"gpt-4o-mini"}` |

## Part 2 — Docker

### Exercise 2.1 — Dockerfile cơ bản

1. Base image là `python:3.11`.
2. `WORKDIR /app` đặt thư mục làm việc cho các lệnh build tiếp theo và cho tiến trình chạy trong container.
3. Copy `requirements.txt` trước khi cài dependency để Docker tái sử dụng layer cài đặt khi chỉ sửa source.
4. `ENTRYPOINT` đặt chương trình chính chạy khi container khởi động. `CMD` đặt lệnh mặc định hoặc đối số mặc định cho `ENTRYPOINT`. Đối số sau tên image trong `docker run` thay `CMD`; cờ `--entrypoint` thay chương trình chính. File này chỉ dùng `CMD ["python", "app.py"]`.

### Exercise 2.2 — Chạy image develop

Image `my-agent:develop` chạy với port host 18014 ánh xạ vào 8000 trong container. `GET /health` trả `"status":"ok"` và `"container":true`.

```console
$ curl -i -X POST 'http://127.0.0.1:18014/ask?question=What%20is%20Docker%3F'
HTTP/1.1 200 OK
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

### Exercise 2.3 — Multi-stage build

- Stage `builder` dựa trên `python:3.11-slim`, cài `gcc` và `libpq-dev`, rồi cài dependency Python vào `/root/.local`.
- Stage `runtime` dùng một base slim mới, copy bộ package đã cài và source cần chạy. Uvicorn chạy bằng user `appuser`.
- Image cuối dùng base slim và chỉ mang artifact cần cho runtime. Compiler và gói phát triển nằm trong stage builder.

Kích thước thực đo trên Docker Desktop (arm64), từ `docker images` và `docker image inspect`:

| Image | Kích thước Docker hiển thị | Dung lượng theo hệ thập phân |
| --- | --- | ---: |
| `my-agent:develop` | 1.67 GB | 1672.17 MB |
| `my-agent:advanced` | 265 MB | 265.49 MB |

Image advanced giảm **84.12%**, tính từ số byte. Lần build đầu gặp lỗi tải gói hệ thống; Dockerfile được chỉnh để tải gói Debian qua HTTPS và thử lại khi cần.

### Exercise 2.4 — Compose stack

```text
Client → Nginx (host :80) → agent:8000
                            ├── redis:6379 (cache, session và rate limiting)
                            └── qdrant:6333 (vector store cho RAG)
```

Bốn service dùng mạng bridge `internal`. Compose chờ Redis và Qdrant healthy trước khi chạy agent. Nginx chuyển tiếp HTTP đến agent qua tên service. Redis và Qdrant có volume dữ liệu riêng. Hai nhánh trong sơ đồ là địa chỉ cấu hình của agent; endpoint mock ở Part 2 trả lời trực tiếp và chưa cần truy vấn hai dịch vụ này.

Chạy `docker compose -p k5-day14-docker up -d --build --wait`. Bốn container hoạt động; agent, Redis và Qdrant qua health check. Sau khi test, dừng stack thử nghiệm.

```console
$ curl -i http://127.0.0.1/health
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json

{"status":"ok","uptime_seconds":5.3,"version":"2.0.0","timestamp":"2026-11-25T10:56:27.220321"}

$ curl -i -X POST http://127.0.0.1/ask -H 'Content-Type: application/json' -d '{"question":"Explain microservices"}'
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

## Part 3 — Cloud Deployment

### Exercise 3.1 / 3.2 — Deploy và so sánh cấu hình

**Trạng thái deploy:** còn thiếu URL public và bốn kết quả kiểm tra CP6. Bản K5 dùng agent trong `06-lab-complete/`. Agent đã đạt `PASS 12/12` trên máy local. Bước kết nối tài khoản Railway đang chờ xác nhận.

| Mục | `03-cloud-deployment/railway/railway.toml` | `03-cloud-deployment/render/render.yaml` |
| --- | --- | --- |
| Build | Cấu hình mẫu chỉ định Nixpacks | Cấu hình mẫu dùng Python runtime và chỉ định lệnh `pip install -r requirements.txt` |
| Chạy và kiểm tra | Uvicorn bind `$PORT`, kiểm tra `/health` và đặt chính sách restart khi lỗi | Uvicorn bind `$PORT`, kiểm tra `/health`, đặt region và tự deploy |
| Redis và secret | File mẫu cấu hình service web. Redis và biến môi trường cần khai báo trên nền tảng. | Blueprint mẫu khai báo web và Redis; có thể tạo ngẫu nhiên `AGENT_API_KEY` bằng `generateValue`. Với agent Part 6 vẫn cần gắn `REDIS_URL` vào service web. |

### Exercise 3.3 — Pipeline Cloud Run

1. `cloudbuild.yaml` cài dependency và chạy `pytest`.
2. Nếu bước test hoàn tất, pipeline build Docker image với hai tag `$COMMIT_SHA` và `latest`, rồi push cả hai tag.
3. Cloud Run deploy image theo tag commit ở `asia-southeast1`; secret được lấy từ Secret Manager.
4. `service.yaml` mô tả tài nguyên, autoscaling 1–10 instance, giới hạn 80 request đồng thời mỗi instance, cùng probe `/health` và `/ready`.

## Part 6 — Kết quả kiểm tra agent dùng để deploy

Đã chạy `python check_production_ready.py` trong `06-lab-complete/` với Docker Desktop và Redis thử nghiệm. Script báo image 297 MB; Docker dừng container trong 0.7 giây, exit code 0.

```text
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 41/41 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
```

Kiểm tra thêm với Docker Compose: 16 request gửi đồng thời với cùng API key nhận đúng 10 mã 200 và 6 mã 429.

Mục 12 xác minh cấu hình triển khai. URL public và các kiểm tra CP6 được ghi riêng trong `DEPLOYMENT.md` sau khi hệ thống chạy trên Railway.

## AI log

- Dùng Codex để đọc đề, đối chiếu code với checkpoint, giải thích lỗi trùng cổng và chuẩn bị câu trả lời cho Part 1–3.
- Exercise 1.2 do người học chạy trên terminal và cung cấp nguyên kết quả HTTP để ghi vào bài.
- Codex chạy các smoke test Part 1 production và Part 2, lấy HTTP từ curl và số byte từ Docker.
- Codex triển khai các TODO của agent Part 6 và chạy script chấm với Docker, Redis. Redis giữ giới hạn theo API key và ngân sách mỗi ngày UTC. Chi phí mock dùng mức ước tính một token cho bốn ký tự.
