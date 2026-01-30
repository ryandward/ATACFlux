/* ATACFlux - Pathway Tracer Component */

const PathwayTracer = {
    container: null,
    thermoCache: {},
    
    init(containerId) {
        this.container = document.getElementById(containerId);
    },
    
    setThermoCache(cache) {
        this.thermoCache = cache;
    },
    
    async show(metId) {
        if (!this.container) return;
        
        this.container.innerHTML = '<p class="loading">Loading metabolite...</p>';
        
        try {
            const data = await API.getMetabolite(metId);
            if (data.error) {
                this.container.innerHTML = `<p class="status error">${data.error}</p>`;
                return;
            }
            this.render(data);
        } catch (e) {
            this.container.innerHTML = `<p class="status error">${e.message}</p>`;
        }
    },
    
    render(met) {
        const compartmentDisplay = met.compartment_name 
            ? `${met.compartment_name} [${met.compartment}]`
            : `[${met.compartment}]`;
            
        let html = `
            <div class="detail-section">
                <h3>${met.name}</h3>
                <p class="detail-subtitle">${met.id}</p>
                <p class="detail-text">Compartment: ${compartmentDisplay}</p>
                ${met.formula ? `<p class="detail-text">Formula: ${met.formula}</p>` : ''}
            </div>
        `;
        
        // Compound thermo
        if (met.thermo && met.thermo.dGf_prime !== null) {
            html += `
                <div class="detail-section">
                    <h3>Formation Energy</h3>
                    <div class="thermo-box">
                        <div class="thermo-value">${met.thermo.dGf_prime.toFixed(1)} kJ/mol</div>
                        <div class="thermo-label">ΔGf'° ± ${met.thermo.uncertainty ? met.thermo.uncertainty.toFixed(1) : '?'}</div>
                    </div>
                </div>
            `;
        }
        
        // Producing reactions
        html += this._renderReactionList(met.producing, 'Produced By', 'producing');
        
        // Consuming reactions
        html += this._renderReactionList(met.consuming, 'Consumed By', 'consuming');
        
        // Back button
        html += `
            <div class="detail-section">
                <button class="btn secondary" onclick="App.clearMetabolite()">← Back to Reaction</button>
            </div>
        `;
        
        this.container.innerHTML = html;
        
        // Attach reaction click handlers
        this.container.querySelectorAll('.pathway-rxn').forEach(el => {
            el.addEventListener('click', () => {
                const rxnId = el.dataset.rxnId;
                if (window.App && window.App.selectReaction) {
                    window.App.selectReaction(rxnId);
                }
            });
        });
    },
    
    _renderReactionList(reactions, title, className) {
        if (!reactions || reactions.length === 0) {
            return `
                <div class="detail-section">
                    <h3>${title}</h3>
                    <p class="detail-text muted">None</p>
                </div>
            `;
        }
        
        return `
            <div class="detail-section">
                <h3>${title} (${reactions.length})</h3>
                <div class="pathway-list ${className}">
                    ${reactions.map(rxn => this._renderReactionItem(rxn)).join('')}
                </div>
            </div>
        `;
    },
    
    _renderReactionItem(rxn) {
        // Thermo badge
        let thermoHtml = '';
        if (rxn.dG_prime !== null && rxn.dG_prime !== undefined) {
            const cls = Utils.getThermoClass(rxn.dG_prime, rxn.uncertainty);
            thermoHtml = `<span class="rxn-thermo ${cls}">${rxn.dG_prime.toFixed(0)}</span>`;
        } else if (rxn.formula_queried === 'transport (no net reaction)') {
            thermoHtml = `<span class="rxn-thermo transport">⇌</span>`;
        }
        
        // Flux badge
        let fluxHtml = '';
        if (rxn.flux !== null && rxn.flux !== undefined) {
            const cls = Utils.getFluxClass(rxn.flux);
            fluxHtml = `<span class="rxn-flux ${cls}">${rxn.flux.toFixed(3)}</span>`;
        }
        
        return `
            <div class="pathway-rxn" data-rxn-id="${rxn.id}">
                <div class="pathway-rxn-header">
                    ${fluxHtml}
                    ${thermoHtml}
                    <span class="rxn-id">${rxn.id}</span>
                    ${rxn.description ? `<span class="rxn-description">${rxn.description}</span>` : 
                      (rxn.location ? `<span class="rxn-location">${rxn.location}</span>` : '')}
                </div>
                <div class="pathway-rxn-name">${rxn.name || 'Unnamed'}</div>
                <div class="pathway-rxn-equation">${rxn.equation || rxn.equation_raw || ''}</div>
                ${rxn.genes ? `<div class="pathway-rxn-genes">${rxn.genes}</div>` : ''}
            </div>
        `;
    },
    
    hide() {
        if (this.container) {
            this.container.style.display = 'none';
        }
    },
    
    showContainer() {
        if (this.container) {
            this.container.style.display = 'block';
        }
    }
};
