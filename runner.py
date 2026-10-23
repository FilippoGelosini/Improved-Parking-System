from __future__ import absolute_import, print_function

import math
import os
import sys
import random

from constants import (
    PREFIX,
    FOLDER_NAME,
    TOTAL_POPULATION,
    BAD_DRIVERS_PERCENTAGE,
    STEPS_PER_CALENDAR_SLOT,
    CONSTANT_BUFFER_SPOTS,
    INITIAL_BUFFER_SPOTS,
    MAX_BUFFER_SPOTS,
    OVERSTAY_THRESHOLD,
    BUFFER_STRATEGY,
    BUFFER_RISK_WEIGHT,
    BUFFER_RESET_PERIOD,
    BUFFER_WARMUP_STEPS,
    STARTING_STOP,
    RUN_SEED,
    stream_seed
)
from bufferManagement import make_buffer_manager
from parkArea import get_park_area, is_out_of_town, step_to_calendar_slot
from vehicle import (
    get_vehicle, 
    get_review_stars, 
    get_good_behaviour, 
    set_good_behaviour, 
    get_overstay_probability, 
    set_wallet
)

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

    # Counts the number of <params> present for each vehicle, and if it does not march "STARTING_STOP" throws an error
    param_counts = {
        sum(1 for child in trip if child.tag == "param") for trip in root
    }
    assert param_counts == {STARTING_STOP}, (
        f"STARTING_STOP={STARTING_STOP} non corrisponde al route file, che "
        f"ha {param_counts} <param> per <trip>: le letture delle soste "
        f"sarebbero sfasate"
    )

    # Counters
    cont_no_park = 0                    # Number of times the vehicles don't park
    cont_end_park = 0                   # Number of times the vehicles end a park
    cont_bad_behaviour_vehicles = 0     # Number of times the vehicles didn't respect the reservations
    simulation_time = 0
    unsatisfied_reservations_cont = 0
    no_found_reservation_cont = 0
    arrived_after_booking_end_cont = 0
    arrived_before_booking_start_cont = 0
    out_of_calendar_arrival_cont = 0
    buffer_rejections = {}              # How many times a reservation is refused because the buffer takes up empty spaces

    # Stores the vehicles (id -> Vehicle)
    vehicles = {}

    # Stores the park areas (name -> ParkArea)
    areas = {}

    # RNG used to determine the vehicles behaviour
    behaviour_rng = random.Random(stream_seed(RUN_SEED, "behaviour"))

    # Counts how many overstays happen in each area (name -> overstay_number)
    bad_behaviour = {}

    # Counts how many vehicles are about to leave each area at every simulation step (name -> number_vehicles)
    leaving_area_park_vehicle = {}

    # Initializes the buffer manager
    buffer_manager = make_buffer_manager(areas)

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

            # Handles the specific case of a vehicle arriving at its booked spot when the booking itself already ended, causing SUMO to end the stop immediately. This makes the vehicle appear as both stopped and about to exit.
            if vehicle is not None and not vehicle.paid and vehicle.booking is not None:
                vehicle.paid = True
                vehicle.slot_release_step = None
                vehicle.park_duration = vehicle.booking[2] * STEPS_PER_CALENDAR_SLOT
                arrived_after_booking_end_cont += 1
                set_wallet(end_stop_vehicle, vehicle.new_wallet)
                vehicle.new_wallet = None
                if len(traci.vehicle.getStops(end_stop_vehicle, 0)) > 1:
                    vehicle.stop_pos += 1

            # Use the supposed exit time if SUMO prevents a vehicle from exiting the spot, else the current step
            release_step = simulation_time
            if vehicle is not None and vehicle.slot_release_step is not None:
                release_step = vehicle.slot_release_step

            overstayed = (
                vehicle is not None
                and vehicle.park_duration is not None
                and release_step > int(vehicle.park_duration)
            )

            # Notify the buffer manager about the vehicle leaving the area (only if the area is "in town")
            if old_park_area and not is_out_of_town(old_park_area):
                buffer_manager.on_exit(end_stop_vehicle, old_park_area, overstayed, step_to_calendar_slot(simulation_time))

                # Update vehicle's reputation and update its behaviour (randomly)
                system_charge(end_stop_vehicle, overstayed, behaviour_rng)

            if vehicle is not None:
                vehicle.booking = None

            # Decrement reservation count for the area the vehicle is leaving
            if vehicle is not None and vehicle.has_reservation:
                old_area = get_park_area(old_park_area, areas)
                if old_area.is_out_of_town:
                    old_area.reservations -= 1
                    if old_area.reservations < 0:
                        print(f"Error: negative reservations for {old_park_area}")
                        exit()
                cont_end_park += 1
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
            # print("Buffer state:", buffer_manager.free_parks(step_to_calendar_slot(simulation_time)))

            # If the vehicle is not stopped
            if not is_stopped_parking and cont_stops > 0:
                # If the vehicle is already parked and it had the reservation
                if vehicle.paid:
                    vehicle.paid = False

                if not vehicle.has_reservation:
                    if not is_out_of_town(park_area):
                        # Check if the vehicle has the requirements to park in "Town" (ParkArea and ParkAreaAlternative)
                        # Else it gets deviated to a park area out of town
                        review_stars = get_review_stars(id_vehicle)
                        # print("Review Stars:", review_stars)
                        good_behaviour = get_good_behaviour(id_vehicle)
                        # print("goodBehaviour:", good_behaviour)
                        if review_stars < 3 and not good_behaviour:
                            new_park_area = go_to_no_system_park(
                                id_vehicle, duration, 0, areas
                            )

                            # print("Stops:", traci.vehicle.getStops(id_vehicle, 0))
                            # print("New Park Area:", new_park_area)
                            set_good_behaviour(id_vehicle, True)
                            root[vehicle.xml_pos][
                                STARTING_STOP + stop_pos_offset
                            ].set("parkingArea", new_park_area)
                            vehicle.last_park = new_park_area
                            park_area = new_park_area

                        # Check vehicle's wallet, if it has enough credits it can park in "Town"
                        if not is_out_of_town(park_area):
                            vehicle.new_wallet = check_wallet(duration, id_vehicle)
                            if not vehicle.new_wallet:
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

                if not vehicle.has_reservation:
                    vehicle.has_reservation = True
                    new_park_area = None

                    # Check if the vehicle can park in the chosen area
                    if not area.is_out_of_town:
                        first_slot, last_slot = booking_slots(id_vehicle, area.name, duration, simulation_time)

                        if not area.can_book(first_slot, last_slot, buffer_of_slot(buffer_manager, area.name)):
                            unsatisfied_reservations_cont += 1

                            unreserved = area.unreserved_spots(first_slot, last_slot)
                            if unreserved > 0:
                                buffer_rejections[unreserved] = buffer_rejections.get(unreserved, 0) + 1

                            new_park_area = change_reservation(id_vehicle, area.name, duration, 0, areas, buffer_manager, first_slot, last_slot)
                            if new_park_area == "End":
                                no_found_reservation_cont += 1
                                new_park_area = go_to_no_system_park(id_vehicle, duration, 0, areas)

                    # If the chosen area is out of town but it's full, choose another out of town area
                    elif not area.has_free_slot(0):
                        new_park_area = go_to_no_system_park(id_vehicle, duration, 0, areas)

                    # If the parking area is not the one initially chosen, we need to update both the XML file and the current area
                    if new_park_area is not None:
                        root[vehicle.xml_pos][STARTING_STOP + stop_pos_offset].set(
                            "parkingArea", new_park_area
                        )
                        vehicle.last_park = new_park_area
                        park_area = new_park_area
                        area = get_park_area(park_area, areas)

                    if not area.is_out_of_town:
                        # Decide if the vehicle overstays the current reservation if the area is in town
                        area.book(id_vehicle, first_slot, last_slot)
                        vehicle.booking = (area.name, first_slot, last_slot)
                        buffer_manager.on_reservation(id_vehicle, area.name, first_slot, last_slot)

                        base_probability = get_overstay_probability(id_vehicle)
                        vehicle_stars = get_review_stars(id_vehicle)

                        vehicle.overstay = overstay_for(
                            base_probability, vehicle_stars, behaviour_rng
                        )

                        # If the vehicle overstays for its current stop, the corresponding entry in the routes file needs to have its duration updated
                        traci.vehicle.replaceStop(
                            id_vehicle,
                            0,
                            park_area,
                            flags=65,
                            duration=0,
                            until=last_slot * STEPS_PER_CALENDAR_SLOT - 1 + vehicle.overstay, # -1 needed to avoid counting a good reservation as an overstay
                            startPos=0.0,
                            )
                    else:
                        # No need to track overstays for out of town park, so "vehicle.overstay" gets reset
                        vehicle.overstay = 0
                        area.reservations += 1

                cont_ending_park = leaving_area_park_vehicle.get(park_area, 0)

                # Check if the designated park area is not fully booked, but still full of vehicles (many vehicles overstayed, leads to NO PARK scenario)
                if traci.parkingarea.getVehicleCount(park_area) == area.capacity:
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

                    if vehicle.booking is not None:
                        area.cancel(id_vehicle, vehicle.booking[1], vehicle.booking[2])
                        buffer_manager.on_cancel(id_vehicle, area.name, vehicle.booking[1], vehicle.booking[2])
                        vehicle.booking = None
                    else:
                        area.reservations -= 1

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

                    get_park_area(new_park_area, areas).reservations += 1

            # If the vehicle is stopped
            if is_stopped_parking:
                stops = list(traci.vehicle.getStops(id_vehicle, 0))

                # In case if the park is "ParkAreaOutOfTown", we don't track the ending time of the reservation
                if not is_out_of_town(vehicle.last_park):
                    current_stop = stops[0]

                    # Simulation step in which the vehicle leaves the spot, used in the first part of the run loop, where we iterate through vehicles about to end a park. The spot gets stored even if the vehicle doesn't actually leave the spot (only happens if SUMO prevents the vehicle from leaving)
                    if vehicle.slot_release_step is None and vehicle.paid and current_stop.duration <= 0:
                        vehicle.slot_release_step = simulation_time

                    # Check only vehicles who are overstaying their current stop
                    if vehicle.overstay > 0:
                        # If the current duration is negative that means someone is blocking the park
                        if current_stop.duration > 0:
                            if vehicle.paid and vehicle.park_duration is not None:
                                # If the current simulation step coincides with the ending of the vehicle's reservation, and said vehicle has not yet left the park area, the vehicle overstayed, and the buffer manager is notified, though only the "incremental" strategy takes action
                                if simulation_time >= int(vehicle.park_duration):
                                    if vehicle.has_reservation:
                                        buffer_manager.on_overstay_start(
                                            id_vehicle,
                                            vehicle.last_park,
                                            step_to_calendar_slot(simulation_time),
                                        )

                                        # Remove the reservation from the area (in order to not give other penalties to the vehicle) and increase the bad behaviour counter of the area
                                        vehicle.has_reservation = False
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
                    # New stop, the previous value needs to be reset
                    vehicle.slot_release_step = None
                    cont_stops = len(stops)
                    # print("Stops:", traci.vehicle.getStops(id_vehicle, 0))

                    # Vehicle doesn't pay if it doesn't park in "Town"
                    if not is_out_of_town(park_area):
                        # Calculate the supposed park ending
                        # print("When it must end the park at:", leaving_time)
                        vehicle.park_duration = vehicle.booking[2] * STEPS_PER_CALENDAR_SLOT
                        # print("Vehicle's ending time park:", leaving_time)

                        area = get_park_area(vehicle.booking[0], areas)
                        effective_arrival_slot = step_to_calendar_slot(simulation_time)

                        # Check if the vehicle arrived outside of its reservation window and increments the counters accordingly
                        if effective_arrival_slot < vehicle.booking[1]:
                            arrived_before_booking_start_cont += 1
                            if area.can_book(effective_arrival_slot, vehicle.booking[1], buffer_of_slot(buffer_manager, area.name)):
                                area.book(vehicle.id, effective_arrival_slot, vehicle.booking[1])
                                vehicle.booking = (area.name, effective_arrival_slot, vehicle.booking[2])
                                buffer_manager.on_reservation(id_vehicle, area.name, effective_arrival_slot, vehicle.booking[2])
                            else:
                                out_of_calendar_arrival_cont += 1
                        elif effective_arrival_slot >= vehicle.booking[2]:
                            arrived_after_booking_end_cont += 1

                        # Wallet overwritten with the new balance. Raises an wxception if, for some reason, the vehicle did not have its wallet checked
                        if vehicle.new_wallet is not None:
                            set_wallet(id_vehicle, vehicle.new_wallet)
                            vehicle.new_wallet = None
                        else:
                            raise ValueError(f"'{vehicle.id}' is parking in town without having its wallet checked")
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
    reservation ={name: area.reservations for name, area in sorted(areas.items()) if area.is_out_of_town}

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
            f"Bookings rejected, area already booked out (events):"
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
            f"  of which only because of the buffer (would pass with no buffer):"
            f" {sum(buffer_rejections.values())}",
            file=f,
        )
        print(
            f"    by unreserved spots left (spots: rejections):"
            f" {dict(sorted(buffer_rejections.items()))}",
            file=f,
        )
        print(
            f"Arrivals at a physically full area (events): {cont_no_park}",
            file=f,
        )
        print(
            f"Vehicles that hit a physically full area at least once:"
            f" {vehicles_change_route_count}",
            file=f,
        )
        print(
            f"Arrivals before the booking started (events):"
            f" {arrived_before_booking_start_cont}",
            file=f,
        )
        print(
            f"  of which outside the calendar (no room to extend backwards):"
            f" {out_of_calendar_arrival_cont}",
            file=f,
        )
        print(
            f"Arrivals after the booking had ended (events):"
            f" {arrived_after_booking_end_cont}",
            file=f,
        )
        print(f"End park(good behaviour): {cont_end_park}", file=f)
        print(f"End park(bad behaviour): {cont_bad_behaviour_vehicles}", file=f)
        print(
            f"Total end park: {cont_end_park + cont_bad_behaviour_vehicles}", file=f
        )
        print(f"Finish time step: {simulation_time}", file=f)
        print(f"Reservation: {reservation}", file=f)
        future_slots = sum(
            1 for area in areas.values() for time_slot in area.calendar if time_slot >= step_to_calendar_slot(simulation_time)
        )
        print(f"Future reserved slots: {future_slots}", file=f)
        print(f"Buffer state: {buffer_manager.free_parks(step_to_calendar_slot(simulation_time))}", file=f)
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
    traci.start([sumoBinary, "--seed", str(stream_seed(RUN_SEED, "sumo")), "-c", sumo_cfg])
    run()
