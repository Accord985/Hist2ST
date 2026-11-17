"""Training loop and artifact saving for the HEST Transformer."""

import csv
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from load_tensors import verify_training_tensors
from plot_figures import plot_loss_history


class _PatchExpressionTransformer(nn.Module):
    """Predict selected gene expression from one spot's PCA features."""

    def __init__(self, n_components=250, n_genes=50, d_model=64, n_heads=4,
                 n_layers=2, dropout=0.1):
        super().__init__()
        self.n_components = n_components
        self.input_projection = nn.Linear(1, d_model)
        self.position = nn.Parameter(torch.zeros(1, n_components, d_model))

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=d_model * 2,
            dropout=dropout,
            batch_first=True,
            activation="gelu",
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(
            encoder_layer,
            num_layers=n_layers,
            enable_nested_tensor=False,
        )
        self.norm = nn.LayerNorm(d_model)
        self.head = nn.Sequential(
            nn.Linear(d_model, d_model),
            nn.GELU(),
            nn.Linear(d_model, n_genes),
        )

    def forward(self, x):
        if x.ndim != 2 or x.shape[1] != self.n_components:
            raise ValueError(
                f"Expected input [batch,{self.n_components}], got {tuple(x.shape)}"
            )
        tokens = self.input_projection(x.unsqueeze(-1)) + self.position
        encoded = self.encoder(tokens)
        pooled = encoded.mean(dim=1)
        return self.head(self.norm(pooled))


def train_transformer(x_train, y_train, x_test, y_test, output_dir,
                      epochs=30, batch_size=256, learning_rate=1e-3,
                      d_model=64, n_heads=4, n_layers=2, dropout=0.1,
                      seed=42, device=None):
    """Train on preloaded tensors and save model, predictions, metrics, and history.

    X inputs must already have been PCA-transformed with PCA fitted on training
    embeddings only. Y tensors contain log-relative expression for selected
    genes. Test loss is reported as a diagnostic; test tensors do not update
    model weights.
    """
    if isinstance(epochs, bool) or not isinstance(epochs, int) or epochs < 1:
        raise ValueError("epochs must be a positive integer.")
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer.")

    # Normalize dtype/device before validating and constructing data loaders.
    x_train, y_train, x_test, y_test = (
        tensor.detach().to(device="cpu", dtype=torch.float32)
        if isinstance(tensor, torch.Tensor) else tensor
        for tensor in (x_train, y_train, x_test, y_test)
    )
    verify_training_tensors(x_train, y_train, x_test, y_test)

    torch.manual_seed(seed)
    np.random.seed(seed)
    target_device = torch.device(
        device or ("cuda" if torch.cuda.is_available() else "cpu")
    )
    if target_device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable.")

    train_loader = DataLoader(
        TensorDataset(x_train, y_train), batch_size=batch_size, shuffle=False
    )
    test_loader = DataLoader(
        TensorDataset(x_test, y_test), batch_size=batch_size, shuffle=False
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    model = _PatchExpressionTransformer(
        n_components=x_train.shape[1],
        n_genes=y_train.shape[1],
        d_model=d_model,
        n_heads=n_heads,
        n_layers=n_layers,
        dropout=dropout,
    ).to(target_device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    history = []

    for epoch in range(epochs):
        model.train()
        total = 0.0
        for xb, yb in train_loader:
            xb, yb = xb.to(target_device), yb.to(target_device)
            optimizer.zero_grad(set_to_none=True)
            loss = F.mse_loss(model(xb), yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total += loss.item() * len(xb)
        train_loss = total / len(x_train)

        model.eval()
        test_squared_error = 0.0
        final_predictions = []
        with torch.inference_mode():
            for xb, yb in test_loader:
                xb, yb = xb.to(target_device), yb.to(target_device)
                predicted = model(xb)
                test_squared_error += F.mse_loss(
                    predicted, yb, reduction="sum"
                ).item()
                if epoch + 1 == epochs:
                    final_predictions.append(predicted.cpu())

        test_loss = test_squared_error / y_test.numel()
        history.append(
            {
                "epoch": epoch + 1,
                "train_loss": train_loss,
                "test_loss": test_loss,
                "train_mse": train_loss,
                "test_mse": test_loss,
            }
        )
        _save_training_history(history, output)
        print(
            f"Epoch {epoch + 1}/{epochs} | train_loss (MSE): {train_loss:.6f} | "
            f"test_loss (MSE): {test_loss:.6f}",
            flush=True,
        )

    prediction = torch.cat(final_predictions)
    actual = y_test
    pred_np, actual_np = prediction.numpy(), actual.numpy()
    pcc = []
    for j in range(actual_np.shape[1]):
        actual_gene, predicted_gene = actual_np[:, j], pred_np[:, j]
        pcc.append(
            float(np.corrcoef(predicted_gene, actual_gene)[0, 1])
            if np.std(predicted_gene) > 0 and np.std(actual_gene) > 0
            else float("nan")
        )
    std = (
        np.std(actual_np, axis=0, ddof=1)
        if len(actual_np) > 1
        else np.zeros(actual_np.shape[1])
    )
    nmae = np.abs(pred_np - actual_np).mean(axis=0) / np.maximum(std, 1e-8)
    config = {
        "n_components": x_train.shape[1],
        "n_genes": y_train.shape[1],
        "d_model": d_model,
        "n_heads": n_heads,
        "n_layers": n_layers,
        "dropout": dropout,
        "seed": seed,
        "device": str(target_device),
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "loss": "mse",
    }
    torch.save(
        {
            "model_state_dict": model.cpu().state_dict(),
            "model_config": config,
        },
        output / "patch_gene_transformer.pt",
    )
    metrics = {
        "train_loss": history[-1]["train_loss"],
        "test_loss": history[-1]["test_loss"],
        "mean_pcc": float(np.nanmean(pcc)),
        "per_gene_pcc": pcc,
        "mean_std_normalized_mae": float(np.mean(nmae)),
        "per_gene_std_normalized_mae": nmae.tolist(),
        "test_patches": len(x_test),
        "history": history,
        "model_config": config,
    }
    (output / "test_metrics.json").write_text(
        json.dumps(metrics, indent=2, allow_nan=True), encoding="utf-8"
    )
    torch.save(prediction, output / "test_predictions.pt")
    plot_loss_history(history, output / "training_loss.png")
    return model, metrics


def _save_training_history(history, output_dir):
    """Write the current epoch history to CSV and JSON files."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    csv_path = output / "training_history.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["epoch", "train_loss", "test_loss", "train_mse", "test_mse"],
        )
        writer.writeheader()
        writer.writerows(history)

    json_path = output / "training_history.json"
    with json_path.open("w", encoding="utf-8") as json_file:
        json.dump(history, json_file, indent=2)
