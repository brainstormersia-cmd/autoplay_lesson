"""Create a portable DarkPegaso release folder ready for sharing."""

from __future__ import annotations

import argparse
import json
import shutil
import textwrap
from pathlib import Path

from autoplay_lesson.client.assets import DEFAULT_LOGO_NAME, export_logo
from autoplay_lesson.client.version import VERSION


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare a distributable DarkPegaso folder",
    )
    parser.add_argument(
        "--exe",
        default=Path("dist") / "DarkPegaso.exe",
        type=Path,
        help="Percorso dell'eseguibile PyInstaller appena generato (default: dist/DarkPegaso.exe)",
    )
    parser.add_argument(
        "--output",
        default=Path("release"),
        type=Path,
        help="Directory in cui creare la cartella condivisibile (default: release)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Sovrascrive eventuali cartelle esistenti senza conferma",
    )
    return parser


def _write_config_template(target: Path) -> None:
    template = {
        "username": "",
        "password": "",
        "remember_me": False,
        "course_mode": "COMPLETE",
        "speed": 2.5,
        "verbose": True,
        "skip_pdf": False,
        "sound": False,
    }
    target.write_text(json.dumps(template, indent=2), encoding="utf-8")


def _write_release_readme(target: Path, exe_name: str) -> None:
    text = textwrap.dedent(
        f"""
        DarkPegaso Control Center v{VERSION}
        ==================================

        Contenuto della cartella:
        - {exe_name}: eseguibile principale
        - assets/{DEFAULT_LOGO_NAME}: logo utilizzato nell'interfaccia
        - config.json.example: file di configurazione di esempio

        Avvio rapido
        ------------
        1. Fai doppio click su {exe_name}.
        2. Inserisci le credenziali nella sezione Configurazione.
        3. Premi "Avvia Automazione" dalla Dashboard.

        Suggerimenti di distribuzione
        -----------------------------
        - Duplica config.json.example e rinominalo in config.json per fornire preset.
        - Inserisci nella stessa cartella eventuali guide o documenti aggiuntivi.
        - Comprimi l'intera directory in uno ZIP prima di condividerla.
        """
    ).strip() + "\n"
    target.write_text(text, encoding="utf-8")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    exe_path = args.exe.resolve()
    if not exe_path.is_file():
        raise SystemExit(f"Impossibile trovare l'eseguibile: {exe_path}")

    output_root = args.output.resolve()
    release_dir = output_root / f"DarkPegaso_{VERSION.replace('.', '_')}"

    if release_dir.exists():
        if args.force:
            shutil.rmtree(release_dir)
        else:
            raise SystemExit(
                f"La cartella {release_dir} esiste già. Usa --force per sovrascrivere."
            )

    release_dir.mkdir(parents=True, exist_ok=True)

    exe_target = release_dir / exe_path.name
    shutil.copy2(exe_path, exe_target)

    assets_dir = release_dir / "assets"
    assets_dir.mkdir(exist_ok=True)
    export_logo(assets_dir / DEFAULT_LOGO_NAME, size=(256, 256))

    _write_config_template(release_dir / "config.json.example")
    _write_release_readme(release_dir / "README.txt", exe_target.name)

    print(f"Cartella pronta: {release_dir}")


if __name__ == "__main__":
    main()
