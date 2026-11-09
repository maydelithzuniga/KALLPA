"""Descarga el modelo faster-whisper «base» a ./models para usarlo sin conexión en la demo.

Uso:  python scripts/download_model.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.transcribe import model_path  # noqa: E402


def main() -> None:
    from huggingface_hub import snapshot_download
    target = model_path()
    target.mkdir(parents=True, exist_ok=True)
    repo = f"Systran/faster-whisper-{settings.whisper_model}"
    print(f"Descargando {repo} en {target} ...")
    snapshot_download(repo_id=repo, local_dir=str(target))
    print("Listo. El backend cargará el modelo desde disco.")


if __name__ == "__main__":
    main()
