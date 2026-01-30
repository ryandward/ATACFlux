# ATACFlux

Thermodynamic and regulatory flux analysis for yeast metabolic engineering.

## Data Files

### `data/compounds_thermo.json`
Metabolite identifier mapping cache. Maps yeast-GEM metabolite IDs to external database identifiers (KEGG, ChEBI, MetaNetX, BiGG) for use by the reaction thermodynamics script.

- 1375 compounds mapped
- Cascading lookup: KEGG → ChEBI → MetaNetX → BiGG → name search
- Primary purpose: provide `queried_as` field (e.g., "kegg:C00002") for reaction formula construction

### `data/reactions_thermo.json`
Reaction thermodynamic cache with ΔG'° values from eQuilibrator.

- 4131 reactions total
- ~2785 valid (uncertainty < 1000 kJ/mol)
- 13 metalloprotein/redox reactions handled via RedoxCarrier
- Includes multicompartmental calculations for transmembrane H+ reactions (e.g., ATP synthase)

### `data/compartment_parameters.json`
Compartment-specific pH and membrane potential values for yeast-GEM. Used by the reaction caching script to calculate thermodynamically correct ΔG' for reactions involving proton transport across membranes.

Compartments defined:
- c (cytoplasm): pH 7.2
- m (mitochondrion): pH 7.5, -160 mV vs cytosol
- v (vacuole): pH 6.0, +30 mV vs cytosol
- er (ER), g (Golgi), p (peroxisome), n (nucleus), e (extracellular), etc.

