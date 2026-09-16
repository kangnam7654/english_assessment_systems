"""Deterministic orchestration over validated request and run records."""

from writing_synthesis.agents.assessor import AgentAssessor
from writing_synthesis.agents.student import AgentStudent
from writing_synthesis.llm.types import LanguageModel
from writing_synthesis.prompts.preparation import PromptPreparation
from writing_synthesis.schemas.provenance import ModelSnapshot
from writing_synthesis.schemas.request import WorkflowRequest
from writing_synthesis.schemas.run import EssayAttempt, RunError, Stage, WorkflowState
from writing_synthesis.storage.base import RunStore, StorageError


class WorkflowExecutionError(RuntimeError):
    """Retain a serializable partial run while chaining the original exception."""

    def __init__(self, state: WorkflowState):
        """Attach the validated partial state to a workflow execution failure.

        Args:
            state: Validated immutable workflow snapshot.
        """
        self.state = state
        super().__init__(f"Workflow {state.run_id} failed during {state.failed_stage}.")


class WritingWorkflow:
    """Run one generation/assessment cycle and persist each validated transition."""

    def __init__(self, llm: LanguageModel, store: RunStore | None = None):
        """Wire the model client, role agents, and optional state store.

        Args:
            llm: Injected language-model client implementing the shared completion contract.
            store: Repository used to persist job or workflow state.
        """
        self.store = store
        self.student = AgentStudent(llm)
        self.assessor = AgentAssessor(llm)
        describe = getattr(llm, "describe", None)
        self.model = (
            describe() if describe else ModelSnapshot(adapter=type(llm).__name__)
        )

    def _save(self, state: WorkflowState) -> WorkflowState:
        """Persist a snapshot when a store is configured and return the same state.

        Args:
            state: Validated immutable workflow snapshot.

        Returns:
            The same validated state after optional persistence.
        """
        if self.store is not None:
            self.store.save(state)
        return state

    def run(self, request: WorkflowRequest) -> WorkflowState:
        """Prepare criteria, obtain an essay, assess it, then persist a terminal state.

        Each stage is saved before its model call so an interrupted run remains
        inspectable. Calls run synchronously once; this is not a retry/job engine.

        Args:
            request: Validated task, grade, genre, mode, and optional source/essay inputs.

        Returns:
            Completed workflow snapshot after persistence of all successful transitions.

        Raises:
            WorkflowExecutionError: Preparation, generation, or assessment fails; the exception
                retains the persisted partial state.
            StorageError: A snapshot cannot be persisted; no successful stored run is reported.
        """
        state = self._save(WorkflowState(request=request, model=self.model))
        state = self._save(state.advance(Stage.PREPARING))
        try:
            preparation = PromptPreparation(request)
            assessor_prompt = preparation.build("assessor")
            state = self._save(
                state.evolve(
                    criteria=(assessor_prompt.reference,),
                    prompts=(assessor_prompt.snapshot,),
                )
            )
            assignment = preparation.assignment
            if request.mode == "synthesis":
                student_prompt = preparation.build("student")
                state = self._save(
                    state.advance(
                        Stage.GENERATING,
                        criteria=(*state.criteria, student_prompt.reference),
                        prompts=(*state.prompts, student_prompt.snapshot),
                    )
                )
                essay = self.student.generate(
                    system_prompt=student_prompt.text, assignment=assignment
                )
                origin = "generated"
            else:
                essay = request.essay
                origin = "provided"
            attempt = EssayAttempt(
                number=1, origin=origin, essay=essay, word_count=len(essay.split())
            )
            state = self._save(state.advance(Stage.ASSESSING, attempts=(attempt,)))
            assessment = self.assessor.assess(
                system_prompt=assessor_prompt.text,
                essay=state.essay,
                assessment_kind=preparation.assessment_kind,
                source_use_applicable=preparation.source_use_applicable,
                assignment=assignment,
            )
            if assessment.grade != request.grade_for_assessor:
                raise ValueError(
                    "Assessment grade does not match the requested assessor grade."
                )
            if (
                assessment.rubric_id != preparation.rubric_id
                or assessment.genre != request.genre
            ):
                raise ValueError("Assessment rubric/genre does not match the request.")
            attempt = EssayAttempt.model_validate(
                {**attempt.model_dump(), "assessment": assessment}
            )
            return self._save(state.advance(Stage.COMPLETED, attempts=(attempt,)))
        except StorageError:
            raise
        except Exception as exc:
            code = (
                "preparation_failed"
                if state.stage == Stage.PREPARING
                else (
                    "invalid_output"
                    if isinstance(exc, (ValueError, TypeError))
                    else "model_call_failed"
                )
            )
            # Never persist provider bodies, credentials or model output from str(exc).
            error = RunError(
                stage=state.stage,
                code=code,
                exception_type=type(exc).__name__,
                message=f"Execution failed during {state.stage}.",
            )
            state = self._save(state.advance(Stage.FAILED, error=error))
            raise WorkflowExecutionError(state) from exc
