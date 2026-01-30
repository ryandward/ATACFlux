/* ATACFlux - API Layer */

const API = {
    // Model
    async loadModel() {
        const response = await fetch('/api/load_model', { method: 'POST' });
        return response.json();
    },
    
    async getModelInfo() {
        const response = await fetch('/api/model_info');
        return response.json();
    },
    
    async getCompartments() {
        const response = await fetch('/api/compartments');
        return response.json();
    },
    
    async optimize() {
        const response = await fetch('/api/optimize', { method: 'POST' });
        return response.json();
    },
    
    // Reactions
    async getReactions(query = '', limit = 50, offset = 0, nonzeroFlux = false) {
        const response = await fetch(
            `/api/reactions?q=${encodeURIComponent(query)}&limit=${limit}&offset=${offset}&nonzero_flux=${nonzeroFlux}`
        );
        return response.json();
    },
    
    async getReaction(rxnId) {
        const response = await fetch(`/api/reaction/${rxnId}`);
        return response.json();
    },
    
    // Thermodynamics
    async getThermoStatus() {
        const response = await fetch('/api/thermo_status');
        return response.json();
    },
    
    async getThermoCache() {
        const response = await fetch('/api/thermo_cache');
        return response.json();
    },
    
    async getThermo(rxnId) {
        const response = await fetch(`/api/thermo/${rxnId}`);
        return response.json();
    },
    
    // Pathway
    async getMetabolite(metId) {
        const response = await fetch(`/api/metabolite/${metId}`);
        return response.json();
    },
    
    async getSubsystems() {
        const response = await fetch('/api/subsystems');
        return response.json();
    },
    
    async getSubsystem(name) {
        const response = await fetch(`/api/subsystem/${encodeURIComponent(name)}`);
        return response.json();
    },
    
    // Constraints
    async getConstraints() {
        const response = await fetch('/api/constraints');
        return response.json();
    },
    
    async addConstraint(constraint) {
        const response = await fetch('/api/constraints', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(constraint)
        });
        return response.json();
    },
    
    async removeConstraint(constraintId) {
        const response = await fetch(`/api/constraints/${constraintId}`, {
            method: 'DELETE'
        });
        return response.json();
    },
    
    async toggleConstraint(constraintId, enabled) {
        const response = await fetch(`/api/constraints/${constraintId}/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled })
        });
        return response.json();
    },
    
    async applyPreset(presetName) {
        const response = await fetch(`/api/constraints/preset/${presetName}`, {
            method: 'POST'
        });
        return response.json();
    },
    
    async clearConstraints() {
        const response = await fetch('/api/constraints/clear', {
            method: 'POST'
        });
        return response.json();
    },
    
    async searchReactions(query, compartment = '') {
        let url = `/api/search/reactions?q=${encodeURIComponent(query)}`;
        if (compartment) {
            url += `&compartment=${encodeURIComponent(compartment)}`;
        }
        const response = await fetch(url);
        return response.json();
    },
    
    async searchMetabolites(query, compartment = '') {
        let url = `/api/search/metabolites?q=${encodeURIComponent(query)}`;
        if (compartment) {
            url += `&compartment=${encodeURIComponent(compartment)}`;
        }
        const response = await fetch(url);
        return response.json();
    },
    
    async searchByAnnotation(query) {
        const response = await fetch(`/api/search/by_annotation?q=${encodeURIComponent(query)}`);
        return response.json();
    }
};
