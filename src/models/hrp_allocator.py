"""Hierarchical Risk Parity (HRP) & Covariance De-noising Module.

Constructs institutional-grade diversified portfolios without inverting
unstable covariance matrices (eliminates Markowitz error maximization).
Based on Marcos López de Prado (Machine Learning for Asset Managers, Chapter 2 & 7).
Includes Diagonal-Preserving Marchenko-Pastur RMT De-noising and Ward's Linkage.
"""

from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform


class HierarchicalRiskParity:
    """Calculates HRP weights and applies diagonal-preserving Marchenko-Pastur covariance cleaning."""

    @staticmethod
    def denoise_covariance(
        cov: np.ndarray, t_obs: int, n_assets: int
    ) -> np.ndarray:
        """Marchenko-Pastur RMT de-noising using constant residual eigenvalue method.

        Strictly preserves the original asset variances on the diagonal:
        diag(Sigma_clean) == diag(Sigma_raw).
        """
        if cov.shape[0] <= 1:
            return cov.copy()

        raw_diag_var = np.diag(cov).copy()
        std_diag = np.sqrt(np.maximum(raw_diag_var, 1e-12))

        # Normalize to symmetric correlation matrix
        corr = cov / np.outer(std_diag, std_diag)
        corr = np.clip(0.5 * (corr + corr.T), -1.0, 1.0)
        np.fill_diagonal(corr, 1.0)

        # Eigendecomposition
        evals, evecs = np.linalg.eigh(corr)
        idx = np.argsort(evals)[::-1]
        evals, evecs = evals[idx], evecs[:, idx]

        # Theoretical Marchenko-Pastur upper bound lambda_+
        q = max(float(t_obs) / max(float(n_assets), 1.0), 1.05)
        sigma_sq = 1.0
        lambda_max = sigma_sq * ((1.0 + np.sqrt(1.0 / q)) ** 2)

        # Replace noise eigenvalues with constant average residual while preserving trace
        signal_mask = evals > lambda_max
        denoised_evals = evals.copy()
        if np.any(~signal_mask) and np.any(signal_mask):
            mean_noise = max(float(np.mean(evals[~signal_mask])), 1e-6)
            denoised_evals[~signal_mask] = mean_noise

        # Reconstruct clean correlation & project back to covariance
        clean_corr = evecs @ np.diag(denoised_evals) @ evecs.T
        d_clean = np.maximum(np.diag(clean_corr), 1e-12)
        clean_corr = clean_corr / np.sqrt(np.outer(d_clean, d_clean))
        clean_corr = np.clip(0.5 * (clean_corr + clean_corr.T), -1.0, 1.0)
        np.fill_diagonal(clean_corr, 1.0)

        clean_cov = clean_corr * np.outer(std_diag, std_diag)
        np.fill_diagonal(clean_cov, raw_diag_var)
        return clean_cov

    @classmethod
    def compute_hrp_weights(cls, returns_df: pd.DataFrame) -> pd.Series:
        """Computes optimal HRP portfolio weights across a universe of assets."""
        if returns_df.empty:
            return pd.Series(dtype=float)

        clean_returns = returns_df.dropna(how="all").fillna(0.0)
        t_obs, n_assets = clean_returns.shape
        if n_assets == 1:
            return pd.Series([1.0], index=clean_returns.columns)

        raw_cov = clean_returns.cov().fillna(0.0).to_numpy(dtype=np.float64, copy=True)
        # Ensure positive variance on diagonal
        diag_idx = np.diag_indices_from(raw_cov)
        raw_cov[diag_idx] = np.maximum(raw_cov[diag_idx], 1e-8)

        # 1. Apply Diagonal-Preserving Marchenko-Pastur RMT De-noising
        clean_cov = cls.denoise_covariance(raw_cov, t_obs=max(t_obs, n_assets + 2), n_assets=n_assets)
        std_diag = np.sqrt(np.maximum(np.diag(clean_cov), 1e-12))
        clean_corr = np.clip(clean_cov / np.outer(std_diag, std_diag), -1.0, 1.0)
        np.fill_diagonal(clean_corr, 1.0)

        # 2. Correlation Distance Matrix: D_{i,j} = sqrt(0.5 * (1 - rho_{i,j}))
        dist = np.sqrt(np.clip(0.5 * (1.0 - clean_corr), 0.0, 1.0))
        np.fill_diagonal(dist, 0.0)

        # 3. Euclidean Distance of Distance Matrix & Ward's Minimum-Variance Linkage
        # Eliminates single-linkage chaining across noisy macro assets
        condensed_dist = squareform(dist, checks=False)
        link = linkage(condensed_dist, method="ward")

        # 4. Quasi-Diagonalization (Sort tree leaves)
        sort_idx = cls._get_quasi_diag(link)
        sorted_tickers = [clean_returns.columns[i] for i in sort_idx]
        sorted_cov = pd.DataFrame(
            clean_cov, index=clean_returns.columns, columns=clean_returns.columns
        ).loc[sorted_tickers, sorted_tickers]

        # 5. Recursive Bisection
        weights = pd.Series(1.0, index=sorted_tickers)
        cluster_list = [sorted_tickers]

        while len(cluster_list) > 0:
            new_clusters = []
            for cluster in cluster_list:
                if len(cluster) > 1:
                    mid = len(cluster) // 2
                    c1 = cluster[:mid]
                    c2 = cluster[mid:]

                    v1 = cls._get_cluster_var(sorted_cov.loc[c1, c1])
                    v2 = cls._get_cluster_var(sorted_cov.loc[c2, c2])

                    alpha = 1.0 - (v1 / (v1 + v2 + 1e-12))
                    weights[c1] *= alpha
                    weights[c2] *= 1.0 - alpha

                    new_clusters.append(c1)
                    new_clusters.append(c2)
            cluster_list = new_clusters

        # Reindex to original column order
        weights = weights.reindex(clean_returns.columns).fillna(0.0)
        return (weights / max(weights.sum(), 1e-12)).round(4)

    @staticmethod
    def _get_quasi_diag(link: np.ndarray) -> List[int]:
        num_leaves = link.shape[0] + 1
        curr_order = [int(link[-1, 0]), int(link[-1, 1])]
        while any(i >= num_leaves for i in curr_order):
            expanded_order = []
            for idx in curr_order:
                if idx >= num_leaves:
                    cluster_row = idx - num_leaves
                    expanded_order.append(int(link[cluster_row, 0]))
                    expanded_order.append(int(link[cluster_row, 1]))
                else:
                    expanded_order.append(idx)
            curr_order = expanded_order
        return curr_order

    @staticmethod
    def _get_cluster_var(sub_cov: pd.DataFrame) -> float:
        diag_vals = np.maximum(np.diag(sub_cov.values), 1e-12)
        ivp = 1.0 / diag_vals
        ivp /= np.sum(ivp)
        w = ivp.reshape(-1, 1)
        res = w.T @ sub_cov.values @ w
        return float(np.asarray(res).item())
