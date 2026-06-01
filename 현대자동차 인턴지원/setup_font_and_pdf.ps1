# 한국어 폰트 자동 탐색 후 PDF 재생성
# 우클릭 → "PowerShell로 실행"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$fontsDir  = "C:\Windows\Fonts"

Write-Host "=== 한국어 폰트 탐색 중 ===" -ForegroundColor Cyan

$candidates = @(
    "malgun.ttf", "malgunbd.ttf",
    "NanumGothic.ttf", "NanumGothicBold.ttf",
    "gulim.ttc", "dotum.ttc", "batang.ttc", "gungsuh.ttc"
)

$found = $null
foreach ($f in $candidates) {
    $p = Join-Path $fontsDir $f
    if (Test-Path $p) {
        Write-Host "  발견: $f" -ForegroundColor Green
        $found = @{ path = $p; file = $f }
        break
    }
}

if ($null -eq $found) {
    Write-Host "한국어 폰트를 찾지 못했습니다." -ForegroundColor Red
    pause; exit 1
}

# 폰트 복사
$dest = Join-Path $scriptDir $found.file
if (-not (Test-Path $dest)) {
    Write-Host "폰트 복사: $($found.path) -> $dest"
    Copy-Item -Path $found.path -Destination $dest -Force
} else {
    Write-Host "폰트 이미 존재: $($found.file)"
}

# PDF 생성
Write-Host "`n=== PDF 생성 중 ===" -ForegroundColor Cyan
$pyScript = Join-Path $scriptDir "make_pdf_v2.py"
python $pyScript

if ($LASTEXITCODE -eq 0) {
    $pdf = Join-Path $scriptDir "자소서_권지성_현대자동차_v2.pdf"
    Write-Host "`n완료! PDF를 엽니다..." -ForegroundColor Green
    Start-Process $pdf
} else {
    Write-Host "PDF 생성 실패." -ForegroundColor Red
}

pause
