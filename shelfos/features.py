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


def split_names(model_name: str) -> list[str]:
    """'a+b' names an ensemble of backbones whose features are concatenated."""
    return [n.strip() for n in str(model_name).split("+") if n.strip()]


class Embedder:
    """One or more frozen backbones ('name_a+name_b' = ensemble: unit features of each are concatenated
    and rescaled so the result has the same norm as a single model). tta: also embed the mirrored crop
    and average (the patch grid is mirrored back first)."""

    def __init__(self, model_name: str = MODEL_NAME, device: str | None = None, size: int = CROP, tta: bool = False):
        self.size = size
        self.model_name = model_name
        self.tta = bool(tta)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.models = [load_backbone(n).to(self.device) for n in split_names(model_name)]
        self.model = self.models[0]
        self.n_prefix = [getattr(m, "num_prefix_tokens", 1) for m in self.models]
        self.half = self.device == "cuda"  # half precision on GPU: 3x faster, cosine to fp32 > 0.99999
        self._plans: dict = {}  # the cameras are fixed, so every area's rectification is computed once
        if self.device == "cpu":
            torch.set_num_threads(max(1, (torch.get_num_threads() or 4)))

    def crop(self, image: np.ndarray, area: Area) -> np.ndarray:
        """Rectified BGR crop; pixels outside the camera image are filled with neutral grey."""
        key = (area.area_id, image.shape[0], image.shape[1])
        plan = self._plans.get(key)
        if plan is None:
            plan = self._plans[key] = area.warp_plan(image.shape, (self.size, self.size), PAD)
        crop = cv2.warpPerspective(image, plan[0], (self.size, self.size), flags=cv2.INTER_LINEAR)
        crop[~plan[1]] = 124
        return crop

    @torch.inference_mode()
    def embed(self, crops: list[np.ndarray], batch: int = 64, compact: bool = True) -> tuple[np.ndarray, np.ndarray]:
        """Return (global [N, 2D] = CLS ++ mean patch, patches [N, P, D]) L2-normalised.
        compact: patches as float16 (for the stored bank); float32 is quicker to use right away."""
        glob, patches = [], []
        norm = torch.nn.functional.normalize
        scale = 1.0 / len(self.models) ** 0.5
        for i in range(0, len(crops), batch):
            x = np.stack([cv2.cvtColor(c, cv2.COLOR_BGR2RGB) for c in crops[i : i + batch]]).astype(np.float32) / 255
            x = torch.from_numpy(((x - _MEAN) / _STD).transpose(0, 3, 1, 2)).to(self.device)
            cls_parts, mean_parts, patch_parts = [], [], []
            for model, n_prefix in zip(self.models, self.n_prefix):
                cls, pt = self._forward(model, n_prefix, x)
                if self.tta:
                    cls2, pt2 = self._forward(model, n_prefix, torch.flip(x, dims=[3]))
                    pt2 = pt2.reshape(len(pt2), GRID, GRID, -1).flip(2).reshape(len(pt2), GRID * GRID, -1)
                    cls, pt = (cls + cls2) / 2, (pt + pt2) / 2
                cls_parts.append(norm(cls, dim=-1) * scale)
                mean_parts.append(norm(pt.mean(1), dim=-1) * scale)
                patch_parts.append(norm(pt, dim=-1) * scale)
            glob.append(torch.cat(cls_parts + mean_parts, -1).cpu().numpy())
            p = torch.cat(patch_parts, -1).cpu().numpy()
            patches.append(p.astype(np.float16) if compact else p)
        return np.concatenate(glob), np.concatenate(patches)

    def _forward(self, model, n_prefix: int, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """-> (CLS [N, D], patch tokens [N, GRID*GRID, D]) in float32."""
        with torch.autocast(self.device, dtype=torch.float16, enabled=self.half):
            tok = model.forward_features(x)
        tok = tok.float()
        cls, pt = tok[:, 0], tok[:, n_prefix:]
        side = int(pt.shape[1] ** 0.5)
        if side > GRID:  # larger inputs: pool the token grid back to GRID x GRID
            pt = torch.nn.functional.adaptive_avg_pool2d(pt.transpose(1, 2).reshape(len(pt), -1, side, side), GRID).flatten(2).transpose(1, 2)
        return cls, pt

    def warmup(self) -> None:
        self.embed([np.full((self.size, self.size, 3), 124, np.uint8)] * 4)
