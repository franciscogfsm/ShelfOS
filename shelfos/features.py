"""DINOv3 embeddings of rectified planogram-area crops."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch

from .planogram import Area

MODEL_NAME = "vit_base_patch16_dinov3.lvd1689m"
CROP = 224
GRID = 14
PAD = 0.08
WEIGHTS_DIR = Path(__file__).resolve().parents[1] / "models" / "backbone"
_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_STD = np.array([0.229, 0.224, 0.225], np.float32)


def load_backbone(model_name: str = MODEL_NAME, weights_dir: Path = WEIGHTS_DIR):
    """Frozen backbone. Weights are kept next to the project after the first download, so every
    later start is offline and does not depend on the network."""
    import timm

    local = Path(weights_dir) / f"{model_name}.pt"
    if local.exists():
        model = timm.create_model(model_name, pretrained=False, num_classes=0)
        model.load_state_dict(torch.load(local, map_location="cpu", weights_only=True))
    else:
        model = timm.create_model(model_name, pretrained=True, num_classes=0)
        local.parent.mkdir(parents=True, exist_ok=True)
        torch.save(model.state_dict(), local)
    return model.eval()


class Embedder:
    def __init__(self, model_name: str = MODEL_NAME, device: str | None = None, size: int = CROP):
        self.size = size
        self.model_name = model_name
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = load_backbone(model_name).to(self.device)
        self.n_prefix = getattr(self.model, "num_prefix_tokens", 1)
        self.half = self.device == "cuda"  # half precision on GPU: 3x faster, cosine to fp32 > 0.99999
        if self.device == "cpu":
            torch.set_num_threads(max(1, (torch.get_num_threads() or 4)))

    def crop(self, image: np.ndarray, area: Area) -> np.ndarray:
        """Rectified BGR crop; pixels outside the camera image are filled with neutral grey."""
        crop, valid = area.warp(image, (self.size, self.size), pad=PAD)
        crop[~valid] = 124
        return crop

    @torch.inference_mode()
    def embed(self, crops: list[np.ndarray], batch: int = 64) -> tuple[np.ndarray, np.ndarray]:
        """Return (global [N, 2D] = CLS ++ mean patch, patches [N, P, D]) L2-normalised."""
        glob, patches = [], []
        norm = torch.nn.functional.normalize
        for i in range(0, len(crops), batch):
            x = np.stack([cv2.cvtColor(c, cv2.COLOR_BGR2RGB) for c in crops[i : i + batch]]).astype(np.float32) / 255
            x = torch.from_numpy(((x - _MEAN) / _STD).transpose(0, 3, 1, 2)).to(self.device)
            with torch.autocast(self.device, dtype=torch.float16, enabled=self.half):
                tok = self.model.forward_features(x)
            tok = tok.float()
            cls, pt = tok[:, 0], tok[:, self.n_prefix :]
            side = int(pt.shape[1] ** 0.5)
            if side > GRID:  # larger inputs: pool the token grid back to GRID x GRID
                pt = torch.nn.functional.adaptive_avg_pool2d(pt.transpose(1, 2).reshape(len(pt), -1, side, side), GRID).flatten(2).transpose(1, 2)
            glob.append(torch.cat([norm(cls, dim=-1), norm(pt.mean(1), dim=-1)], -1).cpu().numpy())
            patches.append(norm(pt, dim=-1).cpu().numpy().astype(np.float16))
        return np.concatenate(glob), np.concatenate(patches)

    def warmup(self) -> None:
        self.embed([np.full((self.size, self.size, 3), 124, np.uint8)] * 4)
