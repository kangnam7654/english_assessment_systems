import json
from pathlib import Path
from typing import Any


class SystemPromptBuilder:
    def __init__(self, rubric_path: str) -> None:
        self.rubrics = self._load_rubrics(rubric_path)

    def _load_rubrics(self, rubric_path: str) -> dict[str, Any]:
        path = Path(rubric_path)
        if not path.exists():
            raise FileNotFoundError(f"Rubric file not found: {path}")
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    # ---------- 공통 유틸 ----------

    def _get_grade_node(self, grade: str) -> dict[str, Any]:
        try:
            return self.rubrics[grade]
        except KeyError:
            return self.rubrics["mid_2"]

    def _get_grade_description(self, grade: str) -> str:
        grade_node = self._get_grade_node(grade)
        return grade_node.get("grade_description", "No grade description available.")

    def _get_level_node(self, grade: str, level: str) -> dict[str, Any]:
        grade_node = self._get_grade_node(grade)
        levels = grade_node.get("levels", {})
        return levels.get(level, levels.get("intermediate", {}))

    def _grade_label(self, grade: str) -> str:
        grade_label_map = {
            "elem_6": "Elementary school, 6th grade",
            "mid_2": "Middle school, 2nd grade",
            "high_2": "High school, 2nd grade",
        }
        return grade_label_map.get(grade, grade)

    def _level_label(self, level: str) -> str:
        level_label_map = {
            "beginner": "Beginner writer for this grade",
            "intermediate": "Intermediate writer for this grade",
            "advanced": "Advanced writer for this grade",
            "master": "Near perfect writer for this grade",
        }
        return level_label_map.get(level, level)

    # ---------- rubric_text 렌더링 ----------

    def _render_assessor_rubric_text(self, grade: str) -> str:
        """
        Assessor용: 한 grade에 대한 4개 level 프로파일을 모두 펼쳐서 보여줌.
        """
        grade_node = self._get_grade_node(grade)
        levels = grade_node.get("levels", {})

        lines: list[str] = []
        for level_name in ["beginner", "intermediate", "advanced", "master"]:
            level_node = levels.get(level_name)
            if not level_node:
                continue
            lines.append(f"[Level: {level_name}]")
            lines.append(f"- Overall: {level_node['description']}")
            lines.append("  Criteria:")
            for crit_name, crit_desc in level_node["criteria"].items():
                lines.append(f"    - {crit_name}: {crit_desc}")
            lines.append("")  # blank line between levels
        return "\n".join(lines).strip()

    def _render_student_rubric_text(self, grade: str, level: str) -> str:
        """
        Student용: 해당 grade+level 조합의 기준만 보여줌.
        """
        level_node = self._get_level_node(grade, level)
        lines: list[str] = []
        lines.append(f"Overall description: {level_node['description']}")
        lines.append("")
        lines.append("Criteria (target writing profile):")
        for crit_name, crit_desc in level_node["criteria"].items():
            lines.append(f"- {crit_name}: {crit_desc}")
        return "\n".join(lines)

    # ---------- 외부에서 쓰는 메서드 ----------

    def build_assessor_prompt(self, template_path: str, grade: str) -> str:
        template = Path(template_path).read_text(encoding="utf-8")

        grade_desc = self._get_grade_description(grade)
        rubric_text = self._render_assessor_rubric_text(grade)

        grade_label = self._grade_label(grade)

        prompt = template.format(
            grade_label=grade_label,
            grade_description=grade_desc,
            rubric_text=rubric_text,
        )
        return prompt

    def build_student_prompt(self, template_path: str, grade: str, level: str) -> str:
        template = Path(template_path).read_text(encoding="utf-8")

        grade_desc = self._get_grade_description(grade)
        level_node = self._get_level_node(grade, level)
        rubric_text = self._render_student_rubric_text(grade, level)

        grade_label = self._grade_label(grade)
        level_label = self._level_label(level)

        prompt = template.format(
            grade_label=grade_label,
            level_label=level_label,
            grade_description=grade_desc,
            level_description=level_node["description"],
            rubric_text=rubric_text,
        )
        return prompt
