from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib

from .config import settings


@dataclass
class ModelBundle:
    model: Any
    metadata: dict[str, Any]
    feature_names: list[str]
    model_version: str


def registry_root() -> Path:
    root = Path(settings.model_registry_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def make_model_version(model_name: str) -> str:
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{model_name}_{ts}"


def save_model_bundle(
    model_version: str,
    model: Any,
    metadata: dict[str, Any],
    feature_names: list[str],
) -> Path:
    model_dir = registry_root() / model_version
    model_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, model_dir / "model.joblib")
    (model_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (model_dir / "features.json").write_text(json.dumps(feature_names, ensure_ascii=False, indent=2), encoding="utf-8")
    return model_dir


def load_model_bundle(model_version: str) -> ModelBundle:
    model_dir = registry_root() / model_version
    model = joblib.load(model_dir / "model.joblib")
    metadata = json.loads((model_dir / "metadata.json").read_text(encoding="utf-8"))
    feature_names = json.loads((model_dir / "features.json").read_text(encoding="utf-8"))
    return ModelBundle(model=model, metadata=metadata, feature_names=feature_names, model_version=model_version)


def update_model_metadata(model_version: str, updates: dict[str, Any]) -> dict[str, Any]:
    model_dir = registry_root() / model_version
    metadata_path = model_dir / "metadata.json"
    current = json.loads(metadata_path.read_text(encoding="utf-8"))
    current.update(updates)
    metadata_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def load_champion_bundle(champion_version: str | None) -> ModelBundle | None:
    if not champion_version:
        return None
    model_dir = registry_root() / champion_version
    if not model_dir.exists():
        return None
    try:
        return load_model_bundle(champion_version)
    except Exception:
        return None
