# Cập nhật LuckyVision lên bản mới trên máy Windows (Docker Desktop).
# Cách dùng: giải nén Luckey.zip mới ĐÈ lên thư mục cũ (giữ nguyên tệp .env), rồi chạy:  .\update.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path ".env")) { Write-Host "Không thấy tệp .env. Đây là lần cài đầu tiên? Hãy chạy .\start.ps1" -ForegroundColor Red; exit 1 }

New-Item -ItemType Directory -Force -Path backups | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmm"
Write-Host "1/3 Sao lưu cơ sở dữ liệu trước khi cập nhật..." -ForegroundColor Cyan
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "backups\truoc-cap-nhat-$stamp.dump"
Write-Host "   Đã lưu backups\truoc-cap-nhat-$stamp.dump"

Write-Host "2/3 Dựng lại và khởi động (tự áp dụng thay đổi cơ sở dữ liệu)..." -ForegroundColor Cyan
docker compose up -d --build
# Caddy không tự đọc lại Caddyfile: tạo lại để chắc chắn dùng cấu hình mới
docker compose up -d --force-recreate --no-deps caddy
Start-Sleep -Seconds 8

Write-Host "3/3 Tự kiểm tra..." -ForegroundColor Cyan
docker compose exec -T api python -m luckyvision.cli migrate
docker compose exec -T api python -m luckyvision.cli doctor
Write-Host ""
Write-Host "Xong. Mở http://localhost và nhấn Ctrl+F5 để trình duyệt tải bản mới." -ForegroundColor Green
