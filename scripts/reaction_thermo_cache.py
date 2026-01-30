"""
reaction_thermo_cache.py

Generate reaction thermodynamic cache from Equilibrator.
Requires compounds_thermo.json to identify failed compounds.
Uses compartment_parameters.json for multicompartmental reactions.
Uses redox_couples.json for metalloprotein/quinone reactions.

Three calculation methods:
1. Standard: cc.standard_dg_prime() for most reactions
2. Multicompartmental: cc.multicompartmental_standard_dg_prime() for H+ transport
3. RedoxCarrier: PhasedReaction with RedoxCarrier objects for metalloproteins

Usage:
    python scripts/reaction_thermo_cache.py models/yeast-GEM.xml data/compounds_thermo.json data/reactions_thermo.json [data/compartment_parameters.json] [data/redox_couples.json]
"""

import json
import sys
from pathlib import Path

import cobra
from equilibrator_api import ComponentContribution, Q_
from equilibrator_api.phased_reaction import PhasedReaction
from equilibrator_api.phased_compound import PhasedCompound, RedoxCarrier

# KEGG ID for H+
PROTON_KEGG = "kegg:C00080"


def build_compound_lookup(compounds):
    """Build lookup tables from compound cache.
    
    Returns dict mapping yeast_gem IDs to compound cache entries.
    """
    lookup = {}
    for key, entry in compounds.items():
        for yeast_id in entry['identifiers'].get('yeast_gem', []):
            lookup[yeast_id] = entry
    return lookup


def load_compartment_params(path, model_name="yeast-GEM"):
    """Load compartment parameters for a model."""
    if path is None or not Path(path).exists():
        return None
    with open(path) as f:
        params = json.load(f)
    return params.get("models", {}).get(model_name)


def analyze_proton_compartments(rxn, compound_lookup):
    """Analyze H+ stoichiometry by compartment.
    
    Returns dict mapping compartment -> net H+ coefficient,
    or None if reaction has no H+ or H+ not in cache.
    """
    proton_by_compartment = {}
    
    for met, coef in rxn.metabolites.items():
        comp_entry = compound_lookup.get(met.id)
        if comp_entry and comp_entry.get("queried_as") == PROTON_KEGG:
            compartment = met.compartment
            proton_by_compartment[compartment] = proton_by_compartment.get(compartment, 0) + coef
    
    # Filter out compartments with zero net H+
    proton_by_compartment = {k: v for k, v in proton_by_compartment.items() if abs(v) > 1e-9}
    
    return proton_by_compartment if proton_by_compartment else None


def is_transmembrane_proton_reaction(proton_compartments, membranes):
    """Check if reaction involves H+ transport across a defined membrane.
    
    Returns (inner_compartment, outer_compartment, membrane_key) or None.
    """
    if proton_compartments is None or len(proton_compartments) < 2:
        return None
    
    compartments = set(proton_compartments.keys())
    
    for membrane_key, membrane in membranes.items():
        inner = membrane["inner"]
        outer = membrane["outer"]
        if inner in compartments and outer in compartments:
            return (inner, outer, membrane_key)
    
    return None


def build_half_reactions(rxn, compound_lookup, inner_compartment, outer_compartment):
    """Split reaction into inner and outer half-reactions for multicompartmental calculation.
    
    Returns (inner_stoich, outer_stoich) as dicts mapping KEGG IDs to coefficients.
    """
    inner_stoich = {}
    outer_stoich = {}
    
    for met, coef in rxn.metabolites.items():
        comp_entry = compound_lookup.get(met.id)
        if not comp_entry or not comp_entry.get("queried_as"):
            continue
        
        query_id = comp_entry["queried_as"]
        compartment = met.compartment
        
        if compartment == inner_compartment:
            inner_stoich[query_id] = inner_stoich.get(query_id, 0) + coef
        elif compartment == outer_compartment:
            outer_stoich[query_id] = outer_stoich.get(query_id, 0) + coef
        # Metabolites in other compartments are ignored for this calculation
    
    # Filter zeros
    inner_stoich = {k: v for k, v in inner_stoich.items() if abs(v) > 1e-9}
    outer_stoich = {k: v for k, v in outer_stoich.items() if abs(v) > 1e-9}
    
    return inner_stoich, outer_stoich


