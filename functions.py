from optparse import OptionParser
import math
from bufferManagement import BufferStrategy
from parkArea import get_park_area
import traci
from constants import (
    TOTAL_POPULATION,
    STEPS_PER_HOUR,
    PARK_AREA_NAMES,
    CONSTANT_BUFFER_SPOTS,
    INITIAL_BUFFER_SPOTS,
    STANDARD_AUCTION_PRICE,
    DOUBLE_ROWS,
    MAX_REVIEW_STARS,
)

SLOT_DURATION = STEPS_PER_HOUR

def get_options(option_list: list):
    """Function to parse command line options"""
    opt_parser = OptionParser()
    for i in option_list:
        opt_parser.add_option(i, action="store_true", default=False)

    options, args = opt_parser.parse_args()
    return options



def check_wallet(duration: int, id_vehicle: str) -> int:
    """Function to check if the vehicle's user has enough money to pay."""

    review_stars = int(traci.vehicle.getParameter(id_vehicle, "reviewStars"))
    cost = int(duration / SLOT_DURATION * STANDARD_AUCTION_PRICE)
    extra_cost = int(cost * 25 / 100) if review_stars < 3 else 0
    current_credit = int(traci.vehicle.getParameter(id_vehicle, "wallet"))
    # print(f"[{id_vehicle}] Credit: {current_credit}")
    new_wallet = current_credit - int(cost + extra_cost)

    if new_wallet < 0:
        print(f"[{id_vehicle}] Insufficient credit!")
        return 0

    return new_wallet


def system_charge(id_vehicle: str):
    """Function to change the vehicle's reputation based on behaviour."""

    review_stars = int(traci.vehicle.getParameter(id_vehicle, "reviewStars"))
    delay = int(traci.vehicle.getParameter(id_vehicle, "delay"))
    if delay > 0:
        traci.vehicle.setParameter(id_vehicle, "goodBehaviour", "False")
        if review_stars == 0:
            return
        warning = int(traci.vehicle.getParameter(id_vehicle, "warning"))
        warning += 1
        if warning == 5:
            review_stars -= 1
            traci.vehicle.setParameter(id_vehicle, "reviewStars", review_stars)
            traci.vehicle.setParameter(id_vehicle, "warning", 0)
        else:
            traci.vehicle.setParameter(id_vehicle, "warning", warning)
            traci.vehicle.setParameter(id_vehicle, "civil", 0)
    else:
        traci.vehicle.setParameter(id_vehicle, "goodBehaviour", "True")
        if review_stars == MAX_REVIEW_STARS:
            return
        civil = int(traci.vehicle.getParameter(id_vehicle, "civil"))
        civil += 1
        if civil == 5:
            review_stars += 1
            traci.vehicle.setParameter(id_vehicle, "reviewStars", review_stars)
            traci.vehicle.setParameter(id_vehicle, "civil", 0)
        else:
            traci.vehicle.setParameter(id_vehicle, "civil", civil)


def go_to_no_system_park(
    id_vehicle: str,
    duration: int,
    stop_pos: int,
    areas: dict
) -> str:
    """Function that changes the vehicle's route to 'ParkAreaOutOfTown'."""

    row_count = math.ceil(TOTAL_POPULATION / 20)
    if row_count < 4:
        row_count = 4

    # Opposite Direction (the vehicles come from right side)
    for row in range(row_count - 1, -1, -1):
        area1 = get_park_area(f"{PARK_AREA_NAMES[2]}{row}", areas)
        park1 = area1.name
        if (
            traci.parkingarea.getVehicleCount(park1) < area1.capacity
            and area1.reservations < area1.capacity
        ):
            print(f"[{id_vehicle}] Changing park to {park1}...")
            traci.vehicle.replaceStop(
                id_vehicle, stop_pos, park1, flags=65, duration=duration, startPos=0.0
            )
            return park1

        area2 = get_park_area(f"-{PARK_AREA_NAMES[2]}{row}", areas)
        park2 = area2.name
        if (
            traci.parkingarea.getVehicleCount(park2) < area2.capacity
            and area2.reservations < area2.capacity
        ):
            print(f"[{id_vehicle}] Changing park to {park2}...")
            traci.vehicle.replaceStop(
                id_vehicle, stop_pos, park2, flags=65, duration=duration, startPos=0.0
            )
            return park2

    raise Exception(
        "Error: vehicle can not park in ParkAreaOutOfTown (no more spots available)"
    )


def change_reservation(
    id_vehicle: str,
    park_area: str,
    duration: int,
    stop_pos: int,
    areas: dict,
    buffer_manager: BufferStrategy
) -> str:
    """Function that tries to get a new reservation for the user."""

    cont_stops = len(list(traci.vehicle.getStops(id_vehicle, 0)))
    if cont_stops < 1:
        return "End"

    # Start searching from the same area type, then try the alternative
    park_area_suffix = PARK_AREA_NAMES[0]
    park_area_suffix2 = PARK_AREA_NAMES[1]
    if PARK_AREA_NAMES[1] in park_area:
        park_area_suffix = PARK_AREA_NAMES[1]
        park_area_suffix2 = PARK_AREA_NAMES[0]

    # Search both suffixes in order
    for suffix in [park_area_suffix, park_area_suffix2]:
        for row in range(DOUBLE_ROWS):
            area1 = get_park_area(f"{suffix}{row}", areas)
            cont_free_parks = buffer_manager.get_buffer(area1.name, INITIAL_BUFFER_SPOTS)
            if CONSTANT_BUFFER_SPOTS != -1:
                cont_free_parks = CONSTANT_BUFFER_SPOTS
            if area1.has_free_slot(cont_free_parks):
                traci.vehicle.replaceStop(
                    id_vehicle, stop_pos, area1.name, flags=65, duration=duration, startPos=0.0
                )
                return area1.name

            area2 = get_park_area(f"-{suffix}{row}", areas)
            cont_free_parks = buffer_manager.get_buffer(area2.name, INITIAL_BUFFER_SPOTS)
            if CONSTANT_BUFFER_SPOTS != -1:
                cont_free_parks = CONSTANT_BUFFER_SPOTS
            if area2.has_free_slot(cont_free_parks):
                traci.vehicle.replaceStop(
                    id_vehicle, stop_pos, area2.name, flags=65, duration=duration, startPos=0.0
                )
                return area2.name

    return "End"