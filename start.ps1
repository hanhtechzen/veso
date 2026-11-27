# Chạy XS247 trên Windows bằng Docker Desktop.
#   Mở PowerShell tại C:\Luckey rồi chạy:  .\start.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Chưa có Docker. Cài Docker Desktop: https://www.docker.com/products/docker-desktop/" -ForegroundColor Red
    exit 1
}

$firstRun = -not (Test-Path ".env")
if ($firstRun) {
    Copy-Item ".env.example" ".env"
    $token = -join ((48..57) + (97..122) | Get-Random -Count 32 | ForEach-Object { [char]$_ })
    $dbpw = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
    (Get-Content ".env") -replace "doi-mat-khau-nay", $dbpw | Set-Content ".env" -Encoding utf8
    Write-Host "Đã tạo tệp .env (mật khẩu cơ sở dữ liệu ngẫu nhiên)." -ForegroundColor Yellow
}

docker compose up -d --build
docker compose up -d --force-recreate --no-deps caddy   # luôn dùng Caddyfile mới nhất
Write-Host "Đang chờ API sẵn sàng..."
for ($i = 0; $i -lt 60; $i++) {
    try { Invoke-RestMethod http://localhost/healthz | Out-Null; break } catch { Start-Sleep 2 }
}

if ($firstRun) {
    # Dữ liệu mẫu để xem thử giao diện
    docker compose exec -T api python -m xs247.cli collect --date 2026-10-26
    docker compose exec -T api python -m xs247.cli collect --date 2026-10-29
    # Tài khoản quản trị đầu tiên (mật khẩu tạm, bắt đổi ở lần đăng nhập đầu)
    $adm = docker compose exec -T api python -m xs247.cli create-admin --username admin --name "Quản trị"
    Write-Host ""
    Write-Host ($adm -join "`n") -ForegroundColor Yellow
    Write-Host "Hãy chép lại mật khẩu tạm ở trên." -ForegroundColor Yellow
}
docker compose exec -T api python -m xs247.cli forecast

Write-Host ""
Write-Host "Trang kết quả:    http://localhost" -ForegroundColor Green
Write-Host "Công cụ:          http://localhost/cong-cu/" -ForegroundColor Green
Write-Host "Trực tiếp:        http://localhost/live.html" -ForegroundColor Green
Write-Host "Dự báo và AI:     http://localhost/du-doan.html" -ForegroundColor Green
Write-Host "Quản trị:         http://localhost/admin.html  (tên đăng nhập: admin)" -ForegroundColor Green
Write-Host "Tài liệu API:     http://localhost/v1/docs" -ForegroundColor Green
Write-Host ""
Write-Host "Hiện mới có dữ liệu mẫu 2 ngày. Bước tiếp theo: xem mục 6 trong HUONG-DAN-CHAY.md để bật nguồn và tải lịch sử." -ForegroundColor Yellow
Write-Host "Tự kiểm tra cấu hình: docker compose exec api python -m xs247.cli doctor" -ForegroundColor Yellow
