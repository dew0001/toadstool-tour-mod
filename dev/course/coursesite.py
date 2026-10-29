"""The real course the generator works on (TTMOD_COURSE, osm.py): its Course class, scorecard, name in the game and
top folder on the disc. pebble.py (Pebble Beach, course code 8, files under E/) or pasadena.py (Pasadena Municipal,
course code 9, files under F/)."""
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import osm  # noqa: E402

_site = importlib.import_module(osm.COURSE)
Course, CARD, NAME, DISC = _site.Course, _site.CARD, _site.NAME, _site.DISC
