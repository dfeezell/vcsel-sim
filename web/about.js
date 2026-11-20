/* Help & theory text for the "Help & theory" tab. */
window.ABOUT_HTML = `
<h2>Getting started</h2>
<p>The design is a list of layers from the <b>exit medium</b> (top, usually air) down to the <b>substrate</b>; both are semi-infinite.
Use <b>＋ Layer</b> / <b>＋ Group</b> to build the stack. A <b>group</b> is a block of layers repeated <i>N</i> times. DBRs and
multi-quantum-well active regions are groups, so changing the number of mirror pairs or wells only means editing the “×” box.
Give the mirror groups the role <i>Top DBR</i> / <i>Bottom DBR</i>, and set <i>Layer type = active</i> on the gain layers (the wells).</p>
<p>Thickness can be entered in <b>nm</b> or in <b>waves</b>, meaning optical thickness <span class="eq">n(λ<sub>design</sub>) · d / λ<sub>design</sub></span>
so a quarter-wave layer is 0.25. Changing the design wavelength rescales every layer given in waves; layers given in nm stay fixed, as in Vertical.</p>
<p>Every edit re-runs the analysis automatically. The design is kept in your browser between visits. Use <b>File → Save</b> to keep a copy and share it.
<b>File → Open</b> also reads old Vertical <code>.vrt</code> files.</p>

<h2>Method</h2>
<h3>Transfer matrices</h3>
<p>The field in each layer is <span class="eq">E(z) = A e<sup>ikz</sup> + B e<sup>−ikz</sup>,   k = 2π ñ / λ,   ñ = n + iκ</span>
with time dependence e<sup>−iωt</sup>, so κ &gt; 0 is loss. An absorption coefficient α (cm⁻¹) enters as κ = αλ/4π, and gain is α &lt; 0.
E and H are matched at every interface using 2×2 characteristic matrices. All integrals of |E|² over a layer are done analytically, with no sampling error.</p>
<h3>Threshold</h3>
<p>The same material gain g is applied to every active layer. The program solves for the wavelength λ and gain g at which the structure
supports a field with <i>only outgoing waves</i> in the exit medium and the substrate. This is the condition for infinite transmission (Vertical's threshold condition).
It uses a complex-wavelength (quasi-normal mode) solve of the passive cavity to start, then a 2D Newton iteration on (λ, g).</p>
<h3>Gain and loss budget</h3>
<p>At threshold, the power generated in the active layers equals the power absorbed in the passive layers plus the power leaving through the top and bottom.
Locally, the absorbed power density is <span class="eq">p(z) = α n |E(z)|²</span> and the power flux of a wave is n|A|².
Every term is divided by the one-way power flux in the active layers, P<sub>ref</sub> = n<sub>a</sub>(|A|²+|B|²)/2, to give the “round-trip” fractions:</p>
<span class="eq">RT gain = 2 g<sub>th</sub> L<sub>a</sub> Γ<sub>enh</sub> = RT internal loss + RT transmission (top + bottom)</span>
<p>Here Γ<sub>enh</sub> = ⟨|E|²⟩<sub>active</sub> / (|A|²+|B|²) is the gain enhancement factor. It is the standing-wave overlap with the wells relative to the local
mean, and is 2 for a thin well at an antinode. The longitudinal confinement factor is energy-weighted,
<span class="eq">Γ = ∫<sub>active</sub> n²|E|² dz / ∫<sub>stack</sub> n²|E|² dz</span>
This defines the effective cavity length L = Γ<sub>enh</sub> L<sub>a</sub>/Γ. The per-length losses are then
<span class="eq">α<sub>i</sub> = −ln(1 − RT loss) / 2L,   α<sub>m</sub> = (1/2L) ln[1/((1 − T<sub>up</sub>)(1 − T<sub>down</sub>))]   (exact, default)<br>α<sub>i</sub> = RT loss / 2L,   α<sub>m</sub> = RT transmission / 2L,   Γ g<sub>th</sub> = α<sub>i</sub> + α<sub>m</sub>   (linear, as Vertical)</span>
The linear forms are the definitions in the course notes (“Vertical Gain and Loss Definitions”), with R<sub>up/down</sub> = exp(−RT transmission up/down); the exact forms use R<sub>up/down</sub> = 1 − RT transmission up/down. The photon lifetime is the stored energy, (ε<sub>0</sub>/2)∫ n n<sub>g</sub> |E|² dz with the group index n<sub>g</sub> of each layer, divided by the power lost to absorption and output. In both cases
the external differential efficiency is η<sub>d</sub> = η<sub>i</sub> × RT transmission / RT gain (slope efficiency η<sub>d</sub> hν/q in W/A).</p>
<h3>Cavity length, penetration depth and confinement (course notes)</h3>
<p>The Results tab also follows the ECE 577 notes (“Vertical Gain and Loss Definitions”) and Coldren &amp; Corzine Appendix 7.
Coldren &amp; Corzine give the penetration depth of a quarter-wave mirror in closed form</p>
<span class="eq">m<sub>eff</sub> = tanh[m ln(n<sub>2</sub>/n<sub>1</sub>)] / tanh[ln(n<sub>2</sub>/n<sub>1</sub>)],   L<sub>eff</sub> = ½ m<sub>eff</sub> Λ [1/(1+r²) − 1/(2m<sub>eff</sub>)]</span>
<p>measured from the first low-index layer. A7.25 is exact, but it measures the phase delay of a wave travelling at the mirror's average index
n̄ = λ/2Λ. Measured in the cavity medium next to the mirror instead, the same delay corresponds to a length shorter by n̄/n<sub>cav</sub>
(about 9% for AlAs/GaAs mirrors next to GaAs). For comparison the Results tab also lists depths taken from the computed
reflection phase, ½|dφ/dβ| with β = 2πn<sub>cav</sub>/λ, which also cover mirrors that are not ideal quarter-wave stacks or that start with a
low-index layer next to a lower-index cavity. The exact, energy-weighted Γ further down the table needs no penetration depth at all.
A high-index mirror layer that touches the cavity is counted in the cavity. The effective length is then
<span class="eq">L = L<sub>cav</sub> + L<sub>eff,1</sub> + L<sub>eff,2</sub>,   Γ = Γ<sub>enh</sub> L<sub>a</sub> / L</span>
from which the modal gain, ⟨α<sub>i</sub>⟩, α<sub>m</sub>, R<sub>up</sub>, R<sub>down</sub> and the cavity optical thickness χ = L n<sub>eff</sub>/λ<sub>0</sub> follow.
The Ch. 3 approximations (tanh(2mr)/2κ, Λ/4r, λ/4Δn) are shown in the mirror table for comparison.
This Γ is not the same quantity as the energy-weighted Γ further down the table. The two can differ by 10–20%.</p>
<h3>Linear or exact round-trip conversion</h3>
<p>The transfer-matrix solve gives the threshold gain and the round-trip fractions exactly. Turning those fractions into losses per length
and mirror reflectances can be done two ways, chosen on the Results tab:</p>
<ul><li><b>Linear (as Vertical):</b> α = RT/2L, R = exp(−trans.), Γg<sub>th</sub> = ⟨α<sub>i</sub>⟩ + α<sub>m</sub> exactly. This matches Vertical and the course notes.</li>
<li><b>Exact:</b> RT = 1 − e<sup>−2αL</sup>, so α = −ln(1 − RT)/2L, and R = 1 − trans. Differences are of order RT/2, typically 0.1–0.5% for a VCSEL.</li></ul>
<p>The field sampling on the Field tab only sets how finely |E|² is plotted. Every integral (gain, loss, Γ<sub>enh</sub>, confinement) is done analytically,
and the peak |E|² is refined inside its layer, so the results do not depend on the sampling. The Vertical column always uses Vertical's 0.1 nm rule.</p>
<h3>DBR design tab</h3>
<p>Designs a quarter-wave mirror on its own. Choose the incident medium, the two layers and the exit medium, and set the number of pairs.
The tab shows the spectrum, R at λ<sub>0</sub> (transfer matrix and analytic), the stopband width, the penetration depth, and how many pairs reach a target reflectance.
<b>Insert into stack</b> adds the mirror to the design as a group.</p>
<h3>Mirror reflectance</h3>
<p>Reflectance spectra are computed for the <b>passive, as-grown</b> structure: active layers carry no gain. There is therefore no lasing pole and no
huge spike at the cavity wavelength. “Top DBR (from cavity)” is the reflectance of everything above the cavity, seen from the cavity layer next to the mirror.
“Bottom DBR (from cavity)” is everything below it, ending in the substrate. The whole-wafer views are what a reflectometer measures from the top or through the substrate.</p>
<h3>Cavity tuning (Vertical's Marks / Force Wave)</h3>
<p>Tick <i>Marked</i> on the layers that may change (for example the two cavity spacers), then press <b>Tune cavity</b>. All marked thicknesses are scaled by a
common factor until the cold-cavity resonance falls exactly on the design wavelength.</p>

<h2>Comparison with Vertical</h2>
<p>For the ECE 577 final-project structure, imported directly from its <code>.vrt</code> file, this program gives the same threshold gain and lasing wavelength as
Vertical (2111.42 cm⁻¹ at 980.000 nm). The transfer matrix agrees to 5–6 digits. Vertical evaluates some quantities with simple numerical rules:</p>
<ul>
<li>It samples |E|² every 0.1 nm in active layers and sums the samples, including both end points.</li>
<li>It measures Γ<sub>enh</sub> against half the <i>global</i> peak of |E|² rather than the local standing-wave mean.</li>
<li>It splits the transmission between top and bottom in proportion to |E|² at each boundary.</li>
</ul>
<p>The <b>Vertical convention</b> column on the Results tab reproduces these rules. It matches Vertical's Results dialog to about 0.1%, which is useful for checking older work.
The main <b>Value</b> column is the exact energy balance. It is the one to use for new designs: Γ<sub>enh</sub> differs by about 1%, and the top/bottom split
differs whenever the exit medium and substrate indices differ.</p>
<p>The <code>.vrt</code> importer reads the layer tree, repetitions, indices, thicknesses, absorption, doping and layer types.
Objects left in Vertical's “Extra” area are ignored. Indices are kept fixed at the values stored in the file. Switch a layer to <i>Material model</i> to use the dispersive database instead.</p>

<h2>Using the engine from Python</h2>
<p>The same engine runs in plain Python or Jupyter (it needs only numpy):</p>
<span class="eq">from vcsel_sim.vrt import read_vrt<br>from vcsel_sim.laser import analyze, reflectance_spectrum<br>s = read_vrt(open("design.vrt","rb").read())<br>a = analyze(s); print(a.threshold_gain, a.wavelength)</span>

<h2>Building the stack visually</h2>
<p>The stack panel has two views. <b>☰ List</b> is the tree, as in Vertical. <b>▤ Diagram</b> draws the stack as blocks, with block height following layer thickness (or equal heights), each group drawn once with its repeat count, and a to-scale strip of the whole wafer on the right (every repeat drawn; the blue bar marks the selection). Click a block or the strip to select and edit it below. Drag blocks to reorder them, drag a layer onto a group header to put it inside the group, and drag the chips at the top (layer, DBR pairs, QW + barrier, spacer, empty group, oxide) into the stack to add new pieces. ⇔ widens the panel, and <b>Hide</b> on the properties panel gives the stack the full height. <b>Heights: fit panel</b> (default) shrinks the blocks so the whole stack is visible without scrolling. <b>PNG</b> / <b>SVG</b> download a labelled drawing of the stack (each group drawn once with ×N). The toolbar buttons (duplicate, move, delete) work in both views.</p>
<p>The DBR design tab draws the mirror it designs and can export it as a layer CSV or save it as a design file.</p>

<h2>Temperature</h2>
<p>The <b>T</b> box in the toolbar sets the structure temperature. It is used by temperature-dependent materials, currently <b>AlGaAs (Gehrsitz, temperature)</b>: Gehrsitz et al., J. Appl. Phys. 87, 7825 (2000), accurate to about 10<sup>−3</sup> below the direct gap, with dn/dT of about 2.6–3.5×10<sup>−4</sup>/K for GaAs and 1.3×10<sup>−4</sup>/K for AlAs near 1 µm (Talghader &amp; Smith, APL 66, 335 (1995), measured 2.67 and 1.43×10<sup>−4</sup>/K). Build the DBRs and cavity from that material and change T to see the resonance tune (about 0.06 nm/K for a 980 nm GaAs/AlGaAs cavity). Layers given in waves are converted to nm at 23 °C, so they stay physically fixed as T changes; thermal expansion (about 6×10<sup>−6</sup>/K) is not included. Other materials ignore T. The model is blank at and above the GaAs gap, so keep absorbing GaAs contact or substrate layers on the Afromowitz AlGaAs model.</p>

<h2>Absorption from doping (optional)</h2>
<p>For n-type and p-type layers, <b>Absorption α → From doping</b> replaces the typed α with free-carrier absorption
α = σ·N, where N is the layer's doping and σ the cross-section of electrons (n-type) or holes (p-type) for the material family at the
wavelength. Manual α stays the default. Enter your own σ in the layer editor to override the literature value. Active layers always use the manual α.</p>
<ul>
<li><b>AlGaAs, InGaAs</b>: σ<sub>n</sub> = 3×10⁻¹⁸ cm², σ<sub>p</sub> = 7×10⁻¹⁸ cm² (H. C. Casey, Jr., J. Appl. Phys. 49, 3684 (1978), eq. 9, GaAs near the gap at room temperature, also applied to AlGaAs).
Other published pairs are 5 / 11 (see Debernardi et al., IEEE JSTQE 25, 1700914 (2019)).</li>
<li><b>InP, InGaAsP, InAlGaAs</b>: holes (intervalence band absorption) 14×10⁻¹⁸ cm² at 1.3 µm and 20×10⁻¹⁸ cm² at 1.5 µm
(H. C. Casey, Jr. and P. L. Carter, Appl. Phys. Lett. 44, 82 (1984)) and 25×10⁻¹⁸ cm² at 1.6 µm (C. H. Henry et al., IEEE J. Quantum Electron. QE-19, 947 (1983), who measured the same
values in InP, In<sub>0.53</sub>Ga<sub>0.47</sub>As and GaAs, so they apply across the lattice-matched quaternary), linear in between and held constant outside;
J. Taylor and V. Tolstikhin, J. Appl. Phys. 87, 1054 (2000) reproduce them with a 6×6 Luttinger–Kohn model.
Electrons use 4×10⁻¹⁸ cm² (n-GaAs at 1.5 µm, D. C. Look et al., Appl. Phys. Lett. 65, 2188 (1994)) until an InP-specific value is added.</li>
<li><b>GaN, AlGaN, InGaN, AlN</b>: electrons use the phonon-assisted cross-section of E. Kioupakis, P. Rinke and C. G. Van de Walle, Appl. Phys. Express 3, 082101 (2010)
(Table I fit, 380–680 nm, light polarized in the c-plane), about 0.6×10⁻¹⁸ cm² at 450 nm, which matches the measurement of S. Pimputkar et al., J. Cryst. Growth 432, 49 (2015).
In Mg-doped layers most of the loss is absorption by holes bound to activated Mg acceptors rather than by free holes, so enter the <b>Mg concentration</b> as the doping.
Two values are offered: the measurement of D. Sizov, R. Bhat and C. Zah, J. Appl. Phys. 113, 203108 (2013), about 1×10⁻¹⁷ cm² per activated Mg, weakly dependent on wavelength
and temperature and isotropic (default), and the first-principles free + bound hole cross-section of Kioupakis et al. (2010) (0.9×10⁻¹⁸ cm² at 450 nm), about ten times smaller.</li>
<li><b>AlGaInP</b>: estimate only (no direct measurement found), interpolated between the binaries as is common for this alloy. Electrons: between the GaAs value
(Casey, scaled by (λ/870 nm)²) at x = 0 and n-GaP at x = 0.51, linear in x/0.51. The GaP value is from W. G. Spitzer et al., J. Phys. Chem. Solids 11, 339 (1959), 295 K:
about 40 cm⁻¹ at 1.2 µm for n = 10¹⁸ cm⁻³, rising as λ<sup>1.56</sup>, extrapolated to shorter wavelengths (about 1.5×10⁻¹⁷ cm² at 650 nm). Electrons in the indirect X valleys of
Al-rich AlGaInP absorb much more than in GaAs. Holes: the GaAs value scaled by (λ/870 nm)².</li></ul>
<p>Typing a doping into an n- or p-type layer whose material has a model switches that layer to “From doping”. Doping in the active region and injected carriers are not included,
nor is the near-band-edge (Urbach) absorption of heavily doped GaN, which matters below about 420 nm.</p>

<h2>Planned</h2>
<ul><li>Phase 2: apertures (oxide / air), effective-index lateral modes, diffraction and scattering loss, 2D modal gain.</li>
<li>User-defined gain spectra g(λ, N) (e.g. from Coldren &amp; Corzine or measurements). The engine already keeps the gain per active layer separate, so this can be added.</li>
<li>More temperature-dependent materials; refine the nitride and InP free-carrier cross-sections (wavelength dependence, near-edge absorption of doped GaN).</li></ul>
`;
