from __future__ import absolute_import, print_function, division

import math
import random
import os
import sys
import subprocess

from constants import (
    PREFIX,
    FOLDER_NAME,
    PARK_AREA_NAMES,
    TOTAL_POPULATION,
    TOTAL_STOPS,
    STOPS_PER_DAY,
    BAD_DRIVERS_PERCENTAGE,
    DOUBLE_ROWS,
    SLOTS_PER_ROW,
    SLOT_WIDTH,
    PARK_ROW_DISTANCE,
    MIN_PARK_DURATION,
    MAX_PARK_DURATION,
    STEPS_PER_HOUR
)

sys.path.append(os.path.join(os.environ["SUMO_HOME"], "tools"))
import sumolib

from functions import get_options

def generate_simulation_map():
    nodes = open(f"{FOLDER_NAME}/{PREFIX}.nod.xml", "w")
    sumolib.xml.writeHeader(nodes, root="nodes")
    edges = open(f"{FOLDER_NAME}/{PREFIX}.edg.xml", "w")
    sumolib.xml.writeHeader(edges, root="edges")

    nodeID = "main0"
    print(f'<node id="in" x="-100" y="0"/>', file=nodes)
    print(f'<edge id="mainin" from="in" to="{nodeID}" numLanes="3"/>', file=edges)

    for row in range(DOUBLE_ROWS):
        nextNodeID = f"main{row}"
        x = row * PARK_ROW_DISTANCE
        print(f'<node id="{nextNodeID}" x="{x}" y="0"/>', file=nodes)
        if row > 0:
            print(f'<edge id="main{row - 1}to{row}" from="{nodeID}" to="{nextNodeID}" numLanes="3"/>', file=edges)
        nodeID = nextNodeID
    
    for row in range(DOUBLE_ROWS):
        nextNodeID = f"mainAlternative{row}"
        x = row * PARK_ROW_DISTANCE + 100
        print(f'<node id="{nextNodeID}" x="{x}" y="0"/>', file=nodes)
        if row > 0:
            print(f'<edge id="mainAlternative{row - 1}to{row}" from="{nodeID}" to="{nextNodeID}" numLanes="3"/>', file=edges)
        nodeID = nextNodeID

    rowNumberOutOfTown = math.ceil(TOTAL_POPULATION / 20)
    offset = 21
    
    if rowNumberOutOfTown < 4:
        rowNumberOutOfTown = 4
    else:
        offset = offset - 14.5 * (rowNumberOutOfTown - 4)
    
    for row in range(rowNumberOutOfTown):
        nextNodeID = f"mainOutOfTown{row}"
        x = row * PARK_ROW_DISTANCE + offset
        print(f'<node id="{nextNodeID}" x="{x}" y="-150"/>', file=nodes)
        if row > 0:
            print(f'<edge id="mainOutOfTown{row}to{row - 1}" from="{nextNodeID}" to="{nodeID}" numLanes="3"/>', file=edges)
        nodeID = nextNodeID
    
    print('<edge id="mainmid" from="main1" to="mainAlternative0" numLanes="3"/>', file=edges)
    print('<node id="out" x="225" y="0"/>', file=nodes)
    print(f'<edge id="mainout" from="mainAlternative{DOUBLE_ROWS - 1}" to="out" numLanes="3"/>', file=edges)

    print('<node id="backin" x="-100" y="-150"/>', file=nodes)
    print('<node id="backout" x="225" y="-150"/>', file=nodes)

    print(f'<edge id="inOutOfTown" from="backout" to="mainOutOfTown{DOUBLE_ROWS * 2 - 1}" numLanes="3"/>', file=edges)
    print('<edge id="outOutOfTown" from="mainOutOfTown0" to="backin" numLanes="3"/>', file=edges)

    print('<edge id="turnbackout" from="out" to="backout" numLanes="3"/>', file=edges)
    print('<edge id="turnbackin" from="backin" to="in" numLanes="3"/>', file=edges)

    y = (SLOTS_PER_ROW + 3) * SLOT_WIDTH
    print(f'<node id="cyber" x="-100" y="{y}"/>', file=nodes)
    
    for row in range(DOUBLE_ROWS):
        nodeID = f"cyber{row}"
        x = row * PARK_ROW_DISTANCE
        print(f'<node id="{nodeID}" x="{x}" y="{y}"/>', file=nodes)
        if row > 0:
            edgeID = f"cyber{row - 1}to{row}"
            print(f'<edge id="{edgeID}" from="cyber{row - 1}" to="cyber{row}" numLanes="2" spreadType="center">', file=edges)
            print('    <lane index="0"/>', file=edges)
            print('    <lane index="1"/>', file=edges)
            print('</edge>', file=edges)
            print(f'<edge id="-{edgeID}" from="cyber{row}" to="cyber{row - 1}" numLanes="2" spreadType="center">', file=edges)
            print('    <lane index="0"/>', file=edges)
            print('    <lane index="1"/>', file=edges)
            print('</edge>', file=edges)
    
    y = (SLOTS_PER_ROW + 3) * SLOT_WIDTH
    print(f'<node id="cyberAlternative" x="-500" y="{y}"/>', file=nodes)
    
    for row in range(DOUBLE_ROWS):
        nodeID = f"cyberAlternative{row}"
        x = row * PARK_ROW_DISTANCE + 100
        print(f'<node id="{nodeID}" x="{x}" y="{y}"/>', file=nodes)
        if row > 0:
            edgeID = f"cyberAlternative{row - 1}to{row}"
            print(f'<edge id="{edgeID}" from="cyberAlternative{row - 1}" to="cyberAlternative{row}" numLanes="2" spreadType="center">', file=edges)
            print('    <lane index="0"/>', file=edges)
            print('    <lane index="1"/>', file=edges)
            print('</edge>', file=edges)
            print(f'<edge id="-{edgeID}" from="cyberAlternative{row}" to="cyberAlternative{row - 1}" numLanes="2" spreadType="center">', file=edges)
            print('    <lane index="0"/>', file=edges)
            print('    <lane index="1"/>', file=edges)
            print('</edge>', file=edges)
    
    y = (SLOTS_PER_ROW + 3) * SLOT_WIDTH - 150
    print(f'<node id="cyberOutOfTown" x="-500" y="{y}"/>', file=nodes)
    
    for row in range(rowNumberOutOfTown):
        nodeID = f"cyberOutOfTown{row}"
        x = row * PARK_ROW_DISTANCE + offset
        print(f'<node id="{nodeID}" x="{x}" y="{y}"/>', file=nodes)
        if row > 0:
            edgeID = f"cyberOutOfTown{row - 1}to{row}"
            print(f'<edge id="{edgeID}" from="cyberOutOfTown{row - 1}" to="cyberOutOfTown{row}" numLanes="2" spreadType="center">', file=edges)
            print('    <lane index="0"/>', file=edges)
            print('    <lane index="1"/>', file=edges)
            print('</edge>', file=edges)
            print(f'<edge id="-{edgeID}" from="cyberOutOfTown{row}" to="cyberOutOfTown{row - 1}" numLanes="2" spreadType="center">', file=edges)
            print('    <lane index="0"/>', file=edges)
            print('    <lane index="1"/>', file=edges)
            print('</edge>', file=edges)

    for row in range(DOUBLE_ROWS):
        # ParkArea
        print(f'<edge id="road{row}" from="main{row}" to="cyber{row}" numLanes="3">', file=edges)
        print('    <lane index="0"/>', file=edges)
        print('    <lane index="1"/>', file=edges)
        print('    <lane index="2"/>', file=edges)
        print('</edge>', file=edges)
        print(f'<edge id="-road{row}" from="cyber{row}" to="main{row}" numLanes="3">', file=edges)
        print('    <lane index="0"/>', file=edges)
        print('    <lane index="1"/>', file=edges)
        print('    <lane index="2"/>', file=edges)
        print('</edge>', file=edges)

        # ParkAreaAlternative
        print(f'<edge id="roadAlternative{row}" from="mainAlternative{row}" to="cyberAlternative{row}" numLanes="3">', file=edges)
        print('    <lane index="0"/>', file=edges)
        print('    <lane index="1"/>', file=edges)
        print('    <lane index="2"/>', file=edges)
        print('</edge>', file=edges)
        print(f'<edge id="-roadAlternative{row}" from="cyberAlternative{row}" to="mainAlternative{row}" numLanes="3">', file=edges)
        print('    <lane index="0"/>', file=edges)
        print('    <lane index="1"/>', file=edges)
        print('    <lane index="2"/>', file=edges)
        print('</edge>', file=edges)

    for row in range(rowNumberOutOfTown):
        # ParkAreaOutOfTown
        print(f'<edge id="roadOutOfTown{row}" from="mainOutOfTown{row}" to="cyberOutOfTown{row}" numLanes="3">', file=edges)
        print('    <lane index="0"/>', file=edges)
        print('    <lane index="1"/>', file=edges)
        print('    <lane index="2"/>', file=edges)
        print('</edge>', file=edges)
        print(f'<edge id="-roadOutOfTown{row}" from="cyberOutOfTown{row}" to="mainOutOfTown{row}" numLanes="3">', file=edges)
        print('    <lane index="0"/>', file=edges)
        print('    <lane index="1"/>', file=edges)
        print('    <lane index="2"/>', file=edges)
        print('</edge>', file=edges)
    
    print("</nodes>", file=nodes)
    print("</edges>", file=edges)
    nodes.close()
    edges.close()

    subprocess.call([sumolib.checkBinary("netconvert"),
                       "-n", f"{FOLDER_NAME}/{PREFIX}.nod.xml", 
                       "-e", f"{FOLDER_NAME}/{PREFIX}.edg.xml", 
                       "-o", f"{FOLDER_NAME}/{PREFIX}.net.xml"])
    
    with open(f"{FOLDER_NAME}/{PREFIX}.add.xml", "w") as stops:
        sumolib.xml.writeHeader(stops, root="additional")
        
        # ParkArea Construction
        for row in range(DOUBLE_ROWS):
            print(f'<parkingArea id="ParkArea{row}" lane="road{row}_1" roadsideCapacity="{SLOTS_PER_ROW}" angle="270" length="8">', file=stops)
            print('</parkingArea>', file=stops)
            print(f'<parkingArea id="-ParkArea{row}" lane="-road{row}_1" roadsideCapacity="{SLOTS_PER_ROW}" angle="270" length="8">', file=stops)
            print('</parkingArea>', file=stops)
        
        # ParkAreaAlternative Construction
        for row in range(DOUBLE_ROWS):
            print(f'<parkingArea id="ParkAreaAlternative{row}" lane="roadAlternative{row}_1" roadsideCapacity="{SLOTS_PER_ROW}" angle="270" length="8">', file=stops)
            print('</parkingArea>', file=stops)
            print(f'<parkingArea id="-ParkAreaAlternative{row}" lane="-roadAlternative{row}_1" roadsideCapacity="{SLOTS_PER_ROW}" angle="270" length="8">', file=stops)
            print('</parkingArea>', file=stops)
        
        # ParkAreaOutOfTown Construction
        for row in range(rowNumberOutOfTown):
            print(f'<parkingArea id="ParkAreaOutOfTown{row}" lane="roadOutOfTown{row}_1" roadsideCapacity="{SLOTS_PER_ROW}" angle="270" length="8">', file=stops)
            print('</parkingArea>', file=stops)
            print(f'<parkingArea id="-ParkAreaOutOfTown{row}" lane="-roadOutOfTown{row}_1" roadsideCapacity="{SLOTS_PER_ROW}" angle="270" length="8">', file=stops)
            print('</parkingArea>', file=stops)
        
        # Colors based on vehicles' behavior
        print('<vType id="car" color="0.7,0.7,0.7"/>', file=stops)
        print('<vType id="carB" color="red"/>', file=stops)
        
        print("</additional>", file=stops)

    return

