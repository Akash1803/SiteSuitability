"""Pipeline stages, in run order. Each module exposes NAME, TITLE and run(site, ctx)."""
from . import parcels, clip, areg, glv, master, crop, landcost, fmb, maps, streetview, soil, sensitive, govtland, glvmap, owners, summary, ppt

STAGES = [parcels, clip, areg, glv, master, crop, landcost, fmb, maps, streetview, soil, sensitive, govtland, glvmap, owners, summary, ppt]
BY_NAME = {s.NAME: s for s in STAGES}
