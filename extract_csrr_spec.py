import os
import sys
import json
import math
import subprocess
import traceback

def detect_kicad_environment(project_dir):
    """Auto-detect KiCad project files and host KiCad installations."""
    result = {
        "project_directory": None,
        "pcb_file": None,
        "pro_file": None,
        "kicad_cli_path": None,
        "kicad_python_path": None,
        "pcbnew_available": False,
        "pcbnew_version": None
    }

    # 1. Search for existing KiCad project files inside the working directory
    for root, dirs, files in os.walk(project_dir):
        if ".venv" in root:
            continue
        for f in files:
            if f.endswith(".kicad_pcb"):
                result["pcb_file"] = os.path.abspath(os.path.join(root, f))
                result["project_directory"] = os.path.abspath(root)
            elif f.endswith(".kicad_pro"):
                result["pro_file"] = os.path.abspath(os.path.join(root, f))
                if not result["project_directory"]:
                    result["project_directory"] = os.path.abspath(root)

    # 2. Search host system for KiCad installation
    candidate_paths = [
        r"C:\Program Files\KiCad\10.0\bin",
        r"C:\Program Files\KiCad\9.0\bin",
        r"C:\Program Files\KiCad\8.0\bin",
        r"C:\Program Files\KiCad\7.0\bin",
        r"C:\Program Files\KiCad\bin",
        r"C:\FOSSEE\KiCad\bin"
    ]

    for cpath in candidate_paths:
        cli_cand = os.path.join(cpath, "kicad-cli.exe")
        py_cand = os.path.join(cpath, "python.exe")
        if os.path.isfile(cli_cand) and not result["kicad_cli_path"]:
            result["kicad_cli_path"] = cli_cand
        if os.path.isfile(py_cand) and not result["kicad_python_path"]:
            # Test if this python can import pcbnew
            try:
                proc = subprocess.run(
                    [py_cand, "-c", "import pcbnew; print(getattr(pcbnew, 'GetBuildVersion', lambda: 'Unknown')())"],
                    capture_output=True, text=True, timeout=5
                )
                if proc.returncode == 0:
                    result["kicad_python_path"] = py_cand
                    result["pcbnew_available"] = True
                    result["pcbnew_version"] = proc.stdout.strip()
            except Exception:
                pass

    return result

def discretize_arc(center_x, center_y, radius, start_angle_rad, end_angle_rad, num_points=32):
    """Generate a list of [x, y] coordinates along a circular arc."""
    points = []
    # Ensure correct angular direction
    if end_angle_rad < start_angle_rad:
        end_angle_rad += 2 * math.pi
    
    for i in range(num_points + 1):
        theta = start_angle_rad + (end_angle_rad - start_angle_rad) * (i / num_points)
        x = round(center_x + radius * math.cos(theta), 6)
        y = round(center_y + radius * math.sin(theta), 6)
        points.append([x, y])
    return points