def generate_routes():
    departTime = 1
    number_bad_vehicles = int(TOTAL_POPULATION * BAD_DRIVERS_PERCENTAGE)
    
    rowNumberOutOfTown = math.ceil(TOTAL_POPULATION / 20)
    if rowNumberOutOfTown < 4:
        rowNumberOutOfTown = 4

    with open(f"{FOLDER_NAME}/{PREFIX}_{TOTAL_POPULATION}.rou.xml", "w") as routes:
        print("<routes>", file=routes)
        
        for i in range(TOTAL_POPULATION):
            is_bad = i >= (TOTAL_POPULATION - number_bad_vehicles)
            vtype = "carB" if is_bad else "car"
            good_behaviour = "False" if is_bad else "True"
            delay = STEPS_PER_HOUR if is_bad else 0
            
            row_idx = (i // 2) % DOUBLE_ROWS
            sign = "" if i % 2 == 0 else "-"
            to_edge = f"{sign}road{row_idx}"

            print(f'    <trip id="v{i}" type="{vtype}" depart="{i * departTime}" from="mainin" to="{to_edge}">', file=routes)
            print(f'        <param key="warning" value="0" />', file=routes)
            print(f'        <param key="civil" value="0" />', file=routes)
            print(f'        <param key="reviewStars" value="3" />', file=routes)
            print(f'        <param key="wallet" value="100" />', file=routes)
            print(f'        <param key="goodBehaviour" value="{good_behaviour}" />', file=routes)
            print(f'        <param key="delay" value="{delay}" />', file=routes)

            for s in range(TOTAL_STOPS):
                duration = random.randrange(MIN_PARK_DURATION, max(2, int(MAX_PARK_DURATION / 8))) * STEPS_PER_HOUR
                park_area_type = random.choice([PARK_AREA_NAMES[0], PARK_AREA_NAMES[1]])
                
                print(f'        <stop parkingArea="{sign}{park_area_type}{row_idx}" duration="{duration}"/>', file=routes)
                
                if (s + 1) % STOPS_PER_DAY == 0:
                    out_duration = random.randrange(int(MAX_PARK_DURATION / 3), max(2, int(MAX_PARK_DURATION - MAX_PARK_DURATION / 3))) * STEPS_PER_HOUR
                    out_idx = i % rowNumberOutOfTown
                    print(f'        <stop parkingArea="{sign}{PARK_AREA_NAMES[2]}{out_idx}" duration="{out_duration}"/>', file=routes)

            print(f'    </trip>', file=routes)

        print("</routes>", file=routes)
        
    return

if __name__ == "__main__":
    if not os.path.exists(FOLDER_NAME):
        os.makedirs(FOLDER_NAME)

    options = get_options(["--routesonly"])

    if not options.routesonly:
        generate_simulation_map()
    generate_routes()

    with open(f"{FOLDER_NAME}/{PREFIX}_{TOTAL_POPULATION}.sumocfg", "w") as sumo_config:
        print(f"""<configuration>
<input>
    <net-file value="{PREFIX}.net.xml"/>
    <route-files value="{PREFIX}_{TOTAL_POPULATION}.rou.xml"/>
    <additional-files value="{PREFIX}.add.xml"/>
    <no-step-log value="True"/>
    <time-to-teleport value="0"/>
</input>
</configuration>""", file=sumo_config)