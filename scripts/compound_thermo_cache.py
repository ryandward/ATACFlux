"""
compound_thermo_cache.py

Generate compound identifier mapping cache from eQuilibrator.

This script maps yeast-GEM metabolite IDs to eQuilibrator identifiers (KEGG, ChEBI, etc.).
The reaction thermodynamics script uses these mappings to build reaction formulas.

Note: This is an ID mapping cache, not a thermodynamic data cache. Reaction ΔG'° values
are calculated directly by eQuilibrator using the reaction formula, not by summing
compound formation energies.

Queries identifiers in priority order: KEGG → ChEBI → MetaNetX → BiGG → name search

Usage:
    python scripts/compound_thermo_cache.py models/yeast-GEM.xml data/compounds_thermo.json
"""

import json
import sys
from collections import defaultdict

import cobra
from equilibrator_api import ComponentContribution


# Priority order for identifier lookup
ID_PRIORITY = [
    ('kegg.compound', 'kegg'),
    ('chebi', 'chebi'),
    ('metanetx.chemical', 'metanetx.chemical'),
    ('bigg.metabolite', 'bigg.metabolite'),
]


def query_compound(cc, query_string):
    """Query eQuilibrator by ID.
    
    Returns (inchi_key, found) where found=True if compound exists.
    Raises exception if compound not found.
    """
    compound = cc.get_compound(query_string)
    if compound is None:
        raise ValueError(f"Compound not found: {query_string}")
    
    inchi_key = getattr(compound, 'inchi_key', None)
    return inchi_key, True


def query_compound_by_name(cc, name):
    """Query eQuilibrator by name search.
    
    Returns (inchi_key, found) where found=True if compound exists.
    Raises exception if no match found.
    """
    compound = cc.search_compound(name)
    if compound is None:
        raise ValueError(f"No match for name: {name}")
    
    inchi_key = getattr(compound, 'inchi_key', None)
    return inchi_key, True


def get_all_identifiers(met):
    """Get all available identifiers for a metabolite."""
    identifiers = []
    if not met.annotation:
        return identifiers
    
    for annotation_key, equilibrator_prefix in ID_PRIORITY:
        value = met.annotation.get(annotation_key)
        if value:
            if annotation_key == 'chebi':
                if not value.startswith('CHEBI:'):
                    value = f"CHEBI:{value}"
                identifiers.append((f"chebi:{value}", annotation_key))
            else:
                identifiers.append((f"{equilibrator_prefix}:{value}", annotation_key))
    
    return identifiers


def query_with_cascade(cc, identifiers, name):
    """Try each identifier in order, then fall back to name search.
    
    Returns (inchi_key, query_string, query_source, errors) 
    where errors is a list of all failed attempts.
    """
    errors = []
    
    # Try each ID in priority order
    for query_string, source in identifiers:
        try:
            inchi_key, found = query_compound(cc, query_string)
            return inchi_key, query_string, source, errors
        except Exception as e:
            errors.append({
                "source": source,
                "query": query_string,
                "error": str(e),
                "found": False
            })
    
    # Fall back to name search
    try:
        inchi_key, found = query_compound_by_name(cc, name)
        return inchi_key, name, "name_search", errors
    except Exception as e:
        errors.append({
            "source": "name_search",
            "query": name,
            "error": str(e),
            "found": False
        })
    
    # Nothing found
    return None, None, None, errors


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/compound_thermo_cache.py <model.xml> <output.json>")
        sys.exit(1)
    
    model_path = sys.argv[1]
    output_path = sys.argv[2]
    
    print("Loading model...")
    model = cobra.io.read_sbml_model(model_path)
    print(f"  {len(model.metabolites)} metabolites")
    
    # Group metabolites by unique compound (using all identifiers as key)
    # We need to deduplicate compartmentalized metabolites
    compound_groups = defaultdict(list)
    
    for met in model.metabolites:
        # Create a hashable key from identifiers
        ids = get_all_identifiers(met)
        if ids:
            # Use first (best) ID as group key
            key = ids[0][0]
        else:
            # No IDs - use metabolite name as key
            key = f"name:{met.name}"
        compound_groups[key].append(met)
    
    print(f"  {len(compound_groups)} unique compounds")
    
    print("\nInitializing eQuilibrator...")
    cc = ComponentContribution()
    
    print("\nQuerying compounds with cascading fallback...")
    compounds = {}
    
    success_by_source = defaultdict(int)
    
    for i, (key, mets) in enumerate(compound_groups.items()):
        if i % 100 == 0:
            print(f"  Processing {i}/{len(compound_groups)}")
        
        # Collect all identifiers from all metabolites in this group
        all_ids = []
        seen = set()
        identifiers = {
            'kegg': None,
            'chebi': None,
            'metanetx': None,
            'bigg': None,
            'yeast_gem': []
        }
        name = None
        
        for met in mets:
            identifiers['yeast_gem'].append(met.id)
            if not name:
                name = met.name
            
            for query_string, source in get_all_identifiers(met):
                if query_string not in seen:
                    seen.add(query_string)
                    all_ids.append((query_string, source))
            
            if met.annotation:
                if not identifiers['kegg']:
                    identifiers['kegg'] = met.annotation.get('kegg.compound')
                if not identifiers['chebi']:
                    identifiers['chebi'] = met.annotation.get('chebi')
                if not identifiers['metanetx']:
                    identifiers['metanetx'] = met.annotation.get('metanetx.chemical')
                if not identifiers['bigg']:
                    identifiers['bigg'] = met.annotation.get('bigg.metabolite')
        
        # Use a stable key - prefer KEGG, then others
        cache_key = (identifiers['kegg'] or identifiers['chebi'] or 
                     identifiers['metanetx'] or identifiers['bigg'] or 
                     mets[0].id)
        
        entry = {
            "name": name,
            "queried_as": None,
            "query_source": None,
            "matched_inchi_key": None,
            "errors": [],
            "identifiers": identifiers
        }
        
        inchi_key, query_string, source, errors = query_with_cascade(cc, all_ids, name)
        
        entry["errors"] = errors
        entry["matched_inchi_key"] = inchi_key
        entry["queried_as"] = query_string
        entry["query_source"] = source
        
        if query_string is not None:
            success_by_source[source] += 1
        
        compounds[cache_key] = entry
    
    with open(output_path, 'w') as f:
        json.dump(compounds, f, indent=2)
    
    # Summary
    found = sum(1 for c in compounds.values() if c["queried_as"] is not None)
    not_found = sum(1 for c in compounds.values() if c["queried_as"] is None)
    
    print(f"\nSaved {len(compounds)} compounds to {output_path}")
    print(f"  Found in eQuilibrator: {found}")
    print(f"  Not found: {not_found}")
    print(f"  Success by source:")
    for source, count in sorted(success_by_source.items(), key=lambda x: -x[1]):
        print(f"    {source}: {count}")
    
    name_search_count = success_by_source.get('name_search', 0)
    if name_search_count > 0:
        print(f"\n  ⚠️  {name_search_count} compounds used name search - review InChI keys!")


if __name__ == "__main__":
    main()
