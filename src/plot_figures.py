"""Plotting helpers for HEST model training."""

from pathlib import Path

import matplotlib.pyplot as plt


def plot_loss_history(history, output_path=None):
    """Plot train/test MSE by epoch and optionally save a PNG."""
    if not history:
        raise ValueError("No completed epochs are available to plot.")

    epochs = [row["epoch"] for row in history]
    train = [row["train_loss"] for row in history]
    test = [row["test_loss"] for row in history]
    fig, ax = plt.subplots(figsize=(8, 5))
    try:
        ax.plot(epochs, train, label="Training MSE")
        ax.plot(epochs, test, label="Test MSE")
        ax.set(
            xlabel="Epoch",
            ylabel="Mean squared error",
            title="Training and test loss",
        )
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        if output_path is not None:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(path, dpi=150, bbox_inches="tight")
            print(f"Saved loss plot: {path}")
        plt.show()
    finally:
        plt.close(fig)
