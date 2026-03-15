"""Compatibility shim for the extracted public PortWorld CLI entrypoint."""

from portworld_cli.main import *  # noqa: F401,F403

if __name__ == "__main__":
    from portworld_cli.main import main

    main()
