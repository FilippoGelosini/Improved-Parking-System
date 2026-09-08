from __future__ import absolute_import, print_function

import math
import os
import sys

from constants import (
    PREFIX,
    FOLDER_NAME,
    TOTAL_POPULATION,
    BAD_DRIVERS_PERCENTAGE,
    MAX_PARK_DURATION,
    STEPS_PER_HOUR,
    CONSTANT_BUFFER_SPOTS,
    INITIAL_BUFFER_SPOTS,
    MAX_BUFFER_SPOTS,
    OVERSTAY_THRESHOLD,
    BUFFER_STRATEGY,
    BUFFER_RISK_WEIGHT,
    BUFFER_RESET_PERIOD,
    BUFFER_WARMUP_STEPS,
    STANDARD_AUCTION_PRICE,
    STARTING_STOP,
)
from bufferManagement import make_buffer_manager
from parkArea import get_park_area, is_out_of_town
from vehicle import get_vehicle

from lxml import etree

if "SUMO_HOME" in os.environ:
    tools = os.path.join(os.environ["SUMO_HOME"], "tools")
    sys.path.append(tools)
else:
    sys.exit("Please set environment variable 'SUMO_HOME'")

import traci
from sumolib import checkBinary

from functions import *

# Derived constants
NUMBER_BAD_VEHICLES = int(TOTAL_POPULATION * BAD_DRIVERS_PERCENTAGE)
NUMBER_GOOD_VEHICLES = TOTAL_POPULATION - NUMBER_BAD_VEHICLES

