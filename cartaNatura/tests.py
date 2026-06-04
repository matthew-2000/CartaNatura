from __future__ import annotations

from unittest.mock import patch

import geopandas
from django.test import Client, SimpleTestCase
from shapely.geometry import box

from cartaNatura.schemas import SelectionArea, SelectionRequest
from cartaNatura.services.gis_clip import clip_selection
from cartaNatura.services.payloads import parse_selection_payload


class PayloadParsingTests(SimpleTestCase):
    def test_parse_selection_payload_accepts_named_areas(self):
        payload = {
            "areas": [
                {
                    "kind": "drawn",
                    "geojson": {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {},
                                "geometry": box(0, 0, 1, 1).__geo_interface__,
                            }
                        ],
                    },
                }
            ]
        }

        selection = parse_selection_payload(payload)

        self.assertEqual(len(selection.areas), 1)
        self.assertEqual(selection.areas[0].kind, "drawn")

    def test_parse_selection_payload_rejects_duplicate_kind(self):
        payload = {
            "areas": [
                {
                    "kind": "drawn",
                    "geojson": {"type": "FeatureCollection", "features": [{"geometry": {}, "properties": {}, "type": "Feature"}]},
                },
                {
                    "kind": "drawn",
                    "geojson": {"type": "FeatureCollection", "features": [{"geometry": {}, "properties": {}, "type": "Feature"}]},
                },
            ]
        }

        with self.assertRaisesMessage(ValueError, "Duplicated area kind"):
            parse_selection_payload(payload)


class GisClipServiceTests(SimpleTestCase):
    @staticmethod
    def _municipality_geojson(name: str):
        municipality_frame = geopandas.GeoDataFrame(
            {"COMUNE": [name]},
            geometry=[box(0, 0, 1, 1)],
            crs="EPSG:4326",
        ).to_crs(epsg=32633)

        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"COMUNE": name},
                    "geometry": municipality_frame.geometry.iloc[0].__geo_interface__,
                }
            ],
        }

    @staticmethod
    def _drawn_geojson():
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": box(0, 0, 2, 1).__geo_interface__,
                }
            ],
        }

    @staticmethod
    def _nature_shapes():
        return geopandas.GeoDataFrame(
            {
                "CODICE": ["41.18"],
                "ettari": [10],
            },
            geometry=[box(0, 0, 2, 2)],
            crs="EPSG:4326",
        )

    @staticmethod
    def _campania_boundaries():
        return geopandas.GeoDataFrame(
            {"COMUNE": ["Comune Uno", "Acerra"]},
            geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
            crs="EPSG:4326",
        )

    @patch("cartaNatura.services.gis_clip.load_campania_boundaries")
    @patch("cartaNatura.services.gis_clip.load_nature_shapes")
    def test_clip_selection_filters_municipalities_without_nature(
        self,
        load_nature_shapes,
        load_campania_boundaries,
    ):
        load_nature_shapes.return_value = self._nature_shapes()
        load_campania_boundaries.return_value = self._campania_boundaries()

        selection = SelectionRequest(
            areas=(
                SelectionArea(
                    kind="municipalities",
                    geojson=self._municipality_geojson("Comune Uno"),
                ),
                SelectionArea(kind="drawn", geojson=self._drawn_geojson()),
            )
        )

        result = clip_selection(selection)

        self.assertEqual(result.intersected_municipalities, ["Comune Uno"])
        self.assertFalse(result.clipped.empty)


class ViewSmokeTests(SimpleTestCase):
    def test_index_renders(self):
        response = Client().get("/progettoGIS/cartaNatura/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '"apiUrl": "/progettoGIS/cartaNatura/gis"')

    def test_gis_rejects_invalid_payload(self):
        response = Client().post(
            "/progettoGIS/cartaNatura/gis",
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
