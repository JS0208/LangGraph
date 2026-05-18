# 9. Human Required Tasks

## 목적

아래 항목은 보안/정책/운영 권한이 필요하여 사람이 수행해야 합니다.

## 작업 목록

1. **실 API 키 발급 및 비밀 관리**
   - DART, LLM Provider, DB 인증정보를 비밀 저장소(Vault/Secrets Manager)에 등록.
2. **인프라 프로비저닝 승인**
   - Neo4j/Qdrant 운영 인스턴스 생성 및 네트워크 정책 승인.
3. **규정 준수/법무 검토**
   - 금융 의사결정 보조 시스템의 로그 보관/감사 요건 확정.
4. **최종 운영 배포 승인**
   - 스테이징 결과 검토 후 프로덕션 배포 승인.
5. **도메인 데이터 품질 검수**
   - 기업별 공시/재무 데이터 정합성 최종 확인.

## 연결 문서

- 전체 상태와 다음 작업: `6_Project_Status_and_Next_Steps.md`
- 실연동 절차: `10_Real_Integration_Playbook.md`
