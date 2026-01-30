"""Pathway tracing service."""

from data_access import cobra_model, thermo


def get_metabolite_context(met_id):
    """Get full context for a metabolite: info, reactions, thermo."""
    met = cobra_model.get_metabolite(met_id)
    if met is None:
        return None
    
    model = cobra_model.get_model()
    compartment_names = model.compartments if model else {}
    
    producing = []
    consuming = []
    
    for rxn in met.reactions:
        coef = rxn.metabolites[met]
        rxn_info = _build_reaction_info(rxn, compartment_names)
        
        if coef < 0:
            consuming.append(rxn_info)
        else:
            producing.append(rxn_info)
    
    return {
        'id': met.id,
        'name': met.name,
        'compartment': met.compartment,
        'compartment_name': compartment_names.get(met.compartment, met.compartment),
        'formula': met.formula or '',
        'thermo': thermo.get_compound_by_met_id(met.id),
        'producing': producing,
        'consuming': consuming
    }


def get_subsystem_reactions(subsystem_name):
    """Get all reactions in a subsystem with full context."""
    model = cobra_model.get_model()
    if model is None:
        return None
    
    compartment_names = model.compartments
    reactions = []
    for rxn in model.reactions:
        if rxn.subsystem == subsystem_name:
            reactions.append(_build_reaction_info(rxn, compartment_names))
    
    return {
        'subsystem': subsystem_name,
        'reactions': reactions
    }


def get_reaction_context(rxn_id):
    """Get full context for a reaction."""
    rxn = cobra_model.get_reaction(rxn_id)
    if rxn is None:
        return None
    
    model = cobra_model.get_model()
    compartment_names = model.compartments if model else {}
    
    # Get human-readable equation info
    eq_info = cobra_model.build_reaction_info(rxn, compartment_names)
    
    result = {
        'id': rxn.id,
        'name': rxn.name,
        'equation_raw': rxn.reaction,
        'equation': eq_info['equation'],
        'location_type': eq_info['location_type'],
        'location': eq_info['location'],
        'lower_bound': rxn.lower_bound,
        'upper_bound': rxn.upper_bound,
        'genes': rxn.gene_reaction_rule or '',
        'subsystem': rxn.subsystem or '',
        'reversible': rxn.reversibility,
        'metabolites': [],
        'thermo': thermo.get_reaction(rxn.id)
    }
    
    # Add metabolites with their thermo - organized as substrates/products
    substrates = []
    products = []
    for met, coef in rxn.metabolites.items():
        met_info = {
            'id': met.id,
            'name': met.name,
            'coefficient': coef,
            'compartment': met.compartment,
            'compartment_name': compartment_names.get(met.compartment, met.compartment),
            'thermo': thermo.get_compound_by_met_id(met.id)
        }
        if coef < 0:
            substrates.append(met_info)
        else:
            products.append(met_info)
    
    result['substrates'] = substrates
    result['products'] = products
    result['metabolites'] = substrates + products  # Keep for backwards compat
    
    # Add EC/KEGG annotations
    if rxn.annotation:
        ec = rxn.annotation.get('ec-code', [])
        result['ec'] = ec if isinstance(ec, list) else [ec] if ec else []
        kegg = rxn.annotation.get('kegg.reaction', [])
        result['kegg'] = kegg if isinstance(kegg, list) else [kegg] if kegg else []
    
    # Add flux
    flux = cobra_model.get_flux(rxn.id)
    if flux is not None:
        result['flux'] = round(flux, 6)
    
    return result


def _build_reaction_info(rxn, compartment_names=None):
    """Build reaction info dict with thermo and flux."""
    # Use shared equation builder
    eq_info = cobra_model.build_reaction_info(rxn, compartment_names)
    
    info = {
        'id': rxn.id,
        'name': rxn.name,
        'equation_raw': rxn.reaction,
        'equation': eq_info['equation'],
        'location_type': eq_info['location_type'],
        'location': eq_info['location'],
        'genes': rxn.gene_reaction_rule or '',
        'subsystem': rxn.subsystem or ''
    }
    
    # Add thermo
    rxn_thermo = thermo.get_reaction(rxn.id)
    if rxn_thermo:
        t = rxn_thermo.get('thermodynamics', {})
        info['dG_prime'] = t.get('dG_prime')
        info['uncertainty'] = t.get('uncertainty')
        info['formula_queried'] = t.get('formula_queried')
    
    # Add flux
    flux = cobra_model.get_flux(rxn.id)
    if flux is not None:
        info['flux'] = round(flux, 6)
    
    return info
