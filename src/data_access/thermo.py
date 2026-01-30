"""Thermodynamic data access layer."""

import json
import os

# Module-level cache
_reactions = {}
_compounds = {}
_loaded = False


def load(data_dir=None):
    """Load thermodynamic caches from JSON files."""
    global _reactions, _compounds, _loaded
    
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(__file__), '../../data')
    
    reactions_path = os.path.join(data_dir, 'reactions_thermo.json')
    if os.path.exists(reactions_path):
        with open(reactions_path) as f:
            _reactions = json.load(f)
    
    compounds_path = os.path.join(data_dir, 'compounds_thermo.json')
    if os.path.exists(compounds_path):
        with open(compounds_path) as f:
            _compounds = json.load(f)
    
    _loaded = True


def is_loaded():
    """Check if caches are loaded."""
    return _loaded and len(_reactions) > 0


def get_reaction(rxn_id):
    """Get thermo data for a reaction."""
    return _reactions.get(rxn_id)


def get_compound(compound_id):
    """Get thermo data for a compound by cache key."""
    return _compounds.get(compound_id)


def get_compound_by_met_id(met_id):
    """Get thermo data for a compound by yeast-GEM metabolite ID."""
    for key, data in _compounds.items():
        if met_id in data.get('identifiers', {}).get('yeast_gem', []):
            return data
    return None


def get_all_reactions():
    """Get full reactions cache (for client-side use)."""
    return _reactions


def get_all_compounds():
    """Get full compounds cache."""
    return _compounds


def stats():
    """Get cache statistics."""
    return {
        'reactions_count': len(_reactions),
        'compounds_count': len(_compounds),
        'loaded': _loaded
    }
