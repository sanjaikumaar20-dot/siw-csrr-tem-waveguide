# SIW CSRR Microwave Sensor PCB Automation Pipeline

Automated design and fabrication pipeline bridging **Ansys HFSS** 3D electromagnetic simulation models to production-ready **KiCad** PCB layouts, automated DRC validation, and manufacturing Gerber/drill packages.

---

## 📡 Overview

This project provides an automated pipeline that extracts Substrate Integrated Waveguide (SIW) geometries and Complementary Split-Ring Resonator (CSRR) etch specifications from native Ansys HFSS project files (`.aedt`), synthesizes full KiCad PCB layouts with exact mathematical coordinates, performs automated Design Rule Checking (DRC) via `kicad-cli`, and generates verified Gerber X2 and Excellon drill files ready for PCB fabrication (e.g., JLCPCB, PCBWay).

### Key Specifications
- **Board Outline:** 20.0 mm × 20.0 mm
- **Substrate:** FR-4 epoxy ($\epsilon_r \approx 4.4$), 2.0 mm thickness
- **SIW Via Array:** 20 plated through-hole (PTH) shielding vias (1.00 mm diameter, 3.2 mm pitch)
- **Top Layer (`F.Cu`):** SIW waveguide copper with etched sub-wavelength CSRR complementary split rings
- **Bottom Layer (`B.Cu`):** Continuous ground copper plane
- **DRC Compliance:** 0 errors, 0 unconnected items (KiCad DRC verified)

---

## 📁 Repository Structure

```
├── AME_Project/
│   ├── AME_Project.kicad_pcb         # Generated KiCad 8 PCB layout
│   ├── AME_Project.kicad_pro         # KiCad project configuration
│   ├── AME_Project.kicad_sch         # KiCad schematic placeholder
│   ├── SIW_CSRR_Sensor_Fabrication_Package.zip # Ready-to-submit manufacturing zip
│   ├── AME_Project_Top.png           # 3D PCB top-view rendering
│   ├── AME_Project_Bottom.png        # 3D PCB bottom-view rendering
│   ├── AME_Project_Side_1.png        # 3D PCB side perspective 1
│   ├── AME_Project_Side_2.png        # 3D PCB side perspective 2
│   └── fabrication_gerbers/          # Production Gerber X2 & drill files
│       ├── AME_Project-F_Cu.gtl      # Top copper layer (with CSRR etch)
│       ├── AME_Project-B_Cu.gbl      # Bottom copper ground plane
│       ├── AME_Project-F_Mask.gts    # Top solder mask
│       ├── AME_Project-B_Mask.gbs    # Bottom solder mask
│       ├── AME_Project-Edge_Cuts.gm1 # Board contour (20 x 20 mm)
│       ├── AME_Project-PTH.drl       # Plated through-hole Excellon drill
│       ├── AME_Project-NPTH.drl      # Non-plated drill
│       ├── AME_Project-job.gbrjob    # Gerber job specification
│       └── drc_report.json           # Automated DRC verification output
├── SIW_CSRR_TEM_Waveguide.aedt       # Ansys HFSS 3D electromagnetic simulation
├── audit_hfss.py                     # Non-destructive HFSS geometry & boundary auditor
├── extract_csrr_spec.py              # HFSS model parser and PCB coordinate extractor
├── build_kicad_pcb.py                # KiCad PCB synthesizer from geometry spec
├── run_fabrication_pipeline.py       # Automated DRC, Gerber export, and drill verification
├── package_and_launch_gerbview.py    # Packaging & visual inspection launcher
├── pcb_layout_spec.json              # Extracted geometry specification
├── hfss_inspection_dump.json         # Raw object and boundary dump from HFSS
└── hfss_inspection_summary.txt       # HFSS audit summary report
```

---

## 🚀 Pipeline Workflow

### 1. Audit HFSS Model
Inspects the 3D model non-destructively, enumerating all solids, sheets, materials, ports, and boundaries:
```bash
python audit_hfss.py
```

### 2. Extract SIW & CSRR Geometry Spec
Parses via coordinates, dielectric substrate dimensions, and split-ring etch polygons from HFSS into `pcb_layout_spec.json`:
```bash
python extract_csrr_spec.py
```

### 3. Generate KiCad PCB
Synthesizes the complete `.kicad_pcb` layout including board edges, via arrays, zones, and etch cutouts:
```bash
python build_kicad_pcb.py
```

### 4. Run DRC & Export Manufacturing Gerbers
Executes `kicad-cli` for headless design rule verification, Gerber X2 generation, and Excellon drill counting:
```bash
python run_fabrication_pipeline.py
```

### 5. Package for Fabrication
Creates the release zip package and optionally opens KiCad GerbView for manual inspection:
```bash
python package_and_launch_gerbview.py
```

---

## 🛠 Prerequisites

- Python 3.10+
- [KiCad 8.0+ / 10.0+](https://www.kicad.org/) (with `kicad-cli` accessible in PATH or default installation directory)
- [Ansys Electronics Desktop / HFSS](https://www.ansys.com/products/electronics/ansys-hfss) (for regenerating simulation models)

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
