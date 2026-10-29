"""Pipeline stages, in run order. Each module exposes NAME, TITLE and run(site, ctx)."""
from . import parcels, clip, areg, glv, master, crop, landcost, fmb, maps, regional, dimensions, streetview, sitephotos, soil, sensitive, govtland, glvmap, owners, companies, summary, ppt

STAGES = [parcels, clip, areg, glv, master, crop, landcost, fmb, maps, regional, dimensions, streetview, sitephotos, soil, sensitive, govtland, glvmap, owners, companies, summary, ppt]
BY_NAME = {s.NAME: s for s in STAGES}
