"""Load pre-split HEST tensors from disk for model training."""

from pathlib import Path

import torch


def load_training_tensors(x_train_path, y_train_path, x_test_path, y_test_path):
    """Load the four train/test feature and target tensors onto CPU.

    Returns ``(x_train, y_train, x_test, y_test)`` as float32 tensors. Shape
    and value validation is handled by ``verify_training_tensors`` below.
    """
    tensors = []
    for path in (x_train_path, y_train_path, x_test_path, y_test_path):
        path = Path(path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Training tensor not found: {path}")
        try:
            tensor = torch.load(path, map_location="cpu", weights_only=True)
        except TypeError:
            # Support PyTorch releases that do not expose weights_only yet.
            tensor = torch.load(path, map_location="cpu")
        if not isinstance(tensor, torch.Tensor):
            raise TypeError(f"{path} must contain a plain torch.Tensor.")
        tensors.append(tensor.float())

    return tuple(tensors)


def verify_training_tensors(x_train, y_train, x_test, y_test):
    """Check tensor types, shapes, and finite values."""
    tensors = {
        "train_x": x_train,
        "train_y": y_train,
        "test_x": x_test,
        "test_y": y_test,
    }
    shapes = {}
    report = []

    for name, tensor in tensors.items():
        if not isinstance(tensor, torch.Tensor):
            raise TypeError(f"{name} must be a torch.Tensor.")
        if tensor.ndim != 2 or min(tensor.shape) < 1:
            raise ValueError(
                f"{name} must be a nonempty [patches, features/genes] tensor, "
                f"got {tuple(tensor.shape)}."
            )
        if not torch.isfinite(tensor).all():
            raise ValueError(f"{name} contains NaN or infinite values.")

        shapes[name] = tuple(tensor.shape)
        report.append(
            {
                "tensor": name,
                "shape": tuple(tensor.shape),
                "patches": tensor.shape[0],
                "columns": tensor.shape[1],
                "dtype": str(tensor.dtype),
                "finite": True,
            }
        )

    if shapes["train_x"][0] != shapes["train_y"][0]:
        raise ValueError("Training X and Y have different patch counts.")
    if shapes["test_x"][0] != shapes["test_y"][0]:
        raise ValueError("Test X and Y have different patch counts.")
    if shapes["train_x"][1] != shapes["test_x"][1]:
        raise ValueError("Training and test X have different feature counts.")
    if shapes["train_y"][1] != shapes["test_y"][1]:
        raise ValueError("Training and test Y have different gene counts.")

    return {
        "tensors": report,
        "train_patches": shapes["train_x"][0],
        "test_patches": shapes["test_x"][0],
        "n_components": shapes["train_x"][1],
        "n_genes": shapes["train_y"][1],
    }
