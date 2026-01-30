/* ATACFlux - Main Application */

const App = {
    // State
    state: {
        currentOffset: 0,
        pageSize: 50,
        totalReactions: 0,
        selectedRxn: null,
        thermoCache: {},
        viewingMetabolite: false,
        hideZeroFlux: false
    },
    
    // Initialize
    async init() {
        // Initialize components
        ReactionList.init('rxn-list');
        ReactionDetail.init('detail-content');
        PathwayTracer.init('detail-content');
        
        // Load thermo cache
        await this.loadThermoCache();
        this.checkThermoStatus();
    },
    
    // Model loading
    async loadModel() {
        const btn = document.getElementById('load-btn');
        const status = document.getElementById('load-status');
        
        btn.disabled = true;
        btn.textContent = 'Loading...';
        Utils.setStatus('load-status', 'info', 'Loading model...');
        
        try {
            const data = await API.loadModel();
            if (data.success) {
                Utils.setStatus('load-status', 'success', `Loaded ${data.path}`);
                document.getElementById('model-stats').classList.remove('hidden');
                document.getElementById('stat-reactions').textContent = data.reactions.toLocaleString();
                document.getElementById('stat-metabolites').textContent = data.metabolites.toLocaleString();
                document.getElementById('stat-genes').textContent = data.genes.toLocaleString();
                btn.textContent = 'Reload';
                
                // Load compartments and pass colors to ReactionList
                const compData = await API.getCompartments();
                if (compData.compartments) {
                    ReactionList.setCompartmentColors(compData.compartments);
                }
                
                this.loadReactions();
                this.checkThermoStatus();
                
                // Initialize constraint builder
                ConstraintBuilder.init('constraints-container');
            } else {
                Utils.setStatus('load-status', 'error', data.error);
                btn.textContent = 'Load yeast-GEM';
            }
        } catch (e) {
            Utils.setStatus('load-status', 'error', e.message);
            btn.textContent = 'Load yeast-GEM';
        }
        btn.disabled = false;
    },
    
    // FBA
    async runFBA() {
        Utils.setStatus('fba-status', 'info', 'Optimizing...');
        try {
            const data = await API.optimize();
            if (data.success) {
                Utils.setStatus('fba-status', 'success', `Growth: ${data.objective_value.toFixed(4)} h⁻¹`);
                this.loadReactions();
            } else {
                Utils.setStatus('fba-status', 'error', data.error);
            }
        } catch (e) {
            Utils.setStatus('fba-status', 'error', e.message);
        }
    },
    
    // Thermodynamics
    async checkThermoStatus() {
        try {
            const data = await API.getThermoStatus();
            const el = document.getElementById('thermo-status');
            if (data.available) {
                el.innerHTML = `<span class="status success">Cache: ${data.reactions_count} reactions</span>`;
            } else {
                el.innerHTML = `<span class="status warn">No thermo cache loaded</span>`;
            }
        } catch (e) {
            document.getElementById('thermo-status').innerHTML = `<span class="status error">Error</span>`;
        }
    },
    
    async loadThermoCache() {
        try {
            const data = await API.getThermoCache();
            if (data.success) {
                this.state.thermoCache = data.reactions;
                ReactionDetail.setThermoCache(data.reactions);
                PathwayTracer.setThermoCache(data.reactions);
            }
        } catch (e) {
            console.error('Failed to load thermo cache:', e);
        }
    },
    
    // Reactions list
    async loadReactions() {
        ReactionList.showLoading();
        const query = document.getElementById('rxn-search').value;
        
        try {
            const data = await API.getReactions(
                query, 
                this.state.pageSize, 
                this.state.currentOffset,
                this.state.hideZeroFlux
            );
            this.state.totalReactions = data.total;
            this.updatePagination();
            
            ReactionList.render(
                data.reactions,
                this.state.selectedRxn,
                this.state.thermoCache,
                (rxnId) => this.selectReaction(rxnId)
            );
        } catch (e) {
            ReactionList.showError(e.message);
        }
    },
    
    searchReactions() {
        this.state.currentOffset = 0;
        this.loadReactions();
    },
    
    updatePagination() {
        const { currentOffset, pageSize, totalReactions } = this.state;
        document.getElementById('page-info').textContent = 
            `${currentOffset + 1}-${Math.min(currentOffset + pageSize, totalReactions)} of ${totalReactions}`;
        document.getElementById('prev-btn').disabled = currentOffset === 0;
        document.getElementById('next-btn').disabled = currentOffset + pageSize >= totalReactions;
    },
    
    prevPage() {
        this.state.currentOffset = Math.max(0, this.state.currentOffset - this.state.pageSize);
        this.loadReactions();
    },
    
    nextPage() {
        this.state.currentOffset += this.state.pageSize;
        this.loadReactions();
    },
    
    // Reaction selection
    async selectReaction(rxnId) {
        this.state.selectedRxn = rxnId;
        this.state.viewingMetabolite = false;
        ReactionList.setSelected(rxnId);
        ReactionDetail.showLoading();
        
        try {
            const rxn = await API.getReaction(rxnId);
            if (rxn.error) {
                ReactionDetail.showError(rxn.error);
                return;
            }
            ReactionDetail.render(rxn);
        } catch (e) {
            ReactionDetail.showError(e.message);
        }
    },
    
    // Metabolite / pathway tracing
    async showMetabolite(metId) {
        this.state.viewingMetabolite = true;
        await PathwayTracer.show(metId);
    },
    
    clearMetabolite() {
        this.state.viewingMetabolite = false;
        if (this.state.selectedRxn) {
            this.selectReaction(this.state.selectedRxn);
        } else {
            ReactionDetail.showPlaceholder();
        }
    },
    
    toggleZeroFlux() {
        this.state.hideZeroFlux = document.getElementById('hide-zero-flux').checked;
        this.state.currentOffset = 0;  // Reset to page 1
        this.loadReactions();
    },
    
    applyFluxFilter() {
        // No longer needed - filtering is done server-side
    }
};

// Global functions for onclick handlers
function loadModel() { App.loadModel(); }
function runFBA() { App.runFBA(); }
function prevPage() { App.prevPage(); }
function nextPage() { App.nextPage(); }
function toggleZeroFlux() { App.toggleZeroFlux(); }
function searchReactions() { App.searchReactions(); }

// Expose App globally for component callbacks
window.App = App;

// Initialize on load
document.addEventListener('DOMContentLoaded', () => App.init());
