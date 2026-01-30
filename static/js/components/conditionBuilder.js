/* ATACFlux - Constraint Builder Component */

const ConstraintBuilder = {
    container: null,
    constraints: {},
    presets: {},
    compartments: [],
    searchTimeout: null,
    editingId: null,
    selectedTarget: null,
    selectedReaction: null,
    searchResults: [],
    
    init(containerId) {
        this.container = document.getElementById(containerId);
        this.load();
        this.loadCompartments();
    },
    
    async load() {
        try {
            const data = await API.getConstraints();
            this.constraints = data.constraints || {};
            this.presets = data.presets || {};
            this.render();
        } catch (e) {
            console.error('Failed to load constraints:', e);
        }
    },
    
    async loadCompartments() {
        try {
            const data = await API.getCompartments();
            this.compartments = data.compartments || [];
        } catch (e) {
            console.error('Failed to load compartments:', e);
        }
    },
    
    render() {
        if (!this.container) return;
        
        const constraintList = Object.entries(this.constraints).map(([id, c]) => `
            <div class="constraint-item ${c.enabled ? '' : 'disabled'}">
                <label class="constraint-toggle">
                    <input type="checkbox" ${c.enabled ? 'checked' : ''} 
                           onchange="ConstraintBuilder.toggle('${id}', this.checked)">
                </label>
                <span class="constraint-label" title="${c.target}" onclick="ConstraintBuilder.edit('${id}')">${c.label}</span>
                <button class="constraint-edit" onclick="ConstraintBuilder.edit('${id}')" title="Edit">✎</button>
                <button class="constraint-remove" onclick="ConstraintBuilder.remove('${id}')" title="Remove">×</button>
            </div>
        `).join('');
        
        // Presets now have description and are annotation-derived
        const presetButtons = Object.entries(this.presets).map(([key, preset]) => `
            <button class="btn-preset" onclick="ConstraintBuilder.applyPreset('${key}')" 
                    title="${preset.description || ''}\nTarget: ${preset.constraint?.target || 'auto-discovered'}">
                ${preset.label}
            </button>
        `).join('');
        
        this.container.innerHTML = `
            <div class="constraints-active">
                ${constraintList || '<p class="constraints-empty">No conditions set</p>'}
            </div>
            
            <div class="constraint-add">
                <button class="btn secondary btn-small" onclick="ConstraintBuilder.showAddModal()">
                    + Add Condition
                </button>
            </div>
            
            ${Object.keys(this.presets).length > 0 ? `
                <div class="constraint-presets">
                    <h4>Quick Presets (auto-discovered)</h4>
                    ${presetButtons}
                </div>
            ` : ''}
        `;
    },
    
    async toggle(id, enabled) {
        const data = await API.toggleConstraint(id, enabled);
        if (data.success) {
            this.constraints = data.constraints;
            this.render();
        }
    },
    
    async remove(id) {
        const data = await API.removeConstraint(id);
        if (data.success) {
            this.constraints = data.constraints;
            this.render();
        }
    },
    
    async applyPreset(presetName) {
        const data = await API.applyPreset(presetName);
        if (data.success) {
            this.constraints = data.constraints;
            this.render();
        }
    },
    
    async clearAll() {
        const data = await API.clearConstraints();
        if (data.success) {
            this.constraints = {};
            this.render();
        }
    },
    
    edit(id) {
        const constraint = this.constraints[id];
        if (!constraint) return;
        
        this.editingId = id;
        this.showAddModal();
        
        // Wait for modal to render, then populate
        setTimeout(() => {
            // Set type
            const typeSelect = document.getElementById('constraint-type');
            typeSelect.value = constraint.type;
            this.onTypeChange();
            
            // Set selected target info
            if (constraint.targetInfo) {
                this.selectedTarget = constraint.targetInfo;
            } else {
                // Fallback: create minimal target info
                this.selectedTarget = {
                    id: constraint.target,
                    name: constraint.label.split(':')[0] || constraint.target,
                    exchange_reaction: constraint.type === 'exchange' ? constraint.target : null
                };
            }
            
            // Show selected target
            const targetInfo = document.getElementById('selected-target-info');
            targetInfo.innerHTML = `
                <strong>${this.selectedTarget.id}</strong>: ${this.selectedTarget.name}
                <br><small>Target: ${constraint.target}</small>
            `;
            document.getElementById('selected-target').style.display = 'block';
            
            // Set bound type and value
            const boundType = constraint.boundType || this.inferBoundType(constraint.bounds);
            document.getElementById('constraint-bound-type').value = boundType;
            this.onBoundTypeChange();
            
            if (boundType === 'fixed') {
                document.getElementById('constraint-value').value = constraint.bounds[0];
            } else if (boundType === 'max') {
                document.getElementById('constraint-value').value = constraint.bounds[1];
            } else if (boundType === 'min') {
                document.getElementById('constraint-value').value = constraint.bounds[0];
            } else {
                document.getElementById('constraint-min').value = constraint.bounds[0];
                document.getElementById('constraint-max').value = constraint.bounds[1];
            }
            
            // Set label
            const labelPart = constraint.label.split(':')[0] || '';
            document.getElementById('constraint-label').value = labelPart.trim();
        }, 50);
    },
    
    inferBoundType(bounds) {
        if (bounds[0] === bounds[1]) return 'fixed';
        if (bounds[0] === -1000 || bounds[0] <= -999) return 'max';
        if (bounds[1] === 1000 || bounds[1] >= 999) return 'min';
        return 'range';
    },
    
    showAddModal() {
        // Reset state for new constraint (edit() will set these after)
        if (!this.editingId) {
            this.selectedTarget = null;
            this.selectedReaction = null;
        }
        
        // Create modal overlay
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.id = 'constraint-modal';
        modal.innerHTML = `
            <div class="modal">
                <div class="modal-header">
                    <h3>${this.editingId ? 'Edit Condition' : 'Add Condition'}</h3>
                    <button class="modal-close" onclick="ConstraintBuilder.closeModal()">×</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label>Type</label>
                        <select id="constraint-type" onchange="ConstraintBuilder.onTypeChange()">
                            <option value="reaction">Reaction</option>
                            <option value="exchange">Metabolite</option>
                        </select>
                    </div>
                    
                    <div class="form-row">
                        <div class="form-group form-group-grow">
                            <label>Search</label>
                            <input type="text" id="constraint-search" 
                                   placeholder="Type to search..." 
                                   oninput="ConstraintBuilder.onSearch()">
                        </div>
                        <div class="form-group" id="compartment-filter-group">
                            <label>Compartment</label>
                            <select id="compartment-filter" onchange="ConstraintBuilder.onSearch()">
                                <option value="">All</option>
                                ${this.compartments.map(c => 
                                    `<option value="${c.id}">${c.name} [${c.id}] (${c.metabolite_count})</option>`
                                ).join('')}
                            </select>
                        </div>
                    </div>
                    
                    <div class="search-results" id="constraint-search-results"></div>
                    
                    <div class="form-group" id="selected-target" style="display:none">
                        <label>Selected</label>
                        <div class="selected-target-info" id="selected-target-info"></div>
                    </div>
                    
                    <div class="form-group">
                        <label>Bound Type</label>
                        <select id="constraint-bound-type" onchange="ConstraintBuilder.onBoundTypeChange()">
                            <option value="fixed">Fixed value (=)</option>
                            <option value="max">Maximum (≤)</option>
                            <option value="min">Minimum (≥)</option>
                            <option value="range">Range</option>
                        </select>
                    </div>
                    
                    <div class="form-group" id="bound-value-group">
                        <label>Value</label>
                        <input type="number" id="constraint-value" value="0" step="0.1">
                    </div>
                    
                    <div class="form-group" id="bound-range-group" style="display:none">
                        <label>Range</label>
                        <div class="range-inputs">
                            <input type="number" id="constraint-min" value="0" step="0.1" placeholder="Min">
                            <span>to</span>
                            <input type="number" id="constraint-max" value="0" step="0.1" placeholder="Max">
                        </div>
                    </div>
                    
                    <div class="form-group">
                        <label>Label (optional)</label>
                        <input type="text" id="constraint-label" placeholder="e.g., Anaerobic">
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn secondary" onclick="ConstraintBuilder.closeModal()">Cancel</button>
                    <button class="btn" onclick="ConstraintBuilder.saveConstraint()">${this.editingId ? 'Update' : 'Add'}</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        
        // Store selected target
        this.selectedTarget = null;
    },
    
    closeModal() {
        const modal = document.getElementById('constraint-modal');
        if (modal) modal.remove();
        this.selectedTarget = null;
        this.selectedReaction = null;
        this.editingId = null;
    },
    
    onTypeChange() {
        // Clear search when type changes
        document.getElementById('constraint-search').value = '';
        document.getElementById('constraint-search-results').innerHTML = '';
        document.getElementById('selected-target').style.display = 'none';
        this.selectedTarget = null;
        this.selectedReaction = null;
        
        // Show compartment filter for both types
        document.getElementById('compartment-filter-group').style.display = 'block';
    },
    
    onBoundTypeChange() {
        const boundType = document.getElementById('constraint-bound-type').value;
        const valueGroup = document.getElementById('bound-value-group');
        const rangeGroup = document.getElementById('bound-range-group');
        
        if (boundType === 'range') {
            valueGroup.style.display = 'none';
            rangeGroup.style.display = 'block';
        } else {
            valueGroup.style.display = 'block';
            rangeGroup.style.display = 'none';
        }
    },
    
    onSearch() {
        clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => this.doSearch(), 300);
    },
    
    async doSearch() {
        const query = document.getElementById('constraint-search').value;
        const type = document.getElementById('constraint-type').value;
        const resultsContainer = document.getElementById('constraint-search-results');
        
        if (query.length < 2) {
            resultsContainer.innerHTML = '';
            return;
        }
        
        try {
            let data;
            const compartment = document.getElementById('compartment-filter').value;
            
            if (type === 'reaction') {
                data = await API.searchReactions(query, compartment);
                if (data.results && data.results.length > 0) {
                    this.searchResults = data.results;
                    let html = '<div class="reaction-select-list">';
                    data.results.forEach((r, idx) => {
                        html += this._renderReactionItem(r, { 
                            radio: true, 
                            radioName: 'selected-reaction',
                            radioIdx: idx,
                            checked: idx === 0,
                            onchange: `ConstraintBuilder.selectReactionFromSearch(${idx})`
                        });
                    });
                    html += '</div>';
                    resultsContainer.innerHTML = html;
                    
                    // Auto-select first
                    this.selectReactionFromSearch(0);
                } else {
                    resultsContainer.innerHTML = '<div class="search-no-results">No results</div>';
                }
            } else {
                // Metabolite search
                data = await API.searchMetabolites(query, compartment);
                
                if (data.results && data.results.length > 0) {
                    resultsContainer.innerHTML = data.results.map(r => {
                        const hasExchange = r.reactions && r.reactions.some(rx => rx.is_exchange);
                        
                        return `
                            <div class="search-result-item ${hasExchange ? 'has-exchange' : 'no-exchange'}" 
                                 onclick="ConstraintBuilder.selectMetabolite(${JSON.stringify(r).replace(/"/g, '&quot;')})">
                                <span class="result-id">${r.id}</span>
                                <span class="result-compartment" title="${r.compartment_name}">[${r.compartment}]</span>
                                <span class="result-name">${r.name}</span>
                                <span class="result-rxn-count">${r.reaction_count} rxns</span>
                            </div>
                        `;
                    }).join('');
                } else {
                    resultsContainer.innerHTML = '<div class="search-no-results">No results</div>';
                }
            }
        } catch (e) {
            resultsContainer.innerHTML = '<div class="search-no-results">Search error</div>';
        }
    },
    
    selectMetabolite(metabolite) {
        // Show metabolite info and list of reactions to choose from
        this.selectedTarget = metabolite;
        document.getElementById('constraint-search-results').innerHTML = '';
        document.getElementById('constraint-search').value = '';
        
        const targetInfo = document.getElementById('selected-target-info');
        
        let html = `<strong>${metabolite.id}</strong>: ${metabolite.name}`;
        html += `<br><small>Compartment: ${metabolite.compartment_name}</small>`;
        html += `<br><br><strong>Select reaction to constrain:</strong>`;
        html += `<div class="reaction-select-list">`;
        
        metabolite.reactions.forEach((rxn, idx) => {
            html += this._renderReactionItem(rxn, { 
                radio: true, 
                radioName: 'selected-reaction',
                radioIdx: idx,
                checked: idx === 0
            });
        });
        
        html += `</div>`;
        
        targetInfo.innerHTML = html;
        document.getElementById('selected-target').style.display = 'block';
        
        // Auto-select first reaction
        this.selectedReaction = metabolite.reactions[0];
        
        // Pre-fill label
        if (!document.getElementById('constraint-label').value) {
            document.getElementById('constraint-label').value = metabolite.name;
        }
    },
    
    selectReaction(idx) {
        this.selectedReaction = this.selectedTarget.reactions[idx];
    },
    
    selectReactionFromSearch(idx) {
        // For direct reaction search - reaction IS the target
        this.selectedTarget = this.searchResults[idx];
        this.selectedReaction = this.searchResults[idx];
        
        // Pre-fill label if empty
        if (!document.getElementById('constraint-label').value) {
            document.getElementById('constraint-label').value = this.selectedTarget.name;
        }
    },
    
    // Shared reaction item renderer
    _renderReactionItem(rxn, opts = {}) {
        const desc = rxn.description || rxn.location || '';
        const bounds = rxn.bounds ? `[${rxn.bounds.join(', ')}]` : '';
        const equation = rxn.equation || '';
        
        if (opts.radio) {
            const onchange = opts.onchange || `ConstraintBuilder.selectReaction(${opts.radioIdx})`;
            return `
                <label class="reaction-select-item">
                    <input type="radio" name="${opts.radioName}" value="${opts.radioIdx}" 
                           onchange="${onchange}"
                           ${opts.checked ? 'checked' : ''}>
                    <span class="rxn-select-id">${rxn.id}</span>
                    <span class="rxn-select-desc">${desc}</span>
                    <span class="rxn-select-bounds">${bounds}</span>
                </label>
                <div class="rxn-select-equation">${equation}</div>
            `;
        } else {
            // Clickable version (fallback)
            return `
                <div class="reaction-select-item clickable" onclick="${opts.onclick}">
                    <span></span>
                    <span class="rxn-select-id">${rxn.id}</span>
                    <span class="rxn-select-desc">${desc}</span>
                    <span class="rxn-select-bounds">${bounds}</span>
                </div>
                <div class="rxn-select-equation">${equation}</div>
            `;
        }
    },
    
    // For direct reaction selection (type = reaction)
    selectTarget(target) {
        this.selectedTarget = target;
        this.selectedReaction = null;  // Not used for direct reactions
        document.getElementById('constraint-search-results').innerHTML = '';
        document.getElementById('constraint-search').value = '';
        
        const targetInfo = document.getElementById('selected-target-info');
        
        // Location label based on type
        const locationLabel = target.location_type === 'compartments' ? 'Compartments' : 'Compartment';
        
        let html = `<strong>${target.id}</strong>: ${target.name}`;
        html += `<br><small>${locationLabel}: ${target.location}</small>`;
        
        if (target.bounds) {
            html += `<br><small>Bounds: [${target.bounds.join(', ')}]</small>`;
        }
        
        if (target.equation) {
            html += `<div class="selected-equation">${target.equation}</div>`;
        }
        
        targetInfo.innerHTML = html;
        document.getElementById('selected-target').style.display = 'block';
        
        // Pre-fill label
        if (!document.getElementById('constraint-label').value) {
            document.getElementById('constraint-label').value = target.name;
        }
    },
    
    async saveConstraint() {
        const type = document.getElementById('constraint-type').value;
        
        // For metabolite type, need selected reaction
        if (type === 'exchange') {
            if (!this.selectedTarget || !this.selectedReaction) {
                alert('Please select a metabolite and reaction');
                return;
            }
        } else {
            if (!this.selectedTarget) {
                alert('Please select a reaction');
                return;
            }
        }
        
        const boundType = document.getElementById('constraint-bound-type').value;
        const label = document.getElementById('constraint-label').value || this.selectedTarget.name;
        
        let bounds;
        let boundLabel;
        
        if (boundType === 'fixed') {
            const val = parseFloat(document.getElementById('constraint-value').value);
            bounds = [val, val];
            boundLabel = `= ${val}`;
        } else if (boundType === 'max') {
            const val = parseFloat(document.getElementById('constraint-value').value);
            bounds = [-1000, val];
            boundLabel = `≤ ${val}`;
        } else if (boundType === 'min') {
            const val = parseFloat(document.getElementById('constraint-value').value);
            bounds = [val, 1000];
            boundLabel = `≥ ${val}`;
        } else {
            const min = parseFloat(document.getElementById('constraint-min').value);
            const max = parseFloat(document.getElementById('constraint-max').value);
            bounds = [min, max];
            boundLabel = `[${min}, ${max}]`;
        }
        
        // Determine target reaction ID
        let targetId;
        if (type === 'exchange') {
            targetId = this.selectedReaction.id;
        } else {
            targetId = this.selectedTarget.id;
        }
        
        // Generate unique ID (or use existing if editing)
        const id = this.editingId || `${type}_${targetId}_${Date.now()}`;
        
        const constraint = {
            id,
            type: 'reaction',  // Always constrain reactions now
            target: targetId,
            bounds,
            label: `${label}: ${boundLabel}`,
            boundType,  // Store for editing
            targetInfo: this.selectedTarget,  // Store for editing
            selectedReaction: this.selectedReaction
        };
        
        const data = await API.addConstraint(constraint);
        if (data.success) {
            this.constraints = data.constraints;
            this.closeModal();
            this.render();
        } else {
            alert('Failed to add constraint: ' + (data.error || 'Unknown error'));
        }
    }
};
