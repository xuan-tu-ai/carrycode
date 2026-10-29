"""System prompts for the runtime roles. Written for this project; not taken from the paper's Appendix D."""

from importlib.resources import files


def load_prompt(name: str) -> str:
    """Return the text of `prompts/<name>.md`."""
    return files("carrycode.prompts").joinpath(f"{name}.md").read_text(encoding="utf-8")
