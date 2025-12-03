#!/usr/bin/env python3
"""Download AI models for Phone Agent.

Downloads:
- Whisper (German STT)
- Llama 3.2 (LLM)
- Piper (German TTS)

Usage:
    python scripts/download_models.py
    python scripts/download_models.py --model whisper
    python scripts/download_models.py --model llm
    python scripts/download_models.py --model tts
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Model configurations
MODELS = {
    "whisper": {
        "name": "distil-whisper-large-v3-german",
        "repo": "primeline/distil-whisper-large-v3-german",
        "size": "~750MB",
        "type": "huggingface",
        "path": "models/whisper",
    },
    "llm": {
        "name": "Llama 3.2 1B Instruct (Q4_K_M)",
        "url": "https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF/resolve/main/Llama-3.2-1B-Instruct-Q4_K_M.gguf",
        "filename": "llama-3.2-1b-instruct-q4_k_m.gguf",
        "size": "~800MB",
        "type": "direct",
        "path": "models/llm",
    },
    "llm-3b": {
        "name": "Llama 3.2 3B Instruct (Q4_K_M)",
        "url": "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "filename": "llama-3.2-3b-instruct-q4_k_m.gguf",
        "size": "~2GB",
        "type": "direct",
        "path": "models/llm",
    },
    "tts": {
        "name": "Piper TTS Thorsten (German)",
        "voice": "de_DE-thorsten-medium",
        "size": "~30MB",
        "type": "piper",
        "path": "models/tts",
    },
}


def print_header(text: str) -> None:
    """Print a header line."""
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")


def print_status(message: str, status: str = "INFO") -> None:
    """Print a status message."""
    colors = {
        "INFO": "\033[94m",
        "OK": "\033[92m",
        "WARN": "\033[93m",
        "ERROR": "\033[91m",
    }
    reset = "\033[0m"
    color = colors.get(status, "")
    print(f"{color}[{status}]{reset} {message}")


def check_dependencies() -> bool:
    """Check if required tools are installed."""
    deps_ok = True

    # Check for huggingface-cli
    try:
        subprocess.run(
            ["huggingface-cli", "--version"],
            capture_output=True,
            check=True,
        )
        print_status("huggingface-cli installed", "OK")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_status("huggingface-cli not found. Install with: pip install huggingface_hub", "WARN")

    # Check for wget/curl
    for tool in ["wget", "curl"]:
        try:
            subprocess.run([tool, "--version"], capture_output=True, check=True)
            print_status(f"{tool} installed", "OK")
            break
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    else:
        print_status("Neither wget nor curl found", "WARN")

    return deps_ok


def download_huggingface(repo: str, target_path: Path) -> bool:
    """Download model from HuggingFace Hub."""
    print_status(f"Downloading from HuggingFace: {repo}")

    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=repo,
            local_dir=target_path,
            local_dir_use_symlinks=False,
        )
        print_status(f"Downloaded to {target_path}", "OK")
        return True
    except ImportError:
        print_status("huggingface_hub not installed", "ERROR")
        print_status("Install with: pip install huggingface_hub", "INFO")
        return False
    except Exception as e:
        print_status(f"Download failed: {e}", "ERROR")
        return False


def download_direct(url: str, target_path: Path, filename: str) -> bool:
    """Download file directly via wget/curl."""
    target_file = target_path / filename

    if target_file.exists():
        print_status(f"File already exists: {target_file}", "OK")
        return True

    print_status(f"Downloading: {filename}")
    print_status(f"URL: {url}")

    target_path.mkdir(parents=True, exist_ok=True)

    # Try wget first, then curl
    try:
        subprocess.run(
            ["wget", "-O", str(target_file), url],
            check=True,
        )
        print_status(f"Downloaded to {target_file}", "OK")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    try:
        subprocess.run(
            ["curl", "-L", "-o", str(target_file), url],
            check=True,
        )
        print_status(f"Downloaded to {target_file}", "OK")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_status("Download failed - install wget or curl", "ERROR")
        return False


def download_piper(voice: str, target_path: Path) -> bool:
    """Download Piper TTS voice model."""
    print_status(f"Downloading Piper voice: {voice}")

    target_path.mkdir(parents=True, exist_ok=True)

    # Piper model URLs
    base_url = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium"
    model_url = f"{base_url}/de_DE-thorsten-medium.onnx"
    config_url = f"{base_url}/de_DE-thorsten-medium.onnx.json"

    model_file = target_path / f"{voice}.onnx"
    config_file = target_path / f"{voice}.onnx.json"

    success = True

    for url, target in [(model_url, model_file), (config_url, config_file)]:
        if target.exists():
            print_status(f"File exists: {target.name}", "OK")
            continue

        try:
            subprocess.run(["wget", "-O", str(target), url], check=True)
            print_status(f"Downloaded: {target.name}", "OK")
        except (subprocess.CalledProcessError, FileNotFoundError):
            try:
                subprocess.run(["curl", "-L", "-o", str(target), url], check=True)
                print_status(f"Downloaded: {target.name}", "OK")
            except (subprocess.CalledProcessError, FileNotFoundError):
                print_status(f"Failed to download: {target.name}", "ERROR")
                success = False

    return success


def download_model(model_key: str, base_path: Path) -> bool:
    """Download a specific model."""
    if model_key not in MODELS:
        print_status(f"Unknown model: {model_key}", "ERROR")
        return False

    config = MODELS[model_key]
    target_path = base_path / config["path"]

    print_header(f"Downloading: {config['name']} ({config['size']})")

    if config["type"] == "huggingface":
        return download_huggingface(config["repo"], target_path / config["name"])
    elif config["type"] == "direct":
        return download_direct(config["url"], target_path, config["filename"])
    elif config["type"] == "piper":
        return download_piper(config["voice"], target_path)
    else:
        print_status(f"Unknown download type: {config['type']}", "ERROR")
        return False


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download AI models for Phone Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/download_models.py                  # Download all
    python scripts/download_models.py --model whisper  # Only STT
    python scripts/download_models.py --model llm      # Only LLM (1B)
    python scripts/download_models.py --model llm-3b   # LLM (3B, larger)
    python scripts/download_models.py --model tts      # Only TTS
    python scripts/download_models.py --list           # List available models
        """,
    )
    parser.add_argument(
        "--model",
        choices=list(MODELS.keys()),
        help="Download specific model only",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available models",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Base path for model storage (default: current directory)",
    )

    args = parser.parse_args()

    if args.list:
        print_header("Available Models")
        for key, config in MODELS.items():
            print(f"  {key:12} - {config['name']} ({config['size']})")
        return 0

    print_header("IT-Friends Phone Agent - Model Downloader")

    # Check dependencies
    check_dependencies()

    # Determine which models to download
    if args.model:
        models_to_download = [args.model]
    else:
        # Default: whisper, llm (1B), tts
        models_to_download = ["whisper", "llm", "tts"]

    print_status(f"Will download: {', '.join(models_to_download)}")
    print_status(f"Target path: {args.path}")

    # Download models
    results = {}
    for model_key in models_to_download:
        results[model_key] = download_model(model_key, args.path)

    # Summary
    print_header("Download Summary")
    all_ok = True
    for model_key, success in results.items():
        status = "OK" if success else "FAILED"
        print_status(f"{MODELS[model_key]['name']}: {status}", "OK" if success else "ERROR")
        if not success:
            all_ok = False

    if all_ok:
        print_status("\nAll models downloaded successfully!", "OK")
        print_status("You can now run the phone agent.", "INFO")
    else:
        print_status("\nSome downloads failed. Check errors above.", "ERROR")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
