# CartaNatura Refactoring Plan

## Goals

- Split GIS business logic from Django views.
- Remove monolithic frontend script and embedded GIS blobs.
- Eliminate remote municipality lookup dependency.
- Centralize vegetation rules and CO2 coefficients.
- Introduce minimal automated verification.

## Target Architecture

```text
cartaNatura/
  domain/
    municipalities.py
    vegetation.py
  services/
    datasets.py
    gis_clip.py
    payloads.py
  static/
    data/
    js/
      modules/
  templates/
```

## Steps

1. Move vegetation and municipality rules into domain layer.
2. Add cached dataset loaders and request parser in service layer.
3. Keep Django views thin: validate request, call service, serialize response.
4. Extract GeoJSON blobs from frontend into static data files.
5. Rewrite frontend into small ES modules around map, API, analysis, PDF, UI.
6. Add tests for payload validation and GIS clip service behavior.

## Done In This Refactor

- Backend service layer introduced.
- Same-origin API contract introduced with explicit `kind` per area.
- App config now injected from Django into frontend.
- Production-sensitive settings moved to env-driven defaults.
