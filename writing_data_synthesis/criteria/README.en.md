# Grade-specific writing rubrics

[한국어](README.md) · [Module](../README.en.md) · [Sources and reconstruction](../docs/rubric-evidence/README.en.md)

**The finalized rubrics are the grade JSON files in `grades/`.** Each Korean guide presents that grade’s genre requirements and full score tables.

K–5 supports opinion, informative and narrative writing; grades 6–12 supports argumentative, informative and narrative writing. Runtime reads one grade file and selects its requested genre.

| Grade | Korean reading guide | Runtime JSON |
| --- | --- | --- |
| K | [평가표](grades/grade-K.ko.md) | [JSON](grades/grade-K.json) |
| 1 | [평가표](grades/grade-1.ko.md) | [JSON](grades/grade-1.json) |
| 2 | [평가표](grades/grade-2.ko.md) | [JSON](grades/grade-2.json) |
| 3 | [평가표](grades/grade-3.ko.md) | [JSON](grades/grade-3.json) |
| 4 | [평가표](grades/grade-4.ko.md) | [JSON](grades/grade-4.json) |
| 5 | [평가표](grades/grade-5.ko.md) | [JSON](grades/grade-5.json) |
| 6 | [평가표](grades/grade-6.ko.md) | [JSON](grades/grade-6.json) |
| 7 | [평가표](grades/grade-7.ko.md) | [JSON](grades/grade-7.json) |
| 8 | [평가표](grades/grade-8.ko.md) | [JSON](grades/grade-8.json) |
| 9 | [평가표](grades/grade-9.ko.md) | [JSON](grades/grade-9.json) |
| 10 | [평가표](grades/grade-10.ko.md) | [JSON](grades/grade-10.json) |
| 11 | [평가표](grades/grade-11.ko.md) | [JSON](grades/grade-11.json) |
| 12 | [평가표](grades/grade-12.ko.md) | [JSON](grades/grade-12.json) |

## Usage

Select `rubric_id: "project-writing-v1"` with a grade and genre. Discover supported selections with `GET /criteria?family=project`.

Content, organization, expression and conventions each receive 1–4 ratings; source use is conditional. The application computes 0–100 display values, with no aggregate or cross-grade ability score.

Provider rubrics and reconstruction materials are consolidated in the [evidence folder](../docs/rubric-evidence/README.en.md). Existing API behavior for omitted rubric IDs is preserved.

This portfolio rubric is Mock-verified for execution only; actual scoring accuracy and educational validity are unvalidated.