def run():
    # Loadind the XML routes file
    xml_file_path = f"{FOLDER_NAME}/{PREFIX}_{TOTAL_POPULATION}.rou.xml"
    xml_document = etree.parse(xml_file_path)
    root = xml_document.getroot()
    max_trips = len(root.xpath("trip"))

    # List of vehicle IDs, in the order they appear in the XML routes file
    vehicle_id_list_xml = [
        root[posTrip].attrib.get("id") for posTrip in range(max_trips)
    ]
    xml_pos_by_id = {v_id: pos for pos, v_id in enumerate(vehicle_id_list_xml)}
    # print("Number of vehicles:", str(max_trips))
    # print("List of vehicles in XML file:", vehicle_id_list_xml)

    # Counters
    cont_no_park = 0                    # Number of times the vehicles don't park
    cont_end_park = 0                   # Number of times the vehicles end a park
    cont_bad_behaviour_vehicles = 0     # Number of times the vehicles didn't respect the reservations
    simulation_time = 0
    unsatisfied_reservations_cont = 0
    no_found_reservation_cont = 0
    new_wallet = 0                      # Temporarily stores the remaining credits of a vehicle after it reserves a spot

    # Stores the vehicles (id -> Vehicle)
    vehicles = {}

    # Stores the park areas (name -> ParkArea)
    areas = {}

    # Counts how many overstays happen in each area (name -> overstay_number)
    bad_behaviour = {}

    # Counts how many vehicles are about to leave each area at every simulation step (name -> number_vehicles)
    leaving_area_park_vehicle = {}

    # Initializes the buffer manager
    buffer_manager = make_buffer_manager()

    while traci.simulation.getMinExpectedNumber() > 0:
        traci.simulationStep()

        # Loading vehicles
        running_vehicle_id_list = list(traci.vehicle.getIDList())
        # print("------------------------ Still active vehicle:", str(len(running_vehicle_id_list)), "------------------------")

        simulation_time = traci.simulation.getTime()
        # print("Time:", simulation_time)

        # Remove all ending park vehicles' reservations
        leaving_area_park_vehicle.clear()
        end_stop_vehicles = list(traci.simulation.getParkingEndingVehiclesIDList())
        # print("List of vehicles that are leaving their park:", end_stop_vehicles)

        # First iterate on vehicles that are about to end a park
        for end_stop_vehicle in end_stop_vehicles:
            vehicle = vehicles.get(end_stop_vehicle)
            old_park_area = vehicle.last_park if vehicle is not None else ""

            overstayed = (
                vehicle is not None
                and vehicle.park_duration is not None
                and simulation_time > int(vehicle.park_duration)
            )

            # Notify the buffer manager about the vehicle leaving the area
            if old_park_area and not is_out_of_town(old_park_area):
                buffer_manager.on_exit(end_stop_vehicle, old_park_area, overstayed)

            # Decrement reservation count for the area the vehicle is leaving
            if vehicle is not None and vehicle.has_reservation:
                old_area = get_park_area(old_park_area, areas)
                old_area.reservations -= 1
                cont_end_park += 1
                if old_area.reservations < 0:
                    print(f"Error: negative reservations for {old_park_area}")
                    exit()
                vehicle.has_reservation = False

            # Update vehicle.last_park to the next stop's park area
            if end_stop_vehicle in xml_pos_by_id:
                vehicle = get_vehicle(end_stop_vehicle, vehicles, xml_pos_by_id)
                stop_pos_offset = vehicle.stop_pos
                next_park_area = root[vehicle.xml_pos][
                    STARTING_STOP + stop_pos_offset
                ].attrib.get("parkingArea")
                vehicle.last_park = next_park_area

                # Count vehicles leaving the "old" park area (for slot availability, used in later code)
                if stop_pos_offset > 0:
                    previous_park_area = root[vehicle.xml_pos][
                        STARTING_STOP + stop_pos_offset - 1
                    ].attrib.get("parkingArea")
                else:
                    previous_park_area = old_park_area

                if previous_park_area:
                    if previous_park_area not in leaving_area_park_vehicle:
                        leaving_area_park_vehicle[previous_park_area] = 1
                    else:
                        leaving_area_park_vehicle[previous_park_area] += 1


        # Then iterate only vehicles that are running in this scenario
        for id_vehicle in running_vehicle_id_list:
            vehicle = get_vehicle(id_vehicle, vehicles, xml_pos_by_id)

            is_stopped_parking = traci.vehicle.isStoppedParking(id_vehicle)

            # Skips vehicles who are already parked in an out of town area and have already paid (speeds up the simulation)
            if (
                is_stopped_parking
                and vehicle.paid
                and vehicle.last_park is not None
                and is_out_of_town(vehicle.last_park)
            ):
                continue

            # print("Reservations per area:", {n: a.reservations for n, a in areas.items()})
            # print("List of vehicles with reservation:", [v.id for v in vehicles.values() if v.has_reservation])
            # print("Number of vehicles with reservation:", sum(1 for v in vehicles.values() if v.has_reservation))

            # print("Vehicle position in XML:", str(vehicle.xml_pos))

            stop_pos_offset = vehicle.stop_pos

            # Park area reserved for the current stop, read from the XML file
            park_area = root[vehicle.xml_pos][
                STARTING_STOP + stop_pos_offset
            ].attrib.get("parkingArea")

            if vehicle.last_park is None:
                vehicle.last_park = park_area

            cont_stops = len(list(traci.vehicle.getStops(id_vehicle, 0)))
            duration = int(
                root[vehicle.xml_pos][STARTING_STOP + stop_pos_offset].attrib.get(
                    "duration"
                )
            )

            # print("Id vehicle:", str(id_vehicle))
            # print("Current Parking-area:", str(vehicle.last_park))
            # print("Next Parking-area:", str(park_area))
            # print("Stop position Offset:", str(stop_pos_offset))
            # print("Number of stops:", cont_stops)
            # print("Is the vehicle stopped?:", str(is_stopped_parking))
            # print("Park's duration:", str(duration))
            # print("Buffer state:", buffer_manager.free_parks)

            # If the vehicle is not stopped
            if not is_stopped_parking and cont_stops > 0:
                # If the vehicle is already parked and it had the reservation
                if vehicle.paid:
                    vehicle.paid = False

                if not vehicle.has_reservation:
                    if not is_out_of_town(park_area):
                        # Check if the vehicle has the requirements to park in "Town" (ParkArea and ParkAreaAlternative)
                        # Else it gets deviated to a park area out of town
                        review_stars = int(
                            traci.vehicle.getParameter(id_vehicle, "reviewStars")
                        )
                        # print("Review Stars:", review_stars)
                        good_behaviour = traci.vehicle.getParameter(
                            id_vehicle, "goodBehaviour"
                        )
                        # print("goodBehaviour:", good_behaviour)
                        if review_stars < 3 and good_behaviour == "False":
                            new_park_area = go_to_no_system_park(
                                id_vehicle, duration, 0, areas
                            )

                            # print("Stops:", traci.vehicle.getStops(id_vehicle, 0))
                            # print("New Park Area:", new_park_area)

                            traci.vehicle.setParameter(
                                id_vehicle, "goodBehaviour", "True"
                            )
                            root[vehicle.xml_pos][
                                STARTING_STOP + stop_pos_offset
                            ].set("parkingArea", new_park_area)
                            vehicle.last_park = new_park_area
                            park_area = new_park_area

                        # Check vehicle's wallet, if it has enough credits it can park in "Town"
                        if not is_out_of_town(park_area):
                            delay = int(traci.vehicle.getParameter(id_vehicle, "delay"))
                            new_wallet = check_wallet(duration - delay, id_vehicle)
                            if not new_wallet:
                                new_park_area = go_to_no_system_park(
                                    id_vehicle, duration, 0, areas
                                )

                                # print("Stops:", traci.vehicle.getStops(id_vehicle, 0))
                                # print("New Park Area:", new_park_area)

                                root[vehicle.xml_pos][
                                    STARTING_STOP + stop_pos_offset
                                ].set("parkingArea", new_park_area)
                                vehicle.last_park = new_park_area
                                park_area = new_park_area

                # Set buffer spots (there are no buffer spots in "ParkAreaOutOfTown")
                area = get_park_area(park_area, areas)
                cont_free_parks = INITIAL_BUFFER_SPOTS
                if not area.is_out_of_town:
                    cont_free_parks = buffer_manager.get_buffer(
                        park_area, INITIAL_BUFFER_SPOTS
                    )
                    if CONSTANT_BUFFER_SPOTS != -1:
                        cont_free_parks = CONSTANT_BUFFER_SPOTS
                else:
                    cont_free_parks = 0

                if not vehicle.has_reservation:
                    vehicle.has_reservation = True
                    area.reservations += 1

                    # Notify the buffer manager about a new reservation (only useful when using the "incremental" strategy)
                    if not area.is_out_of_town:
                        buffer_manager.on_reservation(
                            id_vehicle, park_area, INITIAL_BUFFER_SPOTS
                        )
                        # Re-read updated buffer after reservation, the "incremental" strategy might have increased the buffer dimension
                        cont_free_parks = buffer_manager.get_buffer(
                            park_area, INITIAL_BUFFER_SPOTS
                        )
                        if CONSTANT_BUFFER_SPOTS != -1:
                            cont_free_parks = CONSTANT_BUFFER_SPOTS

                cont_ending_park = leaving_area_park_vehicle.get(park_area, 0)

                # Check if the designated park area is fully booked (NOT full of vehicles) AFTER a vehicle already booked (behaviour of the "original" project)
                if area.is_fully_booked(cont_free_parks):
                    # If someone is leaving in the current step, the vehicle can park in its original destination
                    if cont_ending_park > 0:
                        leaving_area_park_vehicle[park_area] -= 1
                        continue

                    # Else the system tries to find another area with reservable spots
                    if not area.is_out_of_town:
                        unsatisfied_reservations_cont += 1

                        # print("Number of reservations in that Park-Area:", area.reservations)
                        # print("Waiting...")
                        new_park_area = change_reservation(
                            id_vehicle,
                            park_area,
                            duration,
                            0,
                            areas,
                            buffer_manager,
                        )
                        # If there are no reservable spots in any area in town, then the vehicle gets deviated in an area out of town
                        if new_park_area == "End":
                            no_found_reservation_cont += 1
                            new_park_area = go_to_no_system_park(
                                id_vehicle, duration, 0, areas
                            )
                    else:
                        new_park_area = go_to_no_system_park(
                            id_vehicle, duration, 0, areas
                        )

                    # print("Stops:", traci.vehicle.getStops(id_vehicle, 0))
                    # print("New Park Area:", new_park_area)

                    # Update the current (new) area in the XML
                    root[vehicle.xml_pos][STARTING_STOP + stop_pos_offset].set(
                        "parkingArea", new_park_area
                    )
                    vehicle.last_park = new_park_area
                    # Finally, cancel the reservation in the "old" area and book a spot in the new one
                    area.reservations -= 1
                    get_park_area(new_park_area, areas).reservations += 1

                    # print("------------------------")

                    park_area = new_park_area
                    area = get_park_area(park_area, areas)

                    # Create a new reservation and read the buffer dimension for the new area
                    cont_free_parks = INITIAL_BUFFER_SPOTS
                    if not area.is_out_of_town:
                        buffer_manager.on_reservation(
                            id_vehicle, park_area, INITIAL_BUFFER_SPOTS
                            )
                        cont_free_parks = buffer_manager.get_buffer(
                            park_area, INITIAL_BUFFER_SPOTS
                        )
                        if CONSTANT_BUFFER_SPOTS != -1:
                            cont_free_parks = CONSTANT_BUFFER_SPOTS
                    else:
                        cont_free_parks = 0

                cont_ending_park = leaving_area_park_vehicle.get(park_area, 0)

                # Check if the designated park area is not fully booked, but still full of vehicles (many vehicles overstayed, leads to NO PARK scenario)
                if (
                    not area.is_fully_booked(cont_free_parks)
                ) and traci.parkingarea.getVehicleCount(park_area) == area.capacity:
                    # If someone is leaving in the current step, the vehicle can park in its original destination
                    if cont_ending_park > 0:
                        leaving_area_park_vehicle[park_area] -= 1
                        continue

                    # Else the system directs the vehicle out of town, and increases the NO PARK counter
                    if not area.is_out_of_town:
                        if not vehicle.is_waiting:
                            cont_no_park += 1
                            vehicle.is_waiting = True
                        if not vehicle.changed_route:
                            vehicle.changed_route = True

                        # print("Number of vehicles in that Park-Area:", str(traci.parkingarea.getVehicleCount(park_area)))
                        # print("Waiting...")

                    new_park_area = go_to_no_system_park(
                        id_vehicle, duration, 0, areas
                    )

                    # print("Stops:", traci.vehicle.getStops(id_vehicle, 0))
                    # print("New Park Area:", new_park_area)

                    # Update the current (new) area in the XML
                    root[vehicle.xml_pos][STARTING_STOP + stop_pos_offset].set(
                        "parkingArea", new_park_area
                    )
                    vehicle.last_park = new_park_area

                    # Finally, cancel the reservation in the "old" area and book a spot in the new one
                    area.reservations -= 1
                    get_park_area(new_park_area, areas).reservations += 1

            # If the vehicle is stopped
            if is_stopped_parking:
                stops = list(traci.vehicle.getStops(id_vehicle, 0))
                delay = int(traci.vehicle.getParameter(id_vehicle, "delay"))

                # In case if the park is "ParkAreaOutOfTown", we don't track the ending time of the reservation
                if not is_out_of_town(vehicle.last_park):
                    current_stop = stops[0]

                    # Check only bad behavior car (since, by construction, all bad vehicles overstay for a fixed period of simulation steps declared in a specific parameter in the XML file, called "delay")
                    if delay > 0:
                        # If the current duration is negative that means someone is blocking the park
                        if current_stop.duration > 0:
                            if vehicle.paid and vehicle.park_duration is not None:
                                # If the current simulation step coincides with the ending of the vehicle's reservation, the vehicle overstayed, and the buffer manager is notified, though only the "incremental" strategy takes action
                                if simulation_time >= int(vehicle.park_duration):
                                    if vehicle.has_reservation:
                                        buffer_manager.on_overstay_start(
                                            id_vehicle,
                                            vehicle.last_park,
                                            INITIAL_BUFFER_SPOTS,
                                        )

                                        # Remove the reservation from the area and increase the bad behaviour counter of the area
                                        vehicle.has_reservation = False
                                        get_park_area(
                                            vehicle.last_park, areas
                                        ).reservations -= 1
                                        cont_bad_behaviour_vehicles += 1

                                        if vehicle.last_park not in bad_behaviour:
                                            bad_behaviour[vehicle.last_park] = 1
                                        else:
                                            bad_behaviour[vehicle.last_park] += 1

                                        # P.S.: 'vehicle.park_duration' is not reset, and 'vehicle.last_park' is not updated with the next area, since they are both still needed in the first phase (vehicles about to end a park) to check if and where the vehicle overstayed

                # A stopped vehicle who's been a "victim" of a NO PARK situation is now parked out of town, and the flag 'vehicle.is_waiting' is set to false
                if vehicle.is_waiting:
                    vehicle.is_waiting = False

                if not vehicle.paid:
                    vehicle.paid = True
                    cont_stops = len(stops)
                    # print("Stops:", traci.vehicle.getStops(id_vehicle, 0))

                    # Vehicle doesn't pay if it doesn't park in "Town"
                    if not is_out_of_town(park_area):
                        # Calculate the supposed park ending
                        leaving_time = simulation_time + (duration - delay)
                        # print("When it must end the park at:", leaving_time)
                        vehicle.park_duration = leaving_time
                        # print("Vehicle's ending time park:", leaving_time)
                        
                        # Wallet overwritten with the new balance
                        traci.vehicle.setParameter(id_vehicle, "wallet", new_wallet)
                        system_charge(id_vehicle)
                    if cont_stops > 1:
                        # Update which stop the vehicle is at
                        vehicle.stop_pos += 1
                        # print("Where:", vehicle.stop_pos)

                # print("------------------------")
                continue

            # print("------------------------")

        # print("------------------------ Still active vehicle:", str(len(running_vehicle_id_list)), "------------------------")

        # print("Reservation Total:", sum(a.reservations for a in areas.values()))

    # print("Vehicles that not park during sleep time:", len(vehicles_do_not_park))



    # Output log
    vehicles_change_route_count = sum(1 for v in vehicles.values() if v.changed_route)
    reservations_by_area = {
        name: area.reservations for name, area in sorted(areas.items())
    }

    with open("output.txt", "a") as f:
        print(
            f"Which population: {TOTAL_POPULATION}"
            f" ({NUMBER_GOOD_VEHICLES} - {NUMBER_BAD_VEHICLES})",
            file=f,
        )
        if CONSTANT_BUFFER_SPOTS == -1:
            if BUFFER_STRATEGY == "legacy":
                print(
                    f"Buffer: legacy (initial={INITIAL_BUFFER_SPOTS},"
                    f" max={MAX_BUFFER_SPOTS}, reset={BUFFER_RESET_PERIOD},"
                    f" warmup={BUFFER_WARMUP_STEPS})",
                    file=f,
                )
            elif BUFFER_STRATEGY == "incremental":
                print(
                    f"Buffer: incremental (initial={INITIAL_BUFFER_SPOTS},"
                    f" max={MAX_BUFFER_SPOTS}, threshold={OVERSTAY_THRESHOLD})",
                    file=f,
                )
            else:
                print(
                    f"Buffer: weighted (fallback={INITIAL_BUFFER_SPOTS},"
                    f" max={MAX_BUFFER_SPOTS}, risk_weight={BUFFER_RISK_WEIGHT})",
                    file=f,
                )
        else:
            print(f"Buffer: constant={CONSTANT_BUFFER_SPOTS}", file=f)
        print(
            f"Bookings rejected, area already booked out:"
            f" {unsatisfied_reservations_cont}",
            file=f,
        )
        print(
            f"  of which relocated to another in-town area:"
            f" {unsatisfied_reservations_cont - no_found_reservation_cont}",
            file=f,
        )
        print(
            f"  of which sent out of town, no in-town area free:"
            f" {no_found_reservation_cont}",
            file=f,
        )
        print(
            f"Arrivals at a physically full area: {cont_no_park}",
            file=f,
        )
        print(
            f"Vehicles that hit a physically full area at least once:"
            f" {vehicles_change_route_count}",
            file=f,
        )
        print(f"End park(good behaviour): {cont_end_park}", file=f)
        print(f"End park(bad behaviour): {cont_bad_behaviour_vehicles}", file=f)
        print(
            f"Total end park: {cont_end_park + cont_bad_behaviour_vehicles}", file=f
        )
        print(f"Finish time step: {simulation_time}", file=f)
        print(f"Reservation: {reservations_by_area}", file=f)
        print(f"Buffer state: {buffer_manager.free_parks}", file=f)
        print(
            "------------------------------------------------------------------------",
            file=f,
        )

    sys.stdout.flush()


if __name__ == "__main__":
    options = get_options(["--nogui"])

    if options.nogui:
        sumoBinary = checkBinary("sumo")
    else:
        sumoBinary = checkBinary("sumo-gui")

    sumo_cfg = f"{FOLDER_NAME}/{PREFIX}_{TOTAL_POPULATION}.sumocfg"
    traci.start([sumoBinary, "-c", sumo_cfg])
    run()
