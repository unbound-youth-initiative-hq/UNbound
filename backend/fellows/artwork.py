"""Coordinator badge artwork and fellow task icon choices."""
from django.db import models


class BadgeArtwork(models.TextChoices):
    LAUNCHPAD = 'launchpad', 'Rocket on launchpad'
    FLAME = 'flame', 'Flame'
    BLUEPRINT = 'blueprint', 'Rocket blueprint'
    COMET = 'comet', 'Shooting star'
    EQUIPMENT = 'equipment', 'Equipment panel'
    ROCKET = 'rocket', 'Rocket launch'
    GALAXY = 'galaxy', 'Galaxy'
    STARS = 'stars', 'Constellation'
    PLANET = 'planet', 'Ringed planet'
    INFINITY = 'infinity', 'Infinity'
    CHECKLIST = 'checklist', 'Launch checklist'
    YODA = 'yoda', 'Yoda'
    GAUGE = 'gauge', 'Test gauge'
    SOLAR_SYSTEM = 'solar-system', 'Solar system'
    SATELLITE = 'satellite', 'Orbiting satellite'


TASK_ICONS = (
    ('fa-check', 'Checkmark'), ('fa-pen-to-square', 'Notes'), ('fa-book', 'Reading'),
    ('fa-users', 'Team'), ('fa-calendar-days', 'Meeting'), ('fa-flask', 'Experiment'),
    ('fa-lightbulb', 'Idea'), ('fa-rocket', 'Launch'), ('fa-flag', 'Milestone'),
    ('fa-code', 'Code'), ('fa-palette', 'Design'), ('fa-star', 'Star'),
)
