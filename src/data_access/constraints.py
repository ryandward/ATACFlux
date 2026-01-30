"""Constraint management for FBA conditions."""

from . import annotations

# Active constraints (in-memory, could persist to JSON later)
_constraints = {}


def add(constraint_id, constraint_type, target_id, bounds, label=None, bound_type=None, target_info=None):
    """
    Add a constraint.
    
    Args:
        constraint_id: Unique ID for this constraint
        constraint_type: 'reaction' or 'exchange' (metabolite)
        target_id: Reaction ID or metabolite ID
        bounds: Tuple (lower, upper) or single value for fixed
        label: Human-readable label
        bound_type: 'fixed', 'max', 'min', or 'range' (for editing)
        target_info: Original target info dict (for editing)
    """
    _constraints[constraint_id] = {
        'type': constraint_type,
        'target': target_id,
        'bounds': bounds,
        'label': label or constraint_id,
        'enabled': True,
        'boundType': bound_type,
        'targetInfo': target_info
    }


def remove(constraint_id):
    """Remove a constraint."""
    if constraint_id in _constraints:
        del _constraints[constraint_id]
        return True
    return False


def toggle(constraint_id, enabled=None):
    """Enable/disable a constraint."""
    if constraint_id in _constraints:
        if enabled is None:
            _constraints[constraint_id]['enabled'] = not _constraints[constraint_id]['enabled']
        else:
            _constraints[constraint_id]['enabled'] = enabled
        return True
    return False


def get(constraint_id):
    """Get a specific constraint."""
    return _constraints.get(constraint_id)


def list_all():
    """List all constraints."""
    return dict(_constraints)


def get_enabled():
    """Get only enabled constraints."""
    return {k: v for k, v in _constraints.items() if v['enabled']}


def clear():
    """Clear all constraints."""
    _constraints.clear()


def apply_to_model(model):
    """
    Apply all enabled constraints to a COBRA model.
    Returns dict of {constraint_id: success/error}
    """
    results = {}
    
    for cid, constraint in _constraints.items():
        if not constraint['enabled']:
            continue
            
        try:
            if constraint['type'] == 'reaction':
                rxn = model.reactions.get_by_id(constraint['target'])
                bounds = constraint['bounds']
                if isinstance(bounds, (int, float)):
                    rxn.bounds = (bounds, bounds)
                else:
                    rxn.bounds = tuple(bounds)
                results[cid] = {'success': True}
                
            elif constraint['type'] == 'exchange':
                # Find exchange reaction for this metabolite
                met_id = constraint['target']
                exchange_rxn = None
                
                # Target might be reaction ID directly (from selection)
                try:
                    exchange_rxn = model.reactions.get_by_id(met_id)
                except KeyError:
                    # Or it might be metabolite ID - find its exchange
                    try:
                        met = model.metabolites.get_by_id(met_id)
                        exchange_rxns = annotations.find_exchange_reaction(model, met)
                        if exchange_rxns:
                            exchange_rxn = exchange_rxns[0]  # Use first if multiple
                    except KeyError:
                        pass
                
                if exchange_rxn:
                    bounds = constraint['bounds']
                    if isinstance(bounds, (int, float)):
                        exchange_rxn.bounds = (bounds, bounds)
                    else:
                        exchange_rxn.bounds = tuple(bounds)
                    results[cid] = {'success': True, 'reaction': exchange_rxn.id}
                else:
                    results[cid] = {'success': False, 'error': f'No exchange reaction for {met_id}'}
                    
        except Exception as e:
            results[cid] = {'success': False, 'error': str(e)}
    
    return results


def build_preset_from_query(model, name, metabolite_query, bounds, bound_description):
    """
    Build a preset constraint by querying for the metabolite.
    Data-driven: uses annotation lookup instead of hardcoded IDs.
    
    Args:
        model: COBRA model
        name: Preset name (e.g., 'anaerobic')
        metabolite_query: Query string (KEGG ID, name, etc.)
        bounds: Tuple (lower, upper)
        bound_description: Human-readable description
    
    Returns:
        dict with constraint info, or None if not found
    """
    result = annotations.find_exchange_by_query(model, metabolite_query)
    
    if not result['exchanges']:
        return None
    
    # Use first exchange found (there could be multiple)
    exchange = result['exchanges'][0]
    
    return {
        'id': f'preset_{name}',
        'type': 'reaction',
        'target': exchange['id'],
        'bounds': bounds,
        'label': f"{result['metabolites'][0]['name'] if result['metabolites'] else metabolite_query}: {bound_description}",
        'derived_from': {
            'query': metabolite_query,
            'metabolites_found': result['metabolites'],
            'exchange_reaction': exchange,
            'all_exchanges': result['exchanges']  # Include all for transparency
        }
    }


def get_available_presets(model):
    """
    Get available presets for a model by querying annotations.
    Data-driven: discovers what's possible rather than assuming.
    """
    preset_definitions = [
        {
            'name': 'anaerobic',
            'label': 'Anaerobic',
            'description': 'No oxygen uptake',
            'queries': ['C00007', 'oxygen', 'O2'],  # Try multiple identifiers
            'bounds': (0, 0),
            'bound_description': '= 0'
        },
        {
            'name': 'glucose_limited',
            'label': 'Glucose limited',
            'description': 'Restrict glucose uptake',
            'queries': ['C00031', 'glucose', 'D-glucose'],
            'bounds': (-1, 0),
            'bound_description': '≤ 1 mmol/gDW/h'
        },
        {
            'name': 'no_ethanol',
            'label': 'No ethanol',
            'description': 'Block ethanol production',
            'queries': ['C00469', 'ethanol'],
            'bounds': (0, 0),
            'bound_description': '= 0'
        }
    ]
    
    available = {}
    
    for preset_def in preset_definitions:
        # Try each query until one works
        for query in preset_def['queries']:
            constraint = build_preset_from_query(
                model,
                preset_def['name'],
                query,
                preset_def['bounds'],
                preset_def['bound_description']
            )
            if constraint:
                available[preset_def['name']] = {
                    'label': preset_def['label'],
                    'description': preset_def['description'],
                    'constraint': constraint
                }
                break  # Found it, stop trying other queries
    
    return available


def apply_preset(model, preset_name):
    """
    Apply a preset by name.
    Discovers the appropriate reaction via annotation lookup.
    """
    presets = get_available_presets(model)
    
    if preset_name not in presets:
        return {'success': False, 'error': f'Preset {preset_name} not available for this model'}
    
    preset = presets[preset_name]
    constraint = preset['constraint']
    
    # Add the constraint
    add(
        constraint['id'],
        constraint['type'],
        constraint['target'],
        constraint['bounds'],
        constraint['label']
    )
    
    return {
        'success': True,
        'constraint': constraint,
        'derived_from': constraint.get('derived_from')
    }

