"""console entry: serve / init / config。引数なしは TTY 判定（人=ウィザード / 非TTY=サーバ）。"""
import sys

from . import wizard


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    arg = argv[0] if argv else None

    if arg == "serve":
        from . import mcp_server
        raise SystemExit(mcp_server.serve())
    if arg in ("init", "setup"):
        return wizard.run_wizard()
    if arg == "config":
        return wizard.print_config(argv[1] if len(argv) > 1 else None)
    if arg == "selftest":
        from . import ontology
        return ontology.main(["--selftest-gate"])
    if arg in ("-v", "--version"):
        from . import __version__
        sys.stdout.write(__version__ + "\n")
        return 0
    if arg in ("-h", "--help", "help"):
        return wizard.help()
    if not arg:
        if sys.stdin.isatty():
            return wizard.run_wizard()
        from . import mcp_server
        raise SystemExit(mcp_server.serve())
    wizard.help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
