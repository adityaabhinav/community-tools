"""Command-line entry point for the ThoughtSpot group migrator."""

from __future__ import annotations
import argparse
import logging
import sys

from .client import TSConfig
from .migrator import GroupMigrator


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Migrate a ThoughtSpot group (users, objects, permissions) between clusters."
    )
    p.add_argument("group", help="Name of the root group to migrate")

    src = p.add_argument_group("Source cluster")
    src.add_argument("--src-url", required=True, help="Source ThoughtSpot URL")
    src.add_argument("--src-user", required=True, help="Source admin username")
    src.add_argument("--src-password", required=True, help="Source admin password")

    dst = p.add_argument_group("Destination cluster")
    dst.add_argument("--dst-url", required=True, help="Destination ThoughtSpot URL")
    dst.add_argument("--dst-user", required=True, help="Destination admin username")
    dst.add_argument("--dst-password", required=True, help="Destination admin password")

    p.add_argument(
        "--default-password",
        default="Changeme@123",
        help="Initial password for newly created users (default: Changeme@123)",
    )
    p.add_argument(
        "--save-bundle",
        metavar="PATH",
        help="Save the exported bundle as JSON to PATH (useful for auditing or retry)",
    )
    p.add_argument(
        "--from-bundle",
        metavar="PATH",
        help="Skip export; import from a previously saved bundle JSON",
    )
    p.add_argument("--no-verify-ssl", action="store_true", help="Disable SSL certificate verification")
    p.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    return p


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    verify_ssl = not args.no_verify_ssl

    src_cfg = TSConfig(
        url=args.src_url,
        username=args.src_user,
        password=args.src_password,
        verify_ssl=verify_ssl,
    )
    dst_cfg = TSConfig(
        url=args.dst_url,
        username=args.dst_user,
        password=args.dst_password,
        verify_ssl=verify_ssl,
    )

    migrator = GroupMigrator(
        source=src_cfg,
        destination=dst_cfg,
        default_user_password=args.default_password,
        bundle_cache_path=args.save_bundle,
    )

    try:
        if args.from_bundle:
            result = migrator.migrate_from_bundle(args.from_bundle)
        else:
            result = migrator.migrate(args.group)
    except Exception as exc:
        logging.error("Migration failed: %s", exc)
        return 1

    print("\n=== Migration Result ===")
    print(result.summary())
    if result.failed_objects:
        print("\nFailed objects:")
        for name in result.failed_objects:
            print(f"  - {name}")

    return 0 if not result.failed_objects else 2


if __name__ == "__main__":
    sys.exit(main())
