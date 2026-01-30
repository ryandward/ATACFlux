"""ATACFlux - Flask routes."""

from flask import Flask, render_template, jsonify, request

from data_access import thermo, cobra_model, constraints, annotations
from services import pathway, colors

app = Flask(__name__, template_folder='../templates', static_folder='../static')

# Load data on startup
thermo.load()

# ============ Pages ============

@app.route('/')
def index():
    return render_template('index.html')


# ============ Model API ============

@app.route('/api/load_model', methods=['POST'])
def load_model():
    success = cobra_model.load()
    if success:
        info = cobra_model.info()
        return jsonify({'success': True, **info})
    return jsonify({'success': False, 'error': 'Model not found. Place yeast-GEM.xml in models/'})


@app.route('/api/model_info')
def model_info():
    info = cobra_model.info()
    if info:
        return jsonify({'loaded': True, **info})
    return jsonify({'loaded': False})


@app.route('/api/compartments')
def get_compartments():
    """Get compartments from the model with colors."""
    if not cobra_model.is_loaded():
        return jsonify({'error': 'No model loaded'})
    
    model = cobra_model.get_model()
    compartments = []
    for comp_id, comp_name in model.compartments.items():
        count = len([m for m in model.metabolites if m.compartment == comp_id])
        compartments.append({
            'id': comp_id,
            'name': comp_name,
            'metabolite_count': count
        })
    
    # Sort by metabolite count (most populated first)
    compartments.sort(key=lambda x: -x['metabolite_count'])
    
    # Assign colors
    comp_ids = [c['id'] for c in compartments]
    color_map = colors.assign(comp_ids)
    for comp in compartments:
        comp['color'] = color_map[comp['id']]
    
    return jsonify({'compartments': compartments})


@app.route('/api/optimize', methods=['POST'])
def optimize():
    if not cobra_model.is_loaded():
        return jsonify({'success': False, 'error': 'No model loaded'})
    
    try:
        model = cobra_model.get_model()
        
        # Reset to original bounds first
        cobra_model.reset_bounds()
        
        # Then apply active constraints
        constraint_results = constraints.apply_to_model(model)
        
        solution = cobra_model.optimize()
        return jsonify({
            'success': True,
            'status': solution.status,
            'objective_value': solution.objective_value,
            'constraints_applied': constraint_results
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============ Reactions API ============

@app.route('/api/reactions')
def list_reactions():
    if not cobra_model.is_loaded():
        return jsonify({'error': 'No model loaded'})
    
    query = request.args.get('q', '')
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))
    nonzero_flux = request.args.get('nonzero_flux', 'false').lower() == 'true'
    
    reactions, total = cobra_model.list_reactions(query, limit, offset, nonzero_flux)
    
    return jsonify({
        'reactions': reactions,
        'total': total,
        'limit': limit,
        'offset': offset
    })


@app.route('/api/reaction/<rxn_id>')
def get_reaction(rxn_id):
    if not cobra_model.is_loaded():
        return jsonify({'error': 'No model loaded'})
    
    result = pathway.get_reaction_context(rxn_id)
    if result is None:
        return jsonify({'error': f'Reaction {rxn_id} not found'})
    
    return jsonify(result)


# ============ Thermodynamics API ============

@app.route('/api/thermo_status')
def thermo_status():
    stats = thermo.stats()
    return jsonify({
        'available': stats['loaded'] and stats['reactions_count'] > 0,
        **stats
    })


@app.route('/api/thermo_cache')
def get_thermo_cache():
    return jsonify({
        'success': True,
        'reactions': thermo.get_all_reactions()
    })


@app.route('/api/thermo/<rxn_id>')
def get_thermo(rxn_id):
    data = thermo.get_reaction(rxn_id)
    if data:
        return jsonify(data)
    return jsonify({'error': f'No thermo data for {rxn_id}'})


# ============ Pathway API ============

@app.route('/api/metabolite/<met_id>')
def get_metabolite(met_id):
    if not cobra_model.is_loaded():
        return jsonify({'error': 'No model loaded'})
    
    result = pathway.get_metabolite_context(met_id)
    if result is None:
        return jsonify({'error': f'Metabolite {met_id} not found'})
    
    return jsonify(result)


@app.route('/api/subsystems')
def list_subsystems():
    if not cobra_model.is_loaded():
        return jsonify({'error': 'No model loaded'})
    
    return jsonify({'subsystems': cobra_model.list_subsystems()})


@app.route('/api/subsystem/<path:subsystem_name>')
def get_subsystem(subsystem_name):
    if not cobra_model.is_loaded():
        return jsonify({'error': 'No model loaded'})
    
    result = pathway.get_subsystem_reactions(subsystem_name)
    if result is None:
        return jsonify({'error': f'Subsystem {subsystem_name} not found'})
    
    return jsonify(result)


# ============ Constraints API ============

@app.route('/api/constraints')
def list_constraints():
    """List all constraints and available presets."""
    presets = {}
    if cobra_model.is_loaded():
        # Get available presets by querying model annotations
        presets = constraints.get_available_presets(cobra_model.get_model())
    
    return jsonify({
        'constraints': constraints.list_all(),
        'presets': presets
    })


