/* Help & theory text for the "Help & theory" tab. */
window.ABOUT_HTML = `
<p class="note">This tab is a short summary. The full <a href="docs/VCSEL_Simulator_Manual.pdf" target="_blank" rel="noopener">user manual (PDF)</a> covers operation, the physics, assumptions and limitations in detail.</p>
<h2>Getting started</h2>
<p>The design is a list of layers from the <b>exit medium</b> (top, usually air) down to the <b>substrate</b>; both are semi-infinite.
Use <b>＋ Layer</b> / <b>＋ Group</b> to build the stack. A <b>group</b> is a block of layers repeated <i>N</i> times. DBRs and
multi-quantum-well active regions are groups, so changing the number of mirror pairs or wells only means editing the “×” box.
Give the mirror groups the role <i>Top DBR</i> / <i>Bottom DBR</i>, and set <i>Layer type = active</i> on the gain layers (the wells).</p>
<p>Thickness can be entered in <b>nm</b> or in <b>waves</b>, meaning optical thickness <span class="eq">n(λ<sub>design</sub>) · d / λ<sub>design</sub></span>
so a quarter-wave layer is 0.25. Changing the design wavelength rescales every layer given in waves; layers given in nm stay fixed, as in Vertical.</p>
<p>Every edit re-runs the analysis automatically. <b>↶ Undo</b> / <b>↷ Redo</b> in the toolbar (Ctrl+Z / Ctrl+Y outside text boxes) step back and forward through changes to the design. The design is kept in your browser between visits. Use <b>File → Save</b> to keep a copy and share it.
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
This defines the energy length L<sub>E</sub> = Γ<sub>enh</sub> L<sub>a</sub>/Γ, the length that makes Γ = Γ<sub>enh</sub>L<sub>a</sub>/L exact. It is not the Coldren effective cavity length L<sub>cav</sub> + L<sub>pen,1</sub> + L<sub>pen,2</sub> (shown separately); it changes, for example, when the active region grows into regions of different index. The per-length losses use L = L<sub>E</sub>:
<span class="eq">α<sub>i</sub> = −ln(1 − RT loss) / 2L,   α<sub>m</sub> = (1/2L) ln[1/((1 − T<sub>up</sub>)(1 − T<sub>down</sub>))]   (exact, default)<br>α<sub>i</sub> = RT loss / 2L,   α<sub>m</sub> = RT transmission / 2L,   Γ g<sub>th</sub> = α<sub>i</sub> + α<sub>m</sub>   (linear, as Vertical)</span>
The linear forms are the definitions in the course notes (“Vertical Gain and Loss Definitions”), with R<sub>up/down</sub> = exp(−RT transmission up/down); the exact forms use R<sub>up/down</sub> = 1 − RT transmission up/down. The photon lifetime is the stored energy, (ε<sub>0</sub>/2)∫ n n<sub>g</sub> |E|² dz with the group index n<sub>g</sub> of each layer, divided by the power lost to absorption and output. In both cases
the external differential efficiency is η<sub>d</sub> = η<sub>i</sub> × RT transmission / RT gain (slope efficiency η<sub>d</sub> hν/q in W/A).</p>
<h3>Cavity length, penetration depth and confinement (course notes)</h3>
<p>The main Results table reports the physical length and the optical thickness Σ n d / λ<sub>las</sub> of the cavity (all layers between the Top DBR and
Bottom DBR groups; 1.0 is a one-wavelength cavity). A collapsed section at the end of the table, <i>Hand-calculation cross-check</i>, also follows the ECE 577 notes (“Vertical Gain and Loss Definitions”) and Coldren &amp; Corzine Appendix 7.
Coldren &amp; Corzine give the penetration depth of a quarter-wave mirror in closed form</p>
<span class="eq">m<sub>eff</sub> = tanh[m ln(n<sub>2</sub>/n<sub>1</sub>)] / tanh[ln(n<sub>2</sub>/n<sub>1</sub>)],   L<sub>eff</sub> = ½ m<sub>eff</sub> Λ [1/(1+r²) − 1/(2m<sub>eff</sub>)]</span>
<p>measured from the first low-index layer. A7.25 is exact, but it measures the phase delay of a wave travelling at the mirror's average index
n̄ = λ/2Λ. Measured in the cavity medium next to the mirror instead, the same delay corresponds to a length shorter by n̄/n<sub>cav</sub>
(about 9% for AlAs/GaAs mirrors next to GaAs). The main Results table (Mirrors section) lists the depths computed from the actual
reflection phase, ½|dφ/dβ| with β = 2πn<sub>cav</sub>/λ, which also cover mirrors that are not ideal quarter-wave stacks or that start with a
low-index layer next to a lower-index cavity. The exact, energy-weighted Γ in the Confinement section needs no penetration depth at all.
A high-index mirror layer that touches the cavity is counted in the cavity. The effective length is then
<span class="eq">L = L<sub>cav</sub> + L<sub>eff,1</sub> + L<sub>eff,2</sub>,   Γ = Γ<sub>enh</sub> L<sub>a</sub> / L</span>
from which the modal gain, ⟨α<sub>i</sub>⟩, α<sub>m</sub>, R<sub>up</sub>, R<sub>down</sub> and the effective optical length χ = L n<sub>eff</sub>/λ<sub>0</sub> (cavity plus penetration depths) follow.
The Ch. 3 approximations (tanh(2mr)/2κ, Λ/4r, λ/4Δn) are shown in the mirror table for comparison.
This Γ is not the same quantity as the energy-weighted Γ in the main table. The two can differ by 10–20%, because the penetration-depth model replaces each mirror by a hard wall at L<sub>eff</sub>. Use it to check hand calculations; use the main table for design.</p>
<h3>Linear or exact round-trip conversion</h3>
<p>The transfer-matrix solve gives the threshold gain and the round-trip fractions exactly. Turning those fractions into losses per length
and mirror reflectances can be done two ways, chosen on the Results tab:</p>
<ul><li><b>Linear (as Vertical):</b> α = RT/2L, R = exp(−trans.), Γg<sub>th</sub> = ⟨α<sub>i</sub>⟩ + α<sub>m</sub> exactly. This matches Vertical and the course notes.</li>
<li><b>Exact:</b> RT = 1 − e<sup>−2αL</sup>, so α = −ln(1 − RT)/2L, and R = 1 − trans. Differences are of order RT/2, typically 0.1–0.5% for a VCSEL.</li></ul>
<p>The field sampling on the Field tab only sets how finely |E|² is plotted. Every integral (gain, loss, Γ<sub>enh</sub>, confinement) is done analytically,
and the peak |E|² is refined inside its layer, so the results do not depend on the sampling. The Vertical column always uses Vertical's 0.1 nm rule.</p>
<h3>DBR design tab</h3>
<p>Designs a quarter-wave mirror on its own. First choose the <b>Mirror</b> viewpoint: <i>Bottom DBR</i> (from the cavity, looking down), <i>Top DBR</i> (from the cavity, looking up),
or a stand-alone mirror lit from above or from below. For the two DBR choices the incident medium is the cavity layer next to the mirror and the 1st layer is the one touching the cavity;
the drawing shows the mirror as it will sit in the stack (a top DBR has the cavity side at the bottom), and Insert keeps the 1st layer next to the cavity.
Then choose the two layers and the exit medium, and set the number of pairs.
The tab shows the spectrum, R at λ<sub>0</sub> (transfer matrix and analytic), the stopband width, the penetration depth, R (or 1 − R) versus the number of pairs, and how many pairs reach a target reflectance.
The <b>stopband</b> is the continuous band around λ<sub>0</sub> with R ≥ 99% (the usual VCSEL convention; the threshold can be changed). It is zero until the mirror reaches 99% and widens with more pairs toward the
infinite-stack width (4λ<sub>0</sub>/π) arcsin[(n<sub>2</sub> − n<sub>1</sub>)/(n<sub>2</sub> + n<sub>1</sub>)], which is shown next to it.
<b>Insert into stack</b> adds the mirror to the design. As <i>Bottom DBR</i> or <i>Top DBR</i> it replaces the stack's existing bottom or top mirror group (or goes directly above the substrate / below the exit medium if there is none);
stand-alone mirrors (for designing a filter or coating on its own) are not inserted; use Save as design to keep one. Undo restores the previous stack.</p>
<h3>Mirror reflectance</h3>
<p>Reflectance spectra are computed for the <b>passive, as-grown</b> structure: active layers carry no gain. There is therefore no lasing pole and no
huge spike at the cavity wavelength. “Top DBR (from cavity)” is the reflectance of everything above the cavity, seen from the cavity layer next to the mirror.
“Bottom DBR (from cavity)” is everything below it, ending in the substrate. The whole-wafer views are what a reflectometer measures from the top or through the substrate. Where the incident medium itself absorbs strongly
(a GaAs substrate below about 870 nm), reflectance seen from inside it is not defined, and that part of the spectrum is left blank.</p>
<p>The table gives R<sub>max</sub> and where it occurs, and the R ≥ 99% stopband with its center (for whole-wafer spectra the narrow cavity dip is bridged).
The top of a stopband is very flat, so λ at R<sub>max</sub> can lie several nm from the design wavelength when the two mirror materials absorb differently:
the standing wave sits mainly in the low-index layers at the short-wavelength side of the band and in the high-index layers at the long-wavelength side.
The stopband center is the better measure of where a mirror is centered, and the laser locks to the cavity resonance, not to R<sub>max</sub>.</p>
<h3>Parameter sweep</h3>
<p>The <b>Sweep</b> tab varies one input over a range and runs the full threshold analysis at every point: the repeats of a group (DBR pairs, wells),
a layer's thickness, composition x or y, absorption or doping, the thickness scale of one group or of the whole stack (a growth-rate error), a group's grading thickness,
the temperature or the design wavelength. An optional second input gives a family of curves (up to 8 values). Two results can be plotted at once (left and right axis);
the table and CSV hold every computed quantity. The lasing mode is followed continuously from the current design outwards. Click a point to see its values and
<b>Apply to design</b> (Undo reverts it). With <b>Re-tune to the design wavelength</b> ticked, the layers you pick (by default the marked ones) are scaled after each step so the
cold cavity resonates at λ<sub>design</sub> again; otherwise the resonance drifts off the mirrors' Bragg wavelength as the cavity changes. A layer cannot be both varied and re-tuned.</p>
<h3>Retarget λ…</h3>
<p>Moves the whole design to another wavelength: each layer keeps its optical thickness in waves, with dispersion, d<sub>new</sub> = d<sub>old</sub>(λ<sub>new</sub>/λ<sub>old</sub>)n(λ<sub>old</sub>)/n(λ<sub>new</sub>);
quantum wells and metals keep their physical thickness by default and the cavity is then tuned onto λ<sub>new</sub>. The preview compares the threshold before and after and checks each
layer's band gap against the new photon energy: passive layers at or within 0.1 eV of their gap are flagged, and the active layer's bulk gap is reported, since the well composition
(not the mirrors) sets where the gain is.</p>
<h3>Graded DBR interfaces</h3>
<p>A periodic group (e.g. an Al<sub>0.90</sub>Ga<sub>0.10</sub>As/GaAs DBR) can have graded interfaces, set in the group editor: <i>linear</i> or <i>bi-parabolic</i> (two parabolas, S-shaped, zero slope at both ends),
a grade thickness per interface and the number of sub-layers. Each interface inside the group, including those between periods, is replaced by a composition ramp centred on it
(each neighbour gives up half the grade thickness); the group's outer faces stay abrupt. The ramp is drawn as equal-thickness steps whose composition follows the profile, so the
transfer matrix sees the real index profile; doping and absorption come from the nearer layer. With <i>Keep Bragg period</i> (default) the uniform parts of the layers are scaled by one
factor so a period keeps its optical thickness at λ<sub>design</sub>, which keeps the stopband centred. Grading lowers the index contrast seen by the wave, so a graded mirror needs more
pairs for the same reflectance. The DBR design tab has the same option. The Coldren penetration-depth and analytic-R formulas assume abrupt layers and are labelled so;
the transfer-matrix values include the grading. Old Vertical files get the explicit graded layers.</p>
<h3>Cavity tuning (Vertical's Marks / Force Wave)</h3>
<p>Tick <i>Marked</i> on the layers that may change (for example the two cavity spacers), then press <b>Tune cavity</b>. All marked thicknesses are scaled by a
common factor until the cold-cavity resonance falls exactly on the design wavelength. With no marked layers, the cavity spacers between the mirrors are used.</p>
<h3>Center wells</h3>
<p>Tune cavity fixes the resonance but not where the wells sit in the standing wave. After adding a layer on one side of the wells (e.g. an electron-blocking layer),
mark one layer above the wells and one below them and press <b>Center wells</b>: the upper layer is scaled to slide the wells onto a standing-wave peak (maximum Γ<sub>enh</sub>),
and the lower layer is re-tuned after every step so the cavity stays resonant at λ<sub>design</sub>.</p>

<h3>Materials tab</h3>
<p>Plots n and k of any material versus wavelength, with the band gap marked, and gives n, k (and α = 4πk/λ) at one wavelength typed in the <i>n, k at λ</i> box.
The table lists the model and reference used for every material.
Note that the default AlGaAs model (Afromowitz) has a logarithmic term that gives n a sharp cusp exactly at the direct gap and k a step from zero.
Real material has a rounded edge, so features within a few nm of a GaAs or AlGaAs band edge are exaggerated. Below the gap, where VCSEL mirrors and cavities operate, the cusp has no effect; for the most accurate below-gap AlGaAs indices use the Gehrsitz model.</p>

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
<p>The stack panel has two views. <b>☰ List</b> is the tree, as in Vertical. <b>▤ Diagram</b> draws the stack as blocks, with block height following layer thickness (or equal heights), each group drawn once with its repeat count, and a to-scale strip of the whole wafer on the right (every repeat drawn; the blue bar marks the selection). Click a block or the strip to select it and open its editor. Drag blocks to reorder them, drag a layer onto a group header to put it inside the group, and drag the chips at the top (layer, DBR pairs, QW + barrier, spacer, empty group, oxide) into the stack to add new pieces. ⇔ widens the panel, and <b>Hide</b> on the properties panel gives the stack the full height. <b>Heights: fit panel</b> (default) shrinks the blocks so the whole stack is visible without scrolling. <b>PNG</b> / <b>SVG</b> download a labelled drawing of the stack (each group drawn once with ×N). The toolbar buttons (duplicate, move, delete) work in both views.</p>
<p>While the layer editor is open, the layer or group being edited is marked by a faint blue band on the Field &amp; index plot.</p>
<h2>Plots</h2>
<p>The bar above each plot has <b>Zoom</b> (drag a box), <b>Pan</b>, <b>+</b> / <b>−</b>, <b>Reset</b> and <b>PNG</b> / <b>SVG</b> export (PNG at 4× resolution). Double-clicking inside a plot does the same as Reset.
Legends sit inside the plot, in the corner that covers the least of the curves; when every corner would hide part of a curve (for example the dense phase plots) the legend moves below the plot. The <i>Legend</i> box turns it off.</p>
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
Electrons: W. Walukiewicz et al., J. Appl. Phys. 51, 2659 (1980), Table III (n-InP, 300 K, 10 µm, uncompensated), with the optical-phonon, ionized-impurity and
acoustic-phonon parts scaled to the design wavelength as λ<sup>2.5</sup>, λ<sup>3.5</sup> and λ<sup>1.5</sup> (their eq. 2). Impurity scattering grows faster than n, so σ
depends on the doping: about 0.7×10⁻¹⁸ cm² at 1.55 µm and 10¹⁸ cm⁻³. The InP value is also used for the lattice-matched alloys.</li>
<li><b>GaN, AlGaN, InGaN, AlInN, AlN</b> (the alloys take the GaN values, an estimate): electrons use the phonon-assisted cross-section of E. Kioupakis, P. Rinke and C. G. Van de Walle, Appl. Phys. Express 3, 082101 (2010)
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
