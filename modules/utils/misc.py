import os
from pathlib import Path

def get_schematic_path():
    # get the schematic path from a file inside the project config folder
    project_path = Path(os.environ["PROJECT_PATH"])
    # sch_path = project_path / "testing_kicad_proj" / "test_v8" / "test_v8.kicad_sch"
    sch_path = project_path / "export" / "test.kicad_sch"
    sch_path = str(sch_path)
    # # read the text file and get the path
    # with open(sch_path, "r") as f:
    #     lines = f.readlines()
    #     # get the first line
    #     sch_path = lines[0].strip()
    
    return sch_path

def set_schematic_path(sch_path):
    # set the schematic path to a file inside the project config folder
    project_path = Path(os.environ["PROJECT_PATH"])
    sch_path = project_path / "configs" / "sch_file_path.txt"
    # write the text file and set the path
    with open(sch_path, "w") as f:
        f.write(sch_path)
    
    return sch_path


def get_project_path():
    # get the project path from a file inside the project config folder

    # read the text file and get the path
    with open("./configs/proj_folder_path.txt", "r") as f:
        lines = f.readlines()
        # get the first line
        project_path = lines[0].strip()
    
    return project_path

import platform
def get_symbol_lib_path():
    # get the kiCAD symbol library path from a file inside the project config folder
    project_path = Path(os.environ["PROJECT_PATH"])
    lib_path = project_path / "configs" / "symbol_lib_path.txt"
    # read the text file and get the path
    system = platform.system().lower()
    if system == "windows" or os.name == "nt":
        with open(lib_path, "r") as f:
            lines = f.readlines()
            # get the first line
            symbol_lib_path = lines[0].strip()
    else:
        symbol_lib_path = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols/"
    
    return symbol_lib_path

def get_footprint_lib_path():
    # get the kiCAD footprint library path from a file inside the project config folder
    project_path = Path(os.environ["PROJECT_PATH"])
    lib_path = project_path / "configs" / "footprint_lib_path.txt"
    # read the text file and get the path
    system = platform.system().lower()
    if system == "windows" or os.name == "nt":
        with open(lib_path, "r") as f:
            lines = f.readlines()
            # get the first line
            footprint_lib_path = lines[0].strip()
    else:
        footprint_lib_path = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/"
    
    return footprint_lib_path


# If true, then we will reverse the Y coordinate when adding symbols to the schematic.
REVERSE_Y_FLAG = True

def reY(y):
    """
    Reverse the Y coordinate, converting from a normal Y axis to KiCad's Y axis.
    KiCad's Y axis is positive downwards, while we normally use a Y axis that is positive upwards.
    """
    if REVERSE_Y_FLAG:
        return round(210 - y, 2)
    else:
        return y

RAISE_ERR_FLAG = False  # If True, raise error for APIs. If False, return None and print error message.


def check_line_duplicate(line1, line2):
    """
    Check if two lines overlap (touch at one end, meanwhile, co-linear) and find their junction point.
    
    Each line is represented as a list of two points, where each point is [x, y].
    
    Args:
        line1: A list containing two points [[x1, y1], [x2, y2]]
        line2: A list containing two points [[x3, y3], [x4, y4]]
        
    Returns:
        A tuple (overlap, junction) where:
        - overlap is a boolean indicating whether the lines overlap
        - junction is the other junction point [x, y] if overlap is True, None otherwise
    """
    # Extract points
    p1, p2 = line1
    p3, p4 = line2
    
    # Check if any end points are the same
    common_point = None
    other_points = []
    
    if p1 == p3:
        common_point = p1
        other_points = [p2, p4]
    elif p1 == p4:
        common_point = p1
        other_points = [p2, p3]
    elif p2 == p3:
        common_point = p2
        other_points = [p1, p4]
    elif p2 == p4:
        common_point = p2
        other_points = [p1, p3]
    else:
        # No common points, so no overlap
        return False, None
    
    # If we found a common point, check if the lines are in the same direction
    if common_point is not None:
        # Calculate direction vectors
        vec1 = [other_points[0][0] - common_point[0], other_points[0][1] - common_point[1]]
        vec2 = [other_points[1][0] - common_point[0], other_points[1][1] - common_point[1]]
        
        # Check if vectors are parallel (same direction or opposite)
        # by checking if their cross product is zero
        cross_product = vec1[0] * vec2[1] - vec1[1] * vec2[0]
        
        if cross_product == 0:
            # Vectors are parallel, now check if they're in the same direction
            dot_product = vec1[0] * vec2[0] + vec1[1] * vec2[1]
            
            if dot_product > 0:
                # Same direction, so they overlap
                # Find the other junction - the point where the overlapping segment ends
                # We need to find which point is further along the direction vector
                
                # Calculate distances from common point
                dist1 = vec1[0]**2 + vec1[1]**2
                dist2 = vec2[0]**2 + vec2[1]**2
                
                # The point with the smaller distance is inside the overlapping segment
                # The other junction is the point with the smaller distance
                if dist1 <= dist2:
                    return True, other_points[0]
                else:
                    return True, other_points[1]
                
    return False, None