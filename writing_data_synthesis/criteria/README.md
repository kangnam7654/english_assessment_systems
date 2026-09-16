# 학년별 글쓰기 루브릭

[English](README.en.md) · [모듈 소개](../README.md) · [출처와 재구성 근거](../docs/rubric-evidence/README.md)

**확정된 루브릭은 `grades/`의 학년별 JSON입니다.** 한국어 평가표에는 같은 학년의 글 유형별 요구사항과 전체 점수 기준이 담겨 있습니다.

K–5는 의견문·정보문·서사문, 6–12학년은 논증문·정보문·서사문을 지원합니다. 각 학년 파일에서 요청한 글 유형을 선택해 실행합니다.

| 학년 | 한국어 평가표 | 실행용 JSON |
| --- | --- | --- |
| 유치원(K) | [평가표](grades/grade-K.ko.md) | [JSON](grades/grade-K.json) |
| 1학년 | [평가표](grades/grade-1.ko.md) | [JSON](grades/grade-1.json) |
| 2학년 | [평가표](grades/grade-2.ko.md) | [JSON](grades/grade-2.json) |
| 3학년 | [평가표](grades/grade-3.ko.md) | [JSON](grades/grade-3.json) |
| 4학년 | [평가표](grades/grade-4.ko.md) | [JSON](grades/grade-4.json) |
| 5학년 | [평가표](grades/grade-5.ko.md) | [JSON](grades/grade-5.json) |
| 6학년 | [평가표](grades/grade-6.ko.md) | [JSON](grades/grade-6.json) |
| 7학년 | [평가표](grades/grade-7.ko.md) | [JSON](grades/grade-7.json) |
| 8학년 | [평가표](grades/grade-8.ko.md) | [JSON](grades/grade-8.json) |
| 9학년 | [평가표](grades/grade-9.ko.md) | [JSON](grades/grade-9.json) |
| 10학년 | [평가표](grades/grade-10.ko.md) | [JSON](grades/grade-10.json) |
| 11학년 | [평가표](grades/grade-11.ko.md) | [JSON](grades/grade-11.json) |
| 12학년 | [평가표](grades/grade-12.ko.md) | [JSON](grades/grade-12.json) |

## 사용 방법

`rubric_id: "project-writing-v1"`과 학년·글 유형을 지정합니다. 지원 목록은 `GET /criteria?family=project`에서 확인합니다.

내용·구성·표현·문법을 각각 1–4점으로 평가하고, 출처 사용은 해당 과제에서만 평가합니다. 0–100 표시값은 코드가 계산하며 총점이나 학년 간 실력 비교 점수는 아닙니다.

기존 기관별 루브릭과 재구성 자료는 [근거 폴더](../docs/rubric-evidence/README.md)에 모았습니다. 루브릭 ID를 생략하는 기존 API 요청의 동작은 유지했습니다.

포트폴리오용 기준이며 Mock으로 실행 흐름을 검증했습니다. 실제 평가 정확도와 교육적 타당성은 검증하지 않았습니다.
