import os
import sys
import json
import traceback

def test_pcbnew_import():
    """Verify if pcbnew (KiCad Python API) is available in the environment."""
    try:
        import pcbnew
        version = getattr(pcbnew, "GetBuildVersion", lambda: "Unknown")()
        return True, f"pcbnew successfully imported (KiCad version: {version})"
    except ImportError as e:
        return False, f"pcbnew could not be imported ({e}). KiCad Python API is isolated to its standalone installation."

def audit_project(project_path):
    print("=" * 60)
    print("STARTING HFSS GEOMETRY & PROPERTY AUDIT VIA PyAEDT")
    print("=" * 60)
    print(f"[INFO] Target project: {project_path}")

    # 1. Check KiCad Python API
    pcbnew_found, pcbnew_msg = test_pcbnew_import()
    print(f"[INFO] KiCad check: {pcbnew_msg}")

    dump_data = {
        "project_path": project_path,
        "kicad_api_status": pcbnew_msg,
        "metadata": {},
        "coordinate_systems": [],
        "geometry_inventory": [],
        "boundaries": [],
        "excitations": [],
        "boolean_etch_features": []
    }

    try:
        import pyaedt
        from ansys.aedt.core.hfss import Hfss
        print(f"[INFO] PyAEDT version: {pyaedt.__version__}")
    except ImportError as e:
        err_msg = f"Failed to import PyAEDT: {e}\n{traceback.format_exc()}"
        print(f"[ERROR] {err_msg}")
        with open("hfss_inspection_error.log", "w", encoding="utf-8") as f:
            f.write(err_msg)
        return

    # Check student version environment
    version = "2025.2"
    student_ver = True

    print(f"[INFO] Initializing Hfss (version={version}, student_version={student_ver}, non_graphical=False, remove_lock=True)...")
    hfss = None

    try:
        # Initialize HFSS in read-only non-destructive mode
        hfss = Hfss(
            project=project_path,
            version=version,
            student_version=student_ver,
            non_graphical=False,
            new_desktop=True,
            close_on_exit=True,
            remove_lock=True
        )
        print(f"[INFO] Successfully connected to project: '{hfss.project_name}', design: '{hfss.design_name}'")

        # 3. Extract Model Metadata & Coordinate Space
        modeler = hfss.modeler
        units = modeler.model_units
        print(f"[INFO] Modeler units: {units}")

        try:
            bbox = modeler.get_model_bounding_box()
        except Exception:
            try:
                bbox = modeler.bounding_box
            except Exception:
                bbox = None
        print(f"[INFO] Model bounding box [Xmin, Ymin, Zmin, Xmax, Ymax, Zmax]: {bbox}")

        dump_data["metadata"] = {
            "project_name": hfss.project_name,
            "design_name": hfss.design_name,
            "solution_type": getattr(hfss, "solution_type", "Unknown"),
            "model_units": units,
            "bounding_box": bbox
        }

        # Coordinate systems
        cs_list = []
        try:
            cs_objects = getattr(modeler, "coordinate_systems", [])
            for cs in cs_objects:
                cs_data = {
                    "name": getattr(cs, "name", str(cs)),
                    "origin": getattr(cs, "origin", None),
                    "x_axis": getattr(cs, "x_axis", None),
                    "y_axis": getattr(cs, "y_axis", None),
                    "z_axis": getattr(cs, "z_axis", None),
                    "props": getattr(cs, "props", {})
                }
                cs_list.append(cs_data)
        except Exception as e:
            print(f"[WARN] Error fetching coordinate systems: {e}")
        dump_data["coordinate_systems"] = cs_list
        print(f"[INFO] Extracted {len(cs_list)} coordinate system(s)")

        # 4. Geometry & Feature Inventory
        obj_names = modeler.object_names
        print(f"[INFO] Total model objects to inspect: {len(obj_names)}")

        solids_count = 0
        sheets_count = 0
        vias_count = 0
        boolean_features = []

        for name in obj_names:
            try:
                obj = modeler[name]
            except Exception as e:
                print(f"[WARN] Could not access object '{name}': {e}")
                continue

            obj_id = getattr(obj, "id", None)
            mat = getattr(obj, "material_name", "Unknown")
            solve_inside = getattr(obj, "solve_inside", None)
            is3d = getattr(obj, "is3d", None)
            obj_type = getattr(obj, "object_type", "Solid" if is3d else "Sheet")
            obj_bbox = getattr(obj, "bounding_box", None)
            obj_bdims = getattr(obj, "bounding_dimension", None)
            vol = getattr(obj, "volume", None)

            # Check history / operations if available
            op_history = []
            try:
                h_res = obj.history()
                if h_res:
                    if hasattr(h_res, "command"):
                        op_history = h_res.command
                    elif isinstance(h_res, (list, tuple)):
                        op_history = [str(x) for x in h_res]
                    elif isinstance(h_res, dict):
                        op_history = list(h_res.keys())
                    else:
                        op_history = [str(h_res)]
            except Exception:
                pass

            item_data = {
                "id": obj_id,
                "name": name,
                "material": mat,
                "solve_inside": solve_inside,
                "is_solid": is3d,
                "geometry_type": obj_type,
                "bounding_box": obj_bbox,
                "bounding_dimensions": obj_bdims,
                "volume": vol,
                "history_operations": op_history,
                "specific_attributes": {}
            }

            # Check if Cylinder / SIW Via
            is_via = False
            lower_name = name.lower()
            if "via" in lower_name or "cyl" in lower_name:
                is_via = True
            elif op_history and any("cylinder" in str(op).lower() for op in op_history):
                is_via = True

            if is_via and obj_bbox and len(obj_bbox) == 6:
                vias_count += 1
                dx = abs(obj_bbox[3] - obj_bbox[0])
                dy = abs(obj_bbox[4] - obj_bbox[1])
                dz = abs(obj_bbox[5] - obj_bbox[2])

                # Identify axis and radius
                if abs(dx - dy) < 1e-4 and dz > 0:
                    axis = "Z"
                    radius = dx / 2.0
                    height = dz
                    center = [(obj_bbox[0] + obj_bbox[3]) / 2.0, (obj_bbox[1] + obj_bbox[4]) / 2.0, obj_bbox[2]]
                elif abs(dx - dz) < 1e-4 and dy > 0:
                    axis = "Y"
                    radius = dx / 2.0
                    height = dy
                    center = [(obj_bbox[0] + obj_bbox[3]) / 2.0, obj_bbox[1], (obj_bbox[2] + obj_bbox[5]) / 2.0]
                elif abs(dy - dz) < 1e-4 and dx > 0:
                    axis = "X"
                    radius = dy / 2.0
                    height = dx
                    center = [obj_bbox[0], (obj_bbox[1] + obj_bbox[4]) / 2.0, (obj_bbox[2] + obj_bbox[5]) / 2.0]
                else:
                    axis = "Z"
                    radius = min(dx, dy) / 2.0
                    height = dz
                    center = [(obj_bbox[0] + obj_bbox[3]) / 2.0, (obj_bbox[1] + obj_bbox[4]) / 2.0, obj_bbox[2]]

                item_data["specific_attributes"]["cylinder"] = {
                    "is_siw_via": True,
                    "center": center,
                    "radius": radius,
                    "diameter": radius * 2.0,
                    "height": height,
                    "orientation_axis": axis
                }

            # Check if Sheet or thin plate
            is_sheet = not is3d or (obj_bdims and min(obj_bdims) < 0.05) or "metal" in lower_name or "sheet" in lower_name
            if is_sheet:
                sheets_count += 1
                sheet_dict = {}
                try:
                    positions = getattr(obj, "vertex_positions", None)
                    if positions is None:
                        positions = [v.position for v in getattr(obj, "vertices", []) if hasattr(v, "position")]
                    sheet_dict["vertex_count"] = len(positions) if positions else 0
                    sheet_dict["vertex_positions"] = positions
                except Exception as e:
                    sheet_dict["vertex_error"] = str(e)

                # Extract surface normals from planar faces
                try:
                    normals = []
                    for f in getattr(obj, "faces", []):
                        fn = getattr(f, "normal", None)
                        if fn:
                            normals.append(fn)
                    sheet_dict["face_normals"] = normals
                except Exception:
                    pass

                item_data["specific_attributes"]["sheet"] = sheet_dict
            else:
                solids_count += 1

            # Detect Boolean / Cutout / Resonator features
            is_cutout = False
            if any(k in lower_name for k in ["csrr", "slot", "ring", "cut", "gap", "split", "sub"]):
                is_cutout = True
            if op_history and any("subtract" in str(op).lower() for op in op_history):
                is_cutout = True

            if is_cutout or "metal" in lower_name:
                # If Top_Metal has multiple faces / complex vertices, it incorporates the etched CSRR rings
                feat_info = {
                    "object_name": name,
                    "material": mat,
                    "history_operations": op_history,
                    "detected_reason": "Matched keyword or boolean subtract in object/structure"
                }
                boolean_features.append(feat_info)

            dump_data["geometry_inventory"].append(item_data)

        dump_data["boolean_etch_features"] = boolean_features

        # Inspect HFSS Boundaries & Excitations via BoundarySetup module
        print("[INFO] Inspecting HFSS boundaries & ports...")
        boundaries_data = []
        excitations_data = []

        try:
            oboundary = hfss.odesign.GetModule("BoundarySetup")
            raw_boundaries = oboundary.GetBoundaries()
            # raw_boundaries is list like ['PE1', 'Perfect E', 'PE2', 'Perfect E', ...]
            if raw_boundaries and len(raw_boundaries) >= 2:
                for i in range(0, len(raw_boundaries), 2):
                    b_name = raw_boundaries[i]
                    b_type = raw_boundaries[i+1] if i+1 < len(raw_boundaries) else "Unknown"
                    try:
                        assigned = oboundary.GetBoundaryAssignment(b_name)
                    except Exception:
                        assigned = []
                    b_info = {
                        "name": b_name,
                        "type": b_type,
                        "assigned_entities": assigned
                    }
                    boundaries_data.append(b_info)

            raw_excitations = oboundary.GetExcitations()
            # raw_excitations is list like ['1:1', 'Lumped Port', '2:1', 'Lumped Port']
            if raw_excitations and len(raw_excitations) >= 2:
                for i in range(0, len(raw_excitations), 2):
                    e_name = raw_excitations[i]
                    e_type = raw_excitations[i+1] if i+1 < len(raw_excitations) else "Unknown"
                    try:
                        assigned = oboundary.GetBoundaryAssignment(e_name)
                    except Exception:
                        assigned = []
                    e_info = {
                        "name": e_name,
                        "type": e_type,
                        "assigned_entities": assigned
                    }
                    excitations_data.append(e_info)
        except Exception as e:
            print(f"[WARN] Error querying BoundarySetup: {e}")

        dump_data["boundaries"] = boundaries_data
        dump_data["excitations"] = excitations_data

        print(f"[INFO] Found {len(boundaries_data)} boundaries and {len(excitations_data)} excitations.")

        # 5. Safe Cleanup: Close project without saving
        print("[INFO] Closing project without saving (strict read-only audit)...")
        hfss.close_project(save=False)
        hfss.release_desktop(close_projects=False, close_desktop=True)
        hfss = None
        print("[INFO] AEDT session closed and released cleanly.")

        # 6. Report Generation
        json_path = os.path.abspath("hfss_inspection_dump.json")
        summary_path = os.path.abspath("hfss_inspection_summary.txt")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(dump_data, f, indent=2)
        print(f"[SUCCESS] JSON inspection dump saved to: {json_path}")

        # Build readable summary
        summary = []
        summary.append("================================================================================")
        summary.append("                  ANSYS HFSS PROJECT NON-DESTRUCTIVE AUDIT REPORT               ")
        summary.append("================================================================================")
        summary.append(f"Project File:        {project_path}")
        summary.append(f"Active Design:       {dump_data['metadata'].get('design_name', 'Unknown')}")
        summary.append(f"Solution Type:       {dump_data['metadata'].get('solution_type', 'Unknown')}")
        summary.append(f"Modeler Units:       {units}")
        summary.append(f"Bounding Box (extents): {bbox}")
        summary.append(f"KiCad Python API:    {pcbnew_msg}")
        summary.append("--------------------------------------------------------------------------------")
        summary.append("\n1. GEOMETRY & OBJECT INVENTORY:")
        summary.append(f"   - Total Objects Analyzed:      {len(dump_data['geometry_inventory'])}")
        summary.append(f"   - Identified SIW Via Cylinders:{vias_count}")
        summary.append(f"   - Identified Sheets/Thin Plates:{sheets_count}")
        summary.append(f"   - Identified 3D Solid Bodies:   {solids_count}")
        summary.append("\n   Detailed Objects Breakdown:")
        for obj in dump_data["geometry_inventory"]:
            cyl = obj["specific_attributes"].get("cylinder")
            sheet = obj["specific_attributes"].get("sheet")
            if cyl:
                summary.append(
                    f"     * [VIA]   {obj['name']:<14} | Mat: {obj['material']:<10} | Axis: {cyl['orientation_axis']} | "
                    f"Dia: {cyl['diameter']:.4f} {units} | H: {cyl['height']:.4f} {units} | Center: {cyl['center']}"
                )
            elif sheet:
                vc = sheet.get("vertex_count", 0)
                summary.append(
                    f"     * [SHEET] {obj['name']:<14} | Mat: {obj['material']:<10} | Vertices: {vc:<3} | "
                    f"BBox: {obj['bounding_box']}"
                )
            else:
                summary.append(
                    f"     * [SOLID] {obj['name']:<14} | Mat: {obj['material']:<10} | SolveInside: {obj['solve_inside']} | "
                    f"BBox: {obj['bounding_box']}"
                )

        summary.append("\n--------------------------------------------------------------------------------")
        summary.append("2. BOUNDARIES & PORT EXCITATIONS:")
        summary.append(f"   - Boundaries Count:  {len(boundaries_data)}")
        for b in boundaries_data:
            summary.append(f"     * {b['name']:<8} | Type: {b['type']:<15} | Assigned Entities: {b['assigned_entities']}")
        summary.append(f"\n   - Excitations (Ports) Count: {len(excitations_data)}")
        for e in excitations_data:
            summary.append(f"     * {e['name']:<8} | Type: {e['type']:<15} | Assigned Entities: {e['assigned_entities']}")

        summary.append("\n--------------------------------------------------------------------------------")
        summary.append("3. BOOLEAN & ETCH / RESONATOR FEATURES:")
        summary.append(f"   - Detected Features/Cutouts Count: {len(boolean_features)}")
        for feat in boolean_features:
            summary.append(f"     * Object: {feat['object_name']} (Material: {feat['material']}) - {feat['detected_reason']}")

        summary.append("\n================================================================================")
        summary.append("AUDIT EXECUTION STATUS: COMPLETED SUCCESSFULLY WITHOUT MODIFICATION")
        summary.append("================================================================================\n")

        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("\n".join(summary))
        print(f"[SUCCESS] Inspection summary written to: {summary_path}")

    except Exception as e:
        err_msg = f"License or COM exception during PyAEDT inspection: {e}\n{traceback.format_exc()}"
        print(f"[ERROR] {err_msg}")
        with open("hfss_inspection_error.log", "w", encoding="utf-8") as f:
            f.write(err_msg)
    finally:
        if hfss is not None:
            try:
                hfss.close_project(save=False)
                hfss.release_desktop(close_projects=False, close_desktop=True)
            except Exception:
                pass

if __name__ == "__main__":
    proj_path = r"C:\Users\sanja\Downloads\Antenna_Project\SIW_CSRR_TEM_Waveguide.aedt"
    audit_project(proj_path)
