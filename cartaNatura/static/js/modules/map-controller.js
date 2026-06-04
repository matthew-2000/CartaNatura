export class MapController {
  constructor({
    mapConfig,
    municipalitySource,
    municipalityBoundaries,
    categoryByCode,
    onSelectionChange = () => {},
  }) {
    this.categoryByCode = categoryByCode;
    this.onSelectionChange = onSelectionChange;
    this.municipalitySource = municipalitySource;
    this.municipalityBoundaries = municipalityBoundaries;
    this.municipalityNames = municipalityBoundaries.features
      .map((feature) => feature.properties.COMUNE)
      .sort((left, right) => left.localeCompare(right, "it"));

    this.boundaryFeaturesByName = new Map(
      municipalityBoundaries.features.map((feature) => [feature.properties.COMUNE, feature])
    );
    this.sourceFeaturesByName = new Map(
      municipalitySource.features.map((feature) => [feature.properties.COMUNE, feature])
    );

    this.selectedMunicipalities = new Set();
    this.selectedMunicipalityLayers = new Map();

    this.map = L.map("map", { zoomControl: false }).setView(mapConfig.center, mapConfig.zoom);
    this.baseLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png").addTo(
      this.map
    );
    this.baseBoundaryLayer = L.geoJSON(this.municipalityBoundaries, {
      style: {
        color: "#b80f0a",
        weight: 1,
        opacity: 0.5,
        fillOpacity: 0,
      },
    }).addTo(this.map);

    this.selectedMunicipalityGroup = L.featureGroup().addTo(this.map);
    this.drawnItems = new L.FeatureGroup();
    this.map.addLayer(this.drawnItems);

    this.natureLayer = null;
    this.intersectionsLayer = null;

    this._initializeControls();
  }

  _initializeControls() {
    L.control.zoom({ position: "bottomright" }).addTo(this.map);

    const drawControl = new L.Control.Draw({
      position: "bottomleft",
      edit: {
        featureGroup: this.drawnItems,
        poly: {
          allowIntersection: false,
        },
      },
      draw: {
        marker: false,
        polyline: false,
        circle: false,
        circlemarker: false,
        polygon: {
          allowIntersection: false,
          showArea: true,
        },
      },
    });

    this.map.addControl(drawControl);

    this.map.on(L.Draw.Event.CREATED, (event) => {
      const layer = event.layer;
      const popupContent = this._buildPopupContent(layer);
      if (popupContent) {
        layer.bindPopup(popupContent);
      }
      this.drawnItems.addLayer(layer);
      this._fitToUserInputs();
      this._emitSelectionChange();
    });

    this.map.on(L.Draw.Event.EDITED, (event) => {
      event.layers.eachLayer((layer) => {
        const popupContent = this._buildPopupContent(layer);
        if (popupContent) {
          layer.setPopupContent(popupContent);
        }
      });
      this._fitToUserInputs();
      this._emitSelectionChange();
    });

    this.map.on(L.Draw.Event.DELETED, () => {
      this._emitSelectionChange();
    });
  }

  _buildPopupContent(layer) {
    if (!(layer instanceof L.Polygon)) {
      return null;
    }

    const latlngs = layer._defaultShape ? layer._defaultShape() : layer.getLatLngs();
    const area = L.GeometryUtil.geodesicArea(latlngs);
    return `Area: ${L.GeometryUtil.readableArea(area, true)}`;
  }

  getMunicipalityNames() {
    return this.municipalityNames;
  }

  hasSelectedMunicipalities() {
    return this.selectedMunicipalities.size > 0;
  }

  hasDrawnAreas() {
    return this.drawnItems.toGeoJSON().features.length > 0;
  }

  getSelectedMunicipalityCount() {
    return this.selectedMunicipalities.size;
  }

  getDrawnFeatureCount() {
    return this.drawnItems.toGeoJSON().features.length;
  }

  toggleMunicipalitySelection(name, selected) {
    if (selected) {
      if (this.selectedMunicipalityLayers.has(name)) {
        return;
      }

      const feature = this.boundaryFeaturesByName.get(name);
      if (!feature) {
        return;
      }

      const layer = L.geoJSON(feature, {
        style: {
          color: "#80b2f6",
          weight: 3,
          opacity: 1,
          fillOpacity: 0.35,
        },
      }).addTo(this.selectedMunicipalityGroup);

      this.selectedMunicipalityLayers.set(name, layer);
      this.selectedMunicipalities.add(name);
      this._fitToUserInputs();
      this._emitSelectionChange();
      return;
    }

    this.selectedMunicipalities.delete(name);
    const layer = this.selectedMunicipalityLayers.get(name);
    if (layer) {
      this.selectedMunicipalityGroup.removeLayer(layer);
      this.selectedMunicipalityLayers.delete(name);
    }
    this._emitSelectionChange();
  }

  buildSelectedMunicipalityGeoJson() {
    return {
      type: "FeatureCollection",
      features: [...this.selectedMunicipalities]
        .map((name) => this.sourceFeaturesByName.get(name))
        .filter(Boolean),
    };
  }

  buildDrawnGeoJson() {
    return this.drawnItems.toGeoJSON();
  }

  clearUserSelections() {
    this.selectedMunicipalities.clear();
    this.selectedMunicipalityLayers.clear();
    this.selectedMunicipalityGroup.clearLayers();
    this.drawnItems.clearLayers();
    this._emitSelectionChange();
  }

  clearResults() {
    if (this.natureLayer) {
      this.map.removeLayer(this.natureLayer);
      this.natureLayer = null;
    }

    if (this.intersectionsLayer) {
      this.map.removeLayer(this.intersectionsLayer);
      this.intersectionsLayer = null;
    }
  }

  renderNature(clippedGeoJson) {
    if (this.natureLayer) {
      this.map.removeLayer(this.natureLayer);
    }

    this.natureLayer = L.geoJSON(clippedGeoJson, {
      style: (feature) => {
        const category = this.categoryByCode.get(feature.properties?.CODICE);
        const color = category?.color || "#4f4f4f";
        return {
          color,
          fillColor: color,
          fillOpacity: 0.9,
          weight: 1,
        };
      },
    }).addTo(this.map);

    const bounds = this.natureLayer.getBounds();
    if (bounds.isValid()) {
      this.map.fitBounds(bounds, { padding: [20, 20] });
    }
  }

  renderIntersectedMunicipalities(names) {
    if (this.intersectionsLayer) {
      this.map.removeLayer(this.intersectionsLayer);
    }

    const features = names
      .map((name) => this.boundaryFeaturesByName.get(name))
      .filter(Boolean);

    this.intersectionsLayer = L.geoJSON(
      {
        type: "FeatureCollection",
        features,
      },
      {
        style: {
          color: "black",
          weight: 1.25,
          fillOpacity: 0,
        },
      }
    ).addTo(this.map);
  }

  setInteractionDisabled(disabled) {
    const container = this.map.getContainer();
    container.classList.toggle("map-disabled", disabled);
  }

  _fitToUserInputs() {
    const group = new L.FeatureGroup();

    if (this.selectedMunicipalityGroup.getLayers().length) {
      group.addLayer(this.selectedMunicipalityGroup);
    }

    if (this.drawnItems.getLayers().length) {
      group.addLayer(this.drawnItems);
    }

    const bounds = group.getBounds();
    if (bounds.isValid()) {
      this.map.fitBounds(bounds, { padding: [20, 20] });
    }
  }

  _emitSelectionChange() {
    this.onSelectionChange({
      selectedMunicipalityCount: this.getSelectedMunicipalityCount(),
      drawnFeatureCount: this.getDrawnFeatureCount(),
    });
  }
}