def stoich_to_formula(stoich):
    """Convert stoichiometry dict to Equilibrator formula string."""
    subs, prods = [], []
    for query_id, coef in stoich.items():
        term = f"{abs(coef)} {query_id}" if abs(coef) != 1 else query_id
        (subs if coef < 0 else prods).append(term)
    
    lhs = " + ".join(subs) if subs else ""
    rhs = " + ".join(prods) if prods else ""
    return f"{lhs} = {rhs}"


def load_redox_couples(path):
    """Load redox couple definitions from JSON file.
    
    Returns dict mapping KEGG ID -> (is_reduced, potential_mV, couple_name)
    """
    if path is None or not Path(path).exists():
        return {}
    
    with open(path) as f:
        data = json.load(f)
    
    lookup = {}
    for couple_name, couple in data.get("couples", {}).items():
        ox_kegg = couple["oxidized_kegg"]
        red_kegg = couple["reduced_kegg"]
        potential = couple["potential_mV"]
        
        # Oxidized form: reference (0 mV)
        lookup[ox_kegg] = (False, potential, couple_name)
        # Reduced form: stores electron energy
        lookup[red_kegg] = (True, potential, couple_name)
    
    return lookup


def reaction_needs_redox(rxn, compound_lookup, redox_lookup):
    """Check if reaction contains any redox couples that need RedoxCarrier treatment.
    
    Only returns couples where BOTH oxidized AND reduced forms are present.
    This ensures we only handle actual electron transfer, not biosynthesis.
    
    Returns list of (kegg_id, is_reduced, potential_mV, couple_name) tuples,
    or empty list if no complete redox couples found.
    """
    # First pass: collect all KEGG IDs in reaction
    keggs_in_rxn = set()
    for met in rxn.metabolites:
        comp_entry = compound_lookup.get(met.id)
        if comp_entry and comp_entry.get("queried_as"):
            keggs_in_rxn.add(comp_entry["queried_as"])
    
    # Build reverse lookup: couple_name -> (ox_kegg, red_kegg)
    couples_by_name = {}
    for kegg_id, (is_reduced, potential, couple_name) in redox_lookup.items():
        if couple_name not in couples_by_name:
            couples_by_name[couple_name] = {"potential": potential}
        if is_reduced:
            couples_by_name[couple_name]["reduced"] = kegg_id
        else:
            couples_by_name[couple_name]["oxidized"] = kegg_id
    
    # Find couples where BOTH forms are present
    complete_couples = set()
    for couple_name, info in couples_by_name.items():
        ox = info.get("oxidized")
        red = info.get("reduced")
        if ox and red and ox in keggs_in_rxn and red in keggs_in_rxn:
            complete_couples.add(couple_name)
    
    if not complete_couples:
        return []
    
    # Second pass: return info for compounds in complete couples only
    redox_compounds = []
    for met in rxn.metabolites:
        comp_entry = compound_lookup.get(met.id)
        if not comp_entry:
            continue
        
        kegg_id = comp_entry.get("queried_as")
        if kegg_id and kegg_id in redox_lookup:
            is_reduced, potential, couple_name = redox_lookup[kegg_id]
            if couple_name in complete_couples:
                redox_compounds.append((kegg_id, is_reduced, potential, couple_name))
    
    return redox_compounds


def calc_dg_with_redox_carriers(cc, rxn, compound_lookup, redox_lookup):
    """Calculate ΔG°' using RedoxCarrier for metalloprotein redox couples.
    
    This is needed because eQuilibrator cannot calculate formation energies
    for cytochromes and other metalloproteins (no InChI structure available).
    
    Returns (dG_value, dG_uncertainty, method_info) or raises exception.
    """
    sparse = {}
    sparse_with_phases = {}
    couples_used = set()
    
    for met, coef in rxn.metabolites.items():
        comp_entry = compound_lookup.get(met.id)
        if not comp_entry or not comp_entry.get("queried_as"):
            continue
        
        kegg_id = comp_entry["queried_as"]
        compound = cc.get_compound(kegg_id)
        
        # Check if this compound needs RedoxCarrier treatment
        if kegg_id in redox_lookup:
            is_reduced, potential, couple_name = redox_lookup[kegg_id]
            couples_used.add(couple_name)
            
            if is_reduced:
                # Reduced form stores electron energy at the given potential
                phased = RedoxCarrier(compound, potential=Q_(f"{potential} mV"))
            else:
                # Oxidized form is reference (0 mV)
                phased = RedoxCarrier(compound, potential=Q_("0 mV"))
        else:
            # Regular compound
            phased = PhasedCompound(compound)
        
        # Accumulate stoichiometry (metabolites may appear in multiple compartments)
        sparse[compound] = sparse.get(compound, 0) + coef
        sparse_with_phases[phased] = sparse_with_phases.get(phased, 0) + coef
    
    # Build PhasedReaction
    phased_rxn = PhasedReaction(sparse=sparse, sparse_with_phases=sparse_with_phases)
    
    # Calculate ΔG°'
    dG = cc.standard_dg_prime(phased_rxn)
    
    method_info = {
        "method": "redox_carrier",
        "couples_used": list(couples_used),
        "note": "Used RedoxCarrier with literature reduction potentials for metalloprotein redox couples"
    }
    
    return float(dG.value.magnitude), float(dG.error.magnitude), method_info


