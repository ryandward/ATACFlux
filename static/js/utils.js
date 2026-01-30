/* ATACFlux - Utility Functions */

const Utils = {
    // Thermodynamics classification
    getThermoClass(dG, uncertainty) {
        if (dG === null || dG === undefined) return 'unknown';
        if (uncertainty >= 1000) return 'unknown';
        if (dG < -30) return 'favorable';
        if (dG > 30) return 'unfavorable';
        return 'reversible';
    },
    
    getThermoLabel(dG, uncertainty, formula) {
        if (formula === 'transport (no net reaction)') return '⇌';
        if (dG === null || dG === undefined) return '?';
        if (uncertainty >= 1000) return '?';
        return dG.toFixed(0);
    },
    
    getThermoDescription(dG, uncertainty) {
        if (dG === null || dG === undefined) return 'Unknown';
        if (uncertainty >= 1000) return 'High uncertainty';
        if (dG < -30) return 'Forward only';
        if (dG > 30) return 'Reverse only';
        return 'Reversible';
    },
    
    // Flux classification
    getFluxClass(flux) {
        if (flux === null || flux === undefined) return 'zero';
        if (flux > 1e-6) return 'positive';
        if (flux < -1e-6) return 'negative';
        return 'zero';
    },
    
    formatFlux(flux) {
        if (flux === null || flux === undefined) return '';
        return flux.toFixed(3);
    },
    
    // DOM helpers
    $(selector) {
        return document.querySelector(selector);
    },
    
    $$(selector) {
        return document.querySelectorAll(selector);
    },
    
    setStatus(elementId, type, message) {
        const el = document.getElementById(elementId);
        if (el) {
            el.innerHTML = `<div class="status ${type}">${message}</div>`;
        }
    }
};
