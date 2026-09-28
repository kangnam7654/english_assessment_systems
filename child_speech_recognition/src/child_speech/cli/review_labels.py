"""Review AI Hub labels and apply private, human-approved decisions."""

from child_speech.data.label_review import run


def main() -> None:
    """Run the dependency-free label review command."""
    run()


if __name__ == "__main__":
    main()
