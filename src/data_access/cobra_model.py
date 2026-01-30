"""COBRA model access layer."""

import cobra
import os

# Module-level state
_model = None
_model_path = None
_fba_solution = None
_original_bounds = {}  # Store original bounds for reset


def load(model_path=None):
    """Load COBRA model from file."""
    global _model, _model_path, _original_bounds
    
    if model_path and os.path.exists(model_path):
        _model = cobra.io.read_sbml_model(model_path)
        _model_path = model_path
        _store_original_bounds()
        return True
    
    # Search default locations
    base_dir = os.path.dirname(__file__)
    search_paths = [
        '../../models/yeast-GEM.xml',
        '../../models/yeast8.xml',
        '../../../models/yeast-GEM.xml',
    ]
    
    for path in search_paths:
        full_path = os.path.join(base_dir, path)
        if os.path.exists(full_path):
            _model = cobra.io.read_sbml_model(full_path)
            _model_path = full_path
            _store_original_bounds()
            return True
    
    return False


def _store_original_bounds():
    """Store original bounds for all reactions."""
    global _original_bounds
    _original_bounds = {}
    if _model:
        for rxn in _model.reactions:
            _original_bounds[rxn.id] = (rxn.lower_bound, rxn.upper_bound)


def reset_bounds():
    """Reset all reactions to original bounds."""
    if _model and _original_bounds:
        for rxn in _model.reactions:
            if rxn.id in _original_bounds:
                rxn.bounds = _original_bounds[rxn.id]


def build_reaction_info(rxn, compartment_names=None, smart_break=True):
    """
    Build human-readable reaction info.
    
    Returns dict with:
        - equation: human-readable equation with metabolite names
        - equation_raw: original ID-based equation
        - location_type: 'compartment', 'compartments', or 'boundary'
        - location: the location value (e.g., "cytoplasm" or "extracellular ⇌ cytoplasm")
    """
    if compartment_names is None:
        compartment_names = _model.compartments if _model else {}
    
    # Collect compartment info
    all_compartments = set(m.compartment for m in rxn.metabolites.keys())
    single_compartment = len(all_compartments) == 1
    is_exchange = len(rxn.metabolites) == 1
    
    # Determine if transport (same metabolite name in different compartments)
    met_names = [m.name for m in rxn.metabolites.keys()]
    is_transport = len(set(met_names)) == 1 and len(all_compartments) > 1
    
    # Build human-readable equation
    substrates = []
    products = []
    for m, coef in rxn.metabolites.items():
        # Include compartment tag only if multiple compartments (transport)
        if single_compartment or is_exchange:
            met_label = m.name
        else:
            met_label = f"{m.name}[{m.compartment}]"
        
        # Add stoichiometric coefficient if not 1
        abs_coef = abs(coef)
        if abs_coef != 1:
            # Use integer if whole number, otherwise 2 decimal places
            if abs_coef == int(abs_coef):
                met_label = f"{int(abs_coef)} {met_label}"
            else:
                met_label = f"{abs_coef:.2g} {met_label}"
        
        if coef < 0:
            substrates.append(met_label)
        else:
            products.append(met_label)
    
    left = ' + '.join(substrates) if substrates else '∅'
    right = ' + '.join(products) if products else '∅'
    arrow = '⇌' if rxn.reversibility else '→'
    human_equation = f"{left} {arrow} {right}"
    
    # Smart line breaking for long equations
    if smart_break and len(human_equation) > 60:
        human_equation = human_equation.replace(f' {arrow} ', f' {arrow}\n')
        if any(len(part) > 80 for part in human_equation.split('\n')):
            human_equation = human_equation.replace(' + ', ' +\n')
    
    # Determine location info
    if is_exchange:
        # Exchange: compartment ⇌ environment (transport to environment)
        comp_id = list(all_compartments)[0]
        comp_name = compartment_names.get(comp_id, comp_id)
        location_type = 'compartments'
        location = f"{comp_name} ⇌ environment"
    elif is_transport:
        # Transport: compartment A ⇌ compartment B
        ordered_comps = []
        for m, coef in rxn.metabolites.items():
            if m.compartment not in ordered_comps:
                ordered_comps.append(m.compartment)
        comp_names_list = [compartment_names.get(c, c) for c in ordered_comps]
        location_type = 'compartments'
        location = ' ⇌ '.join(comp_names_list)
    elif single_compartment:
        # Standard reaction in one compartment
        comp_id = list(all_compartments)[0]
        comp_name = compartment_names.get(comp_id, comp_id)
        location_type = 'compartment'
        location = comp_name
    else:
        # Multi-compartment reaction (not transport)
        ordered_comps = []
        for m, coef in rxn.metabolites.items():
            if m.compartment not in ordered_comps:
                ordered_comps.append(m.compartment)
        comp_names_list = [compartment_names.get(c, c) for c in ordered_comps]
        location_type = 'compartments'
        location = ', '.join(comp_names_list)
    
    return {
        'equation': human_equation,
        'equation_raw': rxn.reaction,
        'location_type': location_type,
        'location': location,
        'is_exchange': is_exchange
    }


