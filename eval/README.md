# Evaluation — Golden Set & RAGAS Harness

본 폴더는 `14_Upgrade_Master_Plan.md`의 Pillar 7(Eval) 구현 산출물을 담는다.

## 구조

- `golden_set/v0.json` : Sprint 0 골든셋 v0 (12문항). Sprint 5에서 30문항으로 확장.
- `run_eval.py` (Sprint 5 도입 예정) : 골든셋을 hybrid_retrieve + agent graph 에 통과시켜 RAGAS 지표 산출.
- `adversarial/` (Sprint 6 도입 예정) : prompt-injection / jailbreak / empty-data 시나리오.

## Sprint 0 검증 기준

- 12문항 JSON이 `pytest`에서 스키마 적합성 검사를 통과해야 한다 (`tests/test_golden_set_schema.py`).

## 임계 목표 (`scoring_targets`)

| 지표 | 임계 | 측정 시점 |
|---|---|---|
| ragas_faithfulness | ≥ 0.85 | Sprint 5 이후 |
| ragas_answer_correctness | ≥ 0.80 | Sprint 5 이후 |
| citation_attachment_rate | 1.0 | Sprint 3 이후 (모델 출력 lint) |
| context_recall_at_5 | ≥ 0.9 | Sprint 2 이후 |
