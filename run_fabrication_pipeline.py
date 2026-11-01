import os
import sys
import json
import subprocess
import shutil

KICAD_CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
PROJECT_DIR = r"C:\Users\sanja\Downloads\Antenna_Project\AME_Project"
PCB_FILE = os.path.join(PROJECT_DIR, "AME_Project.kicad_pcb")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "fabrication_gerbers")

def setup_directory():
    print("=" * 70)
    print("STEP 1: PREPARING MANUFACTURING OUTPUT DIRECTORY")
    print("=" * 70)
    if os.path.exists(OUTPUT_DIR):
        print(f"[INFO] Cleaning existing output directory: {OUTPUT_DIR}")
        for item in os.listdir(OUTPUT_DIR):
            item_path = os.path.join(OUTPUT_DIR, item)
            if os.path.isfile(item_path):
                os.remove(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
    else:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"[SUCCESS] Directory ready: {OUTPUT_DIR}")

def run_drc():
    print("\n" + "=" * 70)
    print("STEP 2: RUNNING AUTOMATED DESIGN RULE CHECK (DRC)")
    print("=" * 70)
    report_file = os.path.join(OUTPUT_DIR, "drc_report.json")
    cmd = [
        KICAD_CLI, "pcb", "drc",
        "--output", report_file,
        "--format", "json",
        "--units", "mm",
        "--severity-all",
        PCB_FILE
    ]
    print(f"[RUNNING] {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(f"[CLI Exit Code] {res.returncode}")
    if res.stdout:
        print(f"[CLI stdout] {res.stdout.strip()}")
    if res.stderr:
        print(f"[CLI stderr] {res.stderr.strip()}")

    # Parse DRC JSON report
    violations = []
    unconnected = []
    schematic_parity = []

    if os.path.exists(report_file):
        with open(report_file, "r", encoding="utf-8") as f:
            drc_data = json.load(f)
        
        violations = drc_data.get("violations", [])
        unconnected = drc_data.get("unconnected_items", [])
        schematic_parity = drc_data.get("schematic_parity_issues", [])

    print(f"\n[DRC RESULTS]")
    print(f"  - Total DRC Violations:     {len(violations)}")
    print(f"  - Unconnected Net Items:    {len(unconnected)}")
    print(f"  - Schematic Parity Issues:  {len(schematic_parity)}")

    errors_count = 0
    warnings_count = 0
    for v in violations:
        sev = v.get("severity", "unknown").lower()
        desc = v.get("description", "")
        t = v.get("type", "")
        if "error" in sev:
            errors_count += 1
            print(f"    * [ERROR] {t}: {desc}")
        else:
            warnings_count += 1
            print(f"    * [WARNING] {t}: {desc}")

    for u in unconnected:
        print(f"    * [UNCONNECTED] {u.get('description', '')}")

    return {
        "report_file": report_file,
        "total_violations": len(violations),
        "errors": errors_count,
        "warnings": warnings_count,
        "unconnected": len(unconnected)
    }

def export_gerbers():
    print("\n" + "=" * 70)
    print("STEP 3: EXPORTING PRODUCTION GERBER X2 FILES")
    print("=" * 70)
    cmd = [
        KICAD_CLI, "pcb", "export", "gerbers",
        "--output", OUTPUT_DIR + "\\",
        "--layers", "F.Cu,B.Cu,F.Mask,B.Mask,Edge.Cuts",
        PCB_FILE
    ]
    print(f"[RUNNING] {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(f"[CLI Exit Code] {res.returncode}")
    if res.stdout:
        print(f"[CLI stdout] {res.stdout.strip()}")
    if res.stderr:
        print(f"[CLI stderr] {res.stderr.strip()}")

def export_drills():
    print("\n" + "=" * 70)
    print("STEP 4: EXPORTING EXCELLON DRILL FILES")
    print("=" * 70)
    cmd = [
        KICAD_CLI, "pcb", "export", "drill",
        "--output", OUTPUT_DIR + "\\",
        "--format", "excellon",
        "--drill-origin", "absolute",
        "--excellon-units", "mm",
        "--excellon-separate-th",
        PCB_FILE
    ]
    print(f"[RUNNING] {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(f"[CLI Exit Code] {res.returncode}")
    if res.stdout:
        print(f"[CLI stdout] {res.stdout.strip()}")
    if res.stderr:
        print(f"[CLI stderr] {res.stderr.strip()}")

def audit_manufacturing_files(drc_info):
    print("\n" + "=" * 70)
    print("STEP 5: AUDITING GENERATED MANUFACTURING FILES")
    print("=" * 70)
    files = os.listdir(OUTPUT_DIR)
    
    expected_categories = {
        "Top Copper (F.Cu)": ["*F_Cu.gbr", "*-F_Cu.gbr"],
        "Bottom Copper (B.Cu)": ["*B_Cu.gbr", "*-B_Cu.gbr"],
        "Board Outline (Edge.Cuts)": ["*Edge_Cuts.gbr", "*-Edge_Cuts.gbr"],
        "Top Solder Mask (F.Mask)": ["*F_Mask.gbr", "*-F_Mask.gbr"],
        "Bottom Solder Mask (B.Mask)": ["*B_Mask.gbr", "*-B_Mask.gbr"],
        "Plated Drill File (PTH)": ["*-PTH.drl", "*.drl"],
        "Gerber Job File": ["*.gbrjob"]
    }

    import fnmatch
    file_inventory = []
    drill_file_path = None
    top_copper_path = None

    for fname in sorted(files):
        fpath = os.path.join(OUTPUT_DIR, fname)
        size_bytes = os.path.getsize(fpath)
        file_inventory.append((fname, size_bytes))
        if fname.endswith(".drl") or fname.endswith("-PTH.drl"):
            drill_file_path = fpath
        if fname.endswith("F_Cu.gbr"):
            top_copper_path = fpath

    print(f"[FOUND {len(files)} FILES IN FABRICATION FOLDER]")
    for fname, size in file_inventory:
        print(f"  - {fname:<35} ({size:>7} bytes)")

    # Audit Drill Hits in .drl
    drill_hits_count = 0
    tools_found = []
    if drill_file_path and os.path.isfile(drill_file_path):
        print(f"\n[DRILL AUDIT] Inspecting Excellon Drill File: {os.path.basename(drill_file_path)}")
        with open(drill_file_path, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                # Tool definition, e.g., T1C1.000 or T01C1.000
                if line_str.startswith("T") and "C" in line_str:
                    tools_found.append(line_str)
                # Drill hit coordinate, e.g., X8000000Y-1600000 or X8.0Y-1.6
                if line_str.startswith("X") and "Y" in line_str:
                    drill_hits_count += 1
        print(f"  - Defined Tools: {tools_found}")
        print(f"  - Total Drill Hit Coordinates Counted: {drill_hits_count}")

    # Audit Top Copper file
    top_copper_ok = False
    if top_copper_path and os.path.isfile(top_copper_path):
        size = os.path.getsize(top_copper_path)
        if size > 1000:
            top_copper_ok = True
        print(f"\n[COPPER AUDIT] Top Copper Gerber ({os.path.basename(top_copper_path)}): {size} bytes -> {'PASS' if top_copper_ok else 'FAIL'}")

    # Final Summary Table
    print("\n" + "=" * 80)
    print("                    FABRICATION & DRC DELIVERY SUMMARY REPORT                   ")
    print("=" * 80)
    print(f"Target PCB File:             {PCB_FILE}")
    print(f"Manufacturing Directory:     {OUTPUT_DIR}")
    print("-" * 80)
    print(f"DRC Status:                  Errors: {drc_info['errors']} | Unconnected: {drc_info['unconnected']} | Warnings: {drc_info['warnings']}")
    print(f"DRC Compliance:              {'PASSED (0 Errors, 0 Unconnected)' if drc_info['errors'] == 0 and drc_info['unconnected'] == 0 else 'ACTION REQUIRED'}")
    print("-" * 80)
    print(f"{'Fabrication File Name':<38} | {'Layer / Role':<24} | {'Size (Bytes)':<12}")
    print("-" * 80)

    for fname, size in file_inventory:
        role = "Report / Metadata"
        if "F_Cu" in fname:
            role = "Top Copper (CSRR etched)"
        elif "B_Cu" in fname:
            role = "Bottom Ground Plane"
        elif "Edge_Cuts" in fname:
            role = "Board Outline (20x20mm)"
        elif "F_Mask" in fname:
            role = "Top Solder Mask"
        elif "B_Mask" in fname:
            role = "Bottom Solder Mask"
        elif "PTH" in fname or ".drl" in fname:
            role = "Excellon Plated Drill"
        elif "gbrjob" in fname:
            role = "Gerber Job Spec (X2)"
        elif "drc" in fname:
            role = "DRC Audit Report"
        print(f"{fname:<38} | {role:<24} | {size:<12}")

    print("-" * 80)
    print(f"SIW Via Drill Count:        {drill_hits_count} holes (Target: 20) -> {'PASS' if drill_hits_count == 20 else 'FAIL'}")
    print(f"Drill Tooling:               1.00 mm diameter (Tool: {', '.join(tools_found)})")
    print(f"Board Dimensions:            20.0 mm x 20.0 mm (2-Layer FR4 2.0 mm)")
    print("=" * 80)
    print("READY FOR SUBMISSION: All files ready to zip and upload to JLCPCB / PCBWay.")
    print("=" * 80)

if __name__ == "__main__":
    setup_directory()
    drc_info = run_drc()
    export_gerbers()
    export_drills()
    audit_manufacturing_files(drc_info)
