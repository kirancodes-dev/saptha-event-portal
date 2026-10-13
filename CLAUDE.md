# Working on SapthaEvent
docs/FEATURE_REVIEW.md is the source of truth for planned work. Before any change:
1. Read docs/FEATURE_REVIEW.md. Work only on the item ID you're given (UPG-XX or
   BLK-XX). If no ID was given, ask which item it is, or propose adding a new one.
2. Don't start a UPG item while any BLK item is still TODO, unless I say so.
3. Check the item still matches the code: look at git log since its "Last verified"
   commit. If the code changed, update the item before building.
4. If any item it depends on isn't DONE, stop and say so.
5. Build only what the item describes. Every acceptance criterion needs a passing
   test. Run the full pytest before finishing. Never delete, skip or weaken an
   existing test to make it pass.
6. When finished, update docs/FEATURE_REVIEW.md: status → DONE, new evidence
   (file:line), Last verified date + commit, affected rows in the feature inventory
   and event-type tables, and a changelog line.
7. Problems found along the way go in as new items with the next free ID. Don't fix
   them in the same change.
8. Run a full re-verification of every open item once, at the end of each phase, before
   its phase summary. Run one early, and say so, when a change touches files that many
   open items depend on (for example db_adapter.py, models_pg.py,
   services_permission.py or tests/conftest.py).