### `data/redox_couples.json`
Literature standard reduction potentials (E°') for electron transport chain components that eQuilibrator cannot calculate from group contribution methods.

**Why this is needed:**
eQuilibrator uses group contribution methods that require atom-level molecular structure (InChI). Cytochromes and other metalloproteins have no InChI because their thermodynamic properties depend on the protein fold and metal coordination environment, not just the chemical formula. This results in `ΔGf' = None` and `uncertainty = 100,000 kJ/mol` for reactions involving these species.

**Couples defined:**
- Cytochrome c (Fe³⁺/Fe²⁺): E°' = 254 mV
- Cytochrome b5 (Fe³⁺/Fe²⁺): E°' = 5 mV
- Ubiquinone-6/Ubiquinol-6 (CoQ₆/CoQ₆H₂): E°' = 45 mV (stored as 90 mV for n=2)
- Thiosulfate/Tetrathionate (S₂O₃²⁻/S₄O₆²⁻): E°' = 198 mV

## Scripts

### `scripts/compound_thermo_cache.py`
**Purpose:** Build metabolite identifier mapping from yeast-GEM to eQuilibrator.

**What it does:**
1. Extracts all unique metabolites from yeast-GEM
2. Queries eQuilibrator for each using cascading ID lookup (KEGG → ChEBI → MetaNetX → BiGG → name)
3. Stores the successful query identifier for each metabolite

**Usage:**
```bash
python scripts/compound_thermo_cache.py models/yeast-GEM.xml data/compounds_thermo.json
```

**Output:** JSON mapping yeast-GEM metabolite IDs to eQuilibrator identifiers.

### `scripts/reaction_thermo_cache.py`
**Purpose:** Calculate reaction ΔG'° values using eQuilibrator, with proper handling of compartmentalized reactions and metalloprotein redox couples.

**What it does:**
1. For each reaction in yeast-GEM, builds an eQuilibrator formula from mapped metabolite IDs
2. For **standard reactions**: calls `cc.standard_dg_prime()` directly
3. For **transmembrane H+ reactions** (H+ in different compartments): 
   - Splits into inner/outer half-reactions
   - Calls `cc.multicompartmental_standard_dg_prime()` with compartment-specific pH and membrane potential
   - This correctly accounts for proton motive force (e.g., ATP synthase shows ΔG' ≈ -22 kJ/mol instead of +30 kJ/mol)
4. For **proton pumps** (V-ATPases where parser fails):
   - Calculates ΔG°'_chemistry using standard method
   - Adds membrane contribution: n_vectorial × Δμ̃H+ (see below for how vectorial protons are determined)
5. For **metalloprotein redox reactions** (cytochromes, quinones):
   - Creates `RedoxCarrier` objects with literature reduction potentials
   - Builds `PhasedReaction` with `sparse_with_phases` parameter
   - This injects the E°' values into eQuilibrator's internal calculation framework

**Usage:**
```bash
python scripts/reaction_thermo_cache.py models/yeast-GEM.xml data/compounds_thermo.json data/reactions_thermo.json data/compartment_parameters.json data/redox_couples.json
```

**Output:** JSON with reaction thermodynamics including:
- `dG_prime`: Standard transformed Gibbs energy (kJ/mol)
- `uncertainty`: Error estimate (kJ/mol)
- `method`: "standard", "multicompartmental", "proton_pump", or "redox_carrier"
- `formula_queried`: The eQuilibrator formula or method description
- For multicompartmental: `inner_pH`, `outer_pH`, `membrane_potential_mV`, `proton_stoichiometry`
- For proton_pump: `dG_chemistry`, `dG_membrane`, `dG_per_proton`, `vectorial_protons`
- For redox_carrier: `couples_used` (list of redox couple names)

## Thermodynamic Theory and Equations

### Standard Transformed Gibbs Energy

eQuilibrator calculates the **standard transformed Gibbs energy** (ΔG'°), which accounts for biochemical standard state (pH 7, specified ionic strength, Mg²⁺ concentration) using the Legendre transform:

```
ΔG'° = ΔG° + RT·ln(10)·ΔνH+·pH + corrections(I, Mg²⁺)
```

where ΔνH+ is the net proton stoichiometry. For a reaction:

```
ΔG'°_rxn = Σ νᵢ · ΔGf'°(i)
```

where νᵢ are stoichiometric coefficients (negative for reactants) and ΔGf'°(i) are transformed formation energies.

### Actual Gibbs Energy (with concentrations)

The actual ΔG' at physiological concentrations:

```
ΔG' = ΔG'° + RT · Σ νᵢ · ln([i])
```

At 298 K, RT = 2.479 kJ/mol, so a 10-fold concentration ratio contributes ~5.7 kJ/mol.

### Multicompartmental Reactions (Proton Motive Force)

For reactions with H⁺ transport across membranes, the electrochemical potential difference matters:

```
Δμ̃H+ = F·Δψ + RT·ln(10)·ΔpH
```

where:
- F = 96.485 kJ/(mol·V) (Faraday constant)
- Δψ = membrane potential (V)
- ΔpH = pH_out - pH_in

For the mitochondrial inner membrane (Δψ ≈ -160 mV, ΔpH ≈ -0.3):

```
Δμ̃H+ = 96.485 × (-0.160) + 2.479 × ln(10) × (-0.3)
     = -15.4 - 1.7
     ≈ -17 kJ/mol per H⁺ transported out→in
```

eQuilibrator's `multicompartmental_standard_dg_prime()` calculates:

```
ΔG'°_total = ΔG'°_inner(pH_inner) + ΔG'°_outer(pH_outer) + n·F·Δψ
```

**Example: ATP Synthase**
- Standard calculation (ignoring compartments): ΔG'° = +29.6 kJ/mol
- With compartmentalization (3 H⁺ flowing in): ΔG'° = +29.6 + 3×(-17) ≈ -21 kJ/mol

### Redox Reactions and Reduction Potentials

For electron transfer reactions, the relationship between reduction potential and Gibbs energy:

```
ΔG° = -nFE°
```

where:
- n = number of electrons transferred
- F = 96.485 kJ/(mol·V)
- E° = standard reduction potential (V)

At biochemical standard state (pH 7):

```
ΔG'° = -nFE'°
```

**Half-reaction convention:**
```
Oxidized + ne⁻ → Reduced     E'° (reduction potential)
```

For a full redox reaction (A_red + B_ox → A_ox + B_red):

```
ΔG'° = -nF(E'°_acceptor - E'°_donor) = -nFΔE'°
```

**Example: Complex IV (cytochrome c + O₂)**
- Cytochrome c: E'° = +254 mV (Fe³⁺ + e⁻ → Fe²⁺)
- O₂/H₂O: E'° = +815 mV (½O₂ + 2H⁺ + 2e⁻ → H₂O)

For the reaction: 2 cyt c(red) + ½O₂ + 2H⁺ → 2 cyt c(ox) + H₂O

```
ΔG'° = -nF(E'°_O₂ - E'°_cyt_c)
     = -2 × 96.485 × (0.815 - 0.254)
     = -2 × 96.485 × 0.561
     = -108 kJ/mol (for 2 electrons)
     = -54 kJ/mol (per cytochrome c oxidized)
```

### RedoxCarrier Implementation in eQuilibrator

eQuilibrator cannot calculate ΔGf'° for metalloproteins (no InChI structure). The `RedoxCarrier` class injects literature E'° values:

```python
RedoxCarrier.get_stored_standard_dgf_prime() → -F × E'°
```

**Important:** RedoxCarrier always uses n=1 (single electron). For multi-electron carriers, multiply the potential by n:

| Carrier | True E'° | n | Effective potential for RedoxCarrier |
|---------|----------|---|--------------------------------------|
| Cytochrome c | 254 mV | 1 | 254 mV |
| Ubiquinone/Ubiquinol | 45 mV | 2 | 90 mV (2 × 45) |

**Convention used:**
- Oxidized form: E'° = 0 mV (arbitrary reference)
- Reduced form: E'° = n × literature value

This gives:
```
ΔGf'°(reduced) - ΔGf'°(oxidized) = -F × (n × E'°) = -nFE'°
```

For cytochrome c (E'° = 254 mV, n = 1):
```
ΔGf'°(Fe²⁺) - ΔGf'°(Fe³⁺) = -1 × 96.485 × 0.254 = -24.5 kJ/mol
```

This means the reduced form is 24.5 kJ/mol more stable—it "stores" the electron's energy.

**Reaction calculation:**
When eQuilibrator computes ΔG'°_rxn = Σ νᵢ · ΔGf'°(i), the RedoxCarrier contributions:
- Consuming reduced form (ν < 0): adds +nFE'° (releases electron energy)
- Producing reduced form (ν > 0): adds -nFE'° (stores electron energy)

### Validation

For r_0438 (Complex IV simplified): cyt_c_red + 0.25 O₂ + H⁺ → cyt_c_ox + 0.5 H₂O

| E'°(cyt c) | ΔG'° (eQuilibrator) | Expected Δ from 0 mV |
|------------|---------------------|----------------------|
| 0 mV       | -79.6 ± 0.8 kJ/mol  | —                    |
| 254 mV     | -55.1 ± 0.8 kJ/mol  | +24.5 kJ/mol         |
| 500 mV     | -31.3 ± 0.8 kJ/mol  | +48.3 kJ/mol         |

Calculated: nFE = 1 × 96.485 × 0.254 = **24.5 kJ/mol** ✓

The -79.6 kJ/mol at 0 mV represents the O₂ reduction contribution alone. Adding cytochrome c's reduction potential (+24.5 kJ/mol for oxidizing the reduced form) gives -55.1 kJ/mol.

### Code Example

```python
from equilibrator_api import ComponentContribution, Q_
from equilibrator_api.phased_compound import PhasedCompound, RedoxCarrier
from equilibrator_api.phased_reaction import PhasedReaction

cc = ComponentContribution()

# Get compounds
cyt_c_ox = cc.get_compound("kegg:C00125")   # ferricytochrome c
cyt_c_red = cc.get_compound("kegg:C00126")  # ferrocytochrome c
O2 = cc.get_compound("kegg:C00007")
H2O = cc.get_compound("kegg:C00001")
H = cc.get_compound("kegg:C00080")

# Create phased compounds with RedoxCarrier for cytochromes
rc_ox = RedoxCarrier(cyt_c_ox, potential=Q_("0 mV"))
rc_red = RedoxCarrier(cyt_c_red, potential=Q_("254 mV"))
pc_O2 = PhasedCompound(O2)
pc_H2O = PhasedCompound(H2O)
pc_H = PhasedCompound(H)

# Build reaction: cyt_c_red + 0.25 O₂ + H⁺ → cyt_c_ox + 0.5 H₂O
rxn = PhasedReaction(
    sparse={cyt_c_red: -1, O2: -0.25, H: -1, cyt_c_ox: 1, H2O: 0.5},
    sparse_with_phases={rc_red: -1, pc_O2: -0.25, pc_H: -1, rc_ox: 1, pc_H2O: 0.5}
)

dG = cc.standard_dg_prime(rxn)
print(f"ΔG'° = {dG}")  # (-55.1 +/- 0.8) kJ/mol
```

### Remaining Limitations

1. **ATP → AMP + PPi irreversibility**: PPi hydrolysis not captured in ΔG'°
2. **Metabolite concentrations**: Standard state assumes 1 mM; real concentrations differ significantly
3. **Macromolecules**: ~120 reactions (tRNA synthetases, polymers, GPI anchors, specific lipids) involve species outside eQuilibrator's small-molecule scope

### Proton Pump Calculations (V-ATPases)

For proton pumps where eQuilibrator's formula parser fails (all H⁺ on one side), we calculate manually:

```
ΔG'°_total = ΔG'°_chemistry + n_vectorial × Δμ̃H+
```

**Scalar vs Vectorial Protons:**
- **Scalar**: H⁺ in the chemical equation (ADP + Pi + H⁺ ↔ ATP + H₂O) - already in ΔG'°_chemistry
- **Vectorial**: H⁺ that physically traverse the membrane channel (F0 or V0)

**Determining vectorial protons by thermodynamic direction:**
- If Δμ̃H+ < 0 (favorable outer→inner): count H⁺ **leaving outer** (synthesis mode)
- If Δμ̃H+ > 0 (unfavorable outer→inner): count H⁺ **appearing in inner** (pumping mode)

**Example - ATP synthase:**
- H⁺ stoichiometry: {cytosol: -3, matrix: +2}
- Δμ̃H+ = -17.15 kJ/mol (favorable outer→inner)
- Vectorial H⁺ = 3 (leaving outer, flowing down gradient)
- ΔG'° = +29.6 + 3×(-17.15) = **-21.8 kJ/mol** ✓

**Example - V-ATPase (vacuole):**
- H⁺ stoichiometry: {cytosol: -1, vacuole: +2}
- Δμ̃H+ = +9.75 kJ/mol (unfavorable, pumping against gradient)
- Vectorial H⁺ = 2 (appearing in inner, being pumped)
- ΔG'° = -29.6 + 2×(+9.75) = **-10.2 kJ/mol** ✓

## Setup

```bash
pip install -r requirements.txt
```

Place `yeast-GEM.xml` in the `models/` directory.

## Regenerating Thermodynamic Cache

```bash
# Step 1: Build compound ID mapping (only needed if model changes)
python scripts/compound_thermo_cache.py models/yeast-GEM.xml data/compounds_thermo.json

# Step 2: Calculate reaction thermodynamics
python scripts/reaction_thermo_cache.py models/yeast-GEM.xml data/compounds_thermo.json data/reactions_thermo.json data/compartment_parameters.json data/redox_couples.json
```

## Run

```bash
cd src
python app.py
```

Open http://localhost:5000

## Requirements

```
cobra
equilibrator-api
flask
numpy
swiglpk>=1.4
```
