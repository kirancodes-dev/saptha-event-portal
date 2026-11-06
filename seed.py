"""
seed.py — Unified database seeder for SapthaEvent.

Usage:
  python seed.py [--profile demo|events|scale|showcase] [--all] [--summary FILE]

Profiles:
  demo    (default) Seeds verified demo accounts for every role and the
          flagship HackSaptha hackathon event with complete lifecycle details.
  events  Seeds 7 diverse template events covering all event types
          (hackathon, conference, workshop, seminar, sports, cultural, webinar)
          with form schemas, ticket tiers, evaluation rubrics, and triggers.
  scale   Seeds bulk registrations into PostgreSQL for performance and scale testing.
  showcase  Empties every table, then builds a realistic portal through the
          app's own routes for demonstrations (UPG-88); --summary FILE writes
          the accounts and events it made.

This is the one seed command (UPG-15); the data sets live in seeds/.
"""

# BLK-10: refuse production-looking databases before anything connects
from seed_safety import guard  # noqa: E402
guard()

import argparse
import sys
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('seed')


def seed_demo_profile():
    logger.info("Executing demo profile (all roles & flagship event)...")
    from app import app
    if app.config.get('FLASK_ENV') == 'production':
        print("Refusing to seed demo accounts with known passwords in production.")
        sys.exit(1)
    from seeds.all_roles_demo import seed as run_all_roles_seed
    run_all_roles_seed()


def seed_events_profile():
    logger.info("Executing events profile (7 universal template events)...")
    from app import app
    from seeds.events_universal import seed_universal_portal
    with app.app_context():
        import models
        res = seed_universal_portal(models.db)
        logger.info("Events profile seeded: %d events created under '%s'",
                    res.get("events_count", 0), res.get("organization", {}).get("slug", "saptha-tech"))


def seed_scale_profile():
    logger.info("Executing scale profile (bulk registrations)...")
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set in environment for scale profile.")
        sys.exit(1)
    from seeds.scale_test import main as run_scale_test
    run_scale_test()


def seed_showcase_profile(summary=None):
    logger.info("Executing showcase profile (empties every table, then a realistic portal)...")
    from seeds import showcase
    sys.argv = [sys.argv[0]] + (['--summary', summary] if summary else [])
    showcase.main()


def main():
    parser = argparse.ArgumentParser(description="Unified SapthaEvent Database Seeder")
    parser.add_argument(
        '--profile',
        choices=['demo', 'events', 'scale', 'showcase'],
        default='demo',
        help="Seeding profile to execute (default: demo)"
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help="Run both demo and events profiles sequentially"
    )
    parser.add_argument('--summary', help="showcase: write the accounts and events created to this JSON file")

    args = parser.parse_args()

    if args.all:
        seed_demo_profile()
        seed_events_profile()
        return

    if args.profile == 'demo':
        seed_demo_profile()
    elif args.profile == 'events':
        seed_events_profile()
    elif args.profile == 'scale':
        seed_scale_profile()
    elif args.profile == 'showcase':
        seed_showcase_profile(args.summary)
    else:
        logger.error("Unknown profile: %s", args.profile)
        sys.exit(1)


if __name__ == '__main__':
    main()
