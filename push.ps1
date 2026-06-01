Set-Location $PSScriptRoot

# 1. 잠금 파일 제거
$lock = '.git\index.lock'
if (Test-Path $lock) { Remove-Item $lock -Force; Write-Host 'index.lock 제거됨' }

# 2. stage all
git add -A

# 3. commit
git commit -m 'feat: FinGraph Insight final PPT (18 slides) and full codebase update

- PPT 18 slides: layout fixes, slide deletion, video placeholders
- Dept: AI Software Engineering
- Source: agents, retrieval, eval, frontend, CI pipeline'

# 4. push
git push origin main

Write-Host ''
Write-Host '완료!' -ForegroundColor Green
Read-Host '엔터를 누르면 닫힙니다'
