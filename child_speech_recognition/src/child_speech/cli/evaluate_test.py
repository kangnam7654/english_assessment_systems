"""Command-line entry point for child_speech.evaluation.evaluate_test."""


def main() -> None:
    # Load ML dependencies only when this command is invoked.
    """Compare the pretrained and selected models on the fixed Test split."""
    from child_speech.evaluation.evaluate_test import main as run

    run()


if __name__ == "__main__":
    main()
