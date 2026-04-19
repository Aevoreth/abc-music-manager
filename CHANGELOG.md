# Changelog

All notable changes to ABC Music Manager are documented here. Most recent at the top.

## Version 0.1.11b

* Added: Optional Part Renaming for Exported Sets using customizable pattern
* Added: Setlist export now optionally exports an ABC Player compatible playlist
* Added: String Find and Replace during CSV export to allow for shortening part names
* Added: CSV now exports with an appendix, listing players and required instruments for the set
* Fixed: Student Fiddle now properly named Student's Fiddle

## Version 0.1.10b

* Added part hinting to setlist editor:
  * Previous and next part numbers in player card headers
  * Tooltip on card indicating last instrument player used
  * When instrument differs from previous song that a player played in, part number is colored orange
* Tooltip over warning icon in setlist editor indicating what is triggering the warning to be present
* Fixed table column widths in setlist editor not always restoring correctly
* Fixed issue with window size and position not always returning to previous state

## Version 0.1.8b

* Fixes for Setlist not allowing delete of songs or setlist after files moved
* Setlist copy menu:
  * Clarified appending and prepending setlists by renaming them to append to/prepend to setlist
  * Added Prepend/append from setlist
  * Added Copy setlist
* Player level cap increased from 150 to 250 (some level of future-proofing)
* Song import process enhancements (further iteration planned after tester feedback)

## Version 0.1.7b

* Temporary icon set

## Version 0.1.6b

* Updated documentation to fix errors and include AI/LLM tool use transparency.

## Version 0.1.5b

* Further addressing of Setlist item move crash

## Version 0.1.4b

* Fixed a bug that was causing songs that were dragged and dropped in Setlist Editor to lose action column buttons
* Addressed a crash condition with setlist song drag and drop

## Version 0.1.3b

* Custom order (drag and drop) for bands
* Duplication of bands
* Schema documented in SCHEMA.md. Migration logic created for future updates to be able to port database forward across larger version gaps
* Minor bugs fixed.

## Version 0.1.2b

* Fixed: Status and Transcriber filters failed to open after first use.

## Version 0.1.1b – Initial Beta test
