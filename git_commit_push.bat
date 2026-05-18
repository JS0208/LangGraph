@echo off
chcp 65001 > nul
cd /d "%~dp0"

git config core.commitEncoding utf-8
git config i18n.commitEncoding utf-8
git config i18n.logOutputEncoding utf-8

echo [1/4] index.lock 제거 중...
if exist ".git\index.lock" del /f ".git\index.lock" && echo   삭제 완료 || echo   없음

echo [2/4] 스테이징 중...
git add -A

echo [3/4] 커밋 중...
git commit -m "feat: README overhaul and GraphRAG system upgrade

- README: add badges, architecture flow, core feature sections
- feat(streaming): asyncio Queue-based SSE streaming buffer
- feat(observability): OTel distributed tracing layer
- feat(retrieval): sparse search, reranker, semantic cache, community graph
- feat(security): rate limit middleware
- feat(memory): long-term episode store
- feat(ingest): parallel ingest, quality validation, lineage, watermark
- feat(eval): adversarial and chaos eval sets
- fix(.gitignore): exclude intern application files"

echo [4/4] 푸시 중... (GitHub 로그인 창이 뜰 수 있습니다)
git push origin main

echo.
echo 완료!
pause
