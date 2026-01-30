/* ATACFlux - Reaction Detail Component */

const ReactionDetail = {
    container: null,
    thermoCache: {},
    
    init(containerId) {
        this.container = document.getElementById(containerId);
    },
    
    setThermoCache(cache) {
        this.thermoCache = cache;
    },
    
    render(rxn) {
        if (!this.container) return;
        
        // Location label based on type
        const locationLabel = rxn.location_type === 'compartments' ? 'Compartments' : 'Compartment';
        
        let html = `
            <div class="detail-section">
                <h3>${rxn.id}</h3>
                <p class="detail-name">${rxn.name || 'Unnamed'}</p>
            </div>
            
            <div class="detail-section">
                <div class="detail-location">
                    <span class="location-label">${locationLabel}:</span>
                    <span class="location-value">${rxn.location}</span>
                </div>
                <div class="detail-bounds">Bounds: [${rxn.lower_bound}, ${rxn.upper_bound}]</div>
                <div class="equation-box">${rxn.equation}</div>
            </div>
        `;
        
        // Flux if available
        if (rxn.flux !== undefined) {
            html += `
                <div class="detail-section">
                    <h3>Flux</h3>
                    <div class="stat-value">${this._formatFlux(rxn.flux)} <span class="stat-unit">mmol/gDW/h</span></div>
                </div>
            `;
        }
        
        // Thermodynamics
        html += this._renderThermo(rxn);
        
        // Metabolites (clickable for pathway tracing)
        if (rxn.metabolites && rxn.metabolites.length > 0) {
            html += this._renderMetabolites(rxn);
        }
        
        // Gene rule
        if (rxn.genes) {
            html += `
                <div class="detail-section">
                    <h3>Gene Rule</h3>
                    <div class="gene-rule">${rxn.genes}</div>
                </div>
            `;
        }
        
        // Subsystem
        if (rxn.subsystem) {
            html += `
                <div class="detail-section">
                    <h3>Subsystem</h3>
                    <p class="detail-text">${rxn.subsystem}</p>
                </div>
            `;
        }
        
        // EC numbers
        if (rxn.ec && rxn.ec.length) {
            html += `
                <div class="detail-section">
                    <h3>EC</h3>
                    <p class="detail-text">${rxn.ec.join(', ')}</p>
                </div>
            `;
        }
        
        this.container.innerHTML = html;
        
        // Attach metabolite click handlers
        this.container.querySelectorAll('.met-link').forEach(el => {
            el.addEventListener('click', (e) => {
                e.preventDefault();
                const metId = el.dataset.metId;
                if (window.App && window.App.showMetabolite) {
                    window.App.showMetabolite(metId);
                }
            });
        });
    },
    
    _renderThermo(rxn) {
        const thermo = this.thermoCache[rxn.id];
        if (!thermo) return '';
        
        const t = thermo.thermodynamics;
        
        if (t.formula_queried === 'transport (no net reaction)') {
            return `
                <div class="detail-section">
                    <h3>Thermodynamics</h3>
                    <div class="thermo-box">
                        <div class="thermo-value reversible">Transport</div>
                        <div class="thermo-label">ΔG'° = 0 (no net chemical change)</div>
                    </div>
                </div>
            `;
        }
        
        if (t.dG_prime !== null) {
            const dG = t.dG_prime;
            const cls = Utils.getThermoClass(dG, t.uncertainty);
            const desc = Utils.getThermoDescription(dG, t.uncertainty);
            
            return `
                <div class="detail-section">
                    <h3>Thermodynamics</h3>
                    <div class="thermo-box">
                        <div class="thermo-value ${cls}">${dG.toFixed(1)} kJ/mol</div>
                        <div class="thermo-label">ΔG'° ± ${t.uncertainty ? t.uncertainty.toFixed(1) : '?'}</div>
                        <div class="thermo-badge-container">
                            <span class="badge ${cls}">${desc}</span>
                        </div>
                    </div>
                </div>
            `;
        }
        
        if (thermo.errors && thermo.errors.length > 0) {
            const errorTypes = [...new Set(thermo.errors.map(e => e.type))].join(', ');
            return `
                <div class="detail-section">
                    <h3>Thermodynamics</h3>
                    <div class="status warn">Cannot calculate: ${errorTypes}</div>
                </div>
            `;
        }
        
        return '';
    },
    
    _renderMetabolites(rxn) {
        // Use pre-sorted substrates/products from API, or fallback to metabolites array
        const substrates = rxn.substrates || (rxn.metabolites || []).filter(m => m.coefficient < 0);
        const products = rxn.products || (rxn.metabolites || []).filter(m => m.coefficient >= 0);
        
        const renderList = (mets, title) => {
            if (mets.length === 0) return '';
            return `
                <div class="met-group">
                    <h4>${title}</h4>
                    ${mets.map(m => `
                        <a href="#" class="met-link" data-met-id="${m.id}">
                            <span class="met-coef">${Math.abs(m.coefficient)}</span>
                            <span class="met-name">${m.name}</span>
                            <span class="met-compartment" title="${m.compartment_name || m.compartment}">[${m.compartment}]</span>
                        </a>
                    `).join('')}
                </div>
            `;
        };
        
        return `
            <div class="detail-section">
                <h3>Metabolites</h3>
                <div class="metabolites-box">
                    ${renderList(substrates, 'Substrates')}
                    ${renderList(products, 'Products')}
                </div>
            </div>
        `;
    },
    
    showLoading() {
        if (this.container) {
            this.container.innerHTML = '<p class="loading">Loading...</p>';
        }
    },
    
    showPlaceholder() {
        if (this.container) {
            this.container.innerHTML = '<p class="loading">Select a reaction</p>';
        }
    },
    
    showError(message) {
        if (this.container) {
            this.container.innerHTML = `<p class="status error">${message}</p>`;
        }
    },
    
    _formatFlux(flux) {
        if (Math.abs(flux) < 1e-9) return '0';
        if (Math.abs(flux) < 0.01) return flux.toExponential(2);
        return flux.toFixed(3);
    }
};