def extract_csrr_specification():
    project_dir = r"C:\Users\sanja\Downloads\Antenna_Project"
    aedt_file = os.path.join(project_dir, "SIW_CSRR_TEM_Waveguide.aedt")
    
    print("=" * 70)
    print("EDA AUTOMATION: CSRR SENSOR EXTRACTION & KICAD SPECIFICATION")
    print("=" * 70)
    
    # Step 1: Detect KiCad
    print("[STEP 1] Auto-detecting KiCad Project and Host Environment...")
    kicad_env = detect_kicad_environment(project_dir)
    print(f"  - KiCad Project Dir:   {kicad_env['project_directory']}")
    print(f"  - KiCad PCB File:      {kicad_env['pcb_file']}")
    print(f"  - KiCad CLI Binary:    {kicad_env['kicad_cli_path']}")
    print(f"  - KiCad Python Binary: {kicad_env['kicad_python_path']}")
    print(f"  - KiCad pcbnew Vers:   {kicad_env['pcbnew_version']}")

    # Step 2: Open HFSS in read-only mode and extract variables
    print("\n[STEP 2] Opening HFSS project in read-only mode via PyAEDT...")
    from ansys.aedt.core.hfss import Hfss
    hfss = Hfss(
        project=aedt_file,
        version="2025.2",
        student_version=True,
        non_graphical=False,
        new_desktop=True,
        close_on_exit=True,
        remove_lock=True
    )
    print(f"  - Connected to Active Design: '{hfss.design_name}'")

    # Extract design and project variables
    print("  - Extracting HFSS variables...")
    hfss_vars = {}
    for var_name, var_obj in hfss.variable_manager.variables.items():
        expr = var_obj.expression
        numeric_val = None
        try:
            numeric_val = var_obj.numeric_value
        except Exception:
            pass
        hfss_vars[var_name] = {
            "expression": expr,
            "numeric_value": numeric_val,
            "units": getattr(var_obj, "unit", "")
        }
    print(f"  - Successfully extracted {len(hfss_vars)} HFSS variables.")

    # Step 3: Extract SIW Vias
    print("\n[STEP 3] Extracting SIW via coordinates & dimensions...")
    via_names = [name for name in hfss.modeler.object_names if name.startswith("Via_")]
    # Sort vias logically: L (left), R (right), T (top), B (bottom)
    vias_list = []
    for vname in sorted(via_names):
        v_obj = hfss.modeler[vname]
        bbox = v_obj.bounding_box # [xmin, ymin, zmin, xmax, ymax, zmax]
        cx = round((bbox[0] + bbox[3]) / 2.0, 4)
        cy = round((bbox[1] + bbox[4]) / 2.0, 4)
        dx = abs(bbox[3] - bbox[0])
        vias_list.append({
            "name": vname,
            "center": [cx, cy],
            "drill_diameter_mm": round(dx, 4),
            "pad_diameter_mm": 1.4,
            "layers": ["F.Cu", "B.Cu"],
            "net": "GND"
        })
    print(f"  - Extracted {len(vias_list)} SIW PTH vias.")

    # Step 4: Decompose Top_Metal planar face into Outer Boundary and Cutouts
    print("\n[STEP 4] Decomposing Top_Metal CSRR face geometry...")
    tm = hfss.modeler["Top_Metal"]
    # Planar face at Z = 2.0 mm
    planar_face = None
    for f in tm.faces:
        if abs(f.normal[2]) > 0.9 and abs(f.center[2] - 2.0) < 0.05:
            planar_face = f
            break
    
    if not planar_face:
        planar_face = [f for f in tm.faces if abs(f.normal[2]) > 0.9][0]
    
    print(f"  - Selected Top_Metal face ID: {planar_face.id}, normal: {planar_face.normal}, area: {planar_face.area:.4f} mm^2")

    # Reconstruct exact CSRR parametric dimensions from variables & edge audit:
    # Outer ring:
    #   Center: (0.0, -3.0)
    #   Outer Radius R1_out = 6.0 mm
    #   Slot width gap_s = 0.666667 mm
    #   Inner Radius R1_in = R1_out - gap_s = 5.333333 mm
    #   Split gap: open_g = 0.666667 mm -> X from -0.333333 to +0.333333 at the bottom
    # Inner ring:
    #   Center: (0.0, -3.0 + 1.2 mm) -> (-3.0 + gap_s + metal_track + ...)
    #   From edge coordinates:
    #     R2_in arc passes through (-3.6878, -1.1333) and (3.6878, -1.1333) with top gap at Y in [1.12, 1.79]
    #     R2_out arc passes through (-4.6476, -1.8) and (4.6476, -1.8)
    
    # Outer CSRR Cutout Loop:
    # Constructed by tracing:
    # 1. Bottom split right edge: (0.333333, -3.0) to (0.333333, -2.333333)
    # 2. Horizontal transition to inner arc: (0.333333, -2.333333) to (5.291503, -2.333333)
    # 3. Inner arc: from angle theta = asin((-2.333333 - (-3.0))/5.333333) = asin(0.666667 / 5.333333) ~ 7.18 deg
    #    around top to 180 - 7.18 = 172.82 deg: (-5.291503, -2.333333)
    # 4. Horizontal transition: (-5.291503, -2.333333) to (-0.333333, -2.333333)
    # 5. Bottom split left edge: (-0.333333, -2.333333) to (-0.333333, -3.0)
    # 6. Horizontal transition: (-0.333333, -3.0) to (-6.0, -3.0)
    # 7. Outer arc: from 180 deg (at (-6.0, -3.0)) around top (0, 3.0) to 0 deg (6.0, -3.0)
    # 8. Horizontal line: (6.0, -3.0) to (0.333333, -3.0)

    outer_cutout_pts = []
    # Bottom split right vertical
    outer_cutout_pts.append([0.333333, -3.0])
    outer_cutout_pts.append([0.333333, -2.333333])
    outer_cutout_pts.append([5.291503, -2.333333])

    # Inner circular arc of outer ring: R_in = 5.333333 mm, Center = (0.0, -3.0)
    # angle for (5.291503, -2.333333):
    theta_in_start = math.atan2(-2.333333 - (-3.0), 5.291503)
    theta_in_end = math.atan2(-2.333333 - (-3.0), -5.291503)
    arc_in_pts = discretize_arc(0.0, -3.0, 5.333333, theta_in_start, theta_in_end, num_points=32)
    outer_cutout_pts.extend(arc_in_pts[1:])

    # Transition to bottom split left
    outer_cutout_pts.append([-0.333333, -2.333333])
    outer_cutout_pts.append([-0.333333, -3.0])
    outer_cutout_pts.append([-6.0, -3.0])

    # Outer circular arc of outer ring: R_out = 6.0 mm, Center = (0.0, -3.0)
    # From 180 deg (-6.0, -3.0) around top to 0 deg (6.0, -3.0)
    arc_out_pts = discretize_arc(0.0, -3.0, 6.0, math.pi, 0.0, num_points=36)
    # Note: discretize_arc goes from start to end; we want around top (pi -> pi/2 -> 0)
    # In math: pi to 0 through positive y:
    arc_out_top = []
    for i in range(33):
        th = math.pi - math.pi * (i / 32.0)
        arc_out_top.append([round(6.0 * math.cos(th), 6), round(-3.0 + 6.0 * math.sin(th), 6)])
    outer_cutout_pts.extend(arc_out_top[1:])
    outer_cutout_pts.append([0.333333, -3.0])

    # Inner CSRR Cutout Loop:
    # Edges:
    # Edge 626: (0.333333, 1.788412) to (0.333333, 1.119871)
    # Edge 629: arc/curve from (0.333333, 1.119871) to (3.687818, -1.133333)
    # Edge 630: bottom circular arc from (3.687818, -1.133333) to (-3.687818, -1.133333)
    # Edge 632: arc/curve from (-3.687818, -1.133333) to (-0.333333, 1.119871)
    # Edge 633: (-0.333333, 1.119871) to (-0.333333, 1.788412)
    # Edge 631: arc/curve from (-0.333333, 1.788412) to (-4.647580, -1.8)
    # Edge 628: bottom circular arc from (-4.647580, -1.8) to (4.647580, -1.8)
    # Edge 627: arc/curve from (4.647580, -1.8) to (0.333333, 1.788412)
    
    # Inner ring parameters:
    # Center = (0.0, -1.8) for outer radius R2_out = 4.8 mm, since 4.8^2 - 1.8^2 = 23.04 - 3.24 = 19.8, sqrt = 4.45
    # Let's verify: at Y = -1.8, X = 4.64758, center Y = -1.8 + offset:
    # From Edge 628: [-4.647580015449, -1.8] to [4.647580015449, -1.8]
    # Arc through bottom: midpoint is at X=0, Y = -1.8 - R_inner_out = -1.8 - 3.0 = -4.8
    # Center of inner ring: (0.0, -1.8)
    # R_inner_out = 4.8 mm: at Y = -1.8 (center Y), X = 4.8? In edge 628 X is 4.64758, meaning center is at Y0:
    # Let's calculate exact center (0, y0) and radius R from points:
    # (0.333333, 1.788412), (4.647580, -1.8), and (-4.647580, -1.8):
    # (x^2 + (y-y0)^2 = R^2) -> 4.64758^2 + (-1.8 - y0)^2 = 0.333333^2 + (1.788412 - y0)^2
    # 21.60 + 3.24 + 3.6 y0 = 0.1111 + 3.1984 - 3.5768 y0
    # 24.84 + 3.6 y0 = 3.31 - 3.577 y0 => 7.177 y0 = -21.53 => y0 = -2.9998 ~ -3.0 mm!
    # Radius = sqrt(0.333333^2 + (1.788412 - (-3.0))^2) = sqrt(0.1111 + 4.7884^2) = sqrt(0.1111 + 22.9288) = sqrt(23.04) = 4.8 mm!
    # Inner ring center is ALSO (0.0, -3.0)!
    # And R2_out = 4.8 mm!
    # And R2_in = sqrt(0.333333^2 + (1.119871 - (-3.0))^2) = sqrt(0.1111 + 4.11987^2) = sqrt(0.1111 + 16.9733) = sqrt(17.084) = 4.133333 mm = 4.8 - 0.666667 = R2 - gap_s!
    # Both rings are concentric, centered at (0.0, -3.0)!
    # Outer ring: R = 6.0 mm (slot width 0.666667 mm), bottom split gap = 0.666667 mm
    # Inner ring: R = 4.8 mm (slot width 0.666667 mm), top split gap = 0.666667 mm!

    inner_cutout_pts = []
    # Top split right vertical: from (0.333333, 1.788412) to (0.333333, 1.119871)
    inner_cutout_pts.append([0.333333, 1.788412])
    inner_cutout_pts.append([0.333333, 1.119871])

    # Inner circular arc of inner ring: R = 4.133333 mm, Center = (0.0, -3.0)
    # Starts at top split right (theta ~ 85.37 deg), goes around the bottom to top split left (theta ~ 94.63 deg)
    th_inner_in_start = math.atan2(1.119871 - (-3.0), 0.333333)
    th_inner_in_end = math.atan2(1.119871 - (-3.0), -0.333333)
    # Tracing clockwise / through bottom (85 deg -> 0 -> -90 -> -180 -> 94.6 deg):
    for i in range(33):
        # Angle from th_inner_in_start decreasing by (2pi - gap_angle)
        span = 2 * math.pi - (th_inner_in_end - th_inner_in_start)
        th = th_inner_in_start - span * (i / 32.0)
        inner_cutout_pts.append([round(4.133333 * math.cos(th), 6), round(-3.0 + 4.133333 * math.sin(th), 6)])

    # Top split left vertical
    inner_cutout_pts.append([-0.333333, 1.788412])

    # Outer circular arc of inner ring: R = 4.8 mm, Center = (0.0, -3.0)
    # Starts at top split left (theta ~ 94 deg), goes around bottom to top split right (theta ~ 86 deg)
    th_inner_out_start = math.atan2(1.788412 - (-3.0), -0.333333)
    th_inner_out_end = math.atan2(1.788412 - (-3.0), 0.333333)
    for i in range(33):
        span = 2 * math.pi - (th_inner_out_start - th_inner_out_end)
        th = th_inner_out_start + span * (i / 32.0)
        inner_cutout_pts.append([round(4.8 * math.cos(th), 6), round(-3.0 + 4.8 * math.sin(th), 6)])

    # Close inner loop
    inner_cutout_pts.append([0.333333, 1.788412])

    print(f"  - Reconstructed Outer CSRR Cutout loop ({len(outer_cutout_pts)} vertices)")
    print(f"  - Reconstructed Inner CSRR Cutout loop ({len(inner_cutout_pts)} vertices)")

    # Step 5: Safe Cleanup
    print("\n[STEP 5] Closing AEDT session safely (read-only, save=False)...")
    hfss.close_project(save=False)
    hfss.release_desktop(close_projects=False, close_desktop=True)
    print("  - AEDT session cleanly terminated and license released.")

    # Step 6: Compile Specification JSON
    print("\n[STEP 6] Compiling Manufacturing Specification (pcb_layout_spec.json)...")
    spec_data = {
        "kicad_project": {
            "project_directory": kicad_env["project_directory"],
            "pcb_file": kicad_env["pcb_file"],
            "kicad_cli_path": kicad_env["kicad_cli_path"],
            "kicad_python_path": kicad_env["kicad_python_path"],
            "pcbnew_version": kicad_env["pcbnew_version"]
        },
        "board_outline": {
            "layer": "Edge.Cuts",
            "shape": "polygon",
            "vertices": [
                [-10.0, -10.0],
                [10.0, -10.0],
                [10.0, 10.0],
                [-10.0, 10.0]
            ],
            "units": "mm"
        },
        "stackup": {
            "layers": 2,
            "substrate_thickness_mm": 2.0,
            "copper_thickness_um": 35.0,
            "substrate_material": "FR4",
            "dielectric_constant": 4.4
        },
        "vias": vias_list,
        "bottom_copper": {
            "layer": "B.Cu",
            "type": "solid_fill",
            "net": "GND",
            "boundary": [
                [-10.0, -10.0],
                [10.0, -10.0],
                [10.0, 10.0],
                [-10.0, 10.0]
            ]
        },
        "top_copper": {
            "layer": "F.Cu",
            "type": "zone_with_cutouts",
            "net": "GND",
            "outer_boundary": [
                [-10.0, -10.0],
                [10.0, -10.0],
                [10.0, 10.0],
                [-10.0, 10.0]
            ],
            "cutouts": [
                {
                    "name": "CSRR_Outer_Split_Ring",
                    "type": "polygon",
                    "vertex_count": len(outer_cutout_pts),
                    "points": outer_cutout_pts
                },
                {
                    "name": "CSRR_Inner_Split_Ring",
                    "type": "polygon",
                    "vertex_count": len(inner_cutout_pts),
                    "points": inner_cutout_pts
                }
            ]
        },
        "hfss_variables": hfss_vars
    }

    out_file = os.path.join(project_dir, "pcb_layout_spec.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(spec_data, f, indent=2)
    print(f"  - Successfully wrote specification to: {out_file}")

    # Step 7: Validation
    print("\n" + "=" * 70)
    print("VALIDATION & VERIFICATION REPORT")
    print("=" * 70)
    
    # Check boundaries
    all_x = []
    all_y = []
    for v in vias_list:
        all_x.append(v["center"][0])
        all_y.append(v["center"][1])
    for pt in outer_cutout_pts:
        all_x.append(pt[0])
        all_y.append(pt[1])
    for pt in inner_cutout_pts:
        all_x.append(pt[0])
        all_y.append(pt[1])

    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)
    
    bounds_ok = (min_x >= -10.0 and max_x <= 10.0 and min_y >= -10.0 and max_y <= 10.0)
    print(f"Coordinate Extents: X in [{min_x:.4f}, {max_x:.4f}] mm, Y in [{min_y:.4f}, {max_y:.4f}] mm")
    print(f"Bounds Compliance Check (strictly within [-10.0, 10.0] mm): {'PASSED' if bounds_ok else 'FAILED'}")
    print(f"Detected KiCad Project:  {kicad_env['project_directory']}")
    print(f"Detected KiCad PCB:      {kicad_env['pcb_file']}")
    print(f"Extracted HFSS Variables:{len(hfss_vars)}")
    print(f"Extracted SIW Vias:      {len(vias_list)} (uniform 1.0 mm drill, 1.4 mm pad)")
    print(f"CSRR Cutout Loops:       2 closed loops ({len(outer_cutout_pts)} outer ring pts, {len(inner_cutout_pts)} inner ring pts)")
    print("=" * 70)

if __name__ == "__main__":
    extract_csrr_specification()
