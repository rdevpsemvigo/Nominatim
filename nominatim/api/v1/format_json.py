# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of Nominatim. (https://nominatim.org)
#
# Copyright (C) 2023 by the Nominatim developer community.
# For a full list of authors see the git log.
"""
Helper functions for output of results in json formats.
"""
from typing import Mapping, Any, Optional, Tuple

import nominatim.api as napi
from nominatim.api.v1.constants import OSM_ATTRIBUTION, OSM_TYPE_NAME, bbox_from_result
from nominatim.api.v1.classtypes import ICONS, get_label_tag
from nominatim.utils.json_writer import JsonWriter

def _write_osm_id(out: JsonWriter, osm_object: Optional[Tuple[str, int]]) -> None:
    if osm_object is not None:
        out.keyval_not_none('osm_type', OSM_TYPE_NAME.get(osm_object[0], None))\
           .keyval('osm_id', osm_object[1])


def _write_typed_address(out: JsonWriter, address: Optional[napi.AddressLines],
                               country_code: Optional[str]) -> None:
    parts = {}
    for line in (address or []):
        if line.isaddress and line.local_name:
            label = get_label_tag(line.category, line.extratags,
                                  line.rank_address, country_code)
            if label not in parts:
                parts[label] = line.local_name

    for k, v in parts.items():
        out.keyval(k, v)

    if country_code:
        out.keyval('country_code', country_code)


def _write_geocodejson_address(out: JsonWriter,
                               address: Optional[napi.AddressLines],
                               obj_place_id: Optional[int],
                               country_code: Optional[str]) -> None:
    extra = {}
    for line in (address or []):
        if line.isaddress and line.local_name:
            if line.category[1] in ('postcode', 'postal_code'):
                out.keyval('postcode', line.local_name)
            elif line.category[1] == 'house_number':
                out.keyval('housenumber', line.local_name)
            elif (obj_place_id is None or obj_place_id != line.place_id) \
                 and line.rank_address >= 4 and line.rank_address < 28:
                extra[GEOCODEJSON_RANKS[line.rank_address]] = line.local_name

    for k, v in extra.items():
        out.keyval(k, v)

    if country_code:
        out.keyval('country_code', country_code)


def format_base_json(results: napi.ReverseResults, #pylint: disable=too-many-branches
                     options: Mapping[str, Any], simple: bool,
                     class_label: str) -> str:
    """ Return the result list as a simple json string in custom Nominatim format.
    """
    locales = options.get('locales', napi.Locales())

    out = JsonWriter()

    if simple:
        if not results:
            return '{"error":"Unable to geocode"}'
    else:
        out.start_array()

    for result in results:
        label_parts = result.address_rows.localize(locales) if result.address_rows else []

        out.start_object()\
             .keyval_not_none('place_id', result.place_id)\
             .keyval('licence', OSM_ATTRIBUTION)\

        _write_osm_id(out, result.osm_object)

        out.keyval('lat', result.centroid.lat)\
             .keyval('lon', result.centroid.lon)\
             .keyval(class_label, result.category[0])\
             .keyval('type', result.category[1])\
             .keyval('place_rank', result.rank_search)\
             .keyval('importance', result.calculated_importance())\
             .keyval('addresstype', get_label_tag(result.category, result.extratags,
                                                  result.rank_address,
                                                  result.country_code))\
             .keyval('name', locales.display_name(result.names))\
             .keyval('display_name', ', '.join(label_parts))


        if options.get('icon_base_url', None):
            icon = ICONS.get(result.category)
            if icon:
                out.keyval('icon', f"{options['icon_base_url']}/{icon}.p.20.png")

        if options.get('addressdetails', False):
            out.key('address').start_object()
            _write_typed_address(out, result.address_rows, result.country_code)
            out.end_object().next()

        if options.get('extratags', False):
            out.keyval('extratags', result.extratags)

        if options.get('namedetails', False):
            out.keyval('namedetails', result.names)

        bbox = bbox_from_result(result)
        out.key('boundingbox').start_array()\
             .value(bbox.minlat).next()\
             .value(bbox.maxlat).next()\
             .value(bbox.minlon).next()\
             .value(bbox.maxlon).next()\
           .end_array().next()

        if result.geometry:
            for key in ('text', 'kml'):
                out.keyval_not_none('geo' + key, result.geometry.get(key))
            if 'geojson' in result.geometry:
                out.key('geojson').raw(result.geometry['geojson']).next()
            out.keyval_not_none('svg', result.geometry.get('svg'))

        out.end_object()

        if simple:
            return out()

        out.next()

    out.end_array()

    return out()


