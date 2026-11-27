#!/usr/bin/env bash
# PreToolUse hook: chặn lệnh shell nguy hiểm trước khi Claude chạy.
# Đọc JSON sự kiện từ stdin; exit 2 = chặn, nội dung stderr được gửi lại cho Claude.
input=$(cat)

# Lấy giá trị tool_input.command (đủ dùng, không cần jq)
cmd=$(printf '%s' "$input" | tr '\n' ' ' | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\(\([^"\\]\|\\.\)*\)".*/\1/p')
[ -z "$cmd" ] && exit 0

block() {
  echo "Đã chặn lệnh nguy hiểm ($1). Hãy để người dùng tự chạy nếu thật sự cần: $cmd" >&2
  exit 2
}

check() { printf '%s' "$cmd" | grep -Eiq -- "$1"; }

# Xóa hàng loạt
check 'rm[[:space:]]+(-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r|--recursive.*--force|--force.*--recursive)[[:space:]]+(/|~|\$HOME|\*|\.)([[:space:]]|/?$|/\*)' && block "rm -rf thư mục gốc/home"
check 'remove-item.*-recurse.*-force|remove-item.*-force.*-recurse' && block "Remove-Item -Recurse -Force"
check '(^|[;&|[:space:]])(rd|rmdir)[[:space:]]+/s' && block "rmdir /s"
check '(^|[;&|[:space:]])(mkfs|format)[[:space:].]' && block "định dạng ổ đĩa"
check '(^|[;&|[:space:]])dd[[:space:]]+.*of=/dev/' && block "dd ghi vào thiết bị"
check 'chmod[[:space:]]+-R[[:space:]]+777[[:space:]]+/' && block "chmod -R 777 /"

# Dữ liệu Docker / Postgres của dự án
check 'docker([[:space:]]+|-)compose.*down.*(-v|--volumes)' && block "docker compose down -v (xóa dữ liệu)"
check 'docker[[:space:]]+(volume[[:space:]]+(rm|prune)|system[[:space:]]+prune.*--volumes)' && block "xóa volume Docker"
check '(drop[[:space:]]+(table|database|schema)|truncate[[:space:]]+(table[[:space:]]+)?[a-z_])' && block "DROP/TRUNCATE SQL"

# Git phá lịch sử
check 'git[[:space:]]+push.*(--force([[:space:]]|$)|[[:space:]]-f([[:space:]]|$))' && block "git push --force"
check 'git[[:space:]]+reset[[:space:]]+--hard' && block "git reset --hard"
check 'git[[:space:]]+clean[[:space:]]+-[a-z]*f' && block "git clean -f"

# Tải và chạy mã từ mạng
check '(curl|wget|iwr|invoke-webrequest)[^|]*\|[[:space:]]*(sudo[[:space:]]+)?(ba|z)?sh' && block "tải và chạy script từ mạng"

exit 0
