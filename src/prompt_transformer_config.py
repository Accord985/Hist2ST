"""
Interactive path and hyperparameter prompts for HEST training.

ARCHIVED - no usage in the current Hist2ST workflow, but might be helpful in 
scripts designed for command lines.
"""


import math
from pathlib import Path


def _prompt_tensor_path(label, default, filename):
    raw = input(f"{label} .pt file or containing folder [{default}]: ").strip()
    path = Path(raw.strip("\"'") if raw else default).expanduser()
    return path / filename if path.is_dir() else path


def prompt_tensor_paths(
    default_dir=str(Path(__file__).resolve().parent.parent / "training_run")
):
    """Ask for the four tensor paths; no previous notebook state is needed."""
    base = Path(default_dir)
    fields = [
        ("x_train_path", "Training X", "X_train_pca250.pt"),
        ("y_train_path", "Training Y", "y_train.pt"),
        ("x_test_path", "Test X", "X_test_pca250.pt"),
        ("y_test_path", "Test Y", "y_test.pt"),
    ]
    return {
        key: _prompt_tensor_path(label, base / filename, filename)
        for key, label, filename in fields
    }


def prompt_training_config(
    default_dir=str(Path(__file__).resolve().parent.parent / "training_run")
):
    """Prompt for input paths, training settings, device, and output folder."""
    paths = prompt_tensor_paths(default_dir)

    def number(label, default, conversion, valid, requirement):
        while True:
            raw = input(f"{label} [{default}]: ").strip()
            try:
                value = conversion(raw) if raw else default
                if not math.isfinite(value) or not valid(value):
                    raise ValueError
                return value
            except (ValueError, OverflowError):
                print(requirement)

    params = {
        "epochs": number(
            "Epochs", 30, int, lambda value: value > 0,
            "Enter a positive integer.",
        ),
        "batch_size": number(
            "Batch size", 256, int, lambda value: value > 0,
            "Enter a positive integer.",
        ),
        "learning_rate": number(
            "Learning rate", 1e-3, float, lambda value: value > 0,
            "Enter a positive finite number.",
        ),
        "d_model": number(
            "Transformer dimension", 64, int, lambda value: value > 0,
            "Enter a positive integer.",
        ),
    }
    params["n_heads"] = number(
        "Attention heads", 4, int,
        lambda value: value > 0 and params["d_model"] % value == 0,
        "Enter a positive integer that divides the transformer dimension.",
    )
    params["n_layers"] = number(
        "Transformer layers", 2, int, lambda value: value > 0,
        "Enter a positive integer.",
    )
    params["dropout"] = number(
        "Dropout", 0.1, float, lambda value: 0 <= value < 1,
        "Enter a number from 0 up to, but excluding, 1.",
    )
    params["seed"] = number(
        "Random seed", 42, int, lambda value: 0 <= value < 2**32,
        "Enter an integer from 0 to 4294967295.",
    )

    while True:
        value = input("Device: auto / cpu / cuda [auto]: ").strip().lower() or "auto"
        if value in ("auto", "cpu", "cuda"):
            params["device"] = None if value == "auto" else value
            break
        print("Enter auto, cpu, or cuda.")

    default_output = Path(default_dir) / "model"
    raw = input(f"Model output folder [{default_output}]: ").strip()
    params["output_dir"] = Path(
        raw.strip("\"'") if raw else default_output
    ).expanduser()
    return {"paths": paths, "parameters": params}
