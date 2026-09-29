#!/usr/bin/env python3
# Copyright (C) 2025 Deltares
# SPDX-License-Identifier: GPL-3.0-or-later
"""Harmonize ``data/NbS_CORINE_Hazard.xlsx`` (sheet ``NbS_Corine_Hazard``).

Reads:
  - data/NbS_CORINE_Hazard.xlsx (sheet ``NbS_Corine_Hazard``)
  - data/landscapearchetype.csv

Writes:
  - data/nbs_corine_hazard_updated.csv

Columns kept from the source sheet and renamed:
  - ``Column1`` -> ``nbs_code``
  - ``Main NbS type`` -> ``nbs_description``
  - ``Landscape (from survey)`` -> ``landscape_case``
  - ``CORINE (code) classification of the NbS location`` -> ``lu``
  - ``Hazards (same as in LARE tool)`` -> ``hazard``

Additionally:
  - ``clc`` is looked up from ``data/landscapearchetype.csv`` by joining
    ``lu`` (this file) with ``label`` (archetype file).
  - ``hazard`` is stripped and harmonized to a canonical label
    (e.g. ``Floods`` -> ``Flood``), same mapping as
    ``harmonize_clc_nbs_hazard.py``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

# Canonical NBS CSV hazard labels (values used after harmonization).
_HAZARD_CANONICAL: dict[str, str] = {
    'flood': 'Flood',
    'floods': 'Flood',
    'drought': 'Drought',
    'erosion': 'Erosion',
    'fires': 'Fires',
    'fire': 'Fires',
    'heat': 'Heat',
    'other': 'Other',
    'sea level rise': 'Sea level rise',
    'salinisation': 'Salinisation',
}

_SOURCE_SHEET = 'NbS_Corine_Hazard'

_COLUMN_RENAME: dict[str, str] = {
    'Column1': 'nbs_code',
    'Main NbS type': 'nbs_description',
    'Landscape (from survey)': 'landscape_case',
    'CORINE (code) classification of the NbS location': 'lu',
    'Hazards (same as in LARE tool)': 'hazard',
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _harmonize_hazard(value: object) -> str:
    text = str(value).strip()
    if not text or text.lower() == 'nan':
        return ''
    return _HAZARD_CANONICAL.get(text.lower(), text)


def harmonize_nbs_corine_hazard(
    xlsx_path: Path,
    archetype_path: Path,
    out_path: Path,
) -> pd.DataFrame:
    nbs = pd.read_excel(xlsx_path, sheet_name=_SOURCE_SHEET)
    nbs = nbs[list(_COLUMN_RENAME)].rename(columns=_COLUMN_RENAME)

    for col in ('nbs_code', 'nbs_description', 'landscape_case', 'hazard'):
        nbs[col] = nbs[col].astype(str).str.strip()
        nbs.loc[nbs[col].str.lower() == 'nan', col] = ''

    nbs['hazard'] = nbs['hazard'].map(_harmonize_hazard)
    nbs['lu'] = nbs['lu'].astype(int)

    arch = pd.read_csv(archetype_path, sep=';')
    arch['label'] = arch['label'].astype(int)
    # One clc per label; if duplicates disagree, keep the first.
    clc_by_lu = (
        arch[['label', 'clc']]
        .drop_duplicates(subset='label', keep='first')
        .rename(columns={'label': 'lu'})
    )

    merged = nbs.merge(clc_by_lu, on='lu', how='left')

    ordered = ['clc', 'lu', 'nbs_description', 'nbs_code', 'hazard', 'landscape_case']
    merged = merged[ordered].drop_duplicates()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_path, index=False)
    return merged


def main() -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--xlsx',
        type=Path,
        default=root / 'data' / 'NbS_CORINE_Hazard.xlsx',
        help='Input NbS/CORINE/hazard Excel workbook',
    )
    parser.add_argument(
        '--archetype',
        type=Path,
        default=root / 'data' / 'landscapearchetype.csv',
        help='Landscape archetype CSV (semicolon-separated)',
    )
    parser.add_argument(
        '--out',
        type=Path,
        default=root / 'data' / 'nbs_corine_hazard_updated.csv',
        help='Output harmonized CSV',
    )
    args = parser.parse_args()

    if not args.xlsx.is_file():
        raise SystemExit(f'NBS workbook not found: {args.xlsx}')
    if not args.archetype.is_file():
        raise SystemExit(f'Archetype file not found: {args.archetype}')

    df = harmonize_nbs_corine_hazard(args.xlsx, args.archetype, args.out)

    hazard_counts = df['hazard'].value_counts(dropna=False).to_dict()
    unmatched = int(df['clc'].isna().sum())

    print(f'Wrote {len(df)} rows -> {args.out}')
    print(f'Hazards: {hazard_counts}')
    print(f'Unmatched lu (no clc): {unmatched}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
