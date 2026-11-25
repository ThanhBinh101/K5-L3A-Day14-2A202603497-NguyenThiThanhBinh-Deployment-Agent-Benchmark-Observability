# Deployment — Day 14

**Trạng thái:** Agent trong `06-lab-complete/` đã đạt `PASS 12/12` trên máy local với Docker và Redis. Dự kiến triển khai trên Railway, đang chờ xác nhận đăng nhập. Chưa có URL public và ảnh.

## Cấu hình cần thiết

- Dịch vụ web build từ `06-lab-complete/`.
- `REDIS_URL` trỏ tới Redis của môi trường cloud.
- `AGENT_API_KEY` đặt trong cấu hình secret của dịch vụ.
- `PORT` theo cấu hình của nền tảng. Dockerfile và tiến trình web phải dùng cùng cổng.
- `ENVIRONMENT=production`. Agent dùng mock LLM.

## Kiểm tra public URL

Sau khi deploy, đặt `BASE` thành URL HTTPS của dịch vụ và nạp `AGENT_API_KEY` vào môi trường của terminal. Các lệnh chỉ in mã HTTP.

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"  # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"   # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -d '{"question":"Hello"}'  # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'  # 200
```

## Ảnh cần lưu sau khi deploy

- `screenshots/dashboard.png`
- `screenshots/running.png`
- `screenshots/test.png`
