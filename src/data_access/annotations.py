"""Annotation-based metabolite/reaction lookup with cascading fallback."""

from . import thermo


def find_metabolite(model, query, match_type='any'):
    """
    Find metabolite by any identifier using cascading fallback.
    
    Query can be:
    - KEGG ID: "C00007"
    - ChEBI ID: "CHEBI:15379" or "15379"
    - MetaNetX ID: "MNXM4"
    - BiGG ID: "o2"
    - Name: "oxygen", "O2", "dioxygen"
    
    Returns list of matching metabolites (may be multiple compartments).
    """
    query_lower = query.lower().strip()
    query_normalized = query.replace('CHEBI:', '').replace('chebi:', '')
    
    matches = []
    
    for met in model.metabolites:
        # Check annotations
        ann = met.annotation or {}
        
        # KEGG
        kegg = ann.get('kegg.compound', [])
        if isinstance(kegg, str):
            kegg = [kegg]
        if query.upper() in [k.upper() for k in kegg]:
            matches.append(met)
            continue
        
        # ChEBI (handle with or without prefix)
        chebi = ann.get('chebi', [])
        if isinstance(chebi, str):
            chebi = [chebi]
        chebi_normalized = [c.replace('CHEBI:', '').replace('chebi:', '') for c in chebi]
        if query_normalized in chebi_normalized:
            matches.append(met)
            continue
        
        # MetaNetX
        metanetx = ann.get('metanetx.chemical', [])
        if isinstance(metanetx, str):
            metanetx = [metanetx]
        if query.upper() in [m.upper() for m in metanetx]:
            matches.append(met)
            continue
        
        # BiGG
        bigg = ann.get('bigg.metabolite', [])
        if isinstance(bigg, str):
            bigg = [bigg]
        if query_lower in [b.lower() for b in bigg]:
            matches.append(met)
            continue
        
        # Name match (substring for flexibility)
        if match_type == 'exact':
            if query_lower == met.name.lower():
                matches.append(met)
        else:
            if query_lower in met.name.lower() or met.name.lower() in query_lower:
                matches.append(met)
    
    return matches


def find_metabolite_from_thermo_cache(model, query):
    """
    Find metabolite using the thermo compound cache.
    This leverages all the identifier mapping we already did.
    """
    compounds = thermo.get_all_compounds()
    
    # Search thermo cache for matching identifiers
    matching_gem_ids = set()
    query_lower = query.lower().strip()
    query_normalized = query.replace('CHEBI:', '').replace('chebi:', '')
    
    for compound_key, data in compounds.items():
        ids = data.get('identifiers', {})
        
        # Check KEGG
        kegg = ids.get('kegg') or ''
        if kegg and kegg.upper() == query.upper():
            matching_gem_ids.update(ids.get('yeast_gem', []))
            continue
        
        # Check ChEBI
        chebi = ids.get('chebi') or ''
        if chebi and chebi.replace('CHEBI:', '') == query_normalized:
            matching_gem_ids.update(ids.get('yeast_gem', []))
            continue
        
        # Check MetaNetX
        metanetx = ids.get('metanetx') or ''
        if metanetx and metanetx.upper() == query.upper():
            matching_gem_ids.update(ids.get('yeast_gem', []))
            continue
        
        # Check BiGG
        bigg = ids.get('bigg') or ''
        if bigg and bigg.lower() == query_lower:
            matching_gem_ids.update(ids.get('yeast_gem', []))
            continue
        
        # Check name
        name = data.get('name') or ''
        if name and name.lower() == query_lower:
            matching_gem_ids.update(ids.get('yeast_gem', []))
            continue
    
    # Get actual metabolite objects
    matches = []
    for met_id in matching_gem_ids:
        try:
            met = model.metabolites.get_by_id(met_id)
            matches.append(met)
        except KeyError:
            pass
    
    return matches


def find_exchange_reaction(model, metabolite):
    """
    Find exchange reaction(s) for a metabolite.
    Exchange reactions have only one metabolite.
    Returns list (could be multiple or empty).
    """
    exchanges = []
    for rxn in metabolite.reactions:
        if len(rxn.metabolites) == 1:
            exchanges.append(rxn)
    return exchanges


def find_exchange_by_query(model, query):
    """
    Find exchange reaction by metabolite query.
    Combines find_metabolite + find_exchange_reaction.
    
    Returns dict with:
    - metabolites: list of matching metabolites
    - exchanges: list of exchange reactions found
    - query: original query
    """
    # Try thermo cache first (more comprehensive ID mapping)
    metabolites = find_metabolite_from_thermo_cache(model, query)
    
    # Fallback to direct model search
    if not metabolites:
        metabolites = find_metabolite(model, query)
    
    # Find exchange reactions
    exchanges = []
    for met in metabolites:
        exch_list = find_exchange_reaction(model, met)
        for exch in exch_list:
            if exch not in exchanges:
                exchanges.append(exch)
    
    return {
        'query': query,
        'metabolites': [{'id': m.id, 'name': m.name, 'compartment': m.compartment} for m in metabolites],
        'exchanges': [{'id': r.id, 'name': r.name, 'bounds': list(r.bounds)} for r in exchanges]
    }


# Common metabolite identifiers for presets
# These are database IDs, not model-specific reaction IDs
METABOLITE_IDENTIFIERS = {
    'oxygen': {
        'kegg': 'C00007',
        'chebi': 'CHEBI:15379',
        'names': ['oxygen', 'O2', 'dioxygen']
    },
    'glucose': {
        'kegg': 'C00031',
        'chebi': 'CHEBI:17634',
        'names': ['glucose', 'D-glucose', 'dextrose']
    },
    'ethanol': {
        'kegg': 'C00469',
        'chebi': 'CHEBI:16236',
        'names': ['ethanol', 'alcohol', 'EtOH']
    },
    'carbon_dioxide': {
        'kegg': 'C00011',
        'chebi': 'CHEBI:16526',
        'names': ['carbon dioxide', 'CO2']
    },
    'ammonium': {
        'kegg': 'C00014',
        'chebi': 'CHEBI:28938',
        'names': ['ammonium', 'NH4+', 'ammonia']
    }
}


def resolve_metabolite_identifier(name):
    """
    Get database identifiers for a common metabolite name.
    """
    name_lower = name.lower().replace(' ', '_').replace('-', '_')
    return METABOLITE_IDENTIFIERS.get(name_lower)
