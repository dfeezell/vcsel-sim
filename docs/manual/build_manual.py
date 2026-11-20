"""Build the user manual PDF: python docs/manual/build_manual.py

Fills the material table from the engine's catalog into manual.html and prints it to
docs/VCSEL_Simulator_Manual.pdf with headless Chromium (needs node + playwright).
Rebuild whenever a feature or material changes, and commit the PDF with the change."""
import datetime
import html
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from vcsel_sim import materials  # noqa: E402


def materials_table():
    rows = []
    for m in materials.catalog():
        comp = ", ".join(v for v in (m.get("x_label"), m.get("y_label")) if v) or "–"
        rows.append(f"<tr><td><b>{html.escape(m['label'])}</b></td><td>{html.escape(m['category'])}</td>"
                    f"<td>{html.escape(comp)}</td><td>{html.escape(m['reference'])}</td></tr>")
    return ("<table><tr><th style='width:20%'>Material</th><th style='width:11%'>Family</th>"
            "<th style='width:12%'>Composition</th><th>Model / reference</th></tr>" + "".join(rows) + "</table>")


def main():
    src = open(os.path.join(HERE, "manual.html"), encoding="utf-8").read()
    out = src.replace("{{MATERIALS_TABLE}}", materials_table()).replace("{{DATE}}", datetime.date.today().isoformat())
    tmp = os.path.join(HERE, "_build.html")
    open(tmp, "w", encoding="utf-8").write(out)
    pdf = os.path.join(ROOT, "docs", "VCSEL_Simulator_Manual.pdf")
    subprocess.run(["node", os.path.join(HERE, "render_pdf.js"), tmp, pdf], check=True)
    os.remove(tmp)
    print("wrote", pdf)


if __name__ == "__main__":
    main()
