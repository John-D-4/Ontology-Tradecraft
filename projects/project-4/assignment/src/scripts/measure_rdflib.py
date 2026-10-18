#!/usr/bin/env python3
"""
Build an RDF graph that instantiates the CCO Measurement Design Pattern
(see src/cco_measurement_design_pattern.pptx) from src/data/readings_normalized.csv.

Pattern (per the design-pattern slides):
    art-inst  rdf:type        cco:Artifact
    art-inst  bfo:bearer_of   sdc-inst
    sdc-inst  rdf:type        bfo:SDC
    mice-inst rdf:type        cco:MICE
    mice-inst cco:is_measure_of        sdc-inst
    mice-inst cco:has_decimal_value    "<value>"^^xsd:decimal
    mice-inst cco:uses_measurement_unit unit-inst
    unit-inst rdf:type        cco:MU
"""
from __future__ import annotations
from pathlib import Path
from urllib.parse import quote

import pandas as pd
from rdflib import Graph, Namespace, Literal, RDF, RDFS, SKOS, XSD

SCRIPT_DIR = Path(__file__).resolve().parent     # .../src/scripts
SRC_DIR = SCRIPT_DIR.parent                      # .../src
CSV_IN = SRC_DIR / "data" / "readings_normalized.csv"
TTL_OUT = SRC_DIR / "measure_cco.ttl"

BFO = Namespace("http://purl.obolibrary.org/obo/")
CCO = Namespace("https://www.commoncoreontologies.org/")
EX = Namespace("http://example.org/onto-trade/measurements/")

# Exact IRIs from the CCO Measurement Design Pattern
ARTIFACT = CCO.ont00000995   # Material Artifact
SDC = BFO.BFO_0000020        # specifically dependent continuant
MICE = CCO.ont00001163       # Measurement Information Content Entity
MU = CCO.ont00000120         # Measurement Unit

BEARER_OF = BFO.BFO_0000196          # bearer of
IS_MEASURE_OF = CCO.ont00001966      # is a measurement of
USES_MU = CCO.ont00001863            # uses measurement unit
HAS_DECIMAL_VALUE = CCO.ont00001769  # has decimal value
HAS_TEXT_VALUE = CCO.ont00001765     # has text value
HAS_DATETIME_VALUE = CCO.ont00001767 # has datetime value


# Which quantity kind a given (normalized) unit label belongs to. Used to
# check, via SHACL shape #6, that a MICE's unit matches the kind of SDC it
# measures, without requiring every reading of a given SDC to share the
# exact same unit (e.g. a temperature may legitimately be reported in both
# "C" and "F" across sources).
UNIT_KIND = {
    "C": "temperature",
    "F": "temperature",
    "Pa": "pressure",
    "V": "voltage",
    "ohm": "resistance",
}


def slug(value: object) -> str:
    """IRI-safe local name that preserves distinctness between inputs (no lossy collapsing)."""
    return quote(str(value).strip(), safe="").replace("%", "_")


def build_graph(df: pd.DataFrame) -> Graph:
    g = Graph()
    g.bind("bfo", BFO)
    g.bind("cco", CCO)
    g.bind("ex", EX)

    artifact_uris: dict[str, object] = {}
    sdc_uris: dict[tuple[str, str], object] = {}
    unit_uris: dict[str, object] = {}

    for i, row in df.iterrows():
        artifact_id = row["artifact_id"]
        sdc_kind = row["sdc_kind"]
        unit_label = row["unit_label"]
        value = row["value"]
        timestamp = row["timestamp"]

        # Artifact
        art_uri = artifact_uris.get(artifact_id)
        if art_uri is None:
            art_uri = EX[f"artifact_{slug(artifact_id)}"]
            artifact_uris[artifact_id] = art_uri
            g.add((art_uri, RDF.type, ARTIFACT))

        # SDC: one per (artifact, kind) -- the quality/attribute being measured
        sdc_key = (artifact_id, sdc_kind)
        sdc_uri = sdc_uris.get(sdc_key)
        if sdc_uri is None:
            sdc_uri = EX[f"sdc_{slug(artifact_id)}_{slug(sdc_kind)}"]
            sdc_uris[sdc_key] = sdc_uri
            g.add((sdc_uri, RDF.type, SDC))
            g.add((sdc_uri, SKOS.altLabel, Literal(sdc_kind, lang="en")))
            g.add((art_uri, BEARER_OF, sdc_uri))

        # Measurement Unit: one per distinct unit label
        unit_uri = unit_uris.get(unit_label)
        if unit_uri is None:
            unit_uri = EX[f"unit_{slug(unit_label)}"]
            unit_uris[unit_label] = unit_uri
            g.add((unit_uri, RDF.type, MU))
            g.add((unit_uri, HAS_TEXT_VALUE, Literal(unit_label, datatype=XSD.string)))
            unit_kind = UNIT_KIND.get(unit_label)
            if unit_kind:
                g.add((unit_uri, SKOS.altLabel, Literal(unit_kind, lang="en")))

        # MICE: one per reading
        mice_uri = EX[f"mice_{slug(artifact_id)}_{slug(sdc_kind)}_{i}"]
        g.add((mice_uri, RDF.type, MICE))
        g.add((mice_uri, IS_MEASURE_OF, sdc_uri))
        g.add((mice_uri, USES_MU, unit_uri))
        g.add((mice_uri, HAS_DECIMAL_VALUE, Literal(float(value), datatype=XSD.decimal)))
        g.add((mice_uri, HAS_DATETIME_VALUE, Literal(timestamp, datatype=XSD.dateTime)))

    return g


def main() -> None:
    print("[measure_rdflib] CSV_IN :", CSV_IN)
    print("[measure_rdflib] exists?:", CSV_IN.exists())
    if not CSV_IN.exists():
        raise FileNotFoundError(f"Missing {CSV_IN}; run normalize_readings.py first.")

    df = pd.read_csv(CSV_IN, dtype={"artifact_id": str, "sdc_kind": str, "unit_label": str, "timestamp": str})
    g = build_graph(df)

    TTL_OUT.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(destination=str(TTL_OUT), format="turtle")

    print(f"[measure_rdflib] rows processed: {len(df)}")
    print(f"[measure_rdflib] triples written: {len(g)}")
    print(f"[measure_rdflib] wrote: {TTL_OUT}")


if __name__ == "__main__":
    main()
