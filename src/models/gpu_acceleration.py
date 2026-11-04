"""GPU Acceleration & Supervised Causal Quantile TCN Module.

Leverages NVIDIA CUDA architecture (e.g. NVIDIA RTX 4060 8GB VRAM) for
high-throughput batch sequence processing, parallel tensor embeddings,
and supervised Pinball-Loss non-crossing quantile projections (q10 <= q50 <= q90).
"""

from dataclasses import dataclass
import logging
import os
import shutil
import subprocess
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)


@dataclass
class HardwareProfile:
    cuda_available: bool
    device_name: str
    compute_capability: str
    total_memory_mb: float
    free_memory_mb: float
    driver_version: str
    cuda_runtime_version: str
    recommended_batch_size: int
    precision_mode: str  # "fp16", "bf16", or "fp32"


class GPUManager:
    """Manages GPU resource allocation, VRAM limits, and hardware diagnostics."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GPUManager, cls).__new__(cls)
            cls._instance._init_hardware()
        return cls._instance

    def _init_hardware(self):
        self.cuda_available = torch.cuda.is_available()
        self.device = torch.device("cuda:0" if self.cuda_available else "cpu")
        self.profile = self.detect_hardware()
        logger.info(
            f"Hardware acceleration initialized on: {self.profile.device_name} "
            f"(CUDA: {self.profile.cuda_available}, VRAM: {self.profile.free_memory_mb:.1f}MB Free)"
        )

    def detect_hardware(self) -> HardwareProfile:
        """Probes system GPU, driver, and CUDA compute capability."""
        device_name = "CPU (Multi-Core AVX2)"
        comp_cap = "N/A"
        total_mem = 0.0
        free_mem = 0.0
        driver_ver = "N/A"
        cuda_ver = "N/A"
        precision = "fp32"
        batch_size = 32

        if self.cuda_available:
            try:
                device_name = torch.cuda.get_device_name(0)
                major, minor = torch.cuda.get_device_capability(0)
                comp_cap = f"{major}.{minor}"
                total_mem = torch.cuda.get_device_properties(0).total_memory / (1024**2)
                free_mem = (
                    total_mem - (torch.cuda.memory_allocated(0) / (1024**2))
                )
                cuda_ver = torch.version.cuda or "N/A"
                driver_ver = "Installed"

                if major >= 8:
                    precision = "bf16" if torch.cuda.is_bf16_supported() else "fp16"
                    batch_size = 128
                else:
                    precision = "fp16"
                    batch_size = 64
            except Exception as e:
                logger.warning(f"Error querying torch.cuda properties: {e}")

        if not self.cuda_available and shutil.which("nvidia-smi"):
            try:
                res = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=name,memory.total,memory.free,driver_version",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if res.returncode == 0:
                    lines = res.stdout.strip().split("\n")
                    if lines and len(lines[0].split(",")) >= 4:
                        parts = [p.strip() for p in lines[0].split(",")]
                        device_name = f"{parts[0]} (Hardware Ready)"
                        total_mem = float(parts[1])
                        free_mem = float(parts[2])
                        driver_ver = parts[3]
            except Exception:
                pass

        return HardwareProfile(
            cuda_available=self.cuda_available,
            device_name=device_name,
            compute_capability=comp_cap,
            total_memory_mb=round(total_mem, 1),
            free_memory_mb=round(free_mem, 1),
            driver_version=driver_ver,
            cuda_runtime_version=cuda_ver,
            recommended_batch_size=batch_size,
            precision_mode=precision,
        )

    def get_device(self) -> torch.device:
        return self.device

    def to_device(self, tensor: torch.Tensor) -> torch.Tensor:
        return tensor.to(self.device)


class CausalQuantileTCN(nn.Module):
    """Causal Dilated Temporal Convolutional Network with Monotonic Quantile Head.

    Guarantees non-crossing quantile predictions: q10 <= q50 <= q90 via Softplus offsets.
    """

    def __init__(self, in_channels: int = 5, emb_dim: int = 32):
        super().__init__()
        self.pad1 = nn.ConstantPad1d((2, 0), 0.0)  # Causal left padding for k=3, d=1
        self.conv1 = nn.Conv1d(in_channels, emb_dim, kernel_size=3, dilation=1)
        self.pad2 = nn.ConstantPad1d((4, 0), 0.0)  # Causal left padding for k=3, d=2
        self.conv2 = nn.Conv1d(emb_dim, emb_dim, kernel_size=3, dilation=2)
        self.norm = nn.LayerNorm(emb_dim)
        self.head = nn.Linear(emb_dim, 3)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, 5, L)
        h1 = F.gelu(self.conv1(self.pad1(x)))
        h2 = F.gelu(self.conv2(self.pad2(h1))) + h1  # Residual connection
        # Take causal final time step representation + global average pooling
        pooled = 0.5 * h2[:, :, -1] + 0.5 * h2.mean(dim=-1)
        normed = self.norm(pooled)
        raw = torch.tanh(self.head(normed)) * 0.08  # Bounded shock scale [-8%, +8%]

        q50 = raw[:, 1]
        spread_down = F.softplus(raw[:, 0]) * 0.03 + 1e-4
        spread_up = F.softplus(raw[:, 2]) * 0.03 + 1e-4

        q10 = q50 - spread_down
        q90 = q50 + spread_up
        return torch.stack([q10, q50, q90], dim=-1)


def pinball_quantile_loss(
    preds: torch.Tensor,
    targets: torch.Tensor,
    quantiles: Tuple[float, float, float] = (0.10, 0.50, 0.90),
) -> torch.Tensor:
    """Computes Pinball Loss across multiple quantiles simultaneously."""
    losses = []
    target_col = targets.unsqueeze(-1)  # (B, 1)
    for idx, q in enumerate(quantiles):
        err = target_col[:, 0] - preds[:, idx]
        losses.append(torch.maximum(q * err, (q - 1.0) * err).mean())
    return sum(losses) / len(losses)


class TorchSequenceForecaster:
    """Supervised PyTorch Causal TCN sequence encoder for multi-horizon quantile projections."""

    def __init__(
        self,
        sequence_length: int = 30,
        embedding_dim: int = 32,
        horizon: int = 5,
    ):
        self.seq_len = sequence_length
        self.emb_dim = embedding_dim
        self.horizon = horizon
        self.gpu_mgr = GPUManager()
        self.device = self.gpu_mgr.get_device()

        torch.manual_seed(42)
        self.net = CausalQuantileTCN(in_channels=5, emb_dim=self.emb_dim).to(self.device)
        self.net.eval()
        self.is_trained: bool = False
        self._last_trained_len: int = 0

    @staticmethod
    def _extract_channels(df: pd.DataFrame) -> np.ndarray:
        """Extracts 5 normalized geometric candle channels (pct_c, body_open, upper_wick, lower_wick, vol_z)."""
        c = df["Close"].values.astype(np.float32)
        o = df["Open"].values.astype(np.float32) / (c + 1e-8) - 1.0
        h = df["High"].values.astype(np.float32) / (c + 1e-8) - 1.0
        l = df["Low"].values.astype(np.float32) / (c + 1e-8) - 1.0
        pct_c = np.diff(c, prepend=c[0]) / (c + 1e-8)
        v = df["Volume"].values.astype(np.float32)
        v_norm = (v - np.mean(v)) / (np.std(v) + 1e-8)
        return np.stack([pct_c, o, h, l, v_norm], axis=0)  # (5, N)

    def fit(
        self,
        ohlcv_df: pd.DataFrame,
        epochs: int = 12,
        lr: float = 0.005,
    ) -> float:
        """Trains the Causal TCN using Pinball Quantile Loss on strictly historical windows.

        Uses purged targets (excluding the final `horizon` bars) so zero future information leaks.
        """
        n_rows = len(ohlcv_df)
        min_required = self.seq_len + self.horizon + 15
        if n_rows < min_required:
            return 0.0

        channels = self._extract_channels(ohlcv_df)  # (5, N)
        closes = ohlcv_df["Close"].values.astype(np.float32)

        # Build sliding windows up to n_rows - horizon (purged forward targets)
        max_start = n_rows - self.seq_len - self.horizon
        if max_start < 10:
            return 0.0

        # Subsample stride=2 if large for ultra-fast (<15 ms) walk-forward training
        stride = 2 if max_start > 120 else 1
        starts = range(0, max_start, stride)

        X_list = []
        y_list = []
        for s in starts:
            end_idx = s + self.seq_len
            target_idx = end_idx + self.horizon - 1
            X_list.append(channels[:, s:end_idx])
            fwd_ret = (closes[target_idx] - closes[end_idx - 1]) / (closes[end_idx - 1] + 1e-8)
            y_list.append(fwd_ret)

        X_tensor = torch.tensor(np.stack(X_list, axis=0), dtype=torch.float32, device=self.device)
        y_tensor = torch.tensor(np.array(y_list, dtype=np.float32), dtype=torch.float32, device=self.device)

        self.net.train()
        optimizer = torch.optim.AdamW(self.net.parameters(), lr=lr, weight_decay=1e-4)
        final_loss = 0.0

        for _ in range(epochs):
            optimizer.zero_grad()
            preds = self.net(X_tensor)
            loss = pinball_quantile_loss(preds, y_tensor)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.net.parameters(), 1.0)
            optimizer.step()
            final_loss = float(loss.item())

        self.net.eval()
        self.is_trained = True
        self._last_trained_len = n_rows
        return final_loss

    def forecast_tensor(self, ohlcv_df: pd.DataFrame) -> Tuple[float, float, float]:
        """Processes normalized OHLCV window and outputs monotonic non-crossing (q10, q50, q90) shocks."""
        if not self.is_trained and len(ohlcv_df) >= self.seq_len + self.horizon + 15:
            self.fit(ohlcv_df)

        if len(ohlcv_df) < self.seq_len:
            recent = ohlcv_df.copy()
            pad_len = self.seq_len - len(recent)
            pad_rows = pd.concat([recent.iloc[[0]]] * pad_len, ignore_index=True)
            recent = pd.concat([pad_rows, recent], ignore_index=True)
        else:
            recent = ohlcv_df.iloc[-self.seq_len :].copy()

        tensor_in = self._extract_channels(recent)
        t = torch.tensor(tensor_in, dtype=torch.float32).unsqueeze(0).to(self.device)

        self.net.eval()
        with torch.no_grad():
            preds = self.net(t).squeeze(0).cpu().numpy()

        q10_shock = float(preds[0])
        q50_shock = float(preds[1])
        q90_shock = float(preds[2])
        return q10_shock, q50_shock, q90_shock

    def evaluate_directional_conviction(self, ohlcv_df: pd.DataFrame) -> Tuple[int, float]:
        """Evaluates sequence geometric trajectory and skew of trained quantile shocks.

        Returns:
            (direction: 1 or -1, probability: float [0.0, 1.0])
        """
        q10, q50, q90 = self.forecast_tensor(ohlcv_df)

        recent = ohlcv_df.iloc[-min(len(ohlcv_df), 20) :]
        ret_recent = (recent["Close"].iloc[-1] - recent["Close"].iloc[0]) / (
            recent["Close"].iloc[0] + 1e-8
        )

        # Quantile asymmetry + median shock + 20-bar geometric trajectory
        quantile_skew = (q90 + q10) * 0.5
        drift = 0.60 * q50 + 0.25 * quantile_skew + 0.15 * float(ret_recent)

        prob = float(1.0 / (1.0 + np.exp(-drift * 30.0)))
        direction = 1 if prob >= 0.50 else -1
        return direction, round(prob, 3)

    def batch_forecast_universe(
        self, ohlcv_dict: Dict[str, pd.DataFrame]
    ) -> Dict[str, Tuple[float, float, float]]:
        """Batches multiple assets into a single 3D tensor on GPU/CPU for ultra-fast inference."""
        if not ohlcv_dict:
            return {}

        valid_tickers = []
        tensors = []

        for ticker, df in ohlcv_dict.items():
            if df.empty or len(df) < 10:
                continue

            if not self.is_trained and len(df) >= self.seq_len + self.horizon + 15:
                self.fit(df)

            if len(df) < self.seq_len:
                pad_len = self.seq_len - len(df)
                pad_rows = pd.concat([df.iloc[[0]]] * pad_len, ignore_index=True)
                recent = pd.concat([pad_rows, df], ignore_index=True)
            else:
                recent = df.iloc[-self.seq_len :].copy()

            t_asset = self._extract_channels(recent)
            tensors.append(t_asset)
            valid_tickers.append(ticker)

        if not tensors:
            return {}

        batch_arr = np.stack(tensors, axis=0)  # Shape: (N, 5, seq_len)
        batch_t = torch.tensor(batch_arr, dtype=torch.float32).to(self.device)

        self.net.eval()
        with torch.no_grad():
            preds = self.net(batch_t).cpu().numpy()

        results = {}
        for i, ticker in enumerate(valid_tickers):
            q10 = float(preds[i, 0])
            q50 = float(preds[i, 1])
            q90 = float(preds[i, 2])
            results[ticker] = (round(q10, 4), round(q50, 4), round(q90, 4))

        return results
