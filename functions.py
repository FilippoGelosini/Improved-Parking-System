from optparse import OptionParser
import math
from bufferManagement import BufferStrategy
from parkArea import get_park_area
import traci
import random
from vehicle import (
    get_review_stars,
    set_review_stars,
    get_warning,
    set_warning,
    get_civil,
    set_civil,
    get_wallet,
    set_good_behaviour,
    get_overstay_probability,
    set_overstay_probability,
    get_learning_probability
)
from constants import (
    TOTAL_POPULATION,
    STEPS_PER_HOUR,
    PARK_AREA_NAMES,
    CONSTANT_BUFFER_SPOTS,
    INITIAL_BUFFER_SPOTS,
    STANDARD_AUCTION_PRICE,
    DOUBLE_ROWS,
    MAX_REVIEW_STARS,
    GOOD_OVERSTAY_PROBABILITY,
    BAD_OVERSTAY_PROBABILITY,
    RATING_DETERRENCE,
    MIN_OVERSTAY_STEPS,
    MAX_OVERSTAY_STEPS,
    WARNING_LEARNING_RATE,
    STAR_LOSS_LEARNING_RATE,
    BAD_VEHICLE_TYPE
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

    review_stars = get_review_stars(id_vehicle)
    cost = int(duration / SLOT_DURATION * STANDARD_AUCTION_PRICE)
    extra_cost = int(cost * 25 / 100) if review_stars < 3 else 0
    current_credit = get_wallet(id_vehicle)
    # print(f"[{id_vehicle}] Credit: {current_credit}")
    new_wallet = current_credit - int(cost + extra_cost)

    if new_wallet < 0:
        print(f"[{id_vehicle}] Insufficient credit!")
        return 0

    return new_wallet


def system_charge(id_vehicle: str, overstayed: bool, rng: random.Random):
    """Function to change the vehicle's reputation based on behaviour. Called when a vehicle exits an area"""

    review_stars = get_review_stars(id_vehicle)

    if overstayed:
        set_good_behaviour(id_vehicle, False)
        warning = get_warning(id_vehicle) + 1 # Pre-empively increment the warning count
        star_loss = review_stars > 0 and warning == 5 # Used to determined if a vehicle is about to lose a star

        # For the sake of the simulation, the update of the overstay probability is made BEFORE the vehicle gets a warning. This way, even vehicles with 0 stars might improve their behaviour
        if traci.vehicle.getTypeID(id_vehicle) == BAD_VEHICLE_TYPE:
            current_probability = get_overstay_probability(id_vehicle)
            awareness = get_learning_probability(id_vehicle)

            learning_rate = STAR_LOSS_LEARNING_RATE if star_loss else WARNING_LEARNING_RATE
            set_overstay_probability(id_vehicle, update_overstay_probability(
                current_probability, 
                awareness, 
                rng, 
                learning_rate
            ))
        set_civil(id_vehicle, 0)
        if review_stars == 0:
            return
        if star_loss:
            set_review_stars(id_vehicle, review_stars - 1)
            set_warning(id_vehicle, 0)
        else:
            set_warning(id_vehicle, warning)
    else:
        set_good_behaviour(id_vehicle, True)
        if review_stars == MAX_REVIEW_STARS:
            return
        civil = get_civil(id_vehicle) + 1
        if civil == 5:
            set_review_stars(id_vehicle, review_stars + 1)
            set_civil(id_vehicle, 0)
        else:
            set_civil(id_vehicle, civil)


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

def overstay_probability(
    base_probability: float,
    review_stars: int,
    deterrence: float = RATING_DETERRENCE,
) -> float:
    """Determines the probability of overstaying for the given user for his next reservation"""
    return base_probability * (1.0 - deterrence * review_stars / MAX_REVIEW_STARS)


def overstay_for(
    base_probability: float,
    review_stars: int,
    rng: random.Random,
    min_steps: int = MIN_OVERSTAY_STEPS,
    max_steps: int = MAX_OVERSTAY_STEPS,
) -> int:
    """Determines how long the overstay is going to be (if performed) for the given user."""
    if rng.random() >= overstay_probability(base_probability, review_stars):
        return 0

    return rng.randint(min_steps, max_steps)

def update_overstay_probability (
    current_probability: float,
    awareness: float,
    rng: random.Random,
    learning_rate: float,
    floor: float = GOOD_OVERSTAY_PROBABILITY
) -> float:
    """Updates the vehicle behaviour on probability \"awareness\""""
    if rng.random() >= awareness:
        return current_probability
    # Overstay probability should not be lower than a fixed floor (GOOD_OVERSTAY_PROBABILITY by default, see "constants.py")
    return max(floor, current_probability * (1 - learning_rate))