def build_metabolite_reaction_info(rxn, selected_met, compartment_names=None):
    """
    Build reaction info relative to a selected metabolite.
    Adds description of what the reaction does for that metabolite.
    """
    info = build_reaction_info(rxn, compartment_names)
    
    if compartment_names is None:
        compartment_names = _model.compartments if _model else {}
    
    # Determine description relative to selected metabolite
    is_exchange = len(rxn.metabolites) == 1
    
    if is_exchange:
        description = "transport to/from environment"
    else:
        other_mets = [m for m in rxn.metabolites.keys() if m.id != selected_met.id]
        if other_mets:
            other_comps = set(m.compartment for m in other_mets)
            if selected_met.compartment in other_comps:
                description = "internal reaction"
            else:
                other_comp_names = [compartment_names.get(c, c) for c in other_comps]
                description = f"transport to/from {', '.join(other_comp_names)}"
        else:
            description = "reaction"
    
    info['description'] = description
    return info


def is_loaded():
    """Check if model is loaded."""
    return _model is not None


def get_model():
    """Get the loaded model."""
    return _model


def get_path():
    """Get path to loaded model."""
    return _model_path


def info():
    """Get model info."""
    if _model is None:
        return None
    return {
        'id': _model.id,
        'reactions': len(_model.reactions),
        'metabolites': len(_model.metabolites),
        'genes': len(_model.genes),
        'path': os.path.basename(_model_path) if _model_path else None
    }


def optimize():
    """Run FBA optimization."""
    global _fba_solution
    if _model is None:
        return None
    
    # Reset GLPK basis to ensure consistent results
    # (prevents warm-start from biasing toward previous solution path)
    try:
        import swiglpk as glpk
        glpk.glp_std_basis(_model.solver.problem)
    except (ImportError, AttributeError):
        pass  # Non-GLPK solver or swiglpk not available
    
    _fba_solution = _model.optimize()
    return _fba_solution


def get_fba_solution():
    """Get current FBA solution."""
    return _fba_solution


def get_flux(rxn_id):
    """Get flux for a reaction from current FBA solution."""
    if _fba_solution is None:
        return None
    return _fba_solution.fluxes.get(rxn_id)


def get_reaction(rxn_id):
    """Get a reaction by ID."""
    if _model is None:
        return None
    try:
        return _model.reactions.get_by_id(rxn_id)
    except KeyError:
        return None


def get_metabolite(met_id):
    """Get a metabolite by ID."""
    if _model is None:
        return None
    try:
        return _model.metabolites.get_by_id(met_id)
    except KeyError:
        return None


def list_reactions(query=None, limit=50, offset=0, nonzero_flux_only=False):
    """List reactions with optional search and flux filter."""
    if _model is None:
        return [], 0
    
    compartment_names = _model.compartments
    
    results = []
    for rxn in _model.reactions:
        if query:
            searchable = f"{rxn.id} {rxn.name} {rxn.gene_reaction_rule}".lower()
            if query.lower() not in searchable:
                continue
        
        flux = None
        if _fba_solution is not None:
            flux = round(_fba_solution.fluxes.get(rxn.id, 0), 6)
        
        # Filter by non-zero flux if requested
        if nonzero_flux_only:
            if flux is None or abs(flux) <= 1e-6:
                continue
        
        # Get location info
        info = build_reaction_info(rxn, compartment_names, smart_break=False)
        
        results.append({
            'id': rxn.id,
            'name': rxn.name,
            'equation': rxn.reaction,
            'bounds': list(rxn.bounds),
            'genes': rxn.gene_reaction_rule or '',
            'subsystem': rxn.subsystem or '',
            'flux': flux,
            'location_type': info['location_type'],
            'location': info['location'],
            'compartments': list(dict.fromkeys(m.compartment for m in rxn.metabolites.keys()))
        })
    
    total = len(results)
    return results[offset:offset + limit], total


def list_subsystems():
    """List all subsystems with reaction counts."""
    if _model is None:
        return []
    
    subsystems = {}
    for rxn in _model.reactions:
        ss = rxn.subsystem or 'Uncategorized'
        if ss not in subsystems:
            subsystems[ss] = []
        subsystems[ss].append(rxn.id)
    
    return [
        {'name': name, 'count': len(rxns), 'reactions': rxns}
        for name, rxns in sorted(subsystems.items())
    ]