def format_base_geojson(results: napi.ReverseResults,
                        options: Mapping[str, Any],
                        simple: bool) -> str:
    """ Return the result list as a geojson string.
    """
    if not results and simple:
        return '{"error":"Unable to geocode"}'

    locales = options.get('locales', napi.Locales())

    out = JsonWriter()

    out.start_object()\
         .keyval('type', 'FeatureCollection')\
         .keyval('licence', OSM_ATTRIBUTION)\
         .key('features').start_array()

    for result in results:
        if result.address_rows:
            label_parts = result.address_rows.localize(locales)
        else:
            label_parts = []

        out.start_object()\
             .keyval('type', 'Feature')\
             .key('properties').start_object()

        out.keyval_not_none('place_id', result.place_id)

        _write_osm_id(out, result.osm_object)

        out.keyval('place_rank', result.rank_search)\
           .keyval('category', result.category[0])\
           .keyval('type', result.category[1])\
           .keyval('importance', result.calculated_importance())\
           .keyval('addresstype', get_label_tag(result.category, result.extratags,
                                                result.rank_address,
                                                result.country_code))\
           .keyval('name', locales.display_name(result.names))\
           .keyval('display_name', ', '.join(label_parts))

        if options.get('addressdetails', False):
            out.key('address').start_object()
            _write_typed_address(out, result.address_rows, result.country_code)
            out.end_object().next()

        if options.get('extratags', False):
            out.keyval('extratags', result.extratags)

        if options.get('namedetails', False):
            out.keyval('namedetails', result.names)

        out.end_object().next() # properties

        bbox = bbox_from_result(result)
        out.keyval('bbox', bbox.coords)

        out.key('geometry').raw(result.geometry.get('geojson')
                                or result.centroid.to_geojson()).next()

        out.end_object().next()

    out.end_array().next().end_object()

    return out()


def format_base_geocodejson(results: napi.ReverseResults,
                            options: Mapping[str, Any], simple: bool) -> str:
    """ Return the result list as a geocodejson string.
    """
    if not results and simple:
        return '{"error":"Unable to geocode"}'

    locales = options.get('locales', napi.Locales())

    out = JsonWriter()

    out.start_object()\
         .keyval('type', 'FeatureCollection')\
         .key('geocoding').start_object()\
           .keyval('version', '0.1.0')\
           .keyval('attribution', OSM_ATTRIBUTION)\
           .keyval('licence', 'ODbL')\
           .keyval_not_none('query', options.get('query'))\
           .end_object().next()\
         .key('features').start_array()

    for result in results:
        if result.address_rows:
            label_parts = result.address_rows.localize(locales)
        else:
            label_parts = []

        out.start_object()\
             .keyval('type', 'Feature')\
             .key('properties').start_object()\
               .key('geocoding').start_object()

        out.keyval_not_none('place_id', result.place_id)

        _write_osm_id(out, result.osm_object)

        out.keyval('osm_key', result.category[0])\
           .keyval('osm_value', result.category[1])\
           .keyval('type', GEOCODEJSON_RANKS[max(3, min(28, result.rank_address))])\
           .keyval_not_none('accuracy', result.distance)\
           .keyval('label', ', '.join(label_parts))\
           .keyval_not_none('name', locales.display_name(result.names))\

        if options.get('addressdetails', False):
            _write_geocodejson_address(out, result.address_rows, result.place_id,
                                       result.country_code)

            out.key('admin').start_object()
            if result.address_rows:
                for line in result.address_rows:
                    if line.isaddress and (line.admin_level or 15) < 15 and line.local_name:
                        out.keyval(f"level{line.admin_level}", line.local_name)
            out.end_object().next()

        out.end_object().next().end_object().next()

        out.key('geometry').raw(result.geometry.get('geojson')
                                or result.centroid.to_geojson()).next()

        out.end_object().next()

    out.end_array().next().end_object()

    return out()


GEOCODEJSON_RANKS = {
    3: 'locality',
    4: 'country',
    5: 'state', 6: 'state', 7: 'state', 8: 'state', 9: 'state',
    10: 'county', 11: 'county', 12: 'county',
    13: 'city', 14: 'city', 15: 'city', 16: 'city',
    17: 'district', 18: 'district', 19: 'district', 20: 'district', 21: 'district',
    22: 'locality', 23: 'locality', 24: 'locality',
    25: 'street', 26: 'street', 27: 'street', 28: 'house'}
