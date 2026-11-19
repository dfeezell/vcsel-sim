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
<p>The field in each layer is <span class="eq">E(z) = A e^{ikz} + B e^{−ikz},   k = 2π ñ / λ,   ñ = n + iκ</span>
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
<span class="eq">α<sub>i</sub> = RT loss / 2L,   α<sub>m</sub> = RT transmission / 2L,   Γ g<sub>th</sub> = α<sub>i</sub> + α<sub>m</sub></span>
These follow the definitions in the course notes (“Vertical Gain and Loss Definitions”): R<sub>up/down</sub> = exp(−RT transmission up/down), and
the external differential efficiency is η<sub>d</sub> = η<sub>i</sub> × RT transmission / RT gain (slope efficiency η<sub>d</sub> hν/q in W/A).</p>
<h3>Cavity length, penetration depth and confinement (course notes)</h3>
<p>The Results tab also follows the ECE 577 notes (“Vertical Gain and Loss Definitions”) and Coldren &amp; Corzine Appendix 7.
Each DBR's penetration depth comes from the exact quarter-wave expressions</p>
<span class="eq">m<sub>eff</sub> = tanh[m ln(n<sub>2</sub>/n<sub>1</sub>)] / tanh[ln(n<sub>2</sub>/n<sub>1</sub>)],   L<sub>eff</sub> = ½ m<sub>eff</sub> Λ [1/(1+r²) − 1/(2m<sub>eff</sub>)]</span>
<p>measured from the first low-index layer. A high-index mirror layer that touches the cavity is counted in the cavity. The effective length is then
<span class="eq">L = L<sub>cav</sub> + L<sub>eff,1</sub> + L<sub>eff,2</sub>,   Γ = Γ<sub>enh</sub> L<sub>a</sub> / L</span>
from which the modal gain, ⟨α<sub>i</sub>⟩, α<sub>m</sub>, R<sub>up</sub>, R<sub>down</sub> and the cavity optical thickness χ = L n<sub>eff</sub>/λ<sub>0</sub> follow.
The Ch. 3 approximations (tanh(2mr)/2κ, Λ/4r, λ/4Δn) and a penetration depth taken from the computed reflection phase, ½|dφ/dβ|, are shown for comparison.
This Γ is not the same quantity as the energy-weighted Γ further down the table. The two can differ by 10–20%.</p>
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

<h2>Planned</h2>
<ul><li>Phase 2: apertures (oxide / air), effective-index lateral modes, diffraction and scattering loss, 2D modal gain.</li>
<li>User-defined gain spectra g(λ, N) (e.g. from Coldren &amp; Corzine or measurements). The engine already keeps the gain per active layer separate, so this can be added.</li>
<li>Temperature-dependent indices, doping-dependent free-carrier loss tables.</li></ul>
`;
