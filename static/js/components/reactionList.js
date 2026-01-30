/* ATACFlux - Reaction List Component */

const ReactionList = {
    container: null,
    compartmentColors: {},  // Loaded from API
    
    init(containerId) {
        this.container = document.getElementById(containerId);
    },
    
    setCompartmentColors(compartments) {
        // Build color map from compartments data
        this.compartmentColors = {};
        compartments.forEach(c => {
            this.compartmentColors[c.id] = c.color;
        });
    },
    
    _getCompartmentBadge(rxn) {
        const comps = [...new Set(rxn.compartments || [])];
        if (comps.length === 0) return '';
        
        // Same style for all - colored pills
        const badges = comps.slice(0, 2).map(c => {
            const color = this.compartmentColors[c] || '#888';
            return `<span class="rxn-comp-mini" style="background: ${color}">${c}</span>`;
        });
        
        if (comps.length === 1) {
            return `<span class="rxn-comp-single">${badges[0]}</span>`;
        } else {
            return `<span class="rxn-comp-multi">${badges.join('⇌')}</span>`;
        }
    },
    
    render(reactions, selectedId, thermoCache, onSelect) {
        if (!this.container) return;
        
        if (reactions.length === 0) {
            this.container.innerHTML = '<li class="loading">No reactions found</li>';
            return;
        }
        
        this.container.innerHTML = reactions.map(rxn => {
            // Flux display
            let fluxText = '';
            if (rxn.flux !== null && Math.abs(rxn.flux) > 1e-6) {
                const fluxClass = rxn.flux > 0 ? 'positive' : 'negative';
                fluxText = `<span class="rxn-flux ${fluxClass}">${rxn.flux.toFixed(2)}</span>`;
            } else {
                fluxText = `<span class="rxn-flux zero">—</span>`;
            }
            
            // Thermo badge
            let thermoHtml = '<span class="rxn-thermo unknown">—</span>';
            const thermo = thermoCache[rxn.id];
            if (thermo) {
                const t = thermo.thermodynamics;
                const isTransport = t.formula_queried === 'transport (no net reaction)';
                if (isTransport) {
                    thermoHtml = `<span class="rxn-thermo transport" title="Transport (ΔG'° depends on concentrations)">⇌</span>`;
                } else if (t.dG_prime !== null && t.uncertainty < 1000) {
                    const cls = Utils.getThermoClass(t.dG_prime, t.uncertainty);
                    thermoHtml = `<span class="rxn-thermo ${cls}" title="ΔG'° = ${t.dG_prime.toFixed(1)} kJ/mol">${t.dG_prime.toFixed(0)}</span>`;
                }
            }
            
            // Compartment badge
            const compBadge = this._getCompartmentBadge(rxn);
            
            return `
                <li class="rxn-item ${selectedId === rxn.id ? 'selected' : ''}" 
                    data-rxn-id="${rxn.id}"
                    data-has-flux="${rxn.flux !== null && Math.abs(rxn.flux) > 1e-6}">
                    ${fluxText}
                    ${thermoHtml}
                    ${compBadge}
                    <span class="rxn-id">${rxn.id}</span>
                    <span class="rxn-name" title="${rxn.name || 'Unnamed'}">${rxn.name || 'Unnamed'}</span>
                </li>
            `;
        }).join('');
        
        // Attach click handlers
        this.container.querySelectorAll('.rxn-item').forEach(el => {
            el.addEventListener('click', () => {
                const rxnId = el.dataset.rxnId;
                this.setSelected(rxnId);
                if (onSelect) onSelect(rxnId);
            });
        });
    },
    
    setSelected(rxnId) {
        this.container.querySelectorAll('.rxn-item').forEach(el => {
            el.classList.toggle('selected', el.dataset.rxnId === rxnId);
        });
    },
    
    showLoading() {
        if (this.container) {
            this.container.innerHTML = '<li class="loading">Loading...</li>';
        }
    },
    
    showError(message) {
        if (this.container) {
            this.container.innerHTML = `<li class="loading">Error: ${message}</li>`;
        }
    }
};