def main():
    if len(sys.argv) < 4:
        print("Usage: python scripts/reaction_thermo_cache.py <model.xml> <compounds.json> <output.json> [compartment_params.json] [redox_couples.json]")
        sys.exit(1)
    
    model_path = sys.argv[1]
    compounds_path = sys.argv[2]
    output_path = sys.argv[3]
    compartment_path = sys.argv[4] if len(sys.argv) > 4 else None
    redox_path = sys.argv[5] if len(sys.argv) > 5 else None
    
    # Auto-detect redox_couples.json if not specified
    if redox_path is None:
        default_redox = Path(compounds_path).parent / "redox_couples.json"
        if default_redox.exists():
            redox_path = str(default_redox)
    
    print("Loading model...")
    model = cobra.io.read_sbml_model(model_path)
    
    print("Loading compound cache...")
    with open(compounds_path) as f:
        compounds = json.load(f)
    
    # Build lookup by yeast_gem ID
    compound_lookup = build_compound_lookup(compounds)
    print(f"  {len(compound_lookup)} metabolite IDs mapped to {len(compounds)} compounds")
    
    # Load compartment parameters
    compartment_params = load_compartment_params(compartment_path)
    if compartment_params:
        print(f"Loaded compartment parameters for multicompartmental reactions")
        membranes = compartment_params.get("membranes", {})
        compartments = compartment_params.get("compartments", {})
    else:
        print("No compartment parameters - using standard dG' for all reactions")
        membranes = {}
        compartments = {}
    
    # Load redox couples for metalloprotein handling
    redox_lookup = load_redox_couples(redox_path)
    if redox_lookup:
        print(f"Loaded {len(redox_lookup) // 2} redox couples for metalloprotein reactions")
    else:
        print("No redox couples - metalloprotein reactions will have high uncertainty")
    
    print("Initializing Equilibrator...")
    cc = ComponentContribution()
    
    print("Processing reactions...")
    reactions = {}
    
    for i, rxn in enumerate(model.reactions):
        if i % 100 == 0:
            print(f"  Processing {i}/{len(model.reactions)}")
        
        # Build stoichiometry and track issues
        stoichiometry = {}
        metabolites_info = {}
        errors = []
        
        for met, coef in rxn.metabolites.items():
            # Look up compound in cache
            comp_entry = compound_lookup.get(met.id)
            
            met_info = {
                "name": met.name,
                "coef": coef,
                "in_cache": comp_entry is not None,
                "found_in_equilibrator": False,
                "queried_as": None
            }
            
            if comp_entry:
                met_info["queried_as"] = comp_entry.get("queried_as")
                met_info["found_in_equilibrator"] = comp_entry.get("queried_as") is not None
                
                # Use the identifier that found this compound
                query_id = comp_entry.get("queried_as")
                if query_id:
                    # Accumulate coefficients (don't overwrite!)
                    stoichiometry[query_id] = stoichiometry.get(query_id, 0) + coef
            
            metabolites_info[met.id] = met_info
        
        # Remove compounds that net to zero (transport reactions)
        stoichiometry = {k: v for k, v in stoichiometry.items() if abs(v) > 1e-9}
        
        # Identify problems
        not_in_cache = [m for m, info in metabolites_info.items() if not info["in_cache"]]
        not_found = [m for m, info in metabolites_info.items() 
                     if info["in_cache"] and not info["found_in_equilibrator"]]
        
        if not_in_cache:
            errors.append({
                "type": "metabolite_not_in_cache",
                "metabolites": not_in_cache
            })
        
        if not_found:
            errors.append({
                "type": "not_found_in_equilibrator",
                "metabolites": not_found
            })
        
        # Get EC annotation (may be string or list)
        ec = None
        if rxn.annotation:
            ec = rxn.annotation.get('ec-code')
            if ec and not isinstance(ec, list):
                ec = [ec]
        
        entry = {
            "name": rxn.name,
            "reaction": {
                "equation": rxn.reaction,
                "stoichiometry": stoichiometry,
                "metabolites": metabolites_info
            },
            "thermodynamics": {
                "dG_prime": None,
                "uncertainty": None,
                "formula_queried": None
            },
            "errors": errors,
            "references": {
                "kegg_reaction": rxn.annotation.get('kegg.reaction') if rxn.annotation else None,
                "ec": ec
            }
        }
        
        # Skip Equilibrator query if we can't build a valid formula
        if not stoichiometry:
            # Pure transport reaction - all compounds cancel out
            entry["thermodynamics"]["dG_prime"] = 0.0
            entry["thermodynamics"]["uncertainty"] = 0.0
            entry["thermodynamics"]["formula_queried"] = "transport (no net reaction)"
            reactions[rxn.id] = entry
            continue
        
        # Check for redox carriers (cytochromes, quinones) that need literature potentials
        redox_compounds = reaction_needs_redox(rxn, compound_lookup, redox_lookup)
        if redox_compounds:
            try:
                dG_val, dG_unc, method_info = calc_dg_with_redox_carriers(
                    cc, rxn, compound_lookup, redox_lookup
                )
                entry["thermodynamics"]["dG_prime"] = dG_val
                entry["thermodynamics"]["uncertainty"] = dG_unc
                entry["thermodynamics"]["method"] = method_info["method"]
                entry["thermodynamics"]["couples_used"] = method_info["couples_used"]
                entry["thermodynamics"]["formula_queried"] = f"RedoxCarrier-based (couples: {', '.join(method_info['couples_used'])})"
                reactions[rxn.id] = entry
                continue
            except Exception as e:
                errors.append({
                    "type": "redox_carrier_error",
                    "message": str(e),
                    "couples_attempted": [c[3] for c in redox_compounds]
                })
                # Fall through to standard calculation
        
        # Check for transmembrane H+ reactions
        proton_compartments = analyze_proton_compartments(rxn, compound_lookup)
        transmembrane_info = is_transmembrane_proton_reaction(proton_compartments, membranes)
        
        use_multicompartmental = False
        if transmembrane_info and compartment_params:
            # Check if we can use multicompartmental calculation
            inner_comp, outer_comp, membrane_key = transmembrane_info
            membrane = membranes[membrane_key]
            
            inner_stoich, outer_stoich = build_half_reactions(
                rxn, compound_lookup, inner_comp, outer_comp
            )
            
            inner_formula = stoich_to_formula(inner_stoich)
            outer_formula = stoich_to_formula(outer_stoich)
            
            # Check if formulas have empty reactants (eQuilibrator can't parse " = X")
            outer_has_only_products = outer_stoich and all(v > 0 for v in outer_stoich.values())
            inner_has_only_products = inner_stoich and all(v > 0 for v in inner_stoich.values())
            
            if outer_has_only_products or inner_has_only_products:
                # Proton pump: calculate standard ΔG°' for chemistry + manual membrane contribution
                # This handles V-ATPases and other proton pumps where eQuilibrator can't parse formulas
                
                inner_pH = compartments.get(inner_comp, {}).get("pH", 7.0)
                outer_pH = compartments.get(outer_comp, {}).get("pH", 7.0)
                potential_mV = membrane.get("potential_mV", 0)
                
                # Calculate proton electrochemical potential (outer → inner)
                # Δμ̃H+ = F×Δψ + RT×ln(10)×(pH_out - pH_in)
                F = 96.485  # kJ/(mol·V)
                RT_ln10 = 2.479 * 2.303  # kJ/mol at 298K, ≈ 5.71
                
                delta_psi = potential_mV / 1000.0  # Convert to V
                delta_pH = outer_pH - inner_pH
                
                # Energy per H+ transported from outer to inner
                dG_per_proton = F * delta_psi + RT_ln10 * delta_pH
                
                # Determine vectorial protons based on thermodynamic direction
                # Scalar proton (from ATP + H2O <-> ADP + Pi + H+) is already in ΔG_chem
                # Vectorial protons are the ones that physically cross the membrane
                n_outer = proton_compartments.get(outer_comp, 0)  # negative = leaving
                n_inner = proton_compartments.get(inner_comp, 0)  # positive = appearing
                
                if dG_per_proton < 0:
                    # Favorable direction: outer→inner (synthesis mode)
                    # Count H+ leaving outer - they flow down the gradient
                    n_vectorial = abs(n_outer)
                else:
                    # Unfavorable direction: pumping against gradient
                    # Count H+ appearing in inner - they're being pumped
                    n_vectorial = abs(n_inner)
                
                # Total membrane contribution
                dG_membrane = n_vectorial * dG_per_proton
                
                # Calculate standard ΔG°' for the chemical reaction (ignoring compartments)
                try:
                    formula = stoich_to_formula(stoichiometry)
                    parsed = cc.parse_reaction_formula(formula)
                    dG_chem = cc.standard_dg_prime(parsed)
                    
                    dG_total = float(dG_chem.value.magnitude) + dG_membrane
                    uncertainty = float(dG_chem.error.magnitude)
                    
                    entry["thermodynamics"]["dG_prime"] = dG_total
                    entry["thermodynamics"]["uncertainty"] = uncertainty
                    entry["thermodynamics"]["method"] = "proton_pump"
                    entry["thermodynamics"]["formula_queried"] = formula
                    entry["thermodynamics"]["dG_chemistry"] = float(dG_chem.value.magnitude)
                    entry["thermodynamics"]["dG_membrane"] = dG_membrane
                    entry["thermodynamics"]["dG_per_proton"] = dG_per_proton
                    entry["thermodynamics"]["inner_pH"] = inner_pH
                    entry["thermodynamics"]["outer_pH"] = outer_pH
                    entry["thermodynamics"]["membrane_potential_mV"] = potential_mV
                    entry["thermodynamics"]["vectorial_protons"] = n_vectorial
                    entry["thermodynamics"]["proton_stoichiometry"] = proton_compartments
                    reactions[rxn.id] = entry
                    continue
                    
                except Exception as e:
                    errors.append({
                        "type": "proton_pump_error",
                        "message": str(e),
                        "inner_formula": inner_formula,
                        "outer_formula": outer_formula
                    })
                    # Fall through to standard calculation
            else:
                use_multicompartmental = True
        
        if use_multicompartmental:
            entry["thermodynamics"]["formula_queried"] = f"multicompartmental: inner({inner_comp})=[{inner_formula}], outer({outer_comp})=[{outer_formula}]"
            entry["thermodynamics"]["method"] = "multicompartmental"
            entry["thermodynamics"]["membrane"] = membrane_key
            entry["thermodynamics"]["inner_compartment"] = inner_comp
            entry["thermodynamics"]["outer_compartment"] = outer_comp
            entry["thermodynamics"]["proton_stoichiometry"] = proton_compartments
            
            try:
                # Set inner compartment pH
                inner_pH = compartments.get(inner_comp, {}).get("pH", 7.0)
                cc._p_h = Q_(inner_pH, "dimensionless")
                
                # Parse half-reactions
                reaction_inner = cc.parse_reaction_formula(inner_formula)
                reaction_outer = cc.parse_reaction_formula(outer_formula)
                
                # Get membrane potential (convert mV to V)
                potential_mV = membrane.get("potential_mV", 0)
                potential = Q_(potential_mV / 1000.0, "V")
                
                # Get outer compartment conditions
                outer_pH = compartments.get(outer_comp, {}).get("pH", 7.0)
                ionic_strength = Q_(compartment_params.get("default_conditions", {}).get("ionic_strength", 0.1), "M")
                
                dG = cc.multicompartmental_standard_dg_prime(
                    reaction_inner,
                    reaction_outer,
                    potential,
                    Q_(outer_pH, "dimensionless"),
                    ionic_strength
                )
                
                entry["thermodynamics"]["dG_prime"] = float(dG.value.magnitude)
                entry["thermodynamics"]["uncertainty"] = float(dG.error.magnitude)
                entry["thermodynamics"]["inner_pH"] = inner_pH
                entry["thermodynamics"]["outer_pH"] = outer_pH
                entry["thermodynamics"]["membrane_potential_mV"] = potential_mV
                
            except Exception as e:
                errors.append({
                    "type": "multicompartmental_error",
                    "message": str(e)
                })
                # Fall back to standard calculation
                entry["thermodynamics"]["method"] = "standard (fallback)"
                try:
                    formula = stoich_to_formula(stoichiometry)
                    entry["thermodynamics"]["formula_queried"] = formula
                    parsed = cc.parse_reaction_formula(formula)
                    dG = cc.standard_dg_prime(parsed)
                    entry["thermodynamics"]["dG_prime"] = float(dG.value.magnitude)
                    entry["thermodynamics"]["uncertainty"] = float(dG.error.magnitude)
                except Exception as e2:
                    errors.append({
                        "type": "equilibrator_error",
                        "message": str(e2)
                    })
        else:
            # Standard calculation (non-transmembrane or no compartment params)
            subs, prods = [], []
            for query_id, coef in stoichiometry.items():
                term = f"{abs(coef)} {query_id}" if abs(coef) != 1 else query_id
                (subs if coef < 0 else prods).append(term)
            
            formula = " + ".join(subs) + " = " + " + ".join(prods)
            entry["thermodynamics"]["formula_queried"] = formula
            entry["thermodynamics"]["method"] = "standard"
            
            try:
                parsed = cc.parse_reaction_formula(formula)
                dG = cc.standard_dg_prime(parsed)
                entry["thermodynamics"]["dG_prime"] = float(dG.value.magnitude)
                entry["thermodynamics"]["uncertainty"] = float(dG.error.magnitude)
            except Exception as e:
                errors.append({
                    "type": "equilibrator_error",
                    "message": str(e)
                })
        
        reactions[rxn.id] = entry
    
    with open(output_path, 'w') as f:
        json.dump(reactions, f, indent=2)
    
    # Summary
    valid = sum(1 for r in reactions.values() 
                if r["thermodynamics"]["dG_prime"] is not None 
                and r["thermodynamics"].get("uncertainty", float('inf')) < 1000)
    high_uncertainty = sum(1 for r in reactions.values() 
                          if r["thermodynamics"].get("uncertainty") is not None 
                          and r["thermodynamics"]["uncertainty"] >= 1000)
    transport = sum(1 for r in reactions.values()
                    if r["thermodynamics"]["formula_queried"] == "transport (no net reaction)")
    multicompartmental = sum(1 for r in reactions.values()
                              if r["thermodynamics"].get("method") == "multicompartmental")
    proton_pump = sum(1 for r in reactions.values()
                      if r["thermodynamics"].get("method") == "proton_pump")
    redox_carrier = sum(1 for r in reactions.values()
                        if r["thermodynamics"].get("method") == "redox_carrier")
    not_in_cache = sum(1 for r in reactions.values() 
                       if any(e["type"] == "metabolite_not_in_cache" for e in r["errors"]))
    not_found = sum(1 for r in reactions.values() 
                    if any(e["type"] == "not_found_in_equilibrator" for e in r["errors"]))
    eq_errors = sum(1 for r in reactions.values() 
                    if any(e["type"] == "equilibrator_error" for e in r["errors"]))
    multi_errors = sum(1 for r in reactions.values() 
                       if any(e["type"] == "multicompartmental_error" for e in r["errors"]))
    proton_pump_errors = sum(1 for r in reactions.values() 
                              if any(e["type"] == "proton_pump_error" for e in r["errors"]))
    redox_errors = sum(1 for r in reactions.values() 
                       if any(e["type"] == "redox_carrier_error" for e in r["errors"]))
    
    print(f"\nSaved {len(reactions)} reactions to {output_path}")
    print(f"  Valid (uncertainty < 1000): {valid}")
    print(f"  High uncertainty (>= 1000): {high_uncertainty}")
    print(f"  Transport (dG'° = 0): {transport}")
    print(f"  Multicompartmental (H+ transport): {multicompartmental}")
    print(f"  Proton pump (manual membrane calc): {proton_pump}")
    print(f"  Redox carrier (metalloproteins): {redox_carrier}")
    print(f"  Metabolite not in cache: {not_in_cache}")
    print(f"  Not found in eQuilibrator: {not_found}")
    print(f"  eQuilibrator errors: {eq_errors}")
    print(f"  Multicompartmental errors: {multi_errors}")
    print(f"  Proton pump errors: {proton_pump_errors}")
    print(f"  Redox carrier errors: {redox_errors}")


if __name__ == "__main__":
    main()