@app.route('/api/constraints', methods=['POST'])
def add_constraint():
    """Add a new constraint."""
    data = request.get_json()
    
    constraint_id = data.get('id')
    constraint_type = data.get('type')  # 'reaction' or 'exchange'
    target = data.get('target')
    bounds = data.get('bounds')
    label = data.get('label')
    bound_type = data.get('boundType')
    target_info = data.get('targetInfo')
    
    if not all([constraint_id, constraint_type, target, bounds is not None]):
        return jsonify({'success': False, 'error': 'Missing required fields'})
    
    constraints.add(constraint_id, constraint_type, target, bounds, label, bound_type, target_info)
    return jsonify({'success': True, 'constraints': constraints.list_all()})


@app.route('/api/constraints/<constraint_id>', methods=['DELETE'])
def remove_constraint(constraint_id):
    """Remove a constraint."""
    success = constraints.remove(constraint_id)
    return jsonify({'success': success, 'constraints': constraints.list_all()})


@app.route('/api/constraints/<constraint_id>/toggle', methods=['POST'])
def toggle_constraint(constraint_id):
    """Toggle a constraint on/off."""
    data = request.get_json() or {}
    enabled = data.get('enabled')
    success = constraints.toggle(constraint_id, enabled)
    return jsonify({'success': success, 'constraints': constraints.list_all()})


@app.route('/api/constraints/preset/<preset_name>', methods=['POST'])
def apply_preset(preset_name):
    """Apply a preset condition (discovered via annotation lookup)."""
    if not cobra_model.is_loaded():
        return jsonify({'success': False, 'error': 'No model loaded'})
    
    result = constraints.apply_preset(cobra_model.get_model(), preset_name)
    
    if result['success']:
        return jsonify({
            'success': True,
            'constraints': constraints.list_all(),
            'applied': result.get('constraint'),
            'derived_from': result.get('derived_from')
        })
    return jsonify(result)


@app.route('/api/constraints/clear', methods=['POST'])
def clear_constraints():
    """Clear all constraints."""
    constraints.clear()
    return jsonify({'success': True, 'constraints': {}})


@app.route('/api/search/reactions')
def search_reactions_for_constraint():
    """Search reactions for constraint builder."""
    if not cobra_model.is_loaded():
        return jsonify({'error': 'No model loaded'})
    
    query = request.args.get('q', '').lower()
    compartment = request.args.get('compartment', '')
    limit = int(request.args.get('limit', 20))
    
    results = []
    model = cobra_model.get_model()
    compartment_names = model.compartments
    
    for rxn in model.reactions:
        # Filter by compartment if specified (reaction has any metabolite in that compartment)
        if compartment:
            rxn_compartments = set(m.compartment for m in rxn.metabolites.keys())
            if compartment not in rxn_compartments:
                continue
        
        if query in rxn.id.lower() or query in rxn.name.lower():
            info = cobra_model.build_reaction_info(rxn, compartment_names)
            
            results.append({
                'id': rxn.id,
                'name': rxn.name,
                'bounds': list(rxn.bounds),
                **info
            })
            if len(results) >= limit:
                break
    
    return jsonify({'results': results})


@app.route('/api/search/metabolites')
def search_metabolites_for_constraint():
    """Search metabolites for constraint builder."""
    if not cobra_model.is_loaded():
        return jsonify({'error': 'No model loaded'})
    
    query = request.args.get('q', '').lower()
    compartment = request.args.get('compartment', '')
    limit = int(request.args.get('limit', 20))
    
    results = []
    model = cobra_model.get_model()
    compartment_names = model.compartments  # dict of id -> name
    
    for met in model.metabolites:
        # Filter by compartment if specified
        if compartment and met.compartment != compartment:
            continue
            
        if query in met.id.lower() or query in met.name.lower():
            # Get ALL reactions this metabolite participates in
            reactions = []
            for rxn in met.reactions:
                info = cobra_model.build_metabolite_reaction_info(rxn, met, compartment_names)
                
                reactions.append({
                    'id': rxn.id,
                    'name': rxn.name,
                    'bounds': list(rxn.bounds),
                    **info
                })
            
            # Sort: exchange reactions first
            reactions.sort(key=lambda x: (0 if x['is_exchange'] else 1, x['id']))
            
            results.append({
                'id': met.id,
                'name': met.name,
                'compartment': met.compartment,
                'compartment_name': compartment_names.get(met.compartment, met.compartment),
                'reactions': reactions,
                'reaction_count': len(reactions)
            })
            if len(results) >= limit:
                break
    
    # Sort: metabolites with exchange reactions first, then by reaction count
    def has_exchange(x):
        return any(r['is_exchange'] for r in x['reactions'])
    results.sort(key=lambda x: (0 if has_exchange(x) else 1, x['reaction_count'], x['id']))
    
    return jsonify({'results': results})


@app.route('/api/search/by_annotation')
def search_by_annotation():
    """
    Search metabolites by database ID (KEGG, ChEBI, etc.).
    Data-driven: uses annotation lookup.
    """
    if not cobra_model.is_loaded():
        return jsonify({'error': 'No model loaded'})
    
    query = request.args.get('q', '')
    
    if not query:
        return jsonify({'error': 'Query required'})
    
    model = cobra_model.get_model()
    result = annotations.find_exchange_by_query(model, query)
    
    return jsonify(result)


if __name__ == '__main__':
    app.run(debug=True, port=5000)
