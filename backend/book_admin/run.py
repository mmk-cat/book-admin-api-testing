"""Run the demo API: ``python -m book_admin.run``."""

from __future__ import annotations

from .app import create_app
from .config import Settings


def main() -> None:
    settings = Settings.from_env()
    app = create_app(settings)
    app.run(
        host=settings.host,
        port=settings.port,
        threaded=True,
        use_reloader=False,
        debug=False,
    )


if __name__ == "__main__":
    main()
