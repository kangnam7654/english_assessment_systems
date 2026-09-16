"""Command-line entry point for child_speech.training.train."""


def main() -> None:
    # Load ML dependencies only when this command is invoked.
    """Start the recorded NeMo fine-tuning experiment."""
    from child_speech.training.train import main as run

    run()


if __name__ == "__main__":
    main()